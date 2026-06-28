"""
Voice Analysis Service

Analyzes audio characteristics beyond transcription to produce
fluency and confidence metrics for the interview evaluation system.

Metrics produced:
- Filler word detection (um, uh, like, you know, basically)
- Speaking pace (words per minute)
- Pause analysis (long pauses from Whisper segment timestamps)
- Composite voice score (1-10)
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

FILLER_PATTERNS = [
    r"\bum\b",
    r"\buh\b",
    r"\bumm\b",
    r"\buhh\b",
    r"\blike\b(?=\s*,|\s+you\s+know|\s+basically)",
    r"\byou\s+know\b",
    r"\bbasically\b",
    r"\bactually\b",
    r"\bso+\b(?=\s*,)",
    r"\bi\s+mean\b",
    r"\bkind\s+of\b",
    r"\bsort\s+of\b",
]

IDEAL_WPM_RANGE = (120, 160)
LONG_PAUSE_THRESHOLD_SECONDS = 3.0


def analyze_voice(
    transcript: str,
    audio_duration_seconds: float,
    segments: Optional[List[Dict[str, Any]]] = None,
    whisper_confidence: float = 0.0,
) -> Dict[str, Any]:
    """
    Analyze voice characteristics from transcript and audio timing data.

    Args:
        transcript: The transcribed text from speech-to-text
        audio_duration_seconds: Total duration of the audio in seconds
        segments: Optional list of Whisper segment dicts with 'start', 'end', 'text' keys
        whisper_confidence: Average confidence score from Whisper (0-1)

    Returns:
        Voice metrics dictionary with individual scores and composite voice_score
    """
    if not transcript or not transcript.strip():
        return _empty_metrics()

    transcript_clean = transcript.strip()
    words = transcript_clean.split()
    word_count = len(words)

    filler_words, filler_count = _detect_filler_words(transcript_clean)
    wpm = _calculate_wpm(word_count, audio_duration_seconds)
    pause_count, longest_pause = _analyze_pauses(segments)
    fluency_score = _calculate_fluency_score(
        filler_count, word_count, wpm, pause_count, longest_pause
    )
    voice_score = _calculate_composite_score(fluency_score, whisper_confidence)

    return {
        "filler_word_count": filler_count,
        "filler_words_detected": filler_words,
        "words_per_minute": round(wpm, 1),
        "word_count": word_count,
        "audio_duration_seconds": round(audio_duration_seconds, 1),
        "pause_count": pause_count,
        "longest_pause_seconds": round(longest_pause, 1),
        "fluency_score": round(fluency_score, 1),
        "confidence_score": round(whisper_confidence, 2),
        "voice_score": round(voice_score, 1),
    }


def _empty_metrics() -> Dict[str, Any]:
    return {
        "filler_word_count": 0,
        "filler_words_detected": [],
        "words_per_minute": 0.0,
        "word_count": 0,
        "audio_duration_seconds": 0.0,
        "pause_count": 0,
        "longest_pause_seconds": 0.0,
        "fluency_score": 0.0,
        "confidence_score": 0.0,
        "voice_score": 0.0,
    }


def _detect_filler_words(transcript: str) -> Tuple[List[str], int]:
    text_lower = transcript.lower()
    detected = []
    total_count = 0

    for pattern in FILLER_PATTERNS:
        matches = re.findall(pattern, text_lower)
        if matches:
            total_count += len(matches)
            label = re.sub(r"\\b|\\s\+|\(\?=.*\)", "", pattern).strip()
            detected.append(label)

    return detected, total_count


def _calculate_wpm(word_count: int, duration_seconds: float) -> float:
    if duration_seconds <= 0:
        return 0.0
    return (word_count / duration_seconds) * 60.0


def _analyze_pauses(
    segments: Optional[List[Dict[str, Any]]],
) -> Tuple[int, float]:
    if not segments or len(segments) < 2:
        return 0, 0.0

    pause_count = 0
    longest_pause = 0.0

    for i in range(1, len(segments)):
        prev_end = segments[i - 1].get("end", 0)
        curr_start = segments[i].get("start", 0)
        gap = curr_start - prev_end

        if gap >= LONG_PAUSE_THRESHOLD_SECONDS:
            pause_count += 1
            longest_pause = max(longest_pause, gap)

    return pause_count, longest_pause


def _calculate_fluency_score(
    filler_count: int,
    word_count: int,
    wpm: float,
    pause_count: int,
    longest_pause: float,
) -> float:
    score = 10.0

    if word_count > 0:
        filler_ratio = filler_count / word_count
        if filler_ratio > 0.08:
            score -= 3.0
        elif filler_ratio > 0.05:
            score -= 2.0
        elif filler_ratio > 0.02:
            score -= 1.0

    if wpm < IDEAL_WPM_RANGE[0]:
        deviation = (IDEAL_WPM_RANGE[0] - wpm) / IDEAL_WPM_RANGE[0]
        score -= min(2.0, deviation * 4.0)
    elif wpm > IDEAL_WPM_RANGE[1]:
        deviation = (wpm - IDEAL_WPM_RANGE[1]) / IDEAL_WPM_RANGE[1]
        score -= min(2.0, deviation * 4.0)

    score -= min(2.0, pause_count * 0.5)

    if longest_pause > 8.0:
        score -= 1.5
    elif longest_pause > 5.0:
        score -= 1.0

    return max(1.0, min(10.0, score))


def _calculate_composite_score(fluency_score: float, whisper_confidence: float) -> float:
    confidence_score_10 = whisper_confidence * 10.0
    composite = (fluency_score * 0.7) + (confidence_score_10 * 0.3)
    return max(1.0, min(10.0, composite))
