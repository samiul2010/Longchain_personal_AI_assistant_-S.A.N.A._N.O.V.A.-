#!/usr/bin/env python3
"""
health_proxy.py
---------------
HuggingFace Space port 7860 এ চলে।
দুটো কাজ করে:
  1. GET /  → Space এর জন্য status HTML page দেখায়
  2. POST /v1/*  → llama-server (port 8080) এ forward করে
  3. GET /health → llama-server এর health check

এটা দরকার কারণ:
  - HF Space শুধু 7860 expose করে (public URL)
  - llama-server 8080 এ চলে (internal)
  - CrewAI HFS_1 এর public URL দিয়ে call করবে
"""

import os
import httpx
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# llama-server internal address
LLAMA_BASE = "http://127.0.0.1:8080"

# ── Lifespan: shared HTTP client ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(
        base_url=LLAMA_BASE,
        timeout=httpx.Timeout(300.0),   # LLM inference দীর্ঘ সময় নেয়
    )
    log.info("🚀 Proxy server চালু হয়েছে (port 7860)")
    yield
    await app.state.client.aclose()


app = FastAPI(
    title="Gemma 4 12B API (HFS_1)",
    description="OpenAI-compatible LLM API powered by Gemma 4 12B GGUF",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Status page ───────────────────────────────────────────────
STATUS_HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <title>HFS_1 - Gemma 4 12B API</title>
  <style>
    body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; 
           display: flex; flex-direction: column; align-items: center; 
           justify-content: center; min-height: 100vh; margin: 0; }
    .card { background: #16213e; border-radius: 12px; padding: 2rem 3rem; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.5); max-width: 600px; width: 90%; }
    h1 { color: #0f3460; color: #e94560; margin-top: 0; }
    .badge { display: inline-block; background: #0f3460; color: #eee; 
             border-radius: 6px; padding: 4px 12px; margin: 4px; font-size: 0.85rem; }
    .endpoint { background: #0d1b2a; border-left: 3px solid #e94560; 
                padding: 0.5rem 1rem; margin: 0.5rem 0; border-radius: 4px; 
                font-family: monospace; font-size: 0.9rem; }
    .status { color: #4caf50; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🤖 HFS_1 — Gemma 4 12B API</h1>
    <p class="status">✅ সার্ভার চালু আছে</p>
    <p>
      <span class="badge">Model: Gemma 4 12B-it Q4_K_M</span>
      <span class="badge">Engine: llama.cpp</span>
      <span class="badge">CPU Optimized</span>
    </p>
    <h3>📡 API Endpoints (CrewAI সংযোগের জন্য):</h3>
    <div class="endpoint">POST /v1/chat/completions</div>
    <div class="endpoint">GET  /v1/models</div>
    <div class="endpoint">GET  /health</div>
    <h3>📋 CrewAI সংযোগ উদাহরণ:</h3>
    <div class="endpoint">
      base_url = "https://YOUR-SPACE.hf.space/v1"<br>
      api_key  = "not-required"
    </div>
  </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    """HuggingFace Space status page"""
    return STATUS_HTML


# ── Health check ──────────────────────────────────────────────
@app.get("/health")
async def health(request: Request):
    """llama-server health check কে proxy করে"""
    try:
        resp = await request.app.state.client.get("/health")
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type="application/json",
        )
    except Exception as e:
        return Response(
            content=f'{{"status":"error","detail":"{str(e)}"}}',
            status_code=503,
            media_type="application/json",
        )


# ── OpenAI-compatible API proxy ───────────────────────────────
@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_llama(path: str, request: Request):
    """
    সব /v1/* request কে llama-server এ forward করে।
    Streaming response সাপোর্ট করে (stream=True এর জন্য)।
    """
    client: httpx.AsyncClient = request.app.state.client

    # Request body পড়া
    body = await request.body()

    # Headers copy (Content-Type ইত্যাদি)
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding")
    }

    try:
        # llama-server এ forward
        llama_request = client.build_request(
            method=request.method,
            url=f"/v1/{path}",
            headers=headers,
            content=body,
            params=request.query_params,
        )

        # Streaming check (SSE / stream=true)
        is_stream = False
        if body:
            import json
            try:
                payload = json.loads(body)
                is_stream = payload.get("stream", False)
            except Exception:
                pass

        if is_stream:
            # Streaming response (token-by-token)
            async def stream_generator():
                async with client.stream(
                    method=request.method,
                    url=f"/v1/{path}",
                    headers=headers,
                    content=body,
                    params=request.query_params,
                ) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
            )
        else:
            # Normal response
            resp = await client.send(llama_request)
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/json"),
            )

    except httpx.ConnectError:
        return Response(
            content='{"error":{"message":"LLM server এখনো চালু হয়নি। কিছুক্ষণ অপেক্ষা করুন।","type":"server_error"}}',
            status_code=503,
            media_type="application/json",
        )
    except Exception as e:
        log.error(f"Proxy error: {e}")
        return Response(
            content=f'{{"error":{{"message":"{str(e)}","type":"server_error"}}}}',
            status_code=500,
            media_type="application/json",
        )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860,
        log_level="info",
        access_log=True,
    )
