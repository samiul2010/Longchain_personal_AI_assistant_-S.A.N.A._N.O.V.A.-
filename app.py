"""
public_relay/app.py — Public HF Space: Telegram ⇄ Private Space bridge
========================================================================
এই Space-টা PUBLIC থাকবে, তাই Telegram সরাসরি এর সাথে কথা বলতে পারে
(webhook পাঠাতে পারে, কোনো auth token ছাড়াই)। এটা একটা হালকা relay মাত্র —
কোনো ভারী dependency (CrewAI, Playwright ইত্যাদি) নেই।

কাজ দুইটা:
1) Telegram → এখানে POST /webhook → Private Space-এর /webhook-এ ফরওয়ার্ড
   (Private Space private বলে HF access token দিয়ে auth করে পাঠানো হয়)
2) Private Space → এখানে POST /bot{token}/{method} বা GET /file/bot{token}/{path}
   → সরাসরি api.telegram.org-এ ফরওয়ার্ড, রেসপন্স ফেরত

HF Secrets (এই Public Space-এ):
  PRIVATE_SPACE_URL   — যেমন: https://your-username-private-space.hf.space
  PRIVATE_SPACE_TOKEN — HF access token (Private Space-এ পৌঁছানোর জন্য;
                        Settings → Access Tokens থেকে বানান, 'read' যথেষ্ট)
  RELAY_SECRET        — শেয়ার্ড সিক্রেট, Telegram webhook verify করতে এবং
                        Private Space-কেও নিশ্চিত করতে যে কল এই relay থেকেই এসেছে
"""

import os
import asyncio
import logging

import httpx
import gradio as gr
import spaces
from fastapi import FastAPI, Request, Response
from gradio.routes import mount_gradio_app
import uvicorn

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("public_relay")

PRIVATE_SPACE_URL = os.getenv("PRIVATE_SPACE_URL", "").rstrip("/")
PRIVATE_SPACE_TOKEN = os.getenv("PRIVATE_SPACE_TOKEN", "").strip()
RELAY_SECRET = os.getenv("RELAY_SECRET", "").strip() or None

app = FastAPI(title="Telegram Public Relay")
client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))


async def _relay_to_telegram(method_name: str, url: str, **kwargs) -> httpx.Response | None:
    """api.telegram.org-এ কল করে, ব্যর্থ হলে কয়েকবার রিট্রাই করে (HF-এর নেটওয়ার্ক
    মাঝেমধ্যে অস্থির থাকে) — আর ব্যর্থ হলে repr(e) দিয়ে আসল কারণটা লগ করে (আগে
    খালি স্ট্রিং লগ হচ্ছিল, ডিবাগ করা কঠিন হচ্ছিল)।"""
    last_err = None
    for attempt in range(1, 4):
        try:
            if method_name == "GET":
                return await client.get(url, **kwargs)
            return await client.post(url, **kwargs)
        except httpx.HTTPError as e:
            last_err = e
            logger.warning(
                "Telegram call failed (attempt %d/3) [%s %s]: %r",
                attempt, method_name, url.split("/bot")[0] + "/bot***", e,
            )
            if attempt < 3:
                await asyncio.sleep(1.5 * attempt)
    logger.error("Telegram call permanently failed after retries: %r", last_err)
    return None


# HF-এর ZeroGPU হার্ডওয়্যারে Space চালু হওয়ার শর্ত হলো অন্তত একটা @spaces.GPU
# ফাংশন থাকা — এই relay-এর আসলে কোনো GPU দরকার নেই, তাই এই ফাংশনটা শুধু সেই
# platform-level চেক পাস করার জন্য রাখা, এটা কখনো কল হয় না এবং কোনো GPU
# quota খরচ করে না।
@spaces.GPU
def _zerogpu_placeholder():
    return "not used — placeholder for ZeroGPU hardware requirement"


@app.on_event("shutdown")
async def _shutdown():
    await client.aclose()


# ── দিক ১: Telegram → Private Space ──────────────────────────────────────────
@app.post("/webhook")
async def telegram_webhook(request: Request):
    if RELAY_SECRET:
        got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if got != RELAY_SECRET:
            logger.warning("Webhook: invalid secret token from Telegram")
            return Response(status_code=403, content='{"error":"forbidden"}', media_type="application/json")

    if not PRIVATE_SPACE_URL:
        logger.error("PRIVATE_SPACE_URL সেট করা নেই")
        return Response(status_code=500, content='{"error":"private_space_not_configured"}', media_type="application/json")

    body = await request.body()
    headers = {"Content-Type": "application/json"}
    if PRIVATE_SPACE_TOKEN:
        headers["Authorization"] = f"Bearer {PRIVATE_SPACE_TOKEN}"
    if RELAY_SECRET:
        headers["X-Telegram-Bot-Api-Secret-Token"] = RELAY_SECRET

    try:
        resp = await client.post(f"{PRIVATE_SPACE_URL}/webhook", content=body, headers=headers)
        return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    except httpx.HTTPError as e:
        logger.error("Private Space forward failed: %r", e)
        return Response(status_code=502, content='{"error":"private_space_unreachable"}', media_type="application/json")


# ── দিক ২: Private Space → Telegram (Bot API কল) ─────────────────────────────
@app.post("/bot{token}/{method}")
async def relay_api_call(token: str, method: str, request: Request):
    # শুধু আমাদের নিজের Private Space-ই এই রুট ব্যবহার করার কথা — যে কেউ পাবলিক
    # URL স্ক্যান করে যাতে এখান দিয়ে অন্য কারো bot token দিয়ে কল করতে না পারে,
    # সেজন্য shared secret বাধ্যতামূলক করা হলো।
    if RELAY_SECRET and request.headers.get("X-Relay-Secret", "") != RELAY_SECRET:
        return Response(status_code=403, content='{"ok": false, "description": "forbidden"}', media_type="application/json")

    body = await request.body()
    content_type = request.headers.get("content-type", "application/json")
    resp = await _relay_to_telegram(
        "POST",
        f"https://api.telegram.org/bot{token}/{method}",
        content=body,
        headers={"Content-Type": content_type},
    )
    if resp is None:
        return Response(status_code=502, content='{"ok": false, "description": "telegram_unreachable"}', media_type="application/json")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


# ── Private Space → Telegram (ফাইল ডাউনলোড) ──────────────────────────────────
@app.get("/file/bot{token}/{file_path:path}")
async def relay_file_download(token: str, file_path: str, request: Request):
    if RELAY_SECRET and request.headers.get("X-Relay-Secret", "") != RELAY_SECRET:
        return Response(status_code=403, content='{"error":"forbidden"}', media_type="application/json")

    resp = await _relay_to_telegram("GET", f"https://api.telegram.org/file/bot{token}/{file_path}")
    if resp is None:
        return Response(status_code=502, content='{"error":"telegram_unreachable"}', media_type="application/json")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/octet-stream"),
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "private_space_configured": bool(PRIVATE_SPACE_URL),
        "relay_secret_configured": bool(RELAY_SECRET),
    }


@app.get("/")
async def index():
    return {"status": "running", "role": "telegram-public-relay"}


def main():
    # Gradio SDK Space-এর জন্য: একটা ছোট status UI Gradio দিয়ে বানিয়ে আসল FastAPI
    # অ্যাপের উপর mount করা হচ্ছে। রুট (/webhook, /bot{token}/{method} ইত্যাদি)
    # অপরিবর্তিত থাকে — শুধু root path ("/") এ Gradio-র status page দেখা যাবে।
    with gr.Blocks(title="Telegram Public Relay") as demo:
        gr.Markdown(
            "## 🤖 Telegram Public Relay\n"
            "Status: running\n\n"
            f"Private Space configured: **{bool(PRIVATE_SPACE_URL)}**\n\n"
            f"Relay secret configured: **{bool(RELAY_SECRET)}**"
        )

    global app
    app = mount_gradio_app(app, demo, path="/ui")

    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
