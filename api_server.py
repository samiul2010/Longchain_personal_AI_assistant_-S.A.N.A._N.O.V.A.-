#!/usr/bin/env python3
"""
api_server.py — HFS_1 v7
Q2_K + Memory-optimized settings
"""

import os
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import uvicorn
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

MODEL_PATH  = "/app/models/model.gguf"
CTX_SIZE    = int(os.environ.get("CTX_SIZE",    "2048"))  # 4096→2048: RAM বাঁচায়
CPU_THREADS = int(os.environ.get("CPU_THREADS", "2"))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE",  "256"))   # 512→256: RAM বাঁচায়

llm = None


def load_model():
    global llm
    from llama_cpp import Llama

    log.info(f"🔄 মডেল লোড হচ্ছে: {MODEL_PATH}")
    log.info(f"   CTX={CTX_SIZE}, Threads={CPU_THREADS}, Batch={BATCH_SIZE}")

    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=CTX_SIZE,
        n_threads=CPU_THREADS,
        n_batch=BATCH_SIZE,
        n_gpu_layers=0,       # CPU only
        use_mmap=True,        # ফাইল সরাসরি map করে — RAM কম লাগে
        use_mlock=False,      # RAM lock করে না — swap হতে দেয়
        verbose=False,
        chat_format="gemma",
    )
    log.info("✅ মডেল লোড সম্পন্ন!")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    log.info("🚀 API চালু (port 7860)")
    yield
    log.info("🛑 Server বন্ধ")


app = FastAPI(title="Gemma 4 12B API", version="7.0.0", lifespan=lifespan)


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


STATUS_HTML = """<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <title>HFS_1 — Gemma 4 12B API</title>
  <style>
    body { font-family: Arial, sans-serif; background: #0f172a;
           color: #e2e8f0; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; }
    .card { background: #1e293b; border-radius: 16px; padding: 2rem;
            max-width: 600px; width: 100%; border: 1px solid #334155; }
    h1 { color: #38bdf8; margin-bottom: 0.5rem; }
    .ok { color: #4ade80; font-weight: 600; margin-bottom: 1.5rem; }
    .badges { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; }
    .badge { background: #0f3460; color: #93c5fd; border-radius: 20px;
             padding: 0.25rem 0.75rem; font-size: 0.8rem; }
    .ep { background: #0f172a; border-left: 3px solid #38bdf8;
          padding: 0.6rem 1rem; margin: 0.4rem 0; border-radius: 0 6px 6px 0;
          font-family: monospace; font-size: 0.85rem; }
    .m { color: #fbbf24; margin-right: 0.5rem; }
    h3 { color: #94a3b8; font-size: 0.85rem; text-transform: uppercase;
         letter-spacing: 0.05em; margin: 1.25rem 0 0.5rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🤖 HFS_1 — Gemma 4 12B API</h1>
    <div class="ok">✅ সার্ভার সক্রিয়</div>
    <div class="badges">
      <span class="badge">Gemma 4 12B Q2_K</span>
      <span class="badge">llama-cpp-python</span>
      <span class="badge">CPU Optimized</span>
      <span class="badge">OpenAI Compatible</span>
    </div>
    <h3>Endpoints</h3>
    <div class="ep"><span class="m">POST</span>/v1/chat/completions</div>
    <div class="ep"><span class="m">GET</span>/v1/models</div>
    <div class="ep"><span class="m">GET</span>/health</div>
    <h3>সংযোগ</h3>
    <div class="ep">base_url = "https://YOUR-SPACE.hf.space/v1"</div>
  </div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return STATUS_HTML


@app.get("/health")
async def health():
    if llm is None:
        return JSONResponse({"status": "loading"}, status_code=503)
    return JSONResponse({"status": "ok", "model": "gemma-4-12b-q2k"})


@app.get("/v1/models")
async def list_models():
    return JSONResponse({
        "object": "list",
        "data": [{"id": "gemma-4-12b", "object": "model",
                  "created": 1700000000, "owned_by": "google"}]
    })


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    if llm is None:
        return JSONResponse(
            {"error": {"message": "মডেল লোড হচ্ছে।", "type": "server_error"}},
            status_code=503
        )

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
        def generate():
            import time
            for chunk in llm.create_chat_completion(**params, stream=True):
                delta = chunk["choices"][0].get("delta", {})
                yield f"data: {json.dumps({'id': f'chatcmpl-{int(time.time())}', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': req.model, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(generate(), media_type="text/event-stream")

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
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")
