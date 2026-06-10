#!/bin/bash
set -euo pipefail

echo "======================================"
echo "  HFS_1 v8: Gemma 4 12B Q2_K"
echo "  llama-server binary (zero compile)"
echo "======================================"

if ! command -v llama-server > /dev/null 2>&1; then
    echo "llama-server পাওয়া গেল না!"
    exit 1
fi
echo "llama-server ready"

echo "মডেল ডাউনলোড..."
python3 /app/download_model.py

if [ ! -f "/app/models/model.gguf" ]; then
    echo "মডেল নেই!"
    exit 1
fi

SIZE=$(du -sh /app/models/model.gguf | cut -f1)
echo "মডেল প্রস্তুত ($SIZE)"

echo "API Server চালু (port 7860)..."
exec python3 /app/api_server.py