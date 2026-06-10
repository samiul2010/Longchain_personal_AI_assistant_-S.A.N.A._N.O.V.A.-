# ============================================================
# HFS_1 v7 — Gemma 4 12B Q2_K API Server
#
# ইতিহাস:
#   v1-v3: compilation → OOMKilled
#   v4-v5: pre-built wheel → Gemma 4 চেনে না (Jan 2026)
#   v6: llama-server binary → OOMKilled
#
# v7 সমাধান:
#   - মডেল: Q2_K (4.1GB) → RAM ~6GB → 16GB তে নিরাপদ
#   - Wheel: llama-cpp-python source build কিন্তু TINY build
#     (GGML_NATIVE=OFF, no AVX, minimal — OOM হবে না)
#   - CTX=2048, batch=256 → inference এ RAM বাঁচে
# ============================================================

FROM python:3.10-slim

ARG DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# ── Build tools (wheel build এর জন্য, minimal) ───────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    cmake \
    libopenblas0 \
    libgomp1 \
    curl \
    bash \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── HuggingFace tools ─────────────────────────────────────────
RUN pip install --no-cache-dir \
    "huggingface_hub==0.27.0" \
    "hf-transfer==0.1.8" \
    "requests==2.32.3"

# ── llama-cpp-python: MINIMAL build ──────────────────────────
# GGML_NATIVE=OFF → CPU-specific instruction বাদ (OOM এড়ায়)
# CMAKE_BUILD_PARALLEL_LEVEL=1 → একটা thread এ build (RAM বাঁচে)
# GGML_BLAS=OFF → OpenBLAS linking বাদ (সহজ build)
RUN CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_BLAS=OFF -DGGML_OPENMP=OFF" \
    CMAKE_BUILD_PARALLEL_LEVEL=1 \
    pip install --no-cache-dir \
    "llama-cpp-python==0.3.9" \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# ── FastAPI ───────────────────────────────────────────────────
RUN pip install --no-cache-dir \
    "fastapi==0.115.5" \
    "uvicorn[standard]==0.32.1" \
    "pydantic==2.10.3"

# ── App files ─────────────────────────────────────────────────
COPY download_model.py api_server.py start.sh ./
RUN chmod +x /app/start.sh
RUN mkdir -p /app/models

EXPOSE 7860
CMD ["/bin/bash", "/app/start.sh"]
