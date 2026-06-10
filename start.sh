#!/bin/bash
# start.sh — HFS_1 v7
set -euo pipefail

echo "======================================"
echo "  HFS_1 v7: Gemma 4 12B Q2_K Server"
echo "======================================"

echo ""
echo "📥 Step 1: মডেল চেক ও ডাউনলোড..."
python3 /app/download_model.py

MODEL_PATH="/app/models/model.gguf"
if [ ! -f "$MODEL_PATH" ]; then
    echo "❌ মডেল ফাইল পাওয়া গেল না"
    exit 1
fi

SIZE=$(du -sh "$MODEL_PATH" | cut -f1)
echo "✅ মডেল প্রস্তুত ($SIZE)"

echo ""
echo "🚀 Step 2: API Server চালু হচ্ছে (port 7860)..."
echo "======================================"

exec python3 /app/api_server.py
