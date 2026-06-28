"""
Session Summary Builder Service

Aggregates per-answer evaluations into a comprehensive, intelligent final report.
Combines real-time evaluation data with analysis to provide actionable coaching insights.
"""

import logging
from typing import Dict, Any, List, Optional
from collections import Counter
from statistics import mean, stdev

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_valid_eval(evaluation: Dict[str, Any]) -> bool:
    """
    Task 2: Single source of truth for fallback exclusion.

    Returns True only for real LLM evaluations.
    Excludes ALL evaluations where metadata.fallback=True — this covers:
      - System-error fallbacks (average_score=0)
      - Length-based fallbacks (average_score=3–7)
      - too_short fallbacks
      - llm_failure, parse_error, etc.
    """
    return not evaluation.get("metadata", {}).get("fallback", False)


def _build_eval_quality(evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a quality summary block for the session response.

    Counts valid vs fallback evaluations and aggregates score_confidence
    distribution so the frontend can display data reliability.
    """
    total = len([e for e in evaluations if not e["skipped"]])
    fallback_count = sum(
        1 for e in evaluations
        if not e["skipped"] and not _is_valid_eval(e["evaluation"])
    )
    valid_count = total - fallback_count

    confidence_dist: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for e in evaluations:
        if e["skipped"]:
            continue
        conf = e["evaluation"].get("score_confidence", "medium")
        if conf in confidence_dist:
            confidence_dist[conf] += 1

    return {
        "total_evaluated": total,
        "valid_evaluations": valid_count,
        "fallback_evaluations": fallback_count,
        "data_reliability": (
            "high" if fallback_count == 0
            else "medium" if fallback_count / max(total, 1) < 0.3
            else "low"
        ),
        "score_confidence_distribution": confidence_dist,
    }


class SessionSummaryBuilder:
    """Build enhanced final report from per-answer evaluations."""

    
    @staticmethod
    def build_enhanced_summary(
        responses: List[Dict[str, Any]],
        questions: List[Dict[str, Any]],
        job_context: Dict[str, Any],
        session_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build comprehensive final report from interview responses with evaluations.
        
        Args:
            responses: List of answer responses, each with possible 'evaluation' field
            questions: List of interview questions (for reference)
            job_context: Job context (target_role, experience_level, interview_type)
            session_metadata: Optional metadata about session
            
        Returns:
            Comprehensive summary with aggregated scores, insights, and recommendations
        """
        
        # Extract evaluations from responses
        evaluations = SessionSummaryBuilder.extract_evaluations(responses)
        
        if not evaluations:
            logger.warning("No evaluations found in responses - using fallback")
            return SessionSummaryBuilder.build_basic_summary(responses, questions, job_context)
        
        # Calculate aggregate metrics
        scores_by_category = SessionSummaryBuilder.aggregate_scores(evaluations)
        average_scores = SessionSummaryBuilder.calculate_average_scores(scores_by_category)
        overall_score = SessionSummaryBuilder.calculate_overall_score(evaluations)
        consistency_score = SessionSummaryBuilder.calculate_consistency_score(evaluations)
        
        # Identify patterns
        weak_areas = SessionSummaryBuilder.identify_weak_areas(evaluations)
        strength_areas = SessionSummaryBuilder.identify_strength_areas(evaluations)
        most_frequent_weak_areas = SessionSummaryBuilder.count_weak_areas(evaluations)
        most_frequent_strengths = SessionSummaryBuilder.count_strengths(evaluations)
        
        # Generate coaching insights
        improvement_suggestions = SessionSummaryBuilder.generate_improvement_suggestions(
            weak_areas, evaluations, responses, questions, job_context
        )
        coaching_summary = SessionSummaryBuilder.generate_coaching_summary(
            overall_score, strength_areas, weak_areas, improvement_suggestions
        )
        
        # Build final report
        summary = {
            # Core metrics
            "overall_score": round(overall_score, 2),
            "performance_tier": SessionSummaryBuilder.determine_performance_tier(overall_score),
            "consistency_score": round(consistency_score, 2),

            # Category breakdown
            "scores_by_category": average_scores,
            "breakdown": average_scores,
            "category_details": scores_by_category,

            # Per-difficulty analysis
            "scores_by_difficulty": SessionSummaryBuilder.aggregate_by_difficulty(
                responses, evaluations, questions
            ),

            # Patterns and insights
            "strength_areas": strength_areas,
            "improvement_areas": weak_areas,
            "most_frequent_weak_areas": dict(most_frequent_weak_areas),
            "most_frequent_strengths": dict(most_frequent_strengths),
            "topic_coverage": SessionSummaryBuilder.analyze_topic_coverage(evaluations, questions),
            "repetition_warnings": SessionSummaryBuilder.detect_repetitions(evaluations),

            # Coaching
            "coaching_summary": coaching_summary,
            "top_3_improvement_focus": improvement_suggestions[:3],

            # Question-level breakdown
            "per_question_breakdown": SessionSummaryBuilder.build_question_breakdown(
                responses, questions, evaluations
            ),

            # Context
            "job_context": job_context,
            "total_questions": len(questions),
            "answered_questions": len([r for r in responses if not r.get("skipped")]),
            "skipped_questions": len([r for r in responses if r.get("skipped")]),

            "eval_quality": _build_eval_quality(evaluations),
        }

        sector_agg = SessionSummaryBuilder.aggregate_sector_scores(responses)
        summary["sector_averages"] = sector_agg

        if sector_agg.get("composite") is not None:
            summary["overall_composite_score"] = sector_agg["composite"]

        logger.info(f"Enhanced summary generated - Overall Score: {overall_score:.1f}, "
                   f"Composite: {sector_agg.get('composite', 'N/A')}")

        return summary
    
    @staticmethod
    def extract_evaluations(responses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract evaluations from responses (skipping if missing)."""
        evaluations = []
        for i, response in enumerate(responses):
            if response.get("evaluation"):
                evaluations.append({
                    "question_number": i + 1,
                    "question_text": response.get("question_text", ""),
                    "answer_text": response.get("answer_text", ""),
                    "evaluation": response["evaluation"],
                    "skipped": response.get("skipped", False)
                })
        return evaluations
    
    @staticmethod
    def aggregate_scores(evaluations: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """
        Group scores by dimension.

        Task 2: Completely excludes ANY evaluation where metadata.fallback=True,
        regardless of whether the score is zero or non-zero (e.g. length-based
        fallbacks that return score=5 would otherwise inflate results).
        """
        scores_by_category = {
            "technical_accuracy": [],
            "clarity": [],
            "communication": [],
            "completeness": [],
        }

        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue

            evaluation = eval_data["evaluation"]
            if not _is_valid_eval(evaluation):
                continue

            scores = evaluation.get("scores", {})
            for category, score_list in scores_by_category.items():
                if category in scores:
                    try:
                        score_list.append(float(scores[category]))
                    except (TypeError, ValueError):
                        pass

        return scores_by_category
    
    @staticmethod
    def calculate_average_scores(
        scores_by_category: Dict[str, List[float]]
    ) -> Dict[str, float]:
        """Calculate average score for each category."""
        averages = {}
        
        for category, scores in scores_by_category.items():
            if scores:
                avg = mean(scores)
                averages[category] = round(avg, 2)
            else:
                averages[category] = 0.0
        
        return averages
    
    @staticmethod
    def calculate_overall_score(evaluations: List[Dict[str, Any]]) -> float:
        """
        Task 2: Calculate overall score using ONLY fully valid (non-fallback) evaluations.

        Any evaluation with metadata.fallback=True is excluded entirely,
        including length-based fallbacks with non-zero scores.
        If no valid evaluations exist, returns 0.0 (not a fake mid-range value).
        """
        valid_evals = [
            e for e in evaluations
            if not e["skipped"] and _is_valid_eval(e["evaluation"])
        ]

        valid_scores = [
            float(e["evaluation"]["average_score"])
            for e in valid_evals
            if e["evaluation"].get("average_score", 0) > 0
        ]

        if not valid_scores:
            logger.warning(
                "calculate_overall_score: no valid (non-fallback) scores found. "
                "Returning 0.0."
            )
            return 0.0

        return mean(valid_scores)
    
    @staticmethod
    def calculate_consistency_score(evaluations: List[Dict[str, Any]]) -> float:
        """
        Calculate consistency: 1.0 = perfect, 0.0 = highly variable.

        Task 2: Only uses valid (non-fallback) scores for consistency calculation.
        """
        all_scores = [
            float(e["evaluation"]["average_score"])
            for e in evaluations
            if not e["skipped"]
            and _is_valid_eval(e["evaluation"])
            and e["evaluation"].get("average_score") is not None
        ]

        if len(all_scores) < 2:
            return 1.0  # Single valid answer = perfect consistency

        try:
            score_stdev = stdev(all_scores)
            score_mean = mean(all_scores)

            if score_mean == 0:
                return 0.0

            cv = score_stdev / score_mean
            consistency = max(0.0, 1.0 - cv)
            return round(consistency, 2)
        except Exception as e:
            logger.error(f"Error calculating consistency: {e}")
            return 0.5
    
    @staticmethod
    def identify_weak_areas(evaluations: List[Dict[str, Any]]) -> List[str]:
        """Identify pattern of weak areas."""
        weak_areas = set()
        
        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue
            
            weak = eval_data["evaluation"].get("weak_areas", [])
            if isinstance(weak, list):
                weak_areas.update(weak)
        
        return sorted(list(weak_areas))
    
    @staticmethod
    def identify_strength_areas(evaluations: List[Dict[str, Any]]) -> List[str]:
        """Identify pattern of strength areas."""
        strengths = set()
        
        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue
            
            eval_strengths = eval_data["evaluation"].get("strengths", [])
            if isinstance(eval_strengths, list):
                strengths.update(eval_strengths)
        
        return sorted(list(strengths))[:5]  # Top 5
    
    @staticmethod
    def count_weak_areas(evaluations: List[Dict[str, Any]]) -> Counter:
        """Count frequency of each weak area."""
        weak_area_counter = Counter()
        
        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue
            
            weak = eval_data["evaluation"].get("weak_areas", [])
            if isinstance(weak, list):
                for area in weak:
                    weak_area_counter[area] += 1
        
        return weak_area_counter.most_common(5)
    
    @staticmethod
    def count_strengths(evaluations: List[Dict[str, Any]]) -> Counter:
        """Count frequency of each strength."""
        strength_counter = Counter()
        
        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue
            
            strengths = eval_data["evaluation"].get("strengths", [])
            if isinstance(strengths, list):
                for strength in strengths:
                    strength_counter[strength] += 1
        
        return strength_counter.most_common(5)
    
    @staticmethod
    def aggregate_by_difficulty(
        responses: List[Dict[str, Any]],
        evaluations: List[Dict[str, Any]],
        questions: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Aggregate scores by question difficulty."""
        difficulty_scores = {}
        
        for i, question in enumerate(questions):
            difficulty = question.get("difficulty", "unknown").lower()
            
            if difficulty not in difficulty_scores:
                difficulty_scores[difficulty] = {
                    "scores": [],
                    "count": 0,
                    "average": 0.0
                }
            
            # Find corresponding evaluation
            eval_data = next((e for e in evaluations if e["question_number"] == i + 1), None)
            
            if eval_data and not eval_data["skipped"]:
                avg_score = eval_data["evaluation"].get("average_score", 0)
                difficulty_scores[difficulty]["scores"].append(avg_score)
                difficulty_scores[difficulty]["count"] += 1
        
        # Calculate averages
        for difficulty in difficulty_scores:
            scores = difficulty_scores[difficulty]["scores"]
            if scores:
                difficulty_scores[difficulty]["average"] = round(mean(scores), 2)
        
        return difficulty_scores

    @staticmethod
    def analyze_topic_coverage(evaluations: List[Dict[str, Any]], questions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze how well the candidate covered different topics/categories."""
        coverage = {}
        for i, question in enumerate(questions):
            category = question.get("category", "general")
            if category not in coverage:
                coverage[category] = {"questions": 0, "answered": 0, "avg_score": 0.0, "scores": []}
            
            coverage[category]["questions"] += 1
            
            eval_data = next((e for e in evaluations if e["question_number"] == i + 1), None)
            if eval_data and not eval_data["skipped"] and _is_valid_eval(eval_data["evaluation"]):
                coverage[category]["answered"] += 1
                score = eval_data["evaluation"].get("average_score", 0)
                coverage[category]["scores"].append(score)
        
        for cat, data in coverage.items():
            if data["scores"]:
                data["avg_score"] = round(mean(data["scores"]), 2)
            del data["scores"]
            
        return coverage

    @staticmethod
    def detect_repetitions(evaluations: List[Dict[str, Any]]) -> List[str]:
        """Detect if the candidate is repeating the same stories/examples across answers."""
        import re
        warnings = []
        all_answers = []
        
        for eval_data in evaluations:
            if not eval_data["skipped"]:
                answer = eval_data.get("answer_text", "").lower()
                # Use words >= 5 chars to find repeated concepts/stories, ignore common small words
                words = set(re.findall(r'\b\w{5,}\b', answer))
                all_answers.append({"q_num": eval_data["question_number"], "words": words})
                
        # Compare each pair
        for i in range(len(all_answers)):
            for j in range(i + 1, len(all_answers)):
                w1 = all_answers[i]["words"]
                w2 = all_answers[j]["words"]
                if w1 and w2:
                    overlap = len(w1.intersection(w2))
                    min_len = min(len(w1), len(w2))
                    if min_len > 10 and (overlap / min_len) > 0.4:
                        warnings.append(f"High similarity between answers for Q{all_answers[i]['q_num']} and Q{all_answers[j]['q_num']}. Try to use diverse examples.")
                        
        return list(set(warnings))[:3] # Return top 3 unique warnings
    
    @staticmethod
    def generate_improvement_suggestions(
        weak_areas: List[str],
        evaluations: List[Dict[str, Any]],
        responses: List[Dict[str, Any]],
        questions: List[Dict[str, Any]],
        job_context: Dict[str, Any]
    ) -> List[str]:
        """Generate specific, actionable improvement suggestions."""
        suggestions = []
        
        # From weak areas
        if "clarity" in weak_areas:
            suggestions.append(
                "Improve clarity: Practice structuring answers with clear main points first, "
                "then supporting details. Use specific examples."
            )
        
        if "communication" in weak_areas:
            suggestions.append(
                "Enhance communication: Work on pacing and tone. Record yourself answering questions "
                "and listen for areas where you rush or unclear transitions."
            )
        
        if "completeness" in weak_areas:
            suggestions.append(
                "Improve completeness: Make sure you address ALL parts of the question before answering. "
                "Briefly outline the sub-topics the question covers, then tackle each one."
            )

        if "technical_accuracy" in weak_areas:
            role = job_context.get("target_role", "this position")
            suggestions.append(
                f"Strengthen technical knowledge: Review core concepts for {role}. "
                f"Focus on hands-on practice with the tools and technologies mentioned in the job description."
            )
        
        # From lowest scoring questions
        lowest_scores = sorted(
            [(eval_data["question_number"], 
              eval_data["evaluation"].get("average_score", 0))
             for eval_data in evaluations if not eval_data["skipped"]],
            key=lambda x: x[1]
        )
        
        if lowest_scores:
            worst_question_num = lowest_scores[0][0]
            worst_question = questions[worst_question_num - 1] if worst_question_num <= len(questions) else None
            
            if worst_question:
                category = worst_question.get("category", "technical")
                suggestions.append(
                    f"Target category '{category}': This was your weakest area. "
                    f"Review similar questions and practice structured responses."
                )
        
        return suggestions[:5]  # Top 5 suggestions
    
    @staticmethod
    def generate_coaching_summary(
        overall_score: float,
        strength_areas: List[str],
        weak_areas: List[str],
        improvement_suggestions: List[str]
    ) -> str:
        """Generate human-readable coaching summary."""
        
        tier = SessionSummaryBuilder.determine_performance_tier(overall_score)
        tier_descriptions = {
            "Outstanding": "You demonstrated exceptional interview skills with strong performance across all areas.",
            "Strong": "You showed solid performance with clear strengths in several areas.",
            "Solid": "You demonstrated adequate performance with room for targeted improvement.",
            "Developing": "You have a foundation to build on. Focus on the improvement areas identified below.",
            "Beginning": "This is a great opportunity to work on the fundamentals. Start with the core improvement suggestions."
        }
        
        summary = f"{tier_descriptions.get(tier, 'Good effort!')}\n\n"
        
        if strength_areas:
            summary += f"💪 Strengths: {', '.join(strength_areas[:3])}\n"
        
        if weak_areas:
            summary += f"📈 Focus Areas: {', '.join(weak_areas[:3])}\n"
        
        summary += f"\n✨ Key Takeaway: "
        
        if overall_score >= 8.5:
            summary += "You're interview-ready! Consider applying to that position."
        elif overall_score >= 7.0:
            summary += "You're on the right track. Focus on the suggestions above and you'll be very competitive."
        elif overall_score >= 5.5:
            summary += "There's clear improvement potential. Use targeted practice on the focus areas."
        else:
            summary += "Don't get discouraged! Systematic practice on the focus areas will show significant improvement."
        
        return summary
    
    @staticmethod
    def determine_performance_tier(overall_score: float) -> str:
        """Determine performance tier based on overall score."""
        if overall_score >= 8.5:
            return "Outstanding"
        elif overall_score >= 7.5:
            return "Strong"
        elif overall_score >= 6.5:
            return "Solid"
        elif overall_score >= 5.0:
            return "Developing"
        else:
            return "Beginning"
    
    @staticmethod
    def build_question_breakdown(
        responses: List[Dict[str, Any]],
        questions: List[Dict[str, Any]],
        evaluations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build detailed per-question breakdown."""
        breakdown = []
        
        for i, response in enumerate(responses):
            question = questions[i] if i < len(questions) else {}
            eval_data = next((e for e in evaluations if e["question_number"] == i + 1), None)
            
            item = {
                "question_number": i + 1,
                "question": question.get("question", ""),
                "category": question.get("category", "Unknown"),
                "difficulty": question.get("difficulty", "unknown"),
                "answer": response.get("answer_text", ""),
                "skipped": response.get("skipped", False)
            }
            
            if eval_data:
                evaluation = eval_data["evaluation"]
                composite_data = evaluation.get("composite", {})
                item.update({
                    "score": evaluation.get("average_score"),
                    "scores_by_category": evaluation.get("scores"),
                    "feedback": evaluation.get("feedback"),
                    "strengths": evaluation.get("strengths", []),
                    "weaknesses": evaluation.get("weaknesses", []),
                    "weak_areas": evaluation.get("weak_areas", []),
                    "improved_answer": evaluation.get("improved_answer"),
                    "composite_score": composite_data.get("composite_score"),
                    "sector_scores": composite_data.get("sector_scores"),
                })
            
            breakdown.append(item)
        
        return breakdown
    
    @staticmethod
    def aggregate_sector_scores(responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate text, voice, and camera scores across all responses."""
        text_scores = []
        voice_scores = []
        camera_scores = []
        composite_scores = []

        for r in responses:
            if r.get("skipped"):
                continue

            evaluation = r.get("evaluation")
            if not evaluation:
                continue

            if not _is_valid_eval(evaluation):
                continue

            avg = evaluation.get("average_score")
            if avg and float(avg) > 0:
                text_scores.append(float(avg))

            composite_data = evaluation.get("composite", {})
            sector = composite_data.get("sector_scores", {})

            vs = sector.get("voice", {})
            if vs.get("available") and vs.get("score") is not None:
                voice_scores.append(float(vs["score"]))

            cs = sector.get("camera", {})
            if cs.get("available") and cs.get("score") is not None:
                camera_scores.append(float(cs["score"]))

            comp = composite_data.get("composite_score")
            if comp is not None:
                composite_scores.append(float(comp))

        return {
            "text": round(mean(text_scores), 1) if text_scores else None,
            "voice": round(mean(voice_scores), 1) if voice_scores else None,
            "camera": round(mean(camera_scores), 1) if camera_scores else None,
            "composite": round(mean(composite_scores), 1) if composite_scores else None,
            "text_count": len(text_scores),
            "voice_count": len(voice_scores),
            "camera_count": len(camera_scores),
        }

    @staticmethod
    def build_basic_summary(
        responses: List[Dict[str, Any]],
        questions: List[Dict[str, Any]],
        job_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fallback: Build a minimal summary when no per-answer evaluations exist.

        Returns overall_score=0.0 (not a fake 5.0) so the frontend can
        distinguish 'no data' from a real mid-range score.
        """
        logger.warning("build_basic_summary: no per-answer evaluations available")

        empty_breakdown = {
            "technical_accuracy": 0.0,
            "clarity": 0.0,
            "communication": 0.0,
            "completeness": 0.0,
        }

        return {
            "overall_score": 0.0,
            "performance_tier": "No Data",
            "consistency_score": 0.0,
            "scores_by_category": empty_breakdown,
            "breakdown": empty_breakdown,
            "strength_areas": [],
            "improvement_areas": [],
            "coaching_summary": "Interview completed. No per-answer evaluation data was available.",
            "per_question_breakdown": [],
            "job_context": job_context,
            "total_questions": len(questions),
            "answered_questions": len([r for r in responses if not r.get("skipped")]),
            "skipped_questions": len([r for r in responses if r.get("skipped")]),
        }


# Convenience function for backward compatibility
def build_session_summary(
    responses: List[Dict[str, Any]],
    questions: List[Dict[str, Any]],
    job_context: Dict[str, Any],
    session_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Convenience function to build enhanced session summary."""
    return SessionSummaryBuilder.build_enhanced_summary(
        responses, questions, job_context, session_metadata
    )
