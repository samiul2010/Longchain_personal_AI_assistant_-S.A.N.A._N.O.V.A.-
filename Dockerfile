# ============================================================
# HFS_1 v5 — Gemma 4 12B LLM API Server
#
# সমস্যার ইতিহাস:
#   v1: llama.cpp source build → OOMKilled
#   v2: wheel নেই → source build → gcc নেই → fail
#   v3: gcc install + build → OOMKilled
#   v4: python:3.10 + Luigi wheel → app startup হয় না (permission)
#
# v5 সমাধান:
#   - python:3.10-slim (Luigi wheel এর জন্য)
#   - Luigi/llama-cpp-python wheel (Gemma 4 সাপোর্ট, Jan 2026)
#   - USER root এ চালানো (HFS free tier এ permission সমস্যা এড়াতে)
# ============================================================

FROM python:3.10-slim

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# ── System libs ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libgomp1 \
    curl \
    bash \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── HuggingFace download tools ────────────────────────────────
RUN pip install --no-cache-dir \
    "huggingface_hub==0.27.0" \
    "hf-transfer==0.1.8" \
    "requests==2.32.3"

# ── llama-cpp-python: PRE-BUILT WHEEL ─────────────────────────
# Luigi fork — HFS free CPU এর জন্য তৈরি
# Python 3.10 / Linux x86_64 / CPU+OpenBLAS / Jan 2026 build
# Gemma 4 সহ সব আধুনিক architecture সাপোর্ট করে
RUN pip install --no-cache-dir \
    "https://huggingface.co/Luigi/llama-cpp-python-wheels-hf-spaces-free-cpu/resolve/main/llama_cpp_python-0.3.22-cp310-cp310-linux_x86_64.whl"

# ── FastAPI server ─────────────────────────────────────────────
RUN pip install --no-cache-dir \
    "fastapi==0.115.5" \
    "uvicorn[standard]==0.32.1" \
    "pydantic==2.10.3"

# ── App files ─────────────────────────────────────────────────
COPY download_model.py .
COPY start.sh .
COPY api_server.py .

RUN chmod +x /app/start.sh
RUN mkdir -p /app/models

# NOTE: root হিসেবে চালানো হচ্ছে (HFS free tier)
# useradd বাদ দেওয়া হয়েছে — permission সমস্যা এড়াতে

EXPOSE 7860

CMD ["/bin/bash", "/app/start.sh"]
