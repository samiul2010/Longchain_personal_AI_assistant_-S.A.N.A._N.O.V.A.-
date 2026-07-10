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
import logging

import httpx
from fastapi import FastAPI, Request, Response
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
        logger.error("Private Space forward failed: %s", e)
        return Response(status_code=502, content='{"error":"private_space_unreachable"}', media_type="application/json")


# ── দিক ২: Private Space → Telegram (Bot API কল) ─────────────────────────────
@app.post("/bot{token}/{method}")
async def relay_api_call(token: str, method: str, request: Request):
    body = await request.body()
    content_type = request.headers.get("content-type", "application/json")
    try:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/{method}",
            content=body,
            headers={"Content-Type": content_type},
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except httpx.HTTPError as e:
        logger.error("Telegram API relay failed (%s): %s", method, e)
        return Response(status_code=502, content='{"ok": false, "description": "telegram_unreachable"}', media_type="application/json")


# ── Private Space → Telegram (ফাইল ডাউনলোড) ──────────────────────────────────
@app.get("/file/bot{token}/{file_path:path}")
async def relay_file_download(token: str, file_path: str):
    try:
        resp = await client.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
        )
    except httpx.HTTPError as e:
        logger.error("Telegram file relay failed: %s", e)
        return Response(status_code=502, content='{"error":"telegram_unreachable"}', media_type="application/json")


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
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
