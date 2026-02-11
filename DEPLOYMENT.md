# Vast.ai Deployment Quick Start

## TL;DR

1. Build image: `docker build -t your-registry/gpu-server:latest . && docker push`
2. Create 25GB volume in vast.ai template (mounted at `/data`)
3. First launch: 10-15 min (models download to volume)
4. Stop instance when done (volume persists)
5. Restart: 1-2 min (models already in volume) ✅

## Volume Setup

### Via Template (Recommended)

1. Go to https://cloud.vast.ai/templates/
2. Create/edit your GPU server template
3. **Docker image:** `your-registry/gpu-server:latest`
4. **Disk Space section:**
   - ✅ Add recommended volume settings
   - Volume size: **25 GB**
   - Mount path: `/data`
5. Save & launch

### Via CLI

```bash
# Create volume
vastai create volume <offer_id> -s 25 -n gpu-models

# Launch with volume
vastai create instance <offer_id> \
  --image your-registry/gpu-server:latest \
  --env '-v V.<volume_id>:/data' \
  --disk 15
```

## What Happens

### First Launch (One-time: ~10-15 min)
```
Container starts
  ↓
download_models.py runs
  ↓
Checks /data/models/ → empty
  ↓
Downloads Chatterbox TTS (~8GB)
Downloads faster-whisper (~6GB)
  ↓
Saves to /data/models/
  ↓
Server loads models to GPU
  ↓
Ready! 🚀
```

### Subsequent Launches (Fast: ~1-2 min)
```
Container starts
  ↓
download_models.py runs
  ↓
Checks /data/models/ → models found! ✅
  ↓
Skips download
  ↓
Server loads models to GPU
  ↓
Ready! 🚀
```

## Cost Benefits

| Scenario | Without Volume | With Volume |
|----------|---------------|-------------|
| **Image size** | 8GB+ | 2-3GB |
| **First launch** | 15 min (build time) | 10-15 min (download) |
| **Stop/Start** | 15 min (re-download) | 1-2 min (cache hit) |
| **Storage cost** | $0 | ~$5/month |
| **10 restarts** | 150 min wasted | 15 min total |
| **Savings** | — | **135 min saved** |

## Commands

### Check volume mount
```bash
ssh root@<instance-ip> -p <port>
df -h | grep /data
ls -lh /data/models/
```

### Force re-download
```bash
ssh root@<instance-ip> -p <port>
rm -rf /data/models/*
docker restart $(docker ps -q)
```

### View download progress
```bash
docker logs -f $(docker ps -q)
```

## Environment Variables

Set in your backend `.env`:

```bash
VASTAI_GPU_IMAGE=your-registry/gpu-server:latest
MODELS_DIR=/data/models  # Default, can override
```

## Troubleshooting

### Models not downloading
- Check volume is mounted: `df -h | grep /data`
- Check write permissions: `touch /data/test.txt`
- Manual download: `python download_models.py`

### Out of space
- Increase volume size in template to 50GB
- Or create new larger volume and migrate

### Slow download
- First-time download is expected (15GB models)
- Subsequent launches skip download

## API Test

```bash
# Health check
curl http://<instance-ip>:8000/health

# TTS test
curl -X POST http://<instance-ip>:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from vast.ai"}' \
  -o test.wav
```

## Best Practices

✅ **DO:**
- Use volumes for model storage
- Stop instances when not in use
- Monitor volume usage periodically
- Keep volume size >= 25GB

❌ **DON'T:**
- Bake models into Docker image
- Delete volumes between jobs
- Use multiple volumes per instance
- Forget to mount volume at `/data`

## References

- [Vast.ai Volumes](https://docs.vast.ai/documentation/instances/storage/volumes)
- [Volume Pricing](https://vast.ai/pricing)
- [Template Guide](https://docs.vast.ai/documentation/templates/creating-templates)
