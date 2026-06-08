# ============================================================
# HFS_1 v3 — Gemma 4 12B LLM API Server
#
# v2 সমস্যা: llama-cpp-python==0.3.9 pre-built wheel পাওয়া যায়নি
#            → source build → gcc নেই → fail
#
# v3 সমাধান:
#   - gcc/cmake install (ছোট, OOM হবে না)
#   - llama-cpp-python==0.3.27 (latest, Gemma 4 support)
#   - GGML_OPENBLAS=ON (CPU multi-core acceleration)
# ============================================================

FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive

# gcc/g++/cmake: llama-cpp-python C extension build এর জন্য দরকার
# v1 OOM কারণ: পুরো llama.cpp codebase compile (~16GB RAM)
# v3 safe কারণ: শুধু Python C binding compile (~2-3GB RAM max)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    cmake \
    libopenblas-dev \
    libgomp1 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# HuggingFace download tools
RUN pip install --no-cache-dir \
    "huggingface_hub==0.27.0" \
    "hf-transfer==0.1.8" \
    "requests==2.32.3"

# llama-cpp-python CPU build with OpenBLAS
# 0.3.27 = latest stable, Gemma 4 chat format support আছে
RUN CMAKE_ARGS="-DGGML_OPENBLAS=ON" \
    pip install --no-cache-dir \
    "llama-cpp-python==0.3.27"

# FastAPI server
RUN pip install --no-cache-dir \
    "fastapi==0.115.5" \
    "uvicorn[standard]==0.32.1" \
    "pydantic==2.10.3"

WORKDIR /app
COPY download_model.py .
COPY start.sh .
COPY api_server.py .
RUN chmod +x start.sh
RUN mkdir -p /app/models

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 7860
CMD ["/app/start.sh"]
