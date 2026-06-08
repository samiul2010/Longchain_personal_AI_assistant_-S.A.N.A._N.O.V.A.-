#!/usr/bin/env python3
"""
download_model.py  —  HFS_1 v2
Gemma 4 12B Q4_K_M GGUF মডেল ডাউনলোড করে /app/models/model.gguf এ রাখে।

Sources (ক্রমে চেষ্টা করে):
  1. ggml-org/gemma-4-12B-it-GGUF  (official)
  2. bartowski/gemma-4-12b-it-GGUF  (backup)
"""

import os
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

TARGET = Path("/app/models/model.gguf")
MIN_SIZE_BYTES = 1_000_000_000  # 1GB minimum — corrupt check

# HF_TRANSFER → faster parallel downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

HF_TOKEN = os.environ.get("HF_TOKEN", None)

SOURCES = [
    # (repo_id, filename)
    ("ggml-org/gemma-4-12B-it-GGUF",  "gemma-4-12B-it-Q4_K_M.gguf"),
    ("bartowski/gemma-4-12b-it-GGUF", "gemma-4-12b-it-Q4_K_M.gguf"),
    # যদি উপরেরগুলো না চলে তাহলে Q3 চেষ্টা করো (smaller)
    ("ggml-org/gemma-4-12B-it-GGUF",  "gemma-4-12B-it-Q3_K_M.gguf"),
]


def download():
    # ইতিমধ্যে ডাউনলোড আছে কিনা দেখো
    if TARGET.exists() and TARGET.stat().st_size > MIN_SIZE_BYTES:
        gb = TARGET.stat().st_size / 1e9
        log.info(f"✅ মডেল ইতিমধ্যে আছে: {TARGET} ({gb:.1f} GB) — skip")
        return

    TARGET.parent.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import hf_hub_download

    for repo_id, filename in SOURCES:
        try:
            log.info(f"⬇️  ডাউনলোড চেষ্টা: {repo_id}/{filename}")
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=TARGET.parent,
                token=HF_TOKEN,
                repo_type="model",
            )
            downloaded = Path(path)
            # Target path এ rename
            if downloaded.resolve() != TARGET.resolve():
                downloaded.rename(TARGET)

            gb = TARGET.stat().st_size / 1e9
            log.info(f"✅ ডাউনলোড সফল! {gb:.1f} GB → {TARGET}")
            return

        except Exception as e:
            log.warning(f"⚠️  {repo_id} ব্যর্থ: {e}")
            # অসম্পূর্ণ ফাইল মুছে ফেলো
            candidate = TARGET.parent / filename
            if candidate.exists():
                candidate.unlink()
            continue

    log.error("❌ সব source থেকে ডাউনলোড ব্যর্থ!")
    sys.exit(1)


if __name__ == "__main__":
    download()
