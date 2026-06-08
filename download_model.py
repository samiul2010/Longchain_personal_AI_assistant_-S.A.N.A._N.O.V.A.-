#!/usr/bin/env python3
"""
download_model.py
-----------------
Gemma 4 12B GGUF মডেল ডাউনলোড করে।
- Primary:  ggml-org/gemma-4-12B-it-GGUF  (Q4_K_M ~7.4GB)
- Fallback: unsloth/gemma-4-12b-it-GGUF   (Q4_K_M)

HuggingFace free tier: 50GB disk, 16GB RAM
Q4_K_M quantization → ~7.4GB disk, ~8-9GB RAM during inference
"""

import os
import sys
import logging
from pathlib import Path
from huggingface_hub import hf_hub_download, snapshot_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────
MODEL_DIR = Path("/app/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Gemma 4 12B IT (instruction-tuned) Q4_K_M
# ~7.4GB — free tier এ চলবে
PRIMARY_REPO   = "ggml-org/gemma-4-12B-it-GGUF"
PRIMARY_FILE   = "gemma-4-12B-it-Q4_K_M.gguf"

FALLBACK_REPO  = "bartowski/gemma-4-12b-it-GGUF"
FALLBACK_FILE  = "gemma-4-12b-it-Q4_K_M.gguf"

# HF token (HuggingFace Space Secret থেকে পাবে)
HF_TOKEN = os.environ.get("HF_TOKEN", None)

TARGET_PATH = MODEL_DIR / "model.gguf"


def download_model() -> Path:
    """মডেল ডাউনলোড করে target path এ রাখে।"""

    if TARGET_PATH.exists() and TARGET_PATH.stat().st_size > 1_000_000_000:
        log.info(f"✅ মডেল আগেই ডাউনলোড করা আছে: {TARGET_PATH} ({TARGET_PATH.stat().st_size / 1e9:.1f} GB)")
        return TARGET_PATH

    log.info("📥 মডেল ডাউনলোড শুরু হচ্ছে...")

    # Enable hf_transfer for faster downloads
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

    attempts = [
        (PRIMARY_REPO,  PRIMARY_FILE),
        (FALLBACK_REPO, FALLBACK_FILE),
    ]

    for repo_id, filename in attempts:
        try:
            log.info(f"⬇️  চেষ্টা করছি: {repo_id} / {filename}")
            downloaded = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=MODEL_DIR,
                token=HF_TOKEN,
                repo_type="model",
            )
            # Rename to standard name
            src = Path(downloaded)
            if src != TARGET_PATH:
                src.rename(TARGET_PATH)

            size_gb = TARGET_PATH.stat().st_size / 1e9
            log.info(f"✅ ডাউনলোড সফল! ফাইল: {TARGET_PATH} ({size_gb:.1f} GB)")
            return TARGET_PATH

        except Exception as e:
            log.warning(f"⚠️  {repo_id} থেকে ডাউনলোড ব্যর্থ: {e}")
            continue

    log.error("❌ সব source থেকে ডাউনলোড ব্যর্থ হয়েছে!")
    sys.exit(1)


if __name__ == "__main__":
    path = download_model()
    log.info(f"মডেল প্রস্তুত: {path}")
