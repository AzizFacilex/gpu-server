"""
GPU Server — FastAPI endpoints for TTS (Chatterbox) and Captions (faster-whisper).

Runs on Vast.ai GPU instances. The backend worker calls these endpoints via HTTP.

Endpoints:
  POST /tts            — Text-to-speech generation with optional voice cloning
  POST /tts-with-ref   — Text-to-speech with uploaded reference audio for voice cloning
  POST /transcribe     — Audio transcription / captions with word-level timestamps
  POST /transcribe-url — Audio transcription from URL
  GET  /health         — Health check (model readiness)
"""

import io
import os
import sys
import time
import uuid
import tempfile
import logging
import subprocess
from pathlib import Path
from typing import Optional

import torch
import torchaudio
import numpy as np
import soundfile as sf
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gpu-server")

# ---------------------------------------------------------------------------
# Model Storage Configuration (Vast.ai Volume)
# ---------------------------------------------------------------------------
# Models are stored in /data volume (persistent across stop/start)
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/data/models"))
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Set cache directories for model libraries
os.environ["HF_HOME"] = str(MODELS_DIR / "huggingface")
os.environ["TRANSFORMERS_CACHE"] = str(MODELS_DIR / "huggingface")
os.environ["TORCH_HOME"] = str(MODELS_DIR / "torch")

logger.info(f"📁 Models directory: {MODELS_DIR}")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="GPU Audio Server",
    description="Chatterbox TTS + faster-whisper captions on GPU",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Global model holders (lazy-loaded on first request or at startup)
# ---------------------------------------------------------------------------
tts_model = None
whisper_model = None
models_ready = {"tts": False, "whisper": False}

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"🖥️  Device: {DEVICE} | CUDA available: {torch.cuda.is_available()}")


def load_tts_model():
    """Load Chatterbox TTS model."""
    global tts_model, models_ready
    if tts_model is not None:
        return tts_model
    logger.info("🔄 Loading Chatterbox TTS model...")
    t0 = time.time()
    from chatterbox.tts import ChatterboxTTS
    tts_model = ChatterboxTTS.from_pretrained(device=DEVICE)
    models_ready["tts"] = True
    logger.info(f"✅ TTS model loaded in {time.time() - t0:.1f}s")
    return tts_model


def load_whisper_model():
    """Load faster-whisper model."""
    global whisper_model, models_ready
    if whisper_model is not None:
        return whisper_model
    logger.info("🔄 Loading faster-whisper large-v3 model...")
    t0 = time.time()
    from faster_whisper import WhisperModel
    compute_type = "float16" if DEVICE == "cuda" else "int8"
    whisper_model = WhisperModel("large-v3", device=DEVICE, compute_type=compute_type)
    models_ready["whisper"] = True
    logger.info(f"✅ Whisper model loaded in {time.time() - t0:.1f}s")
    return whisper_model


@app.on_event("startup")
async def startup_load_models():
    """Download models to volume (if needed) and pre-load them on server startup."""
    # First, ensure models are downloaded to the volume
    logger.info("🔍 Checking if models exist in volume...")
    try:
        # Run download_models.py to check/download models
        result = subprocess.run(
            [sys.executable, "download_models.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info(f"📦 Model check output:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Model download failed:\n{e.stdout}\n{e.stderr}")
        logger.warning("⚠️ Server will continue but models may not load properly")
    
    # Now load models into memory
    try:
        load_tts_model()
    except Exception as e:
        logger.error(f"❌ Failed to load TTS model: {e}")
    try:
        load_whisper_model()
    except Exception as e:
        logger.error(f"❌ Failed to load Whisper model: {e}")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            "gpu_name": torch.cuda.get_device_name(0),
            "gpu_memory_total_mb": round(torch.cuda.get_device_properties(0).total_mem / 1e6),
            "gpu_memory_used_mb": round(torch.cuda.memory_allocated(0) / 1e6),
        }
    return {
        "status": "ok",
        "device": DEVICE,
        "models": models_ready,
        "gpu": gpu_info,
    }


# ---------------------------------------------------------------------------
# TTS — Text to Speech
# ---------------------------------------------------------------------------
class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize", max_length=10000)
    audio_prompt_url: Optional[str] = Field(None, description="URL of reference audio for voice cloning")
    exaggeration: float = Field(0.5, ge=0.0, le=1.0, description="Expressiveness (0–1)")
    cfg_weight: float = Field(0.5, ge=0.0, le=1.0, description="CFG weight (0–1)")
    language: str = Field("en", description="Language code (en, fr, es, etc.)")
    output_format: str = Field("wav", description="Output format: wav or mp3")


class TTSResponse(BaseModel):
    success: bool
    duration_seconds: float
    sample_rate: int
    generation_time_ms: int


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Generate speech from text using Chatterbox TTS Turbo.
    
    Returns the audio file as a streaming response.
    Audio is returned as WAV (or MP3 if requested).
    """
    t0 = time.time()

    try:
        model = load_tts_model()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"TTS model not available: {e}")

    try:
        # Generate audio with voice cloning
        audio_prompt_path = None

        # If a reference audio URL was provided, download it to a temp file
        if request.audio_prompt_url:
            import urllib.request
            audio_prompt_path = tempfile.mktemp(suffix=".wav")
            urllib.request.urlretrieve(request.audio_prompt_url, audio_prompt_path)

        # Generate with voice cloning if reference audio is provided
        if audio_prompt_path:
            wav = model.generate(
                request.text,
                audio_prompt_path=audio_prompt_path,
                exaggeration=request.exaggeration,
                cfg_weight=request.cfg_weight,
            )
        else:
            # Generate without voice cloning (uses default voice)
            wav = model.generate(
                request.text,
                exaggeration=request.exaggeration,
                cfg_weight=request.cfg_weight,
            )

        # Clean up temp reference file
        if audio_prompt_path and os.path.exists(audio_prompt_path):
            os.unlink(audio_prompt_path)

        # wav is a torch tensor [1, samples] at model.sr sample rate
        sample_rate = model.sr
        duration = wav.shape[-1] / sample_rate
        generation_time_ms = int((time.time() - t0) * 1000)

        logger.info(
            f"🎤 TTS generated: {duration:.1f}s audio in {generation_time_ms}ms "
            f"({len(request.text)} chars)"
        )

        # Convert to bytes
        buf = io.BytesIO()
        torchaudio.save(buf, wav.cpu(), sample_rate, format="wav")
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="audio/wav",
            headers={
                "X-Duration-Seconds": str(round(duration, 2)),
                "X-Sample-Rate": str(sample_rate),
                "X-Generation-Time-Ms": str(generation_time_ms),
            },
        )

    except Exception as e:
        logger.error(f"❌ TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


# ---------------------------------------------------------------------------
# TTS with file upload for voice reference
# ---------------------------------------------------------------------------
@app.post("/tts-with-ref")
async def text_to_speech_with_reference(
    text: str = Form(...),
    audio_prompt: UploadFile = File(...),
    exaggeration: float = Form(0.5),
    cfg_weight: float = Form(0.5),
):
    """
    Generate speech from text using a voice reference audio file upload.
    Use this when the reference audio is uploaded directly (not via URL).
    """
    t0 = time.time()

    try:
        model = load_tts_model()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"TTS model not available: {e}")

    try:
        # Save uploaded reference audio to temp file
        suffix = os.path.splitext(audio_prompt.filename or "ref.wav")[1] or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await audio_prompt.read()
            tmp.write(content)
            tmp_path = tmp.name

        wav = model.generate(
            text,
            audio_prompt_path=tmp_path,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )

        # Cleanup temp file
        os.unlink(tmp_path)

        sample_rate = model.sr
        duration = wav.shape[-1] / sample_rate
        generation_time_ms = int((time.time() - t0) * 1000)

        buf = io.BytesIO()
        torchaudio.save(buf, wav.cpu(), sample_rate, format="wav")
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="audio/wav",
            headers={
                "X-Duration-Seconds": str(round(duration, 2)),
                "X-Sample-Rate": str(sample_rate),
                "X-Generation-Time-Ms": str(generation_time_ms),
            },
        )

    except Exception as e:
        logger.error(f"❌ TTS with ref failed: {e}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


# ---------------------------------------------------------------------------
# Transcription / Captions — faster-whisper
# ---------------------------------------------------------------------------
class TranscriptionWord(BaseModel):
    start: float
    end: float
    word: str
    probability: float


class TranscriptionSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: list[TranscriptionWord]


class TranscriptionResponse(BaseModel):
    success: bool
    language: str
    language_probability: float
    duration_seconds: float
    segments: list[TranscriptionSegment]
    generation_time_ms: int


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio file to transcribe (wav, mp3, etc.)"),
    language: Optional[str] = Form(None, description="Language code (auto-detect if omitted)"),
    word_timestamps: bool = Form(True, description="Include word-level timestamps"),
    vad_filter: bool = Form(True, description="Use VAD to filter silence"),
    beam_size: int = Form(5, description="Beam size for decoding"),
):
    """
    Transcribe audio using faster-whisper (large-v3).
    
    Returns segments with word-level timestamps, perfect for caption generation.
    Supports auto language detection or explicit language code.
    """
    t0 = time.time()

    try:
        model = load_whisper_model()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Whisper model not available: {e}")

    try:
        # Save uploaded audio to temp file
        suffix = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Transcribe
        segments_gen, info = model.transcribe(
            tmp_path,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
            language=language,
        )

        # Collect segments
        segments = []
        for i, seg in enumerate(segments_gen):
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(TranscriptionWord(
                        start=round(w.start, 3),
                        end=round(w.end, 3),
                        word=w.word.strip(),
                        probability=round(w.probability, 4),
                    ))
            segments.append(TranscriptionSegment(
                id=i,
                start=round(seg.start, 3),
                end=round(seg.end, 3),
                text=seg.text.strip(),
                words=words,
            ))

        # Cleanup temp file
        os.unlink(tmp_path)

        generation_time_ms = int((time.time() - t0) * 1000)
        duration = info.duration if hasattr(info, "duration") else (
            segments[-1].end if segments else 0.0
        )

        logger.info(
            f"📝 Transcribed: {duration:.1f}s audio → {len(segments)} segments "
            f"in {generation_time_ms}ms (lang={info.language})"
        )

        return TranscriptionResponse(
            success=True,
            language=info.language,
            language_probability=round(info.language_probability, 4),
            duration_seconds=round(duration, 2),
            segments=segments,
            generation_time_ms=generation_time_ms,
        )

    except Exception as e:
        logger.error(f"❌ Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


# ---------------------------------------------------------------------------
# Transcribe from URL (no file upload needed)
# ---------------------------------------------------------------------------
class TranscribeURLRequest(BaseModel):
    audio_url: str = Field(..., description="URL of the audio file to transcribe")
    language: Optional[str] = Field(None, description="Language code (auto-detect if omitted)")
    word_timestamps: bool = Field(True, description="Include word-level timestamps")
    vad_filter: bool = Field(True, description="Use VAD to filter silence")
    beam_size: int = Field(5, description="Beam size for decoding")


@app.post("/transcribe-url", response_model=TranscriptionResponse)
async def transcribe_audio_from_url(request: TranscribeURLRequest):
    """Transcribe audio from a URL."""
    t0 = time.time()

    try:
        model = load_whisper_model()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Whisper model not available: {e}")

    try:
        import urllib.request
        tmp_path = tempfile.mktemp(suffix=".wav")
        urllib.request.urlretrieve(request.audio_url, tmp_path)

        segments_gen, info = model.transcribe(
            tmp_path,
            beam_size=request.beam_size,
            word_timestamps=request.word_timestamps,
            vad_filter=request.vad_filter,
            language=request.language,
        )

        segments = []
        for i, seg in enumerate(segments_gen):
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(TranscriptionWord(
                        start=round(w.start, 3),
                        end=round(w.end, 3),
                        word=w.word.strip(),
                        probability=round(w.probability, 4),
                    ))
            segments.append(TranscriptionSegment(
                id=i,
                start=round(seg.start, 3),
                end=round(seg.end, 3),
                text=seg.text.strip(),
                words=words,
            ))

        os.unlink(tmp_path)

        generation_time_ms = int((time.time() - t0) * 1000)
        duration = info.duration if hasattr(info, "duration") else (
            segments[-1].end if segments else 0.0
        )

        return TranscriptionResponse(
            success=True,
            language=info.language,
            language_probability=round(info.language_probability, 4),
            duration_seconds=round(duration, 2),
            segments=segments,
            generation_time_ms=generation_time_ms,
        )

    except Exception as e:
        logger.error(f"❌ URL transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
