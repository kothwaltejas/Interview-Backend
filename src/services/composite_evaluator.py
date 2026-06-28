"""
Composite Evaluator Service

Combines three evaluation sectors into a single weighted score:
  1. Text Answer (60%) — LLM + dataset-based evaluation
  2. Voice Analysis (20%) — fluency, pace, filler words, confidence
  3. Camera Analysis (20%) — attention, presence, engagement

Falls back gracefully when voice or camera data is unavailable.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

SECTOR_WEIGHTS = {
    "text": 0.60,
    "voice": 0.20,
    "camera": 0.20,
}


def compute_composite_evaluation(
    text_evaluation: Dict[str, Any],
    voice_metrics: Optional[Dict[str, Any]] = None,
    camera_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Combine text, voice, and camera evaluations into a composite result.

    When voice or camera data is missing, redistributes their weight
    proportionally among the available sectors.

    Args:
        text_evaluation: Full evaluation dict from EnhancedEvaluationService
        voice_metrics: Dict from voice_analyzer.analyze_voice() or None
        camera_metrics: Dict from frontend camera analysis or None

    Returns:
        Composite evaluation with sector breakdown and weighted score
    """
    text_score = float(text_evaluation.get("average_score", 0))
    voice_score = _extract_voice_score(voice_metrics)
    camera_score = _extract_camera_score(camera_metrics)

    active_sectors: Dict[str, float] = {"text": text_score}
    weights: Dict[str, float] = {"text": SECTOR_WEIGHTS["text"]}

    if voice_score is not None:
        active_sectors["voice"] = voice_score
        weights["voice"] = SECTOR_WEIGHTS["voice"]

    if camera_score is not None:
        active_sectors["camera"] = camera_score
        weights["camera"] = SECTOR_WEIGHTS["camera"]

    total_weight = sum(weights.values())
    normalized_weights = {k: v / total_weight for k, v in weights.items()}

    composite_score = sum(
        active_sectors[k] * normalized_weights[k] for k in active_sectors
    )
    composite_score = round(max(1.0, min(10.0, composite_score)), 1)

    tier = _determine_tier(composite_score)
    feedback = _generate_multi_sector_feedback(
        text_evaluation, voice_metrics, camera_metrics, composite_score
    )
    improvement_areas = _identify_improvement_areas(
        text_evaluation, voice_metrics, camera_metrics
    )

    return {
        "composite_score": composite_score,
        "performance_tier": tier,
        "sector_scores": {
            "text": {
                "score": text_score,
                "weight": round(normalized_weights.get("text", 0), 2),
                "available": True,
            },
            "voice": {
                "score": voice_score if voice_score is not None else None,
                "weight": round(normalized_weights.get("voice", 0), 2),
                "available": voice_score is not None,
                "metrics": voice_metrics,
            },
            "camera": {
                "score": camera_score if camera_score is not None else None,
                "weight": round(normalized_weights.get("camera", 0), 2),
                "available": camera_score is not None,
                "metrics": camera_metrics,
            },
        },
        "text_evaluation_score": text_score,
        "feedback": feedback,
        "improvement_areas": improvement_areas,
        "sectors_active": list(active_sectors.keys()),
    }


def _extract_voice_score(voice_metrics: Optional[Dict[str, Any]]) -> Optional[float]:
    if not voice_metrics:
        return None
    score = voice_metrics.get("voice_score")
    if score is None or score == 0.0:
        return None
    return float(score)


def _extract_camera_score(camera_metrics: Optional[Dict[str, Any]]) -> Optional[float]:
    if not camera_metrics:
        return None
    score = camera_metrics.get("cameraScore") or camera_metrics.get("camera_score")
    if score is None or score == 0.0:
        return None
    return float(score)


def _determine_tier(score: float) -> str:
    if score >= 8.5:
        return "Outstanding"
    elif score >= 7.5:
        return "Strong"
    elif score >= 6.5:
        return "Solid"
    elif score >= 5.0:
        return "Developing"
    return "Beginning"


def _generate_multi_sector_feedback(
    text_eval: Dict[str, Any],
    voice_metrics: Optional[Dict[str, Any]],
    camera_metrics: Optional[Dict[str, Any]],
    composite_score: float,
) -> str:
    parts = []

    text_feedback = text_eval.get("feedback") or text_eval.get("reasoning", "")
    if text_feedback:
        parts.append(text_feedback)

    if voice_metrics:
        fluency = voice_metrics.get("fluency_score", 0)
        filler_count = voice_metrics.get("filler_word_count", 0)
        wpm = voice_metrics.get("words_per_minute", 0)

        if fluency < 5:
            parts.append(
                f"Your speaking fluency needs work — {filler_count} filler words detected "
                f"and pace was {wpm:.0f} WPM. Practice speaking more smoothly."
            )
        elif fluency < 7:
            parts.append(
                f"Decent verbal delivery ({wpm:.0f} WPM) but try reducing filler words ({filler_count} detected)."
            )
        else:
            parts.append("Strong verbal delivery with good fluency and pacing.")

    if camera_metrics:
        attention = camera_metrics.get("attentionScore", 0)
        presence = camera_metrics.get("presenceScore", 0)

        if attention < 0.5:
            parts.append(
                "You appeared distracted during the interview. Maintain eye contact with the camera."
            )
        elif attention < 0.7:
            parts.append(
                "Try to maintain more consistent eye contact with the camera."
            )

        if presence < 0.7:
            parts.append("Make sure you stay visible on camera throughout the interview.")

        multi_face = camera_metrics.get("multipleFaceCount", 0) or 0
        if multi_face > 2:
            parts.append(
                "Multiple people were detected on camera. Ensure you are in a private setting."
            )

    return " ".join(parts)


def _identify_improvement_areas(
    text_eval: Dict[str, Any],
    voice_metrics: Optional[Dict[str, Any]],
    camera_metrics: Optional[Dict[str, Any]],
) -> List[str]:
    areas = []

    text_weak = text_eval.get("weak_areas", []) or text_eval.get("gaps", [])
    areas.extend(text_weak[:3])

    if voice_metrics:
        if voice_metrics.get("fluency_score", 10) < 6:
            areas.append("Reduce filler words and improve speaking fluency")
        if voice_metrics.get("words_per_minute", 140) > 180:
            areas.append("Slow down your speaking pace for better clarity")
        elif voice_metrics.get("words_per_minute", 140) < 100:
            areas.append("Increase speaking pace — you sound hesitant")
        if voice_metrics.get("pause_count", 0) >= 3:
            areas.append("Reduce long pauses between thoughts")

    if camera_metrics:
        if (camera_metrics.get("attentionScore", 1) or 1) < 0.6:
            areas.append("Maintain eye contact with the camera")
        if (camera_metrics.get("distractionCount", 0) or 0) > 3:
            areas.append("Minimize distractions — stay focused on the screen")
        if (camera_metrics.get("multipleFaceCount", 0) or 0) > 2:
            areas.append("Ensure you are alone in a quiet environment during the interview")
        if (camera_metrics.get("presenceScore", 1) or 1) < 0.5:
            areas.append("Stay visible on camera — you were away from the screen too often")

    return areas[:6]
