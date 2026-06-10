#!/usr/bin/env python3
# ============================================================
# api_server_v8.py
# llama-server কে background এ চালায়
# FastAPI দিয়ে port 7860 এ proxy করে
# ============================================================
#৳৳৳

import os
import subprocess
import time
import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

MODEL_PATH  = "/app/models/model.gguf"
CTX_SIZE    = int(os.environ.get("CTX_SIZE",    "2048"))
CPU_THREADS = int(os.environ.get("CPU_THREADS", "2"))
LLAMA_PORT  = 8080
API_PORT    = 7860

llama_proc = None


def start_llama_server():
    global llama_proc
    cmd = [
        "/app/llama-server",
        "--model",        MODEL_PATH,
        "--host",         "127.0.0.1",
        "--port",         str(LLAMA_PORT),
        "--ctx-size",     str(CTX_SIZE),
        "--threads",      str(CPU_THREADS),
        "--n-gpu-layers", "0",
        "--batch-size",   "256",
        "--ubatch-size",  "128",
        "--alias",        "gemma-4-12b",
        "--log-disable",
    ]
    log.info("🔄 llama-server চালু হচ্ছে...")
    llama_proc = subprocess.Popen(cmd)

    for i in range(120):
        time.sleep(2)
        try:
            r = httpx.get(
                f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=3
            )
            if r.status_code == 200:
                log.info("✅ llama-server প্রস্তুত!")
                return
        except Exception:
            pass
        if i % 10 == 0:
            log.info(f"   অপেক্ষা... ({i*2}s)")

    raise RuntimeError("llama-server চালু হয়নি!")


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_llama_server()
    yield
    if llama_proc:
        llama_proc.terminate()


app = FastAPI(
    title="Gemma 4 12B API — v8",
    version="8.0.0",
    lifespan=lifespan
)

STATUS_HTML = """<!DOCTYPE html>
<html lang="bn"><head><meta charset="UTF-8"><title>HFS_1 v8</title>
<style>
body{font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;
     display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#1e293b;border-radius:16px;padding:2rem;max-width:600px;
      width:100%;border:1px solid #334155}
h1{color:#38bdf8;margin-bottom:.5rem}
.ok{color:#4ade80;font-weight:600;margin-bottom:1.5rem}
.b{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1.5rem}
.badge{background:#0f3460;color:#93c5fd;border-radius:20px;
       padding:.25rem .75rem;font-size:.8rem}
.ep{background:#0f172a;border-left:3px solid #38bdf8;padding:.6rem 1rem;
    margin:.4rem 0;border-radius:0 6px 6px 0;font-family:monospace;font-size:.85rem}
.m{color:#fbbf24;margin-right:.5rem}
h3{color:#94a3b8;font-size:.85rem;text-transform:uppercase;margin:1.25rem 0 .5rem}
</style></head>
<body><div class="card">
<h1>🤖 HFS_1 v8 — Gemma 4 12B</h1>
<div class="ok">✅ সার্ভার সক্রিয়</div>
<div class="b">
  <span class="badge">Gemma 4 12B Q2_K</span>
  <span class="badge">llama-server backend</span>
  <span class="badge">CPU Only</span>
  <span class="badge">OpenAI Compatible</span>
</div>
<h3>Endpoints</h3>
<div class="ep"><span class="m">POST</span>/v1/chat/completions</div>
<div class="ep"><span class="m">GET</span>/v1/models</div>
<div class="ep"><span class="m">GET</span>/health</div>
<h3>সংযোগ</h3>
<div class="ep">base_url = "https://YOUR-SPACE.hf.space/v1"</div>
</div></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return STATUS_HTML


@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=3
            )
            if r.status_code == 200:
                return JSONResponse(
                    {"status": "ok", "model": "gemma-4-12b-q2k"}
                )
    except Exception:
        pass
    return JSONResponse({"status": "loading"}, status_code=503)


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    url = f"http://127.0.0.1:{LLAMA_PORT}/v1/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k != "host"}

    async with httpx.AsyncClient(timeout=300) as c:
        resp = await c.request(
            method=request.method,
            url=url,
            content=body,
            headers=headers,
        )

    if "text/event-stream" in resp.headers.get("content-type", ""):
        return StreamingResponse(
            resp.aiter_bytes(),
            media_type="text/event-stream",
        )

    return JSONResponse(
        content=resp.json(),
        status_code=resp.status_code,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="info")
    