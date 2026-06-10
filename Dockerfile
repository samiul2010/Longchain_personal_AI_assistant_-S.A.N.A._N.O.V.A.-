FROM ghcr.io/ggml-org/llama.cpp:server AS llama_source
FROM python:3.10-slim
WORKDIR /app
COPY --from=llama_source /app/llama-server /usr/local/bin/llama-server
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libopenblas0 curl bash \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    "huggingface_hub==0.27.0" "hf-transfer==0.1.8" "requests==2.32.3"
RUN pip install --no-cache-dir \
    "fastapi==0.115.5" "uvicorn==0.32.1" "httpx==0.28.1"
COPY download_model.py /app/download_model.py
COPY api_server.py /app/api_server.py
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh && mkdir -p /app/models
EXPOSE 7860
CMD ["/bin/bash", "/app/start.sh"]