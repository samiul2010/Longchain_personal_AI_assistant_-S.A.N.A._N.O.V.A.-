# ============================================================
# HFS_1 - Gemma 4 12B LLM API Server
# Strategy: llama.cpp (C++ binary) + GGUF Q4_K_M quantized model
# API: OpenAI-compatible /v1/chat/completions (CrewAI সাপোর্ট করে)
# Hardware: HuggingFace Free CPU Tier (2 vCPU, 16GB RAM, 50GB disk)
# Port: 7860 (HuggingFace Space required port)
# ============================================================

FROM ubuntu:22.04

# Build arguments
ARG DEBIAN_FRONTEND=noninteractive

# ── Step 1: System dependencies ─────────────────────────────
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    curl \
    wget \
    python3 \
    python3-pip \
    python3-dev \
    libopenblas-dev \
    libgomp1 \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Step 2: Python packages (fixed versions for compatibility) ──
# huggingface_hub==0.23.4 → stable, hf_transfer support
# fastapi==0.111.0 → stable with pydantic v2
# uvicorn==0.30.1 → compatible with fastapi 0.111
# httpx==0.27.0 → needed by fastapi test client
# pydantic==2.7.4 → compatible with fastapi 0.111
RUN pip3 install --no-cache-dir \
    "huggingface_hub==0.23.4" \
    "fastapi==0.111.0" \
    "uvicorn[standard]==0.30.1" \
    "httpx==0.27.0" \
    "pydantic==2.7.4" \
    "requests==2.32.3" \
    "hf-transfer==0.1.8"

# ── Step 3: Build llama.cpp from source (CPU optimized, OpenBLAS) ──
# llama.cpp এর নিজস্ব OpenAI-compatible server আছে
# GGML_OPENBLAS=ON → multi-core CPU acceleration
WORKDIR /opt
RUN git clone --depth 1 https://github.com/ggerganov/llama.cpp.git && \
    cd llama.cpp && \
    mkdir build && \
    cd build && \
    cmake .. \
        -DGGML_OPENBLAS=ON \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=ON \
    && make -j$(nproc) llama-server && \
    cp bin/llama-server /usr/local/bin/llama-server && \
    chmod +x /usr/local/bin/llama-server

# ── Step 4: App directory ────────────────────────────────────
WORKDIR /app
COPY download_model.py .
COPY start.sh .
COPY health_proxy.py .
RUN chmod +x start.sh

# ── Step 5: Create model cache directory ─────────────────────
RUN mkdir -p /app/models

# HuggingFace Space এ non-root user দিয়ে run করতে হয়
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /opt/llama.cpp
USER appuser

# ── Step 6: Expose port ──────────────────────────────────────
EXPOSE 7860

# ── Step 7: Entrypoint ───────────────────────────────────────
CMD ["/app/start.sh"]
