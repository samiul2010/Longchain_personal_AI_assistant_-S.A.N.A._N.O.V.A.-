#!/bin/bash
# ============================================================
# start_v8.sh
# ============================================================
#৳৳
set -euo pipefail

echo "======================================"
echo "  HFS_1 v8: Gemma 4 12B Q2_K"
echo "  llama-server binary (zero compile)"
echo "======================================"

# binary চেক
if ! command -v llama-server &> /dev/null; then
    echo "❌ llama-server পাওয়া গেল না!"
    exit 1
fi
echo "✅ llama-server ready"

echo ""
echo "📥 মডেল ডাউনলোড (Q2_K ~4.1GB)..."
python3 /app/download_model.py

if [ ! -f "/app/models/model.gguf" ]; then
    echo "❌ মডেল নেই!"
    exi