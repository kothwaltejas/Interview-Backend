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
            # Basic metrics
            "overall_score": round(overall_score, 2),
            "performance_tier": SessionSummaryBuilder.determine_performance_tier(overall_score),
            "consistency_score": round(consistency_score, 2),  # 0-1, how consistent across answers
            
            # Category breakdown
            "scores_by_category": average_scores,
            "category_details": scores_by_category,
            
            # Per-difficulty analysis (if available)
            "scores_by_difficulty": SessionSummaryBuilder.aggregate_by_difficulty(
                responses, evaluations, questions
            ),
            
            # Patterns and insights
            "strength_areas": strength_areas,
            "improvement_areas": weak_areas,
            "most_frequent_weak_areas": dict(most_frequent_weak_areas),  # Counter → dict
            "most_frequent_strengths": dict(most_frequent_strengths),
            
            # Coaching and next steps
            "coaching_summary": coaching_summary,
            "top_3_improvement_focus": improvement_suggestions[:3],
            
            # Question-level breakdown
            "per_question_breakdown": SessionSummaryBuilder.build_question_breakdown(
                responses, questions, evaluations
            ),
            
            # Additional context
            "job_context": job_context,
            "total_questions": len(questions),
            "answered_questions": len([r for r in responses if not r.get("skipped")]),
            "skipped_questions": len([r for r in responses if r.get("skipped")]),
        }
        
        logger.info(f"Enhanced summary generated - Overall Score: {overall_score:.1f}, "
                   f"Strengths: {len(strength_areas)}, Improvements: {len(weak_areas)}")
        
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
        """Group scores by category across all answers."""
        scores_by_category = {
            "technical_accuracy": [],
            "clarity": [],
            "communication": [],
            "confidence": []
        }
        
        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue
                
            scores = eval_data["evaluation"].get("scores", {})
            
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
        """Calculate overall score across all categories and questions."""
        all_scores = []
        
        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue
                
            avg = eval_data["evaluation"].get("average_score")
            if avg is not None:
                try:
                    all_scores.append(float(avg))
                except (TypeError, ValueError):
                    pass
        
        return mean(all_scores) if all_scores else 0.0
    
    @staticmethod
    def calculate_consistency_score(evaluations: List[Dict[str, Any]]) -> float:
        """
        Calculate consistency: 1.0 = perfect consistency, 0.0 = highly variable.
        
        Uses coefficient of variation (stdev/mean) inverted.
        """
        all_scores = []
        
        for eval_data in evaluations:
            if eval_data["skipped"]:
                continue
            
            avg = eval_data["evaluation"].get("average_score")
            if avg is not None:
                try:
                    all_scores.append(float(avg))
                except (TypeError, ValueError):
                    pass
        
        if len(all_scores) < 2:
            return 1.0  # Only one answer - perfect consistency
        
        try:
            score_stdev = stdev(all_scores)
            score_mean = mean(all_scores)
            
            if score_mean == 0:
                return 0.0
            
            # Coefficient of variation: lower = more consistent
            cv = score_stdev / score_mean
            
            # Invert to get consistency score (1 = consistent, 0 = variable)
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
        
        if "confidence" in weak_areas:
            suggestions.append(
                "Build confidence: Practice more answers to this role. The more you practice, "
                "the more confident you'll sound naturally."
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
                item.update({
                    "score": evaluation.get("average_score"),
                    "scores_by_category": evaluation.get("scores"),
                    "feedback": evaluation.get("feedback"),
                    "strengths": evaluation.get("strengths", []),
                    "weaknesses": evaluation.get("weaknesses", []),
                    "weak_areas": evaluation.get("weak_areas", []),
                    "improved_answer": evaluation.get("improved_answer")
                })
            
            breakdown.append(item)
        
        return breakdown
    
    @staticmethod
    def build_basic_summary(
        responses: List[Dict[str, Any]],
        questions: List[Dict[str, Any]],
        job_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback: Build basic summary without evaluations."""
        logger.warning("Building basic summary - no evaluations available")
        
        return {
            "overall_score": 5.0,
            "performance_tier": "Neutral",
            "consistency_score": 0.5,
            "scores_by_category": {
                "technical_accuracy": 0.0,
                "clarity": 0.0,
                "communication": 0.0,
                "confidence": 0.0
            },
            "strength_areas": [],
            "improvement_areas": [],
            "coaching_summary": "Interview completed. No evaluation data available.",
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
