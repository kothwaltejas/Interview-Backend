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
import re
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from difflib import SequenceMatcher
from .llm_groq_config import chat_completion

logger = logging.getLogger(__name__)

# Global dataset cache
_DATASET_CACHE: Optional[List[Dict[str, Any]]] = None
_DATASET_LOADED = False


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
    ) -> Optional[Dict[str, Any]]:
        """
        Find matching question in dataset using similarity matching.
        
        Args:
            question: The question asked
            target_role: Optional filter by target_role
            
        Returns:
            Matched dataset entry or None
        """
        if not self.dataset:
            return None
        
        best_match = None
        best_score = 0.0
        
        for entry in self.dataset:
            # Filter by role if specified
            if target_role and entry.get('target_role') != target_role:
                continue
            
            # Calculate similarity
            similarity = self._similarity_score(
                question.lower(),
                entry.get('question', '').lower()
            )
            
            if similarity > best_score:
                best_score = similarity
                best_match = entry
        
        # Only return if similarity is reasonably high (>0.3)
        if best_score > 0.3:
            logger.info(f"📊 Found matching question with similarity {best_score:.2f}")
            return best_match
        
        logger.info(f"❌ No matching question found (best similarity: {best_score:.2f})")
        return None
    
    def _similarity_score(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        return SequenceMatcher(None, text1, text2).ratio()
    
    async def evaluate_answer_with_dataset(
        self,
        question: str,
        candidate_answer: str,
        target_role: str = "Backend Engineer",
        experience_level: str = "Mid",
        interview_type: str = "Mixed"
    ) -> Dict[str, Any]:
        """
        Evaluate answer using dataset context + LLM.
        
        Args:
            question: The interview question
            candidate_answer: Candidate's response
            target_role: Target position
            experience_level: Experience level (Entry/Mid/Senior)
            interview_type: Interview type (Technical/Behavioral/Mixed)
            
        Returns:
            Structured evaluation with scores, feedback, weak areas, etc.
        """
        logger.info("🔍 Starting enhanced answer evaluation...")
        
        # Validation
        if not candidate_answer or len(candidate_answer.strip()) < 10:
            return self._generate_fallback_evaluation(
                "Answer too short",
                candidate_answer,
                "Your answer is too brief. Please provide more details and examples."
            )
        
        try:
            # Find matching question in dataset
            matched_entry = self.find_matching_question(question, target_role)
            
            # Build evaluation context
            context = {
                "question": question,
                "candidate_answer": candidate_answer,
                "target_role": target_role,
                "experience_level": experience_level,
                "interview_type": interview_type,
                "has_dataset_match": matched_entry is not None,
                "matched_entry": matched_entry
            }
            
            # If dataset match found, use it for comparison
            if matched_entry:
                logger.info("✅ Using dataset-based evaluation with comparison answers")
                return await self._evaluate_with_comparison(context)
            else:
                logger.info("⚠️ No dataset match, using generic evaluation")
                return await self._evaluate_generic(context)
        
        except Exception as e:
            logger.error(f"❌ Evaluation error: {e}")
            return self._generate_fallback_evaluation("error", candidate_answer, str(e))
    
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
        
        prompt = f"""You are an expert technical interviewer evaluating a candidate answer.

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

REFERENCE ANSWERS FROM DATASET:
- Ideal Answer (Score 9): {reference_answers.get('ideal', {}).get('text', '')[:300]}...
- Good Answer (Score 7.8): {reference_answers.get('good', {}).get('text', '')[:300]}...
- Average Answer (Score 5.8): {reference_answers.get('average', {}).get('text', '')[:300]}...
- Poor Answer (Score 1.8): {reference_answers.get('poor', {}).get('text', '')[:300]}...

EVALUATION CRITERIA:
1. **Technical Accuracy**: Does the answer contain correct technical information?
2. **Clarity**: Is the answer clear and well-structured?
3. **Communication**: Does the candidate articulate ideas effectively?
4. **Confidence**: Is the candidate confident in their answer?

WEAK AREAS (if applicable):
- technical: Low technical accuracy or missing key concepts
- clarity: Unclear or poorly structured explanation
- communication: Difficulty articulating ideas
- confidence: Uncertainty or lack of conviction

EVALUATION TASK:
1. Rate the candidate's answer on each criterion (1-10)
2. Compare with reference answers - which level is closest?
3. Provide 2-3 sentence actionable feedback
4. Identify 2-3 key strengths of the answer
5. Identify 2-3 key weaknesses or areas for improvement
6. List any weak_areas from the criteria
7. Provide an improved version of the answer (better than candidate's)

Return ONLY valid JSON (no markdown):
{{
  "scores": {{
    "technical_accuracy": 8,
    "clarity": 8,
    "communication": 8,
    "confidence": 8
  }},
  "overall_score_explanation": "Why this score reflects the performance",
  "comparison_with_dataset": "Closest to ideal/good/average/poor answer and why",
  "feedback": "Actionable constructive feedback...",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2", "weakness 3"],
  "weak_areas": ["technical", "clarity"],
  "improved_answer": "Enhanced version addressing the weaknesses...",
  "coaching_tips": ["tip 1", "tip 2", "tip 3"]
}}"""
        
        logger.info("📞 Calling GROQ LLM for dataset-based evaluation...")
        
        response = chat_completion(
            prompt=prompt,
            max_tokens=1500,
            temperature=0.1  # Low temperature for consistency
        )
        
        if not response:
            logger.error("❌ No response from LLM")
            return self._generate_fallback_evaluation(
                "llm_error",
                candidate_answer,
                "Failed to get evaluation from LLM"
            )
        
        # Parse and validate response
        try:
            cleaned = self._clean_json_response(response)
            evaluation = json.loads(cleaned)
            
            # Validate and normalize structure
            evaluation = self._normalize_evaluation(evaluation)
            
            # Add metadata
            evaluation["metadata"] = {
                "dataset_match": True,
                "matched_question_category": category,
                "matched_question_difficulty": difficulty,
                "key_points_count": len(key_points),
                "comparison_enabled": True
            }
            
            logger.info(f"✅ Evaluation complete: Score={evaluation['scores'].get('technical_accuracy')}")
            return evaluation
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}")
            return self._generate_fallback_evaluation(
                "parse_error",
                candidate_answer,
                "Failed to parse evaluation response"
            )
    
    async def _evaluate_generic(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic evaluation without dataset comparison."""
        
        question = context["question"]
        candidate_answer = context["candidate_answer"]
        target_role = context["target_role"]
        experience_level = context["experience_level"]
        
        prompt = f"""You are an expert technical interviewer.

QUESTION:
"{question}"

CANDIDATE'S ANSWER:
"{candidate_answer}"

CONTEXT:
- Role: {target_role}
- Experience Level: {experience_level}

Evaluate based on:
1. Technical Accuracy (1-10)
2. Clarity (1-10)
3. Communication (1-10)
4. Confidence (1-10)

Provide:
- Short feedback (2-3 sentences)
- Strengths (2-3 bullet points)
- Weaknesses (2-3 bullet points)
- Weak areas to focus on
- Improved version of the answer

Return ONLY valid JSON:
{{
  "scores": {{
    "technical_accuracy": 6,
    "clarity": 6,
    "communication": 6,
    "confidence": 5
  }},
  "feedback": "Feedback here...",
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "weak_areas": [],
  "improved_answer": "...",
  "coaching_tips": ["...", "..."]
}}"""
        
        logger.info("📞 Calling GROQ LLM for generic evaluation...")
        
        response = chat_completion(
            prompt=prompt,
            max_tokens=1200,
            temperature=0.1
        )
        
        if not response:
            return self._generate_fallback_evaluation(
                "llm_error",
                candidate_answer,
                "Failed to evaluate answer"
            )
        
        try:
            cleaned = self._clean_json_response(response)
            evaluation = json.loads(cleaned)
            evaluation = self._normalize_evaluation(evaluation)
            
            evaluation["metadata"] = {
                "dataset_match": False,
                "comparison_enabled": False
            }
            
            return evaluation
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}")
            return self._generate_fallback_evaluation(
                "parse_error",
                candidate_answer,
                "Failed to parse response"
            )
    
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
        """Normalize and validate evaluation structure."""
        
        # Ensure scores exist and are in valid range
        if 'scores' not in evaluation:
            evaluation['scores'] = {}
        
        for criterion in ['technical_accuracy', 'clarity', 'communication', 'confidence']:
            if criterion not in evaluation['scores']:
                evaluation['scores'][criterion] = 5
            else:
                # Clamp to 1-10
                try:
                    evaluation['scores'][criterion] = max(1, min(10, int(evaluation['scores'][criterion])))
                except (ValueError, TypeError):
                    evaluation['scores'][criterion] = 5
        
        # Calculate average score
        scores = list(evaluation['scores'].values())
        evaluation['average_score'] = round(sum(scores) / len(scores), 1) if scores else 5.0
        
        # Ensure all required fields
        evaluation.setdefault('feedback', "Thank you for your answer.")
        evaluation.setdefault('strengths', [])
        evaluation.setdefault('weaknesses', [])
        evaluation.setdefault('weak_areas', [])
        evaluation.setdefault('improved_answer', "")
        evaluation.setdefault('coaching_tips', [])
        
        # Ensure arrays are lists
        for field in ['strengths', 'weaknesses', 'weak_areas', 'coaching_tips']:
            if not isinstance(evaluation.get(field), list):
                evaluation[field] = []
        
        return evaluation
    
    def _generate_fallback_evaluation(
        self,
        reason: str,
        answer: str,
        feedback_msg: str
    ) -> Dict[str, Any]:
        """Generate fallback evaluation for errors."""
        
        answer_length = len(answer.strip())
        
        # Basic length-based scoring
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
                "confidence": score - 1 if score > 1 else 1
            },
            "average_score": score,
            "feedback": feedback_msg or default_feedback,
            "strengths": ["Attempted to answer the question"],
            "weaknesses": ["Could provide more detail and examples"],
            "weak_areas": [],
            "improved_answer": "",
            "coaching_tips": ["Practice articulating your thoughts clearly", "Add specific examples"],
            "metadata": {
                "fallback": True,
                "reason": reason,
                "evaluation_type": "basic"
            }
        }


# Singleton instance
_service_instance = None

def get_evaluation_service() -> EnhancedEvaluationService:
    """Get or create the evaluation service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EnhancedEvaluationService()
    return _service_instance


async def evaluate_answer_enhanced(
    question: str,
    candidate_answer: str,
    target_role: str = "Backend Engineer",
    experience_level: str = "Mid",
    interview_type: str = "Mixed"
) -> Dict[str, Any]:
    """
    Main API function for enhanced answer evaluation.
    
    Args:
        question: The interview question
        candidate_answer: Candidate's response
        target_role: Target position
        experience_level: Experience level
        interview_type: Interview type
        
    Returns:
        Structured evaluation response
    """
    service = get_evaluation_service()
    return await service.evaluate_answer_with_dataset(
        question=question,
        candidate_answer=candidate_answer,
        target_role=target_role,
        experience_level=experience_level,
        interview_type=interview_type
    )
