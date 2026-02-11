# GPU Audio Server (Vast.ai)

FastAPI server optimized for Vast.ai GPU instances with **persistent volume storage**:

- **TTS** — Chatterbox Turbo (350M params, zero-shot voice cloning)
- **Captions** — faster-whisper large-v3 (word-level timestamps)
- **Volume-based storage** — Models persist across instance stop/start

## Architecture

```
Backend API (Node.js)
  ↓ enqueue job
Redis (BullMQ)
  ↓ dequeue
GPU Worker (same Node.js process)
  ↓ acquireGpuInstance()
Vast.ai API → start/stop instance
  ↓ HTTP call
GPU Server (this) → run TTS / Whisper (models from /data volume)
  ↓ return result
Worker → upload to storage → stop GPU
```

## Key Changes: Volume-Based Storage

**Old approach:**
- Models baked into Docker image at build time
- 8GB+ image size
- Slow to push/pull on vast.ai
- Long start/stop times

**New approach:**
- Lightweight Docker image (no models)
- Models downloaded at runtime to `/data` volume
- Volume persists across instance stop/start
- Fast subsequent launches (models already there)

## Vast.ai Volume Setup (Required)

### Create Volume in Template

1. Go to [cloud.vast.ai/templates](https://cloud.vast.ai/templates/)
2. Create/edit template
3. In **Disk Space** section:
   - Enable "Add recommended volume settings"
   - Volume size: **25 GB minimum**
   - Mount path: `/data` (default)
4. Save & use template

### Or via CLI

```bash
# Create volume
vastai create volume <offer_id> -s 25 -n "gpu-models"

# Launch instance with volume
vastai create instance <offer_id> \
  --image your-registry/gpu-audio-server:latest \
  --env '-v V.<volume_id>:/data' \
  --disk 15
```

## How Runtime Model Loading Works

### First Launch
1. Instance starts → volume mounted at `/data`
2. Server runs `download_models.py`
3. Checks `/data/models/` for existing models
4. Downloads if missing (~10-15 min one-time)
5. Models cached in volume
6. Server loads models into GPU memory

### Subsequent Launches (Fast ⚡)
1. Instance starts → volume mounted
2. Server runs `download_models.py`
3. **Detects models in volume** ✅
4. **Skips download**
5. Loads models into GPU (~1-2 min)

## Building the Docker Image

```bash
cd gpu-server
docker build -t your-registry/gpu-audio-server:latest .
docker push your-registry/gpu-audio-server:latest
```

**Image size:** ~2-3GB (no models baked in)

## API Reference

### POST /tts

```json
{
  "text": "Hello, this is a test of the text to speech system.",
  "audio_prompt_url": "https://example.com/reference.wav",
  "exaggeration": 0.5,
  "cfg_weight": 0.5,
  "language": "en"
}
}
```

Returns: `audio/wav` stream with headers:
- `X-Duration-Seconds`: Audio duration
- `X-Sample-Rate`: Sample rate (e.g., 24000)
- `X-Generation-Time-Ms`: Processing time

### POST /transcribe

Multipart form:
- `audio`: Audio file (wav, mp3, etc.)
- `language`: Language code (optional, auto-detect)
- `word_timestamps`: Boolean (default: true)
- `vad_filter`: Boolean (default: true)
- `beam_size`: Integer (default: 5)

Returns JSON with word-level timestamps:

```json
{
  "success": true,
  "language": "en",
  "duration_seconds": 12.5,
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 2.5,
      "text": "Hello world",
      "words": [
        {"start": 0.0, "end": 1.0, "word": "Hello", "probability": 0.99},
        {"start": 1.1, "end": 2.5, "word": "world", "probability": 0.98}
      ]
    }
  ]
}
```

## Environment Variables

- `MODELS_DIR`: Model storage path (default: `/data/models`)
- `HF_HOME`: HuggingFace cache (auto-set)
- `TRANSFORMERS_CACHE`: Transformers cache (auto-set)
- `TORCH_HOME`: PyTorch cache (auto-set)

## Cost Optimization

**Volume Storage:** ~$0.10-0.20/GB/month
- 25GB volume: **~$2.50-5/month**
- Models stay cached when instance stopped
- No re-download costs

**Instance Costs:**
- **Stop** when not in use (no GPU charges)
- **Start** when needed (models already there)
- First launch: ~10-15 min (one-time download)
- Subsequent: ~1-2 min (just load to GPU)

**Savings:** Without volume, you'd pay bandwidth + time for 15GB download on every launch. With volume, pay once and reuse forever.

## Troubleshooting

### Check volume mount
```bash
ssh -p <port> root@<instance-ip>
df -h | grep /data
ls -lh /data/models/
```

### Manually download models
```bash
python download_models.py
```

### Clear corrupted models
```bash
rm -rf /data/models/huggingface/hub/*
python download_models.py
```

### View logs
```bash
docker logs -f $(docker ps -q)
```

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tts` | Text-to-speech (JSON body) |
| `POST` | `/tts-with-ref` | TTS with uploaded reference audio |
| `POST` | `/transcribe` | Transcribe uploaded audio file |
| `POST` | `/transcribe-url` | Transcribe audio from URL |
| `GET` | `/health` | Health check + model status |

## References

- [Vast.ai Volumes Docs](https://docs.vast.ai/documentation/instances/storage/volumes)
- [Vast.ai Templates Guide](https://docs.vast.ai/documentation/templates/creating-templates)
- [Chatterbox TTS](https://huggingface.co/chatterbox)
- [faster-whisper](https://github.com/guillaumekln/faster-whisper)
