"""
Download models to /data volume at runtime.
Models persist across instance stop/start cycles via vast.ai volumes.
"""

import os
import sys
from pathlib import Path

# Volume mount point - vast.ai mounts volumes at /data by default
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/data/models"))
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Set cache directories for HuggingFace and other libraries
os.environ["HF_HOME"] = str(MODELS_DIR / "huggingface")
os.environ["TRANSFORMERS_CACHE"] = str(MODELS_DIR / "huggingface")
os.environ["TORCH_HOME"] = str(MODELS_DIR / "torch")

print(f"📁 Models directory: {MODELS_DIR}")

# Check if models already exist in volume
tts_cache = MODELS_DIR / "huggingface" / "hub"
whisper_cache = MODELS_DIR / "huggingface" / "hub"

print("📥 Checking/Downloading Chatterbox TTS model...")
try:
    from chatterbox.tts import ChatterboxTTS
    
    if tts_cache.exists() and any(tts_cache.glob("*chatterbox*")):
        print("✅ Chatterbox TTS model found in volume, skipping download")
    else:
        print("🔄 Downloading Chatterbox TTS model to volume...")
        model = ChatterboxTTS.from_pretrained(device="cpu")
        del model
        print("✅ Chatterbox TTS model downloaded to volume")
except Exception as e:
    print(f"⚠️ Chatterbox TTS download failed: {e}")
    sys.exit(1)

print("📥 Checking/Downloading faster-whisper large-v3 model...")
try:
    from faster_whisper import WhisperModel
    
    if whisper_cache.exists() and any(whisper_cache.glob("*whisper*")):
        print("✅ faster-whisper model found in volume, skipping download")
    else:
        print("🔄 Downloading faster-whisper large-v3 model to volume...")
        # This will download the CTranslate2 model from HuggingFace
        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        del model
        print("✅ faster-whisper large-v3 model downloaded to volume")
except Exception as e:
    print(f"⚠️ faster-whisper download failed: {e}")
    sys.exit(1)

print("🎉 Model check/download complete!")
