"""
public_relay/app.py — Public HF Space: Telegram ⇄ Private Space bridge
========================================================================
এই Space-টা PUBLIC থাকবে, তাই Telegram সরাসরি এর সাথে কথা বলতে পারে
(webhook পাঠাতে পারে, কোনো auth token ছাড়াই)।

এখন python-telegram-bot লাইব্রেরি ব্যবহার করে:
- সব ধরনের মেসেজ (টেক্সট, ফটো, ভিডিও, ডকুমেন্ট, অডিও, ভয়েস, লোকেশন, কন্ট্যাক্ট) হ্যান্ডেল করে
- নির্দিষ্ট Chat ID থেকে আসা মেসেজে রিপ্লাই দেয়
- ফাইল ডাউনলোড ও সেভ করতে পারে
- Private Space-এ ফরওয়ার্ড করতে পারে
"""

import os
import asyncio
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
import gradio as gr
import spaces
from fastapi import FastAPI, Request, Response
from gradio.routes import mount_gradio_app
import uvicorn

# python-telegram-bot
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest

# ─── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("public_relay")

# ─── Environment Variables ──────────────────────────────────────────────
PRIVATE_SPACE_URL = os.getenv("PRIVATE_SPACE_URL", "").rstrip("/")
PRIVATE_SPACE_TOKEN = os.getenv("PRIVATE_SPACE_TOKEN", "").strip()
RELAY_SECRET = os.getenv("RELAY_SECRET", "").strip() or None
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip()

# ─── Download Directory ──────────────────────────────────────────────────
DOWNLOAD_DIR = Path("/tmp/telegram_downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ─── FastAPI Setup ──────────────────────────────────────────────────────
app = FastAPI(title="Telegram Public Relay")
client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))

# ─── Telegram Bot Setup ──────────────────────────────────────────────────
telegram_app = None
telegram_request = HTTPXRequest(
    connect_timeout=30.0,
    read_timeout=60.0,
    write_timeout=30.0,
)

# ─── Helper Functions ──────────────────────────────────────────────────

async def get_public_url() -> str:
    """Hugging Face Space-এর পাবলিক URL Auto-Detect করে"""
    
    # 1. Environment Variable থেকে চেক করুন
    if PUBLIC_URL:
        return PUBLIC_URL.rstrip("/")
    
    # 2. Hugging Face Space-এর জন্য
    space_id = os.getenv("SPACE_ID", "")
    if space_id:
        return f"https://{space_id}.hf.space"
    
    # 3. Railway-এর জন্য
    railway_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if railway_url:
        return f"https://{railway_url}"
    
    # 4. Heroku-এর জন্য
    heroku_url = os.getenv("HEROKU_APP_NAME", "")
    if heroku_url:
        return f"https://{heroku_url}.herokuapp.com"
    
    # 5. Localhost (ডেভেলপমেন্ট)
    return "http://localhost:7860"


async def is_allowed_user(update: Update) -> bool:
    """চেক করে এই Chat ID কি অনুমোদিত"""
    if not TELEGRAM_ALLOWED_CHAT_ID:
        return True
    chat_id = str(update.effective_chat.id) if update.effective_chat else None
    return chat_id == TELEGRAM_ALLOWED_CHAT_ID


async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Telegram-এ মেসেজ পাঠায়"""
    if not TELEGRAM_BOT_TOKEN:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = await client.post(url, json={"chat_id": chat_id, "text": text})
        return resp.status_code == 200
    except Exception:
        return False


async def forward_to_private_space(data: Dict[str, Any]) -> bool:
    """Private Space-এ ডেটা ফরওয়ার্ড করে"""
    if not PRIVATE_SPACE_URL:
        return False
    
    headers = {"Content-Type": "application/json"}
    if PRIVATE_SPACE_TOKEN:
        headers["Authorization"] = f"Bearer {PRIVATE_SPACE_TOKEN}"
    if RELAY_SECRET:
        headers["X-Relay-Secret"] = RELAY_SECRET
    
    try:
        resp = await client.post(
            f"{PRIVATE_SPACE_URL}/telegram_forward",
            json=data,
            headers=headers,
            timeout=30.0
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"❌ Private Space forward failed: {e}")
        return False


# ─── Telegram Handlers ──────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সব ধরনের মেসেজ হ্যান্ডেল করে - ফাইলসহ"""
    if not await is_allowed_user(update):
        await update.message.reply_text("⛔ আপনি এই বট ব্যবহার করার অনুমতি পাচ্ছেন না।")
        return
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_name = user.full_name if user else "Unknown"
    
    # ── মেসেজ টাইপ ডিটেক্ট ──────────────────────────────────────────
    message_type = "unknown"
    file_info = None
    file_name = None
    file = None
    caption = ""
    
    if update.message.text:
        message_type = "text"
        text = update.message.text
        logger.info(f"📝 Text from {user_name}: {text[:50]}...")
        
        await update.message.reply_text(
            f"✅ ইয়ে আমি সফলভাবে কানেক্ট হয়েছি!\n\n"
            f"আপনার মেসেজ: {text[:100]}\n"
            f"📊 টাইপ: টেক্সট"
        )
        return
    
    elif update.message.photo:
        message_type = "photo"
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_name = f"photo_{photo.file_id[:8]}.jpg"
        file_info = {"file_id": photo.file_id, "file_size": photo.file_size}
        caption = update.message.caption or ""
        logger.info(f"📷 Photo from {user_name}")
        
    elif update.message.document:
        message_type = "document"
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        file_name = doc.file_name or f"document_{doc.file_id[:8]}"
        file_info = {
            "file_id": doc.file_id,
            "file_size": doc.file_size,
            "file_name": doc.file_name,
            "mime_type": doc.mime_type,
        }
        caption = update.message.caption or ""
        logger.info(f"📁 Document from {user_name}: {file_name}")
        
    elif update.message.video:
        message_type = "video"
        video = update.message.video
        file = await context.bot.get_file(video.file_id)
        file_name = f"video_{video.file_id[:8]}.mp4"
        file_info = {
            "file_id": video.file_id,
            "file_size": video.file_size,
            "duration": video.duration,
        }
        caption = update.message.caption or ""
        logger.info(f"🎬 Video from {user_name}")
        
    elif update.message.audio:
        message_type = "audio"
        audio = update.message.audio
        file = await context.bot.get_file(audio.file_id)
        file_name = audio.file_name or f"audio_{audio.file_id[:8]}.mp3"
        file_info = {
            "file_id": audio.file_id,
            "file_size": audio.file_size,
            "duration": audio.duration,
            "performer": audio.performer,
            "title": audio.title,
        }
        caption = update.message.caption or ""
        logger.info(f"🎵 Audio from {user_name}")
        
    elif update.message.voice:
        message_type = "voice"
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        file_name = f"voice_{voice.file_id[:8]}.ogg"
        file_info = {
            "file_id": voice.file_id,
            "file_size": voice.file_size,
            "duration": voice.duration,
        }
        logger.info(f"🎤 Voice from {user_name}")
        
    elif update.message.video_note:
        message_type = "video_note"
        vn = update.message.video_note
        file = await context.bot.get_file(vn.file_id)
        file_name = f"videonote_{vn.file_id[:8]}.mp4"
        file_info = {
            "file_id": vn.file_id,
            "file_size": vn.file_size,
            "duration": vn.duration,
        }
        logger.info(f"🎥 Video Note from {user_name}")
        
    elif update.message.sticker:
        message_type = "sticker"
        sticker = update.message.sticker
        file = await context.bot.get_file(sticker.file_id)
        file_name = f"sticker_{sticker.file_id[:8]}.webp"
        file_info = {
            "file_id": sticker.file_id,
            "file_size": sticker.file_size,
            "emoji": sticker.emoji,
        }
        logger.info(f"🎨 Sticker from {user_name}")
        
    elif update.message.location:
        message_type = "location"
        loc = update.message.location
        file_info = {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
        }
        logger.info(f"📍 Location from {user_name}")
        
    elif update.message.contact:
        message_type = "contact"
        contact = update.message.contact
        file_info = {
            "phone_number": contact.phone_number,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
        }
        logger.info(f"👤 Contact from {user_name}")
        
    else:
        await update.message.reply_text("❓ আমি এই ধরনের মেসেজ চিনতে পারিনি।")
        return
    
    # ── ফাইল ডাউনলোড করো ────────────────────────────────────────────
    download_path = None
    if file and file_name:
        try:
            download_path = DOWNLOAD_DIR / file_name
            await file.download_to_drive(download_path)
            logger.info(f"✅ ফাইল ডাউনলোড হয়েছে: {download_path}")
        except Exception as e:
            logger.error(f"❌ ফাইল ডাউনলোড ব্যর্থ: {e}")
    
    # ── Private Space-এ ফরওয়ার্ড করো ──────────────────────────────
    forward_data = {
        "chat_id": chat_id,
        "user_id": user.id,
        "user_name": user_name,
        "message_type": message_type,
        "file_info": file_info,
        "caption": caption,
        "download_path": str(download_path) if download_path else None,
    }
    await forward_to_private_space(forward_data)
    
    # ── রিপ্লাই দাও ──────────────────────────────────────────────────
    reply_text = (
        f"✅ ইয়ে আমি সফলভাবে কানেক্ট হয়েছি!\n\n"
        f"📊 মেসেজ টাইপ: {message_type}\n"
        f"👤 পাঠিয়েছেন: {user_name}\n"
        f"📁 ফাইল: {file_name or 'না'}\n"
        f"💾 সাইজ: {file_info.get('file_size', 'N/A') if file_info else 'N/A'} bytes\n"
        f"📥 ডাউনলোড: {'✅ সম্পন্ন' if download_path else '❌ ব্যর্থ'}"
    )
    
    await update.message.reply_text(reply_text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start কমান্ড হ্যান্ডেলার"""
    if not await is_allowed_user(update):
        await update.message.reply_text("⛔ আপনি এই বট ব্যবহার করার অনুমতি পাচ্ছেন না।")
        return
    
    await update.message.reply_text(
        "👋 হ্যালো! আমি আপনার Telegram Relay Bot!\n\n"
        "আমি নিচের জিনিসগুলো হ্যান্ডেল করতে পারি:\n"
        "📝 টেক্সট\n📷 ফটো\n📁 ডকুমেন্ট\n🎬 ভিডিও\n"
        "🎵 অডিও\n🎤 ভয়েস\n🎨 স্টিকার\n📍 লোকেশন\n👤 কন্ট্যাক্ট\n\n"
        "আমাকে যেকোনো কিছু পাঠান, আমি রিপ্লাই দেব!"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """এরর হ্যান্ডেলার"""
    logger.error(f"❌ Update {update} caused error: {context.error}")


# ─── FastAPI Routes ──────────────────────────────────────────────────────

@spaces.GPU
def _zerogpu_placeholder():
    return "not used — placeholder for ZeroGPU hardware requirement"


async def setup_telegram_bot():
    """Telegram Bot সেটআপ করে"""
    global telegram_app
    
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN সেট নেই")
        return False
    
    # Application তৈরি করো
    telegram_app = Application.builder() \
        .token(TELEGRAM_BOT_TOKEN) \
        .request(telegram_request) \
        .build()
    
    # হ্যান্ডলার যোগ করো
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.ALL, handle_message))
    telegram_app.add_error_handler(error_handler)
    
    # Webhook সেট করো
    public_url = await get_public_url()
    webhook_url = f"{public_url}/webhook_telegram"
    
    logger.info(f"🌐 Public URL: {public_url}")
    logger.info(f"🔗 Setting webhook to: {webhook_url}")
    
    try:
        await telegram_app.bot.set_webhook(
            url=webhook_url,
            secret_token=RELAY_SECRET,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
        logger.info(f"✅ Webhook সেট করা হয়েছে: {webhook_url}")
        
        info = await telegram_app.bot.get_webhook_info()
        logger.info(f"📋 Webhook Info: {info}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Webhook সেট করতে ব্যর্থ: {e}")
        return False


@app.on_event("startup")
async def startup():
    """অ্যাপ স্টার্টআপে Telegram Webhook সেট করে"""
    _zerogpu_placeholder()
    if TELEGRAM_BOT_TOKEN:
        await setup_telegram_bot()
    else:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN সেট নেই")


@app.on_event("shutdown")
async def shutdown():
    await client.aclose()
    if telegram_app:
        await telegram_app.shutdown()


# ─── Telegram Webhook Endpoint ──────────────────────────────────────────
@app.post("/webhook_telegram")
async def telegram_webhook(request: Request):
    """Telegram থেকে Webhook কল এখানে আসবে"""
    if RELAY_SECRET:
        got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if got != RELAY_SECRET:
            logger.warning("❌ Webhook: invalid secret token")
            return Response(status_code=403, content='{"ok": false, "error": "forbidden"}')
    
    try:
        body = await request.body()
        data = json.loads(body)
        
        if telegram_app:
            update = Update.de_json(data, telegram_app.bot)
            if update:
                await telegram_app.process_update(update)
                return Response(content='{"ok": true}', status_code=200)
        
        return Response(content='{"ok": false, "error": "bot not ready"}', status_code=503)
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return Response(content='{"ok": false, "error": "internal error"}', status_code=500)


# ─── Old Webhook (Backward Compatible) ──────────────────────────────────
@app.post("/webhook")
async def old_webhook(request: Request):
    """পুরোনো webhook - Private Space-এ ফরওয়ার্ড"""
    if not PRIVATE_SPACE_URL:
        return Response(status_code=500, content='{"error":"private_space_not_configured"}')
    
    body = await request.body()
    headers = {"Content-Type": "application/json"}
    if PRIVATE_SPACE_TOKEN:
        headers["Authorization"] = f"Bearer {PRIVATE_SPACE_TOKEN}"
    
    try:
        resp = await client.post(f"{PRIVATE_SPACE_URL}/webhook", content=body, headers=headers)
        return Response(content=resp.content, status_code=resp.status_code)
    except Exception as e:
        logger.error(f"❌ Private Space forward failed: {e}")
        return Response(status_code=502, content='{"error":"private_space_unreachable"}')


# ─── Health Check ──────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "private_space_configured": bool(PRIVATE_SPACE_URL),
        "relay_secret_configured": bool(RELAY_SECRET),
        "telegram_bot_configured": bool(TELEGRAM_BOT_TOKEN),
        "telegram_chat_configured": bool(TELEGRAM_ALLOWED_CHAT_ID),
        "public_url": await get_public_url(),
        "webhook_set": bool(telegram_app),
    }


@app.get("/")
async def index():
    return {
        "status": "running",
        "role": "telegram-public-relay",
        "telegram_bot_configured": bool(TELEGRAM_BOT_TOKEN),
        "public_url": await get_public_url(),
    }


# ─── Main ──────────────────────────────────────────────────────────────
def main():
    with gr.Blocks(title="Telegram Public Relay") as demo:
        gr.Markdown(
            "## 🤖 Telegram Public Relay\n"
            "Status: running\n\n"
            f"Telegram Bot: **{'✅ Configured' if TELEGRAM_BOT_TOKEN else '❌ Missing'}**\n"
            f"Allowed Chat: **{TELEGRAM_ALLOWED_CHAT_ID or 'All users'}**\n"
            f"Private Space: **{'✅' if PRIVATE_SPACE_URL else '❌'}**\n\n"
            f"📥 Downloads: `{DOWNLOAD_DIR}`"
        )

    global app
    app = mount_gradio_app(app, demo, path="/ui")

    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()