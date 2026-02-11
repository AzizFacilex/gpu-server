# Architecture Overview

## Volume-Based Model Storage

```
┌─────────────────────────────────────────────────────────────────┐
│                     Vast.ai GPU Instance                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │               Docker Container                            │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │         FastAPI Server (server.py)                 │  │  │
│  │  │                                                     │  │  │
│  │  │  Startup:                                           │  │  │
│  │  │  1. Run download_models.py                         │  │  │
│  │  │  2. Load models from /data/models/                 │  │  │
│  │  │  3. Start API endpoints                            │  │  │
│  │  └─────────────────┬──────────────────────────────────┘  │  │
│  │                     │ reads from                          │  │
│  │                     ↓                                      │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │         Volume Mount: /data                         │ │  │
│  │  │  ┌──────────────────────────────────────────────┐  │ │  │
│  │  │  │  /data/models/                                │  │ │  │
│  │  │  │    └─ huggingface/                            │  │ │  │
│  │  │  │         └─ hub/                                │  │ │  │
│  │  │  │              ├─ chatterbox-tts (8GB)          │  │ │  │
│  │  │  │              └─ faster-whisper (6GB)          │  │ │  │
│  │  │  └──────────────────────────────────────────────┘  │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                   ↕                              │
│                    Volume persists across:                       │
│                    • Stop/Start                                  │
│                    • Container restart                           │
│                    • Image updates                               │
└─────────────────────────────────────────────────────────────────┘
```

## Launch Flow

### First Launch (One-time: 10-15 min)

```
┌─────────────┐
│ Start       │
│ Instance    │
└──────┬──────┘
       ↓
┌─────────────────────┐
│ Mount /data volume  │
│ (empty)             │
└──────┬──────────────┘
       ↓
┌──────────────────────────┐
│ Run download_models.py   │
└──────┬───────────────────┘
       ↓
┌───────────────────────────┐      ┌────────────────────┐
│ Check /data/models/       │ ───> │ NOT FOUND          │
└──────┬────────────────────┘      └────────┬───────────┘
       │                                      │
       │              ┌───────────────────────┘
       ↓              ↓
┌──────────────────────────────────────┐
│ Download models to /data/models/     │
│ • Chatterbox TTS: ~8GB               │
│ • faster-whisper: ~6GB               │
│ Time: ~10-15 minutes                 │
└──────┬───────────────────────────────┘
       ↓
┌──────────────────────────┐
│ Load models to GPU       │
└──────┬───────────────────┘
       ↓
┌──────────────────────────┐
│ API Ready ✅             │
└──────────────────────────┘
```

### Subsequent Launches (Fast: 1-2 min)

```
┌─────────────┐
│ Start       │
│ Instance    │
└──────┬──────┘
       ↓
┌─────────────────────┐
│ Mount /data volume  │
│ (has models)        │
└──────┬──────────────┘
       ↓
┌──────────────────────────┐
│ Run download_models.py   │
└──────┬───────────────────┘
       ↓
┌───────────────────────────┐      ┌────────────────────┐
│ Check /data/models/       │ ───> │ FOUND ✅           │
└──────┬────────────────────┘      └────────┬───────────┘
       │                                      │
       │              ┌───────────────────────┘
       ↓              ↓
┌──────────────────────────────────────┐
│ Skip download (models exist)         │
│ Time: ~0 seconds                     │
└──────┬───────────────────────────────┘
       ↓
┌──────────────────────────┐
│ Load models to GPU       │
└──────┬───────────────────┘
       ↓
┌──────────────────────────┐
│ API Ready ✅             │
│ Time: 1-2 minutes total  │
└──────────────────────────┘
```

## Request Flow

```
Backend Worker
    │
    │ 1. acquire GPU instance
    ↓
┌───────────────┐
│ Vast.ai API   │
└───────┬───────┘
        │ 2. start instance (if stopped)
        ↓
┌────────────────────┐
│ GPU Instance       │
│ (models in volume) │
└────────┬───────────┘
         │ 3. HTTP POST /tts
         ↓
┌─────────────────────┐
│ FastAPI Server      │
│ • Load from volume  │
│ • Run TTS           │
│ • Return audio      │
└────────┬────────────┘
         │ 4. audio bytes
         ↓
Backend Worker
    │
    │ 5. upload to R2
    │ 6. stop instance (volume persists)
    ↓
Done ✅
```

## Cost Comparison

### Without Volume (Old)

```
┌─────────────┐
│ Start       │
│ Instance    │
└──────┬──────┘
       ↓
┌──────────────────────┐
│ Pull Docker Image    │
│ Size: 8GB            │
│ Time: 10-15 min      │ ← SLOW
│ Cost: Bandwidth      │
└──────┬───────────────┘
       ↓
┌──────────────────────┐
│ API Ready            │
└──────────────────────┘
```

**Every restart = 10-15 min + bandwidth cost**

### With Volume (New)

```
┌─────────────┐
│ Start       │
│ Instance    │
└──────┬──────┘
       ↓
┌──────────────────────┐
│ Pull Docker Image    │
│ Size: 2-3GB          │ ← SMALLER
│ Time: 2-3 min        │ ← FASTER
│ Cost: Minimal        │
└──────┬───────────────┘
       ↓
┌──────────────────────┐
│ Load from Volume     │
│ Time: 1-2 min        │ ← FAST
│ Cost: $5/month       │ ← FIXED
└──────┬───────────────┘
       ↓
┌──────────────────────┐
│ API Ready            │
└──────────────────────┘
```

**Every restart = 1-2 min + fixed $5/month**

## Environment Variables

```
Container startup
    ↓
Set env vars:
    • MODELS_DIR=/data/models
    • HF_HOME=/data/models/huggingface
    • TRANSFORMERS_CACHE=/data/models/huggingface
    • TORCH_HOME=/data/models/torch
    ↓
All downloads go to /data volume
    ↓
Persist across restarts ✅
```

## Key Advantages

```
┌─────────────────────────────┐
│ Lightweight Image           │ → Fast build, push, pull
├─────────────────────────────┤
│ Persistent Volume           │ → No re-download
├─────────────────────────────┤
│ Fast Restart                │ → 1-2 min vs 10-15 min
├─────────────────────────────┤
│ Cost-Effective              │ → Fixed $5/month storage
├─────────────────────────────┤
│ Scalable                    │ → Easy to add more models
└─────────────────────────────┘
```
