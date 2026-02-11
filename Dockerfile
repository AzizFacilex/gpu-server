# # GPU Server Dockerfile for Vast.ai
# # Runs Chatterbox TTS (text-to-speech) and faster-whisper (captions/transcription)
# #
# # Strategy: Lightweight image with runtime model downloads to persistent volume.
# # Models are downloaded on first run to /data volume (default vast.ai mount point).
# # Volume persists across instance stop/start, eliminating re-download overhead.

# # FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
# FROM vastai/base-image:cuda-13.1.0-auto
# # Prevent interactive prompts during build
# ENV DEBIAN_FRONTEND=noninteractive
# ENV PYTHONUNBUFFERED=1
# ARG HF_TOKEN
# ENV HUGGINGFACE_HUB_TOKEN=$HF_TOKEN
# # System dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     python3.11 \
#     python3.11-venv \
#     python3-pip \
#     ffmpeg \
#     libsndfile1 \
#     git \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# # Make python3.11 the default
# RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
#     && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# WORKDIR /app

# # Install Python dependencies
# COPY requirements.txt .
# RUN pip install --no-cache-dir --upgrade pip && \
#     pip install --no-cache-dir -r requirements.txt

# # Copy application code (models will be downloaded at runtime to /data volume)
# COPY download_models.py .
# COPY server.py .

# # Health check
# HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
#     CMD curl -f http://localhost:8000/health || exit 1

# EXPOSE 8000

# # Run with uvicorn
# CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
FROM vastai/base-image:cuda-12.8.1-auto
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/data/hf-cache
ARG HF_TOKEN
ENV HUGGINGFACE_HUB_TOKEN=$HF_TOKEN

WORKDIR /app

# System deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps (already has Python)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY download_models.py .
COPY server.py .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]