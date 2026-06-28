"""
Answer Evaluator — Backward-Compatible Wrapper

All evaluation is now delegated to EnhancedEvaluationService to guarantee:
  - Consistent 4-dimension scoring schema across ALL endpoints
  - Strict scoring rubric applied uniformly
  - Dataset-based comparison where available
  - Typed fallback metadata

This module retains its public API so callers are unaffected.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


async def evaluate_answer(
    question: str,
    candidate_answer: str,
    job_context: Dict[str, Any],
    question_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluate a candidate's answer using the enhanced evaluation service.

    Backward-compatible wrapper: maps legacy call parameters to the
    EnhancedEvaluationService and returns the standardised schema.

    Args:
        question: The interview question asked
        candidate_answer: Candidate's response text
        job_context: Dict with target_role, experience_level, interview_type
        question_metadata: Optional extra metadata (category, difficulty, focus_area)

    Returns:
        Standard evaluation dict — see EnhancedEvaluationService schema
    """
    from .enhanced_evaluation_service import evaluate_answer_enhanced

    target_role = job_context.get("target_role", "Software Engineer")
    experience_level = job_context.get("experience_level", "Mid")
    interview_type = job_context.get("interview_type", "Technical")

    logger.info(
        f"evaluate_answer() → delegating to enhanced service "
        f"[role={target_role}, level={experience_level}]"
    )

    return await evaluate_answer_enhanced(
        question=question,
        candidate_answer=candidate_answer,
        target_role=target_role,
        experience_level=experience_level,
        interview_type=interview_type,
    )


def batch_evaluate_session(
    responses: List[Dict[str, Any]],
    job_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Aggregate pre-computed per-answer evaluations into a session summary.

    This is a pure aggregation function — it does NOT call the LLM.
    It reads evaluation data already stored in response['evaluation'].

    Args:
        responses: List of answer dicts, each potentially containing 'evaluation'
        job_context: Job context information

    Returns:
        Aggregated evaluation summary dict
    """
    if not responses:
        return {
            "overall_score": 0.0,
            "average_score": 0.0,
            "total_questions": 0,
            "answered": 0,
            "skipped": 0,
            "evaluated": 0,
            "feedback": "No responses to evaluate.",
            "performance_tier": "No Data",
        }

    valid_scores: List[float] = []

    for response in responses:
        if response.get("skipped", False):
            continue

        evaluation = response.get("evaluation")
        if not evaluation:
            continue

        # Skip system-error fallbacks with zero scores — they are not real scores
        is_fallback = evaluation.get("metadata", {}).get("fallback", False)
        avg = evaluation.get("average_score", 0)

        if is_fallback and float(avg) == 0.0:
            logger.debug("batch_evaluate: skipping zero-score system-error fallback")
            continue

        try:
            score = float(avg)
            if score > 0:
                valid_scores.append(score)
        except (TypeError, ValueError):
            logger.warning(f"batch_evaluate: invalid average_score value: {avg!r}")

    average_score = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 0.0

    # Determine performance tier
    if average_score >= 8.5:
        tier = "Outstanding"
        feedback = "Excellent performance! Strong technical knowledge and communication across the board."
    elif average_score >= 7.5:
        tier = "Strong"
        feedback = "Good performance overall. A few areas could benefit from greater depth."
    elif average_score >= 6.5:
        tier = "Solid"
        feedback = "Solid performance with room for targeted improvement."
    elif average_score >= 5.0:
        tier = "Developing"
        feedback = "Fair performance. Focus on strengthening core concepts and articulation."
    elif average_score > 0:
        tier = "Beginning"
        feedback = "Needs improvement. Practice structured responses and review core concepts."
    else:
        tier = "No Data"
        feedback = "Insufficient evaluation data — most answers could not be scored."

    return {
        "overall_score": average_score,
        "average_score": average_score,
        "total_questions": len(responses),
        "answered": len([r for r in responses if not r.get("skipped", False)]),
        "skipped": len([r for r in responses if r.get("skipped", False)]),
        "evaluated": len(valid_scores),
        "feedback": feedback,
        "performance_tier": tier,
    }


# ---------------------------------------------------------------------------
# Internal helpers kept for import safety (no longer used by evaluate_answer)
# ---------------------------------------------------------------------------

def clean_json_response(response: str) -> str:
    """Legacy JSON cleaner — retained for import compatibility."""
    import re
    if not response:
        return "{}"
    response = re.sub(r"```json\s*", "", response, flags=re.IGNORECASE)
    response = re.sub(r"```\s*", "", response)
    first_brace = response.find("{")
    if first_brace != -1:
        response = response[first_brace:]
    last_brace = response.rfind("}")
    if last_brace != -1:
        response = response[: last_brace + 1]
    response = response.replace("\n", " ")
    response = re.sub(r",\s*}", "}", response)
    response = re.sub(r",\s*]", "]", response)
    return response.strip() or "{}"


def generate_fallback_evaluation(answer: str) -> Dict[str, Any]:
    """
    Legacy length-based fallback — retained for import compatibility.
    Returns standard schema so downstream code is not broken.
    """
    answer_length = len(answer.strip())

    if answer_length < 50:
        score = 3
    elif answer_length < 150:
        score = 5
    elif answer_length < 300:
        score = 6
    else:
        score = 7

    return {
        "scores": {
            "technical_accuracy": score,
            "clarity": score,
            "communication": score,
            "completeness": max(1, score - 1),
        },
        "average_score": float(score),
        "feedback": "Answer received. Detailed evaluation was unavailable.",
        "strengths": [],
        "weak_areas": [],
        "metadata": {
            "fallback": True,
            "dataset_match": False,
            "type": "length_based",
        },
    }
