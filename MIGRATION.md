# Migration to Volume-Based Model Storage

## Changes Made

This update optimizes the vast.ai GPU server deployment by switching from **baked-in models** to **persistent volume storage**.

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Model storage** | Baked into Docker image | Persistent `/data` volume |
| **Image size** | 8GB+ | 2-3GB |
| **Build time** | 15-20 min | 3-5 min |
| **First launch** | Instant (models in image) | 10-15 min (one-time download) |
| **Restart** | Slow (re-pull 8GB image) | Fast (models in volume) |
| **Stop/Start** | 10-15 min | 1-2 min ⚡ |
| **Storage cost** | $0 | ~$5/month |

## Files Modified

### 1. [Dockerfile](Dockerfile)
**Change:** Removed `RUN python download_models.py` from build step

**Before:**
```dockerfile
COPY download_models.py .
RUN python download_models.py  # ❌ Bakes models into image
COPY server.py .
```

**After:**
```dockerfile
COPY download_models.py .
COPY server.py .
# Models downloaded at runtime to /data volume ✅
```

### 2. [download_models.py](download_models.py)
**Changes:**
- Set `MODELS_DIR=/data/models` (volume mount point)
- Configure cache dirs: `HF_HOME`, `TRANSFORMERS_CACHE`, `TORCH_HOME`
- Check if models already exist before downloading
- Exit with error code if download fails

**Key logic:**
```python
if tts_cache.exists() and any(tts_cache.glob("*chatterbox*")):
    print("✅ Model found in volume, skipping download")
else:
    print("🔄 Downloading to volume...")
```

### 3. [server.py](server.py)
**Changes:**
- Import `subprocess` and `Path`
- Set `MODELS_DIR=/data/models` and cache env vars
- Call `download_models.py` in `startup_load_models()`
- Models loaded from volume cache instead of image

**Key logic:**
```python
@app.on_event("startup")
async def startup_load_models():
    # Run download_models.py to ensure models exist
    subprocess.run([sys.executable, "download_models.py"], check=True)
    
    # Load models from /data/models cache
    load_tts_model()
    load_whisper_model()
```

### 4. [README.md](README.md)
**Changes:**
- Added "Volume-Based Storage" architecture section
- Added volume setup instructions (GUI + CLI)
- Added "How Runtime Model Loading Works" flowcharts
- Added cost optimization breakdown
- Added troubleshooting for volumes
- Updated API reference

### 5. [DEPLOYMENT.md](DEPLOYMENT.md) *(New)*
Quick reference guide covering:
- Volume setup steps
- First launch vs subsequent launches
- Cost comparison table
- Common commands
- Troubleshooting tips

## Volume Configuration

### Vast.ai Template Settings

```yaml
Disk Space:
  ☑ Add recommended volume settings
  Volume size: 25 GB
  Mount path: /data
```

### CLI Command

```bash
vastai create instance <offer_id> \
  --image your-registry/gpu-server:latest \
  --env '-v V.<volume_id>:/data' \
  --disk 15
```

## Why This Change?

### Problem with Baked-in Models
1. **Slow image builds** (15+ min to download 15GB models)
2. **Slow pushes** (8GB image to registry)
3. **Slow pulls** on vast.ai (download 8GB every time)
4. **Slow stop/start** (instance management is slow)
5. **Not cost-effective** for frequent restarts

### Benefits of Volume Storage
1. **Fast image builds** (no model downloads)
2. **Fast deploys** (2-3GB image)
3. **Fast restarts** (models already on instance)
4. **One-time download** (models persist in volume)
5. **Cost-effective** (~$5/month vs bandwidth costs)

## Migration Steps

If you have existing instances running the old image:

1. **Build and push new image:**
   ```bash
   cd gpu-server
   docker build -t your-registry/gpu-server:v2 .
   docker push your-registry/gpu-server:v2
   ```

2. **Update vast.ai template:**
   - Edit template
   - Change image to `:v2`
   - Enable volume (25GB at `/data`)
   - Save

3. **Stop old instances:**
   ```bash
   vastai stop instance <instance_id>
   ```

4. **Launch new instance with volume:**
   - Use updated template
   - First launch will download models (10-15 min)
   - Subsequent launches are fast (1-2 min)

5. **Destroy old instances** (optional):
   ```bash
   vastai destroy instance <old_instance_id>
   ```

## Testing

### 1. Check volume mount
```bash
ssh -p <port> root@<ip>
df -h | grep /data
```

Expected: `/data` mounted with 25GB capacity

### 2. Check models downloaded
```bash
ls -lh /data/models/huggingface/hub/
```

Expected: Directories containing `chatterbox` and `whisper` models

### 3. Test API
```bash
curl http://<ip>:8000/health
```

Expected:
```json
{
  "status": "ok",
  "models": {"tts": true, "whisper": true}
}
```

## Rollback Plan

If issues arise, rollback to old approach:

1. Update Dockerfile:
   ```dockerfile
   COPY download_models.py .
   RUN python download_models.py
   COPY server.py .
   ```

2. Rebuild and push

3. Update template (remove volume requirement)

## Cost Analysis

### Scenario: 10 restarts per month

**Without volume:**
- Image download: 8GB × 10 = 80GB bandwidth
- Time wasted: 15 min × 10 = 150 min
- Cost: Bandwidth charges + compute time

**With volume:**
- Volume storage: 25GB × $0.20/GB = $5/month
- Time saved: 135 minutes
- One-time download: First launch only

**Winner:** Volume storage (significant time savings for minimal cost)

## Support

- [Vast.ai Volumes Docs](https://docs.vast.ai/documentation/instances/storage/volumes)
- [Vast.ai Support Discord](https://discord.gg/vast)
- Email: contact@vast.ai
