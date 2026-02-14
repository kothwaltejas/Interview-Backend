"""
Speech-to-Text Service using faster-whisper
Provides LOCAL, FREE speech recognition for the interview system.

Architecture Notes:
- This is an INTERFACE LAYER, not core logic
- The service is modular and can be swapped with any STT provider
- Optimized for CPU usage (no GPU required)
- Returns clean text without touching interview logic
"""

import os
import io
import logging
import tempfile
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy load faster-whisper to avoid import errors if not installed
_whisper_model = None
_model_size = "base"  # Options: tiny, base, small, medium, large-v2


def get_whisper_model():
    """
    Lazy-load the Whisper model on first use.
    This prevents slow startup times and allows graceful fallback.
    
    Model sizes (pick based on your hardware):
    - tiny: ~39MB, fastest, lowest accuracy
    - base: ~74MB, good balance (RECOMMENDED for CPU)
    - small: ~244MB, better accuracy, slower
    - medium: ~769MB, high accuracy, requires decent RAM
    - large-v2: ~1.5GB, best accuracy, slow on CPU
    """
    global _whisper_model
    
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            
            logger.info(f"🎤 Loading Whisper model: {_model_size}")
            
            # Use CPU with int8 quantization for faster inference
            # compute_type options: int8 (fastest), float16 (GPU), float32 (best quality)
            _whisper_model = WhisperModel(
                _model_size,
                device="cpu",  # Use "cuda" if you have GPU
                compute_type="int8",  # Fastest for CPU
                cpu_threads=4,  # Adjust based on your CPU
                num_workers=1  # Single worker for consistent results
            )
            
            logger.info(f"✅ Whisper model loaded successfully")
            
        except ImportError:
            logger.error("❌ faster-whisper not installed. Run: pip install faster-whisper")
            raise ImportError("faster-whisper is required for STT. Install with: pip install faster-whisper")
        except Exception as e:
            logger.error(f"❌ Failed to load Whisper model: {e}")
            raise
    
    return _whisper_model


def convert_audio_to_wav_16k(audio_bytes: bytes, original_format: str = "webm") -> bytes:
    """
    Convert audio to WAV format (16kHz, mono) required by Whisper.
    Uses ffmpeg subprocess which is most reliable for browser-recorded webm.
    
    Why 16kHz mono?
    - Whisper was trained on 16kHz audio
    - Mono reduces file size without losing speech quality
    - Consistent format prevents transcription errors
    
    Args:
        audio_bytes: Raw audio data from frontend
        original_format: Source format (webm, mp3, etc.)
    
    Returns:
        WAV bytes at 16kHz mono
    """
    input_tmp_path = None
    output_tmp_path = None
    
    logger.info(f"🎵 Converting audio: {len(audio_bytes)} bytes, format: {original_format}")
    
    # Debug: Log first few bytes to check file signature
    if len(audio_bytes) > 10:
        header_hex = ' '.join(f'{b:02x}' for b in audio_bytes[:20])
        logger.info(f"🔍 Audio header (hex): {header_hex}")
    
    try:
        import subprocess
        import shutil
        
        # Check if ffmpeg is available
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            logger.warning("ffmpeg not found in PATH, trying fallbacks...")
            return _convert_with_fallbacks(audio_bytes, original_format)
        
        # Write input to temp file
        suffix = f".{original_format}" if original_format else ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_input:
            tmp_input.write(audio_bytes)
            input_tmp_path = tmp_input.name
        
        # Create output temp file path
        output_tmp_path = tempfile.mktemp(suffix='.wav')
        
        # Use ffmpeg to convert - most reliable for browser webm
        # -y: overwrite output
        # -i: input file
        # -ar 16000: sample rate 16kHz
        # -ac 1: mono channel
        # -acodec pcm_s16le: 16-bit PCM WAV
        # -f wav: output format
        cmd = [
            ffmpeg_path,
            '-y',                    # Overwrite output
            '-loglevel', 'error',    # Only show errors
            '-i', input_tmp_path,    # Input file
            '-ar', '16000',          # 16kHz sample rate
            '-ac', '1',              # Mono
            '-acodec', 'pcm_s16le',  # 16-bit PCM
            '-f', 'wav',             # WAV format
            output_tmp_path          # Output file
        ]
        
        logger.info(f"🎵 Converting audio with ffmpeg: {len(audio_bytes)} bytes")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30  # 30 second timeout
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='ignore')
            logger.warning(f"ffmpeg conversion failed: {error_msg}")
            return _convert_with_fallbacks(audio_bytes, original_format, input_tmp_path)
        
        # Read the converted WAV file
        with open(output_tmp_path, 'rb') as f:
            wav_bytes = f.read()
        
        logger.info(f"✅ Audio converted: {len(audio_bytes)} bytes -> {len(wav_bytes)} bytes WAV")
        return wav_bytes
        
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timed out, trying fallbacks...")
        return _convert_with_fallbacks(audio_bytes, original_format, input_tmp_path)
    except Exception as e:
        logger.warning(f"ffmpeg conversion error: {e}, trying fallbacks...")
        return _convert_with_fallbacks(audio_bytes, original_format, input_tmp_path)
    finally:
        # Clean up temp files
        for path in [input_tmp_path, output_tmp_path]:
            if path:
                try:
                    os.unlink(path)
                except:
                    pass


def _convert_with_fallbacks(audio_bytes: bytes, original_format: str, input_tmp_path: str = None) -> bytes:
    """Try multiple fallback methods to convert audio."""
    
    # Try PyAV first
    try:
        return _convert_with_pyav(audio_bytes, original_format, input_tmp_path)
    except Exception as e:
        logger.warning(f"PyAV fallback failed: {e}")
    
    # Try pydub
    try:
        return _convert_with_pydub(audio_bytes, original_format, input_tmp_path)
    except Exception as e:
        logger.warning(f"Pydub fallback failed: {e}")
    
    # Last resort - return original and hope Whisper can handle it
    logger.warning("All conversion methods failed - returning original audio")
    return audio_bytes


def _convert_with_pyav(audio_bytes: bytes, original_format: str, input_tmp_path: str = None) -> bytes:
    """Convert audio using PyAV library."""
    output_tmp_path = None
    should_cleanup_input = False
    
    try:
        import av
        import numpy as np
        import wave
        
        # Write input to temp file if not already created
        if not input_tmp_path:
            suffix = f".{original_format}" if original_format else ".webm"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_input:
                tmp_input.write(audio_bytes)
                input_tmp_path = tmp_input.name
                should_cleanup_input = True
        
        # Open with PyAV and decode
        container = av.open(input_tmp_path)
        audio_stream = container.streams.audio[0]
        
        # Collect all audio frames
        samples = []
        for frame in container.decode(audio_stream):
            frame_resampled = frame.reformat(format='s16', layout='mono', rate=16000)
            arr = frame_resampled.to_ndarray()
            samples.append(arr.flatten())
        
        container.close()
        
        if not samples:
            raise ValueError("No audio samples decoded")
        
        # Concatenate all samples
        audio_data = np.concatenate(samples)
        
        # Write to WAV
        output_tmp_path = tempfile.mktemp(suffix='.wav')
        with wave.open(output_tmp_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_data.tobytes())
        
        with open(output_tmp_path, 'rb') as f:
            return f.read()
            
    finally:
        if should_cleanup_input and input_tmp_path:
            try:
                os.unlink(input_tmp_path)
            except:
                pass
        if output_tmp_path:
            try:
                os.unlink(output_tmp_path)
            except:
                pass


def _convert_with_pydub(audio_bytes: bytes, original_format: str, input_tmp_path: str = None) -> bytes:
    """Fallback audio conversion using pydub/ffmpeg."""
    try:
        from pydub import AudioSegment
        
        # Create temp file if not already created
        if not input_tmp_path:
            suffix = f".{original_format}" if original_format else ".webm"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_input:
                tmp_input.write(audio_bytes)
                input_tmp_path = tmp_input.name
        
        # Try loading with format hint
        try:
            audio = AudioSegment.from_file(input_tmp_path, format=original_format)
        except Exception:
            # Try without format hint (auto-detect)
            audio = AudioSegment.from_file(input_tmp_path)
        
        # Convert to Whisper's preferred format
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)
        
        # Export as WAV
        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        
        return wav_buffer.read()
        
    except Exception as e:
        logger.warning(f"Pydub conversion also failed: {e} - returning original")
        return audio_bytes
    finally:
        if input_tmp_path:
            try:
                os.unlink(input_tmp_path)
            except:
                pass


def _filter_hallucinations(transcript: str) -> str:
    """
    Detect and filter Whisper hallucinations.
    
    Common hallucination patterns:
    - Repeated phrases: "I'm sorry, I'm sorry, I'm sorry..."
    - Thank you repeated: "Thank you for watching, thank you..."
    - Subscribe/like patterns from YouTube
    - Very short repeated words
    
    Returns filtered transcript or empty string if hallucination detected.
    """
    import re
    
    if not transcript:
        return ""
    
    transcript = transcript.strip()
    
    # Pattern 1: Same short phrase repeated 3+ times
    # Split into words and look for repeating patterns
    words = transcript.split()
    
    # If less than 3 words, probably not a hallucination
    if len(words) < 6:
        return transcript
    
    # Check for repeated bigrams/trigrams (common hallucination pattern)
    # "I'm sorry" repeated = ["I'm", "sorry", "I'm", "sorry", ...]
    bigrams = [' '.join(words[i:i+2]) for i in range(len(words)-1)]
    trigrams = [' '.join(words[i:i+3]) for i in range(len(words)-2)]
    
    # Count occurrences
    for gram_list, threshold in [(bigrams, 5), (trigrams, 4)]:
        if gram_list:
            most_common_gram = max(set(gram_list), key=gram_list.count)
            count = gram_list.count(most_common_gram)
            ratio = count / len(gram_list)
            
            # If any gram repeats more than threshold times with high ratio, it's hallucination
            if count >= threshold and ratio > 0.4:
                logger.warning(f"🚫 Detected hallucination pattern: '{most_common_gram}' repeated {count}x ({ratio:.0%})")
                return ""
    
    # Pattern 2: Known hallucination phrases that shouldn't appear in interviews
    hallucination_phrases = [
        r"thank you for watching",
        r"subscribe.*channel",
        r"like.*video",
        r"comment below",
        r"don't forget to",
        r"see you next time",
        r"(i'm sorry[,.\s]*){3,}",  # "I'm sorry" 3+ times
        r"(thank you[,.\s]*){3,}",  # "Thank you" 3+ times
        r"(yes[,.\s]*){5,}",        # "yes" 5+ times
        r"(no[,.\s]*){5,}",         # "no" 5+ times
        r"(um[,.\s]*){5,}",         # "um" 5+ times
        r"(uh[,.\s]*){5,}",         # "uh" 5+ times
    ]
    
    for pattern in hallucination_phrases:
        if re.search(pattern, transcript.lower()):
            logger.warning(f"🚫 Detected hallucination phrase matching: {pattern}")
            return ""
    
    return transcript


def transcribe_audio(
    audio_bytes: bytes,
    audio_format: str = "webm",
    language: str = "en"
) -> Tuple[str, float]:
    """
    Transcribe audio to text using faster-whisper.
    
    This function is the ONLY entry point for STT in the application.
    It handles all preprocessing and returns clean text.
    
    Args:
        audio_bytes: Raw audio data from the frontend
        audio_format: Format of the audio (webm, wav, mp3)
        language: Language code (default: English)
    
    Returns:
        Tuple of (transcribed_text, confidence_score)
        
    Design Decisions:
    - We use a temp file because faster-whisper doesn't support BytesIO
    - Audio conversion is optional but improves accuracy
    - We return confidence for potential UI feedback
    """
    
    if not audio_bytes:
        logger.warning("Empty audio received")
        return "", 0.0
    
    try:
        model = get_whisper_model()
        
        # Convert audio to optimal format for Whisper
        processed_audio = convert_audio_to_wav_16k(audio_bytes, audio_format)
        
        # Write to temp file (faster-whisper requires file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(processed_audio)
            tmp_path = tmp_file.name
        
        try:
            # First try with VAD filter (removes silence for better accuracy)
            segments, info = model.transcribe(
                tmp_path,
                language=language,
                beam_size=5,  # Balance between speed and accuracy
                best_of=5,  # Number of candidates to consider
                temperature=0.0,  # Deterministic output (no randomness)
                condition_on_previous_text=False,  # Each segment independent
                vad_filter=True,  # Voice Activity Detection - removes silence
                vad_parameters={
                    "min_silence_duration_ms": 300,  # Reduced from 500 - more sensitive
                    "speech_pad_ms": 400,  # Increased padding around speech
                    "threshold": 0.3  # Lower threshold - more lenient VAD
                }
            )
            
            # Collect all segments into full transcript
            full_text = ""
            total_confidence = 0.0
            segment_count = 0
            
            for segment in segments:
                full_text += segment.text + " "
                # Average probability across words gives confidence
                total_confidence += segment.avg_logprob
                segment_count += 1
            
            # If VAD filtered everything, this means NO SPEECH was detected
            # Return empty string immediately - DO NOT retry without VAD
            # Retrying without VAD causes hallucinations on silence/background noise
            if segment_count == 0:
                logger.info("⚠️ VAD filtered all audio - no speech detected, returning empty")
                return "", 0.0
            
            # Calculate average confidence (logprob -> rough percentage)
            avg_confidence = 0.0
            if segment_count > 0:
                # Convert log probability to rough confidence (0-1 scale)
                avg_confidence = min(1.0, max(0.0, 1.0 + (total_confidence / segment_count)))
            
            transcript = full_text.strip()
            
            # Detect and filter Whisper hallucinations
            # Common patterns: repeated phrases, "I'm sorry", "Thank you", etc.
            transcript = _filter_hallucinations(transcript)
            
            logger.info(f"✅ Transcribed {len(transcript)} characters with confidence {avg_confidence:.2f}")
            return transcript, avg_confidence
            return transcript, avg_confidence
            
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        logger.error(f"❌ Transcription failed: {e}")
        raise


def is_stt_available() -> bool:
    """
    Check if STT service is available and properly configured.
    Useful for graceful degradation to text mode.
    """
    try:
        from faster_whisper import WhisperModel
        return True
    except ImportError:
        return False


def get_supported_languages() -> list:
    """
    Return list of supported language codes.
    Whisper supports 100+ languages, but we list common ones.
    """
    return [
        "en",  # English
        "es",  # Spanish
        "fr",  # French
        "de",  # German
        "it",  # Italian
        "pt",  # Portuguese
        "ru",  # Russian
        "ja",  # Japanese
        "ko",  # Korean
        "zh",  # Chinese
        "ar",  # Arabic
        "hi",  # Hindi
    ]
