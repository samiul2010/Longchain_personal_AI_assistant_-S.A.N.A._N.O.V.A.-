FROM ghcr.io/ggml-org/llama.cpp:server

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl bash \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
    "huggingface_hub==0.27.0" \
    "hf-transfer==0.1.8" \
    "requests==2.32.3" \
    "fastapi==0.115.5" \
    "uvicorn==0.32.1" \
    "httpx==0.28.1"

COPY download_model.py /app/download_model.py
COPY api_server.py /app/api_server.py
COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh && mkdir -p /app/models

EXPOSE 7860
ENTRYPOINT []
CMD ["/bin/bash", "/app/start.sh"]