"""
Enhanced Evaluation Service using Final Dataset

This service provides production-grade answer evaluation using:
- Final dataset (questions with ideal/good/average/poor answers)
- GROQ LLM for detailed structured evaluation
- Similarity matching for question finding
- Comprehensive feedback with weak area detection
- Strict score consistency checking

Uses dataset format:
{
  "question": "...",
  "category": "system_design",
  "difficulty": "hard",
  "answers": {
    "ideal": {"text": "...", "scores": {...}, "feedback": "...", "weak_areas": []},
    "good": {...},
    "average": {...},
    "poor": {...},
    "improved": {...}
  }
}
"""

import json
import logging
import os
import re
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from difflib import SequenceMatcher
from .llm_groq_config import chat_completion, LLMUnavailableError

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    _EMBEDDINGS_AVAILABLE = True
except ImportError:
    _EMBEDDINGS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Global dataset cache
_DATASET_CACHE: Optional[List[Dict[str, Any]]] = None
_DATASET_LOADED = False

# Embeddings state
_EMBEDDING_MODEL = None
_QUESTION_EMBEDDINGS = None

# ---------------------------------------------------------------------------
# Strict enum for weak areas — ONLY these values are allowed in evaluations.
# Keeps Counter aggregation in SessionSummaryBuilder deterministic.
# ---------------------------------------------------------------------------
VALID_WEAK_AREAS = frozenset({
    "technical_accuracy",
    "clarity",
    "communication",
    "completeness",
})

# Scoring dimensions — MUST match prompt and normalization logic
SCORING_DIMENSIONS = ["technical_accuracy", "clarity", "communication", "completeness"]

# Shared rubric block injected into every evaluation prompt
_SCORING_RUBRIC = """
SCORING RUBRIC (apply STRICTLY — do NOT deviate):
  9–10 : Complete, precise, includes concrete examples, zero errors
  7–8  : Mostly correct, minor gaps only, clear explanation
  5–6  : Partial understanding, lacks depth or specific examples
  3–4  : Weak answer, multiple inaccuracies or significant gaps
  1–2  : Incorrect, irrelevant, or essentially empty

Rules:
  - Scores MUST be integers between 1 and 10 (inclusive)
  - Use ONLY the four dimensions listed: technical_accuracy, clarity, communication, completeness
  - Do NOT invent new categories or dimensions
  - completeness measures whether ALL aspects of the question are addressed
"""

# ---------------------------------------------------------------------------
# Task 5: Evaluation quality counters (in-process, resets on server restart)
# Logged every 20 evaluations; use /api/evaluate-answer/status to read live.
# ---------------------------------------------------------------------------
EVAL_STATS: Dict[str, int] = {
    "total": 0,
    "fallback": 0,
    "dataset_match": 0,
    "strong_match": 0,
    "llm_unavailable": 0,  # incremented whenever LLMUnavailableError is caught
}

# Similarity thresholds — configurable via environment variables.
# Defaults match the original hardcoded values so existing behaviour is unchanged.
EVAL_WEAK_THRESHOLD = float(os.getenv("EVAL_WEAK_MATCH_THRESHOLD", "0.60"))
EVAL_STRONG_THRESHOLD = float(os.getenv("EVAL_STRONG_MATCH_THRESHOLD", "0.75"))
# Keep legacy names as aliases so nothing inside the class needs touching yet
_MATCH_THRESHOLD = EVAL_WEAK_THRESHOLD
_STRONG_THRESHOLD = EVAL_STRONG_THRESHOLD

# Difficulty adjustment applied AFTER LLM scoring
_DIFFICULTY_ADJUSTMENTS: Dict[str, float] = {
    "easy": -0.5,   # easy questions should require higher bar
    "medium": 0.0,
    "hard": +0.5,   # hard questions earn a slight bonus
}


# ---------------------------------------------------------------------------
# Module-level helpers (no class dependency — can be tested independently)
# ---------------------------------------------------------------------------

def apply_difficulty_adjustment(avg_score: float, difficulty: str) -> float:
    """
    Task 1: Adjust score based on question difficulty.

    Hard questions earn a +0.5 bonus; easy questions carry a -0.5 penalty
    to keep scores comparable across difficulty levels.

    Result is clamped to [1.0, 10.0].
    """
    adjustment = _DIFFICULTY_ADJUSTMENTS.get(difficulty.lower(), 0.0)
    adjusted = avg_score + adjustment
    return round(max(1.0, min(10.0, adjusted)), 1)


def compute_score_confidence(metadata: Dict[str, Any], answer_len: int = 0) -> str:
    """
    Task 3: Return a human-readable confidence label for the score.
    HIGH: strong dataset match (>0.75) AND answer length sufficient
    MEDIUM: generic LLM evaluation OR fallback used but good structure
    LOW: short answer OR weak match
    """
    if metadata.get("fallback"):
        if answer_len > 150:
            return "medium"
        return "low"
    if metadata.get("strong_match") and answer_len > 50:
        return "high"
    if metadata.get("dataset_match"):
        return "medium"
    if answer_len < 50:
        return "low"
    return "medium"


def _update_eval_stats(evaluation: Dict[str, Any]) -> None:
    """
    Task 5: Update module-level quality counters after every evaluation.
    Logs a summary every 20 evaluations.
    """
    global EVAL_STATS
    EVAL_STATS["total"] += 1

    meta = evaluation.get("metadata", {})
    if meta.get("fallback"):
        EVAL_STATS["fallback"] += 1
    if meta.get("dataset_match"):
        EVAL_STATS["dataset_match"] += 1
    if meta.get("strong_match"):
        EVAL_STATS["strong_match"] += 1

    if EVAL_STATS["total"] % 20 == 0:
        total = EVAL_STATS["total"]
        fallback_pct = round(EVAL_STATS["fallback"] / total * 100, 1) if total else 0
        match_pct = round(EVAL_STATS["dataset_match"] / total * 100, 1) if total else 0
        strong_pct = round(EVAL_STATS["strong_match"] / total * 100, 1) if total else 0
        logger.info(
            f"[EVAL STATS] total={total} | "
            f"fallback={EVAL_STATS['fallback']} ({fallback_pct}%) | "
            f"dataset_match={EVAL_STATS['dataset_match']} ({match_pct}%) | "
            f"strong_match={EVAL_STATS['strong_match']} ({strong_pct}%)"
        )


class EnhancedEvaluationService:
    """Production-grade answer evaluation with dataset support."""
    
    # Singleton instance for caching
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the evaluation service."""
        if not self._initialized:
            self.dataset = None
            self._initialized = True
            self._load_dataset()
    
    def _load_dataset(self) -> bool:
        """Load final_dataset.json into memory (cached)."""
        global _DATASET_CACHE, _DATASET_LOADED
        
        if _DATASET_LOADED:
            self.dataset = _DATASET_CACHE
            logger.info(f"✅ Dataset loaded from cache ({len(self.dataset) if self.dataset else 0} entries)")
            return True
        
        try:
            # Find final_dataset.json
            dataset_paths = [
                Path(__file__).parent.parent.parent.parent / "final_dataset.json",  # D:\InterviewAI\final_dataset.json
                Path(__file__).parent.parent / "final_dataset.json",  # D:\InterviewAI\backend\src\final_dataset.json
            ]
            
            dataset_path = None
            for path in dataset_paths:
                if path.exists():
                    dataset_path = path
                    break
            
            if not dataset_path or not dataset_path.exists():
                logger.warning(f"❌ Dataset not found at expected locations: {dataset_paths}")
                self.dataset = None
                _DATASET_LOADED = True
                return False
            
            with open(dataset_path, 'r', encoding='utf-8') as f:
                self.dataset = json.load(f)
            
            _DATASET_CACHE = self.dataset
            _DATASET_LOADED = True
            
            logger.info(f"✅ Enhanced Evaluation Service loaded {len(self.dataset)} dataset entries from {dataset_path}")
            
            # Precompute embeddings if available
            global _EMBEDDING_MODEL, _QUESTION_EMBEDDINGS, _EMBEDDINGS_AVAILABLE
            if _EMBEDDINGS_AVAILABLE:
                try:
                    if _EMBEDDING_MODEL is None:
                        logger.info("⏳ Loading sentence-transformers model (all-MiniLM-L6-v2)...")
                        _EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
                        
                    logger.info("⏳ Computing dataset embeddings...")
                    questions = [entry.get('question', '') for entry in self.dataset]
                    _QUESTION_EMBEDDINGS = _EMBEDDING_MODEL.encode(questions)
                    logger.info("✅ Dataset embeddings computed and cached.")
                except Exception as e:
                    logger.error(f"❌ Failed to load embedding model or compute embeddings: {e}")
                    _EMBEDDINGS_AVAILABLE = False
                    
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load dataset: {e}")
            self.dataset = None
            _DATASET_LOADED = True
            return False
    
    def find_matching_question(
        self,
        question: str,
        target_role: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], float]:
        """
        Find the best matching question in the dataset using semantic matching.
        Falls back to SequenceMatcher if semantic matching fails.
        """
        if not self.dataset:
            return None, 0.0

        best_match = None
        best_score = 0.0
        
        global _EMBEDDINGS_AVAILABLE, _EMBEDDING_MODEL, _QUESTION_EMBEDDINGS
        
        # Step 1: Semantic Matching (Primary)
        if _EMBEDDINGS_AVAILABLE and _EMBEDDING_MODEL is not None and _QUESTION_EMBEDDINGS is not None:
            try:
                query_embedding = _EMBEDDING_MODEL.encode([question])
                similarities = cosine_similarity(query_embedding, _QUESTION_EMBEDDINGS)[0]
                
                for idx, similarity in enumerate(similarities):
                    entry = self.dataset[idx]
                    if target_role and entry.get('target_role') and entry.get('target_role') != target_role:
                        continue
                    
                    if similarity > best_score:
                        best_score = float(similarity)
                        best_match = entry
                        
                if best_score > _MATCH_THRESHOLD:
                    logger.info(f"📊 Semantic match found: similarity={best_score:.2f} ({'strong' if best_score > _STRONG_THRESHOLD else 'weak'})")
                    return best_match, best_score
            except Exception as e:
                logger.error(f"❌ Semantic matching failed: {e}. Falling back to string matching.")

        # Step 2: Fallback String Matching
        best_score = 0.0
        best_match = None
        for entry in self.dataset:
            if target_role and entry.get('target_role') and entry.get('target_role') != target_role:
                continue
            similarity = self._similarity_score(question.lower(), entry.get('question', '').lower())
            if similarity > best_score:
                best_score = similarity
                best_match = entry

        # String matching thresholds are usually lower than semantic
        if best_score > 0.55:
            logger.info(f"📊 String match found: similarity={best_score:.2f} ({'strong' if best_score > 0.70 else 'weak'})")
            return best_match, best_score

        logger.info(f"❌ No match above threshold (best: {best_score:.2f})")
        return None, best_score
    
    def _similarity_score(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        return SequenceMatcher(None, text1, text2).ratio()

    def _compute_rule_based_scores(self, question: str, answer: str, matched_entry: Optional[Dict[str, Any]] = None) -> float:
        """Compute deterministic rule-based scoring signals."""
        answer_len = len(answer.strip())
        
        # Length score: > 300 chars = 10, < 50 = 2, scale linearly
        length_score = max(2.0, min(10.0, (answer_len / 300.0) * 10.0))
        
        # Keyword match score
        words = set(re.findall(r'\w+', answer.lower()))
        if matched_entry and matched_entry.get("key_points_expected"):
            key_points = matched_entry.get("key_points_expected", [])
            key_words = set(re.findall(r'\w+', " ".join(key_points).lower()))
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were'}
            key_words = key_words - stop_words
            overlap = words.intersection(key_words)
            match_ratio = len(overlap) / max(1, len(key_words))
            keyword_score = max(2.0, min(10.0, match_ratio * 15.0))
        else:
            q_words = set(re.findall(r'\w+', question.lower())) - {'what', 'how', 'why', 'describe', 'explain', 'tell', 'me', 'about', 'the', 'a', 'an'}
            overlap = words.intersection(q_words)
            keyword_score = min(10.0, 5.0 + len(overlap) * 0.5)

        # Repetition penalty
        total_words = len(re.findall(r'\w+', answer.lower()))
        unique_words = len(words)
        repetition_penalty = 0.0
        if total_words > 20 and unique_words / max(1, total_words) < 0.4:
            repetition_penalty = 2.0

        rule_score = (length_score * 0.6) + (keyword_score * 0.4) - repetition_penalty
        return max(1.0, min(10.0, rule_score))
    
    async def evaluate_answer_with_dataset(
        self,
        question: str,
        candidate_answer: str,
        target_role: str = "Backend Engineer",
        experience_level: str = "Mid",
        interview_type: str = "Mixed",
        question_difficulty: str = "medium",
    ) -> Dict[str, Any]:
        """
        Evaluate answer using dataset context + LLM.

        Args:
            question: The interview question
            candidate_answer: Candidate's response
            target_role: Target position
            experience_level: Experience level (Entry/Mid/Senior)
            interview_type: Interview type (Technical/Behavioral/Mixed)
            question_difficulty: Difficulty hint from caller ('easy'|'medium'|'hard')

        Returns:
            Structured evaluation following the standard schema.
        """
        global EVAL_STATS
        logger.info("🔍 Starting enhanced answer evaluation...")

        # --- Input validation ---
        if not candidate_answer or len(candidate_answer.strip()) < 10:
            evaluation = self._generate_fallback_evaluation(
                reason="too_short",
                answer=candidate_answer or "",
                feedback_msg="Your answer is too brief. Please provide more details and examples.",
                fallback_type="too_short",
            )
            _update_eval_stats(evaluation)
            # Ensure the final response contains the exact requested fields of Task 2
            evaluation["score"] = evaluation["average_score"]
            evaluation["dataset_match_type"] = "no_match"
            evaluation.setdefault("llm_used", False)
            evaluation.setdefault("reasoning", evaluation.get("feedback", ""))
            evaluation.setdefault("strengths", ["Attempted to answer the question"])
            evaluation.setdefault("gaps", ["Could provide more detail and examples"])
            
            asyncio.create_task(log_eval_stats_to_db(EVAL_STATS.copy()))
            return evaluation

        try:
            # --- Dataset matching ---
            matched_entry, similarity_score = self.find_matching_question(question, target_role)
            dataset_match = matched_entry is not None
            strong_match = similarity_score > _STRONG_THRESHOLD

            # Build base context
            context = {
                "question": question,
                "candidate_answer": candidate_answer,
                "target_role": target_role,
                "experience_level": experience_level,
                "interview_type": interview_type,
                "question_difficulty": question_difficulty,
                "matched_entry": matched_entry,
                "dataset_match": dataset_match,
                "strong_match": strong_match,
                "similarity_score": similarity_score,
            }

            # --- Rule-Based Scoring Signal ---
            rule_score = self._compute_rule_based_scores(question, candidate_answer, matched_entry)

            # --- Routing: only pass dataset to LLM when it's a strong match ---
            if strong_match:
                logger.info("✅ Strong dataset match — using dataset-based evaluation")
                evaluation = await self._evaluate_with_comparison(context)
                
                # --- Score Fusion Engine ---
                dataset_llm_score = evaluation.get("average_score", 5.0)
                # To avoid expensive double LLM calls, we use dataset_llm_score as the primary fallback representation
                final_score = (0.5 * dataset_llm_score) + (0.3 * dataset_llm_score) + (0.2 * rule_score)
                evaluation["average_score"] = round(max(1.0, min(10.0, final_score)), 1)
                
            elif dataset_match:
                logger.info("⚠️ Weak dataset match — using generic evaluation (avoiding noise)")
                evaluation = await self._evaluate_generic(context)
                
                # --- Score Fusion Engine ---
                fallback_llm_score = evaluation.get("average_score", 5.0)
                final_score = (0.7 * fallback_llm_score) + (0.3 * rule_score)
                evaluation["average_score"] = round(max(1.0, min(10.0, final_score)), 1)
                
            else:
                logger.info("⚠️ No dataset match — using generic evaluation")
                evaluation = await self._evaluate_generic(context)
                
                # --- Score Fusion Engine ---
                fallback_llm_score = evaluation.get("average_score", 5.0)
                final_score = (0.7 * fallback_llm_score) + (0.3 * rule_score)
                evaluation["average_score"] = round(max(1.0, min(10.0, final_score)), 1)

            # --- Post-processing: difficulty adjustment ---
            difficulty = (
                matched_entry.get("difficulty", question_difficulty)
                if matched_entry
                else question_difficulty
            )
            evaluation["average_score"] = apply_difficulty_adjustment(
                evaluation["average_score"], difficulty
            )
            evaluation["difficulty"] = difficulty

            # --- Score confidence indicator ---
            evaluation["score_confidence"] = compute_score_confidence(
                evaluation.get("metadata", {}),
                len(candidate_answer.strip())
            )

            # --- Inject strong_match into metadata ---
            evaluation.setdefault("metadata", {})
            evaluation["metadata"]["strong_match"] = strong_match
            evaluation["metadata"]["similarity_score"] = round(similarity_score, 3)

            # Ensure the final response contains the exact requested fields of Task 2
            evaluation["score"] = evaluation["average_score"]
            evaluation["dataset_match_type"] = (
                "strong_match" if strong_match
                else "weak_match" if dataset_match
                else "no_match"
            )
            evaluation.setdefault("llm_used", not bool(evaluation.get("metadata", {}).get("fallback")))
            evaluation.setdefault("reasoning", evaluation.get("feedback", ""))
            evaluation.setdefault("strengths", [])
            evaluation.setdefault("gaps", evaluation.get("weaknesses", []))

            # --- Update global quality counters ---
            _update_eval_stats(evaluation)

            # Fire-and-forget insert to eval_stats_log
            asyncio.create_task(log_eval_stats_to_db(EVAL_STATS.copy()))
            
            return evaluation

        except Exception as e:
            logger.error(f"❌ Evaluation error: {e}", exc_info=True)
            evaluation = self._generate_fallback_evaluation(
                reason="unexpected_error",
                answer=candidate_answer,
                feedback_msg="An unexpected error occurred during evaluation.",
                fallback_type="llm_failure",
            )
            # Ensure the final response contains the exact requested fields of Task 2
            evaluation["score"] = evaluation["average_score"]
            evaluation["dataset_match_type"] = "no_match"
            evaluation.setdefault("llm_used", False)
            evaluation.setdefault("reasoning", evaluation.get("feedback", ""))
            evaluation.setdefault("strengths", ["Attempted to answer the question"])
            evaluation.setdefault("gaps", ["Could provide more detail and examples"])

            _update_eval_stats(evaluation)

            asyncio.create_task(log_eval_stats_to_db(EVAL_STATS.copy()))
            
            return evaluation
    
    async def _evaluate_with_comparison(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate using dataset comparison (ideal/good/average/poor answers)."""
        
        question = context["question"]
        candidate_answer = context["candidate_answer"]
        target_role = context["target_role"]
        experience_level = context["experience_level"]
        matched_entry = context["matched_entry"]
        
        # Extract comparison answers from dataset
        reference_answers = matched_entry.get("answers", {})
        key_points = matched_entry.get("key_points_expected", [])
        category = matched_entry.get("category", "general")
        difficulty = matched_entry.get("difficulty", "medium")
        
        # Build detailed evaluation prompt
        key_points_str = json.dumps(key_points[:5], indent=2)
        # Truncate reference answers — use 500 chars for better LLM anchoring
        ideal_text   = reference_answers.get("ideal",   {}).get("text", "")[:500]
        good_text    = reference_answers.get("good",    {}).get("text", "")[:500]
        average_text = reference_answers.get("average", {}).get("text", "")[:500]
        poor_text    = reference_answers.get("poor",    {}).get("text", "")[:500]

        prompt = f"""You are a strict technical interviewer.

Evaluate the candidate's answer using these criteria:
1. Technical Accuracy (0-10)
2. Completeness (0-10)
3. Clarity (0-10)
4. Communication (0-10)

Rules:
* Penalize vague answers
* Penalize missing examples
* Penalize incorrect or shallow explanations
* Reward structured, concise, and technically correct answers

QUESTION:
"{question}"

CANDIDATE'S ANSWER:
"{candidate_answer}"

CONTEXT:
- Role: {target_role}
- Experience Level: {experience_level}
- Category: {category}
- Difficulty: {difficulty}

KEY POINTS EXPECTED:
{key_points_str}

REFERENCE ANSWERS (use these to calibrate your scores and compare explicitly):
- Ideal Answer   (score ~9–10): {ideal_text}
- Good Answer    (score ~7–8) : {good_text}
- Average Answer (score ~5–6) : {average_text}
- Poor Answer    (score ~1–2) : {poor_text}

You must respond ONLY with a valid JSON object. No explanation outside the JSON.
Required keys:
{{
  "score": <float 1.0 to 10.0>,
  "reasoning": "<1-2 sentences explaining the score>",
  "strengths": ["<up to 2 specific strengths observed>"],
  "gaps": ["<up to 2 specific gaps or missing points>"]
}}"""
        
        logger.info("📞 Calling GROQ LLM for dataset-based evaluation...")

        try:
            response = await chat_completion(
                prompt=prompt,
                max_tokens=1500,
                temperature=0.1,
                json_mode=True,
            )
        except LLMUnavailableError as llm_err:
            logger.error(f"❌ LLM unavailable (dataset-based path): {llm_err}")
            EVAL_STATS["llm_unavailable"] += 1
            fallback = self._generate_fallback_evaluation(
                reason="llm_unavailable",
                answer=candidate_answer,
                feedback_msg="Evaluation temporarily unavailable. Score based on answer quality.",
                fallback_type="llm_failure",
            )
            fallback["llm_used"] = False
            fallback["fallback_reason"] = "llm_unavailable"
            return fallback

        if not response:
            logger.error("❌ No response from LLM (dataset-based path)")
            return self._generate_fallback_evaluation(
                reason="llm_no_response",
                answer=candidate_answer,
                feedback_msg="Evaluation temporarily unavailable. Please try again.",
                fallback_type="llm_failure",
            )
        
        # Parse and validate response
        llm_used = True
        try:
            parsed = json.loads(response)
        except Exception as parse_err:
            try:
                cleaned = self._clean_json_response(response)
                parsed = json.loads(cleaned)
            except Exception as e:
                logger.error(f"❌ json.loads failed. Raw response: {response}. Error: {e}")
                llm_used = False
                rule_score = self._compute_rule_based_scores(question, candidate_answer, matched_entry)
                parsed = {
                    "score": rule_score,
                    "reasoning": "Rule-based fallback due to LLM response parsing failure.",
                    "strengths": [],
                    "gaps": []
                }

        # Extract score and clamp between 1.0 and 10.0
        try:
            score = float(parsed.get("score", 5.0))
        except (ValueError, TypeError):
            score = 5.0
        score = max(1.0, min(10.0, score))
        parsed["score"] = score

        evaluation = {
            "score": score,
            "reasoning": parsed.get("reasoning", ""),
            "strengths": parsed.get("strengths", []),
            "gaps": parsed.get("gaps", []),
            "llm_used": llm_used,
            "dataset_match_type": "strong_match",
            "difficulty": difficulty,
            # Backward compatibility fields:
            "average_score": score,
            "feedback": parsed.get("reasoning", ""),
            "weak_areas": parsed.get("gaps", []),
            "improved_answer": "",
            "coaching_tips": [],
            "scores": {
                "technical_accuracy": int(score),
                "clarity": int(score),
                "communication": int(score),
                "completeness": int(score)
            },
            "evaluation_metadata": parsed
        }

        # Inject rich metadata (strong_match comes from caller via context)
        strong_match = context.get("strong_match", True)
        evaluation["metadata"] = {
            "fallback": not llm_used,
            "dataset_match": True,
            "strong_match": strong_match,
            "matched_question_category": category,
            "matched_question_difficulty": difficulty,
            "key_points_count": len(key_points),
            "comparison_enabled": True,
            "similarity_score": round(context.get("similarity_score", 0.0), 3),
        }

        logger.info(
            f"✅ Dataset-based evaluation complete — "
            f"avg_score={evaluation['average_score']}"
        )
        return evaluation
    
    async def _evaluate_generic(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic evaluation without dataset comparison."""

        question = context["question"]
        candidate_answer = context["candidate_answer"]
        target_role = context["target_role"]
        experience_level = context["experience_level"]

        prompt = f"""You are a strict technical interviewer.

Evaluate the candidate's answer using these criteria:
1. Technical Accuracy (0-10)
2. Completeness (0-10)
3. Clarity (0-10)
4. Communication (0-10)

Rules:
* Penalize vague answers
* Penalize missing examples
* Penalize incorrect or shallow explanations
* Reward structured, concise, and technically correct answers

QUESTION:
"{question}"

CANDIDATE'S ANSWER:
"{candidate_answer}"

CONTEXT:
- Role: {target_role}
- Experience Level: {experience_level}

You must respond ONLY with a valid JSON object. No explanation outside the JSON.
Required keys:
{{
  "score": <float 1.0 to 10.0>,
  "reasoning": "<1-2 sentences explaining the score>",
  "strengths": ["<up to 2 specific strengths observed>"],
  "gaps": ["<up to 2 specific gaps or missing points>"]
}}"""
        
        logger.info("📞 Calling GROQ LLM for generic evaluation...")

        try:
            response = await chat_completion(
                prompt=prompt,
                max_tokens=1200,
                temperature=0.1,
                json_mode=True,
            )
        except LLMUnavailableError as llm_err:
            logger.error(f"❌ LLM unavailable (generic path): {llm_err}")
            EVAL_STATS["llm_unavailable"] += 1
            fallback = self._generate_fallback_evaluation(
                reason="llm_unavailable",
                answer=candidate_answer,
                feedback_msg="Evaluation temporarily unavailable. Score based on answer quality.",
                fallback_type="llm_failure",
            )
            fallback["llm_used"] = False
            fallback["fallback_reason"] = "llm_unavailable"
            return fallback

        if not response:
            logger.error("❌ No response from LLM (generic path)")
            return self._generate_fallback_evaluation(
                reason="llm_no_response",
                answer=candidate_answer,
                feedback_msg="Evaluation temporarily unavailable. Please try again.",
                fallback_type="llm_failure",
            )

        # Determine match type based on whether context has dataset_match
        dataset_match = context.get("dataset_match", False)
        dataset_match_type = "weak_match" if dataset_match else "no_match"
        difficulty = context.get("question_difficulty", "medium")

        # Parse and validate response
        llm_used = True
        try:
            parsed = json.loads(response)
        except Exception as parse_err:
            try:
                cleaned = self._clean_json_response(response)
                parsed = json.loads(cleaned)
            except Exception as e:
                logger.error(f"❌ json.loads failed. Raw response: {response}. Error: {e}")
                llm_used = False
                rule_score = self._compute_rule_based_scores(question, candidate_answer, None)
                parsed = {
                    "score": rule_score,
                    "reasoning": "Rule-based fallback due to LLM response parsing failure.",
                    "strengths": [],
                    "gaps": []
                }

        # Extract score and clamp between 1.0 and 10.0
        try:
            score = float(parsed.get("score", 5.0))
        except (ValueError, TypeError):
            score = 5.0
        score = max(1.0, min(10.0, score))
        parsed["score"] = score

        evaluation = {
            "score": score,
            "reasoning": parsed.get("reasoning", ""),
            "strengths": parsed.get("strengths", []),
            "gaps": parsed.get("gaps", []),
            "llm_used": llm_used,
            "dataset_match_type": dataset_match_type,
            "difficulty": difficulty,
            # Backward compatibility fields:
            "average_score": score,
            "feedback": parsed.get("reasoning", ""),
            "weak_areas": parsed.get("gaps", []),
            "improved_answer": "",
            "coaching_tips": [],
            "scores": {
                "technical_accuracy": int(score),
                "clarity": int(score),
                "communication": int(score),
                "completeness": int(score)
            },
            "evaluation_metadata": parsed
        }

        # Inject metadata — generic path means no dataset context was used
        evaluation["metadata"] = {
            "fallback": not llm_used,
            "dataset_match": dataset_match,
            "strong_match": False,
            "comparison_enabled": False,
            "similarity_score": round(context.get("similarity_score", 0.0), 3),
        }

        logger.info(
            f"✅ Generic evaluation complete — "
            f"avg_score={evaluation['average_score']}"
        )
        return evaluation
    
    def _clean_json_response(self, response: str) -> str:
        """Extract and clean JSON from LLM response."""
        if not response:
            return "{}"
        
        # Remove markdown
        response = re.sub(r'```json\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'```\s*', '', response)
        
        # Find JSON boundaries
        first_brace = response.find('{')
        last_brace = response.rfind('}')
        
        if first_brace != -1 and last_brace != -1:
            response = response[first_brace:last_brace + 1]
        
        # Fix common JSON issues
        response = response.replace('\n', ' ')
        response = re.sub(r',\s*}', '}', response)
        response = re.sub(r',\s*]', ']', response)
        
        return response.strip() or "{}"
    
    def _normalize_evaluation(self, evaluation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize and validate evaluation structure to guarantee backward compatibility.
        Maps the new strict prompt JSON structure to the legacy schema expected by the frontend.
        """
        # Convert flat strict structure to nested scores structure if needed
        if "scores" not in evaluation:
            evaluation["scores"] = {}
            for dim in SCORING_DIMENSIONS:
                if dim in evaluation:
                    evaluation["scores"][dim] = evaluation.pop(dim)

        if not isinstance(evaluation["scores"], dict):
            evaluation["scores"] = {}

        # Validate and clamp each scoring dimension
        for criterion in SCORING_DIMENSIONS:
            if criterion not in evaluation["scores"]:
                evaluation["scores"][criterion] = 5
            else:
                try:
                    evaluation["scores"][criterion] = max(
                        1, min(10, int(float(evaluation["scores"][criterion])))
                    )
                except (ValueError, TypeError):
                    evaluation["scores"][criterion] = 5

        # Clean extra dimensions
        evaluation["scores"] = {
            k: v for k, v in evaluation["scores"].items() if k in SCORING_DIMENSIONS
        }

        # Handle final_score vs average_score
        if "final_score" in evaluation:
            evaluation["average_score"] = evaluation.pop("final_score")
        elif "average_score" not in evaluation:
            scores = list(evaluation["scores"].values())
            evaluation["average_score"] = round(sum(scores) / len(scores), 1) if scores else 0.0

        # String fields defaults
        evaluation.setdefault("feedback", "Thank you for your answer.")
        evaluation.setdefault("improved_answer", "")

        # List fields defaults
        for field in ["strengths", "weaknesses", "weak_areas", "coaching_tips"]:
            if field not in evaluation or not isinstance(evaluation[field], list):
                evaluation[field] = []

        # If weak_areas is empty, dynamically populate it based on scores <= 6
        if not evaluation["weak_areas"]:
            for dim, val in evaluation["scores"].items():
                if val <= 6 and dim in VALID_WEAK_AREAS:
                    evaluation["weak_areas"].append(dim)

        evaluation["weak_areas"] = [
            w for w in evaluation["weak_areas"] if w in VALID_WEAK_AREAS
        ]

        # Metadata defaults
        meta = evaluation.setdefault("metadata", {})
        meta.setdefault("fallback", False)
        meta.setdefault("dataset_match", False)

        return evaluation
    
    def _generate_fallback_evaluation(
        self,
        reason: str,
        answer: str,
        feedback_msg: str,
        fallback_type: str = "length_based"
    ) -> Dict[str, Any]:
        """
        Generate a structured fallback evaluation when LLM is unavailable.

        Uses answer length as a basic quality signal.
        Always marks metadata.fallback = True so downstream aggregators
        can exclude or flag these scores.

        Args:
            reason: Short identifier for why fallback was triggered
            answer: The candidate's answer text
            feedback_msg: Primary feedback message to return
            fallback_type: 'length_based' | 'llm_failure' | 'parse_error' | 'too_short'
        """
        answer_length = len(answer.strip())

        if answer_length < 50:
            score = 3
            default_feedback = "Your answer is very brief. Please provide more detail with specific examples."
        elif answer_length < 150:
            score = 5
            default_feedback = "Good start! Add more depth and specific examples to strengthen your answer."
        elif answer_length < 300:
            score = 6
            default_feedback = "Solid answer. Consider adding more specific examples or industry best practices."
        else:
            score = 7
            default_feedback = "Comprehensive answer. Review it to ensure all points are directly relevant."

        return {
            "scores": {
                "technical_accuracy": score,
                "clarity": score,
                "communication": score,
                "completeness": max(1, score - 1),
            },
            "average_score": float(score),
            "score": float(score),
            "reasoning": feedback_msg or default_feedback,
            "feedback": feedback_msg or default_feedback,
            "strengths": ["Attempted to answer the question"],
            "gaps": ["Could provide more detail and examples"],
            "weaknesses": ["Could provide more detail and examples"],
            "weak_areas": [],
            "improved_answer": "",
            "coaching_tips": [
                "Practice articulating your thoughts clearly",
                "Add specific examples to support your points",
            ],
            "metadata": {
                "fallback": True,
                "dataset_match": False,
                "type": fallback_type,
                "reason": reason,
            },
            "llm_used": False,
            "dataset_match_type": "no_match",
            "difficulty": "medium"
        }


# Singleton instance
_service_instance = None

def get_evaluation_service() -> EnhancedEvaluationService:
    """Get or create the evaluation service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EnhancedEvaluationService()
    return _service_instance


async def log_eval_stats_to_db(stats: dict) -> None:
    """
    Fire-and-forget logging of evaluation statistics to Supabase.
    """
    try:
        from database.supabase_client import _db_insert
        # Prepare the payload for eval_stats_log table
        data = {
            "total": stats.get("total", 0),
            "fallback": stats.get("fallback", 0),
            "dataset_match": stats.get("dataset_match", 0),
            "strong_match": stats.get("strong_match", 0),
            "llm_unavailable": stats.get("llm_unavailable", 0)
        }
        await _db_insert("eval_stats_log", data)
    except Exception as e:
        logger.warning(f"⚠️ Failed to log evaluation statistics to db (non-fatal): {e}")


async def evaluate_answer_enhanced(
    question: str,
    candidate_answer: str,
    target_role: str = "Backend Engineer",
    experience_level: str = "Mid",
    interview_type: str = "Mixed",
    question_difficulty: str = "medium",
) -> Dict[str, Any]:
    """
    Main API function for enhanced answer evaluation.

    Args:
        question: The interview question
        candidate_answer: Candidate's response
        target_role: Target position
        experience_level: Experience level
        interview_type: Interview type
        question_difficulty: 'easy' | 'medium' | 'hard' (default 'medium')

    Returns:
        Standard evaluation schema including score_confidence and metadata.strong_match
    """
    service = get_evaluation_service()
    return await service.evaluate_answer_with_dataset(
        question=question,
        candidate_answer=candidate_answer,
        target_role=target_role,
        experience_level=experience_level,
        interview_type=interview_type,
        question_difficulty=question_difficulty,
    )


def get_eval_stats() -> Dict[str, Any]:
    """
    Task 5: Return current evaluation quality counters.
    Exposed via /api/evaluate-answer/status for monitoring.
    """
    total = EVAL_STATS["total"]
    if total == 0:
        return {**EVAL_STATS, "fallback_pct": 0.0, "match_pct": 0.0, "strong_pct": 0.0}
    return {
        **EVAL_STATS,
        "fallback_pct": round(EVAL_STATS["fallback"] / total * 100, 1),
        "match_pct": round(EVAL_STATS["dataset_match"] / total * 100, 1),
        "strong_pct": round(EVAL_STATS["strong_match"] / total * 100, 1),
    }
