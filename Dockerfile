# ============================================================
# HFS_1 v4 — Gemma 4 12B LLM API Server
#
# সমস্যার ইতিহাস:
#   v1: llama.cpp source build → OOMKilled (16GB RAM শেষ)
#   v2: llama-cpp-python==0.3.9, extra-index-url → wheel নেই → source build → gcc নেই → fail
#   v3: gcc install + llama-cpp-python==0.3.27 build → OOMKilled (16GB RAM শেষ)
#
# v4 চূড়ান্ত সমাধান:
#   Direct pre-built wheel URL দিয়ে install → ZERO compilation
#   Source: sergey21000/llama-cpp-python-wheels (GitHub)
#   Wheel: llama_cpp_python-0.3.15-cp311-cp311-linux_x86_64.whl
#   Size: ~4MB, install time: <10 seconds
# ============================================================

FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive

# ── Minimal runtime libs only (gcc/cmake নেই!) ───────────────
# libopenblas0: CPU matrix acceleration (runtime)
# libgomp1: OpenMP threading (runtime)
# curl: health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libgomp1 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── HuggingFace download tools ────────────────────────────────
RUN pip install --no-cache-dir \
    "huggingface_hub==0.27.0" \
    "hf-transfer==0.1.8" \
    "requests==2.32.3"

# ── llama-cpp-python: PRE-BUILT WHEEL (zero compilation!) ─────
# sergey21000/llama-cpp-python-wheels থেকে direct download
# Python 3.11 / Linux x86_64 / CPU-only / v0.3.15
# v0.3.15 এ Gemma 3/4 chat format সাপোর্ট আছে
RUN pip install --no-cache-dir \
    "https://github.com/sergey21000/llama-cpp-python-wheels/releases/download/v0.3.9-cpu/llama_cpp_python-0.3.9-cp311-cp311-linux_x86_64.whl"

# ── FastAPI server ─────────────────────────────────────────────
RUN pip install --no-cache-dir \
    "fastapi==0.115.5" \
    "uvicorn[standard]==0.32.1" \
    "pydantic==2.10.3"

# ── App files ─────────────────────────────────────────────────
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
