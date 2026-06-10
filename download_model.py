#!/usr/bin/env python3
# ============================================================
# download_model_v8.py
# Gemma 4 12B Q2_K (~4.1GB) ডাউনলোড করে
# Q2_K কেন: RAM মাত্র ~6GB → 16GB HFS তে নিরাপদ
# ============================================================

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
MIN_SIZE_BYTES = 500_000_000  # 500MB

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
HF_TOKEN = os.environ.get("HF_TOKEN", None)

SOURCES = [
    ("unsloth/gemma-4-E4B-it-GGUF", "gemma-4-E4B-it-Q4_K_M.gguf"),
]


def download():
    if TARGET.exists() and TARGET.stat().st_size > MIN_SIZE_BYTES:
        gb = TARGET.stat().st_size / 1e9
        log.info(f"✅ মডেল আছে ({gb:.1f} GB) — skip")
        return

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import hf_hub_download

    for repo_id, filename in SOURCES:
        try:
            log.info(f"⬇️  ডাউনলোড: {repo_id}/{filename}")
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=TARGET.parent,
                token=HF_TOKEN,
                repo_type="model",
            )
            downloaded = Path(path)
            if downloaded.resolve() != TARGET.resolve():
                downloaded.rename(TARGET)
            gb = TARGET.stat().st_size / 1e9
            log.info(f"✅ সফল! {gb:.1f} GB → {TARGET}")
            return
        except Exception as e:
            log.warning(f"⚠️  {repo_id} ব্যর্থ: {e}")
            candidate = TARGET.parent / filename
            if candidate.exists():
                candidate.unlink()

    log.error("❌ ডাউনলোড ব্যর্থ!")
    sys.exit(1)


if __name__ == "__main__":
    download()
