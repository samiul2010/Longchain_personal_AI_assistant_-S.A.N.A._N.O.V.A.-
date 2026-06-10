# ============================================================
# HFS_1 Dockerfile_v8
# ============================================================
# ZERO compilation — yusiwen/llama.cpp থেকে binary copy
# Gemma 4 সম্পূর্ণ সাপোর্ট (daily updated image)
# ============================================================

# Step 1: llama-server binary নাও (কোনো compilation নেই)
FROM yusiwen/llama.cpp:latest AS llama_source

# Step 2: হালকা Python image
FROM python:3.10-slim

WORKDIR /app

# llama-server binary copy করো
COPY --from=llama_source /usr/local/bin/llama-server /usr/local/bin/llama-server

# Runtime libs (gcc/cmake নেই — build tools দরকার নেই)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas0 \
    curl \
    bash \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# HuggingFace download tools
RUN pip install --no-cache-dir \
    "huggingface_hub==0.27.0" \
    "hf-transfer==0.1.8" \
    "requests==2.32.3"

# FastAPI proxy server
RUN pip install --no-cache-dir \
    "fastapi==0.115.5" \
    "uvicorn==0.32.1" \
    "httpx==0.28.1"

# App files
COPY download_model.py /app/download_model.py
COPY api_server.py /app/api_server.py
COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh
RUN mkdir -p /app/models

EXPOSE 7860
CMD ["/bin/bash", "/app/start.sh"]
