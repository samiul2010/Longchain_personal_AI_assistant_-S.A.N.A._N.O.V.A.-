# ============================================================
# HFS_1 - Gemma 4 12B LLM API Server  (v2 — OOM fixed)
# 
# v1 সমস্যা: llama.cpp source build → OOMKilled (RAM শেষ)
# v2 সমাধান: pre-built llama-cpp-python CPU wheel (pip install)
#            → কোনো compilation নেই, build RAM সমস্যা নেই
#
# API: OpenAI-compatible /v1/chat/completions (CrewAI সাপোর্ট)
# Hardware: HuggingFace Free CPU (2 vCPU, 16GB RAM, 50GB disk)
# Port: 7860 (HuggingFace Space required port)
# ============================================================

FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive

# ── Step 1: Minimal system dependencies only ────────────────
# libopenblas → CPU matrix multiply acceleration
# curl        → health check এ ব্যবহার
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libgomp1 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Step 2: Python packages (pre-built wheels, no compilation) ──
#
# llama-cpp-python CPU wheel:
#   - oobabooga/llama-cpp-binaries এ pre-built CPU wheel আছে
#   - কোনো cmake/gcc লাগে না
#   - OpenAI-compatible server built-in আছে
#
# Pinned versions (tested compatible):
#   llama-cpp-python  0.3.9   ← latest stable with Gemma 4 support
#   fastapi           0.115.5 ← stable, pydantic v2 compatible
#   uvicorn           0.32.1  ← fastapi compatible
#   httpx             0.27.2  ← proxy client
#   pydantic          2.10.3  ← fastapi dependency
#   huggingface_hub   0.27.0  ← model download
#   hf-transfer       0.1.8   ← fast download
#   requests          2.32.3  ← utility

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "huggingface_hub==0.27.0" \
        "hf-transfer==0.1.8" \
        "requests==2.32.3"

# llama-cpp-python CPU pre-built wheel আলাদা install করা হচ্ছে
# extra-index-url থেকে CPU-only wheel নামবে (compilation নেই)
RUN pip install --no-cache-dir \
    "llama-cpp-python==0.3.9" \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# FastAPI + Uvicorn + HTTPX
RUN pip install --no-cache-dir \
    "fastapi==0.115.5" \
    "uvicorn[standard]==0.32.1" \
    "httpx==0.27.2" \
    "pydantic==2.10.3"

# ── Step 3: App directory ────────────────────────────────────
WORKDIR /app
COPY download_model.py .
COPY start.sh .
COPY api_server.py .
RUN chmod +x start.sh

# Model cache directory
RUN mkdir -p /app/models

# HuggingFace Space: non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# ── Port ─────────────────────────────────────────────────────
EXPOSE 7860

# ── Entrypoint ───────────────────────────────────────────────
CMD ["/app/start.sh"]
