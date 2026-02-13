# FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
# ENV DEBIAN_FRONTEND=noninteractive
# ENV PYTHONUNBUFFERED=1
# WORKDIR /workspace
# ENV MODELS_DIR=/workspace/models
# ENV HF_HOME=/workspace/models/huggingface
# ENV TORCH_HOME=/workspace/models/torch

# # Install Python 3.11 and minimal dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     software-properties-common \
#     python3.11 \
#     python3.11-venv \
#     python3.11-dev \
#     python3-pip \
#     libsndfile1 \
#     ffmpeg \
#     curl \
#     ca-certificates \
#     && rm -rf /var/lib/apt/lists/*

# # Make python3.11 the default python
# RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
#  && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# # Upgrade pip and install build essentials
# RUN python -m pip install --upgrade pip setuptools wheel

# # ── PyTorch + torchaudio ONLY (pinned to latest available CUDA 12.1 version) ──
# # DO NOT install torchvision — it pulls in torchvision::nms operators
# # that conflict with transformers' modeling imports.
# # Versions: torch==2.5.1, torchaudio==2.5.1 (CUDA 12.1 wheels)
# RUN pip install --no-cache-dir \
#     torch==2.5.1+cu121 \
#     torchaudio==2.5.1+cu121 \
#     --index-url https://download.pytorch.org/whl/cu121

# # ── Pin transformers to the known-good version ──
# RUN pip install --no-cache-dir transformers==4.46.3

# # ── Install numpy/Cython before requirements (some deps need them at build time) ──
# RUN pip install --no-cache-dir Cython numpy

# # Install other dependencies from requirements.txt
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# # Copy app
# COPY . .

# EXPOSE 8000
# CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Stage 1: Build stage ──
# ── Stage 1: Build ──
# ── Stage 1: Build ──
# ── Stage 1: Build ──
# ── Stage 1: Build ──
# ── Stage 1: Build Stage ──
# ── Stage 1: Build Stage ──
# ── Stage 1: Build stage ──
# ── Stage 1: Build ──
# ── Stage 1: Build ──
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS build

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    build-essential libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip inside venv
RUN pip install --upgrade pip

COPY requirements.txt .

# Install torch (CUDA 12.1)
RUN pip install \
    torch==2.5.1+cu121 \
    torchaudio==2.5.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Install transformers
RUN pip install transformers==4.46.3

# Install other dependencies (must include uvicorn here)
RUN pip install -r requirements.txt

COPY . /app

# ─────────────────────────────────────────────

FROM nvidia/cuda:12.1.1-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/workspace/models/huggingface

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    libsndfile1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy app
COPY --from=build /app .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
