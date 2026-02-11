# 🚀 Quick Reference Card

## Volume Setup (One-Time)

```bash
# 1. Build image
docker build -t your-registry/gpu-server:latest .
docker push your-registry/gpu-server:latest

# 2. Create volume (25GB)
vastai create volume <offer_id> -s 25 -n gpu-models

# 3. Launch with volume
vastai create instance <offer_id> \
  --image your-registry/gpu-server:latest \
  --env '-v V.<volume_id>:/data' \
  --disk 15
```

## Key Commands

```bash
# Health check
curl http://<ip>:8000/health

# Check volume
ssh -p <port> root@<ip> 'df -h | grep /data'

# View logs
ssh -p <port> root@<ip> 'docker logs -f $(docker ps -q)'

# Check models
ssh -p <port> root@<ip> 'ls -lh /data/models/huggingface/hub/'

# Restart instance
vastai stop instance <id> && vastai start instance <id>
```

## Expected Timeline

```
First Launch:  10-15 minutes (one-time download)
Restart:       1-2 minutes (models in volume) ⚡
Stop:          Instant
```

## Volume Requirements

- **Size:** 25 GB minimum
- **Mount:** `/data`
- **Cost:** ~$5/month
- **Persists:** Across stop/start/restart

## API Endpoints

```bash
# TTS
curl -X POST http://<ip>:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello"}' -o out.wav

# Transcribe
curl -X POST http://<ip>:8000/transcribe \
  -F "audio=@input.mp3" | jq .
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Volume not mounted | Check template has volume enabled |
| Models not downloading | Run `python /app/download_models.py` manually |
| Out of space | Increase volume to 50GB |
| Slow first launch | Expected (15GB download), subsequent launches fast |

## File Locations

```
/app/server.py              # FastAPI server
/app/download_models.py     # Model downloader
/data/                      # Volume mount point
/data/models/               # Model cache
/data/models/huggingface/   # HF cache
```

## Success Indicators

✅ Volume mounted at `/data` (25GB)  
✅ Models in `/data/models/huggingface/hub/`  
✅ Health endpoint returns `{"models":{"tts":true,"whisper":true}}`  
✅ Restart takes 1-2 min (not 10-15 min)  

## Cost Breakdown

| Item | Cost |
|------|------|
| Volume (25GB) | ~$5/month |
| Instance (stopped) | $0/hour |
| Instance (running) | $0.10-0.50/hour |
| Bandwidth | Minimal |

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) - Quick start
- [MIGRATION.md](MIGRATION.md) - Migration guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - Diagrams
- [README.md](README.md) - Full docs
