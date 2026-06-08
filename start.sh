#!/bin/bash
# ============================================================
# start.sh — HFS_1 v2 startup
# ক্রম:
#   1. মডেল ডাউনলোড (না থাকলে)
#   2. api_server.py চালু (port 7860 — মডেল লোড + API একসাথে)
# ============================================================
set -euo pipefail

echo "======================================"
echo "  HFS_1 v2: Gemma 4 12B API Server"
echo "======================================"

# ── Step 1: মডেল ডাউনলোড ────────────────────────────────────
echo ""
echo "📥 Step 1: মডেল চেক ও ডাউনলোড..."
python3 /app/download_model.py

MODEL_PATH="/app/models/model.gguf"
if [ ! -f "$MODEL_PATH" ]; then
    echo "❌ মডেল ফাইল পাওয়া গেল না: $MODEL_PATH"
    exit 1
fi

SIZE=$(du -sh "$MODEL_PATH" | cut -f1)
echo "✅ মডেল প্রস্তুত ($SIZE)"

# ── Step 2: API server চালু করা (port 7860) ─────────────────
echo ""
echo "🚀 Step 2: API Server চালু হচ্ছে (port 7860)..."
echo "   মডেল লোড সময় নেবে — /health poll করে wait করুন"
echo "======================================"

exec python3 /app/api_server.py
