#!/usr/bin/env python3
"""
api_server.py  —  HFS_1 Main API Server
----------------------------------------
llama-cpp-python এর built-in OpenAI-compatible server ব্যবহার করে।

Port 7860 এ সরাসরি চলে (proxy দরকার নেই — v1 এর চেয়ে সহজ)।

Endpoints:
  GET  /              → Status HTML page
  GET  /health        → {"status": "ok"}
  GET  /v1/models     → model list
  POST /v1/chat/completions → chat (streaming + non-streaming)
  POST /v1/completions      → text completion
"""

import os
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import uvicorn
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

MODEL_PATH = "/app/models/model.gguf"
CTX_SIZE   = int(os.environ.get("CTX_SIZE", "4096"))
CPU_THREADS = int(os.environ.get("CPU_THREADS", "2"))

# ── Global model instance ─────────────────────────────────────
llm = None


def load_model():
    """llama-cpp-python দিয়ে মডেল লোড করে।"""
    global llm
    from llama_cpp import Llama

    log.info(f"🔄 মডেল লোড হচ্ছে: {MODEL_PATH}")
    log.info(f"   Context size: {CTX_SIZE}, Threads: {CPU_THREADS}")

    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=CTX_SIZE,
        n_threads=CPU_THREADS,
        n_gpu_layers=0,          # CPU only (HFS free tier)
        verbose=False,
        chat_format="gemma",     # Gemma 4 chat template
    )
    log.info("✅ মডেল লোড সম্পন্ন!")
    return llm


# ── Lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    log.info("🚀 API Server চালু (port 7860)")
    yield
    log.info("🛑 Server বন্ধ হচ্ছে")


app = FastAPI(
    title="Gemma 4 12B API — HFS_1",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Pydantic models ───────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "gemma-4-12b"
    messages: List[Message]
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.95
    top_k: Optional[int] = 64
    repeat_penalty: Optional[float] = 1.1
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None


# ── Status page ───────────────────────────────────────────────
STATUS_HTML = """<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HFS_1 — Gemma 4 12B API</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; 
           color: #e2e8f0; min-height: 100vh; display: flex; 
           align-items: center; justify-content: center; padding: 1rem; }
    .card { background: #1e293b; border-radius: 16px; padding: 2rem; 
            max-width: 640px; width: 100%; border: 1px solid #334155; }
    h1 { font-size: 1.5rem; color: #38bdf8; margin-bottom: 0.5rem; }
    .status { color: #4ade80; font-weight: 600; margin-bottom: 1.5rem; }
    .badges { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; }
    .badge { background: #0f3460; color: #93c5fd; border-radius: 20px; 
             padding: 0.25rem 0.75rem; font-size: 0.8rem; }
    h3 { color: #94a3b8; font-size: 0.9rem; text-transform: uppercase; 
         letter-spacing: 0.05em; margin-bottom: 0.75rem; margin-top: 1.25rem; }
    .endpoint { background: #0f172a; border-left: 3px solid #38bdf8; 
                padding: 0.6rem 1rem; margin: 0.4rem 0; border-radius: 0 6px 6px 0; 
                font-family: monospace; font-size: 0.85rem; color: #e2e8f0; }
    .method { color: #fbbf24; margin-right: 0.5rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🤖 HFS_1 — Gemma 4 12B API</h1>
    <div class="status">✅ সার্ভার সক্রিয় আছে</div>
    <div class="badges">
      <span class="badge">Gemma 4 12B-it Q4_K_M</span>
      <span class="badge">llama-cpp-python</span>
      <span class="badge">CPU Optimized</span>
      <span class="badge">OpenAI Compatible</span>
    </div>
    <h3>API Endpoints</h3>
    <div class="endpoint"><span class="method">POST</span>/v1/chat/completions</div>
    <div class="endpoint"><span class="method">GET</span>/v1/models</div>
    <div class="endpoint"><span class="method">GET</span>/health</div>
    <h3>CrewAI সংযোগ</h3>
    <div class="endpoint">base_url = "https://YOUR-SPACE.hf.space/v1"</div>
  </div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return STATUS_HTML


# ── Health check ──────────────────────────────────────────────
@app.get("/health")
async def health():
    if llm is None:
        return JSONResponse({"status": "loading"}, status_code=503)
    return JSONResponse({"status": "ok", "model": "gemma-4-12b"})


# ── Models list ───────────────────────────────────────────────
@app.get("/v1/models")
async def list_models():
    return JSONResponse({
        "object": "list",
        "data": [{
            "id": "gemma-4-12b",
            "object": "model",
            "created": 1700000000,
            "owned_by": "google",
        }]
    })


# ── Chat completions ──────────────────────────────────────────
@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    if llm is None:
        return JSONResponse(
            {"error": {"message": "মডেল লোড হচ্ছে। একটু অপেক্ষা করুন।", "type": "server_error"}},
            status_code=503
        )

    # Messages convert করা
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    params = dict(
        messages=messages,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
        top_k=req.top_k,
        repeat_penalty=req.repeat_penalty,
        stop=req.stop,
    )

    if req.stream:
        # Streaming (SSE)
        def generate():
            import time
            stream = llm.create_chat_completion(**params, stream=True)
            for chunk in stream:
                delta = chunk["choices"][0].get("delta", {})
                sse_data = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": req.model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}]
                }
                yield f"data: {json.dumps(sse_data)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    else:
        # Normal response
        import time
        result = llm.create_chat_completion(**params)
        return JSONResponse({
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": result["choices"],
            "usage": result.get("usage", {}),
        })


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860,
        log_level="info",
    )
