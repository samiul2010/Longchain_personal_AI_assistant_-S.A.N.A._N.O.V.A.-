#!/bin/bash
# ============================================================
# start.sh — HFS_1 startup script
# ক্রম:
#   1. মডেল ডাউনলোড (না থাকলে)
#   2. llama-server চালু (port 8080, OpenAI-compatible)
#   3. health_proxy চালু (port 7860, public)
# ============================================================

set -euo pipefail

echo "======================================"
echo "  HFS_1: Gemma 4 12B API Server"
echo "======================================"

# ── Step 1: মডেল ডাউনলোড ───────────────────────────────────
echo ""
echo "📥 Step 1: মডেল ডাউনলোড চেক করছি..."
python3 /app/download_model.py

MODEL_PATH="/app/models/model.gguf"
if [ ! -f "$MODEL_PATH" ]; then
    echo "❌ মডেল ফাইল পাওয়া যাচ্ছে না: $MODEL_PATH"
    exit 1
fi

MODEL_SIZE=$(du -sh "$MODEL_PATH" | cut -f1)
echo "✅ মডেল প্রস্তুত: $MODEL_PATH ($MODEL_SIZE)"

# ── Step 2: llama-server চালু করা ───────────────────────────
echo ""
echo "🚀 Step 2: llama-server চালু হচ্ছে (port 8080)..."

# CPU thread count (free tier: 2 vCPU)
CPU_THREADS=${CPU_THREADS:-2}

# Context window (16GB RAM এ 4096 নিরাপদ)
CTX_SIZE=${CTX_SIZE:-4096}

llama-server \
    --model "$MODEL_PATH" \
    --host 127.0.0.1 \
    --port 8080 \
    --threads "$CPU_THREADS" \
    --ctx-size "$CTX_SIZE" \
    --n-predict -1 \
    --temp 0.7 \
    --top-p 0.95 \
    --top-k 64 \
    --repeat-penalty 1.1 \
    --batch-size 512 \
    --ubatch-size 512 \
    --chat-template gemma \
    --log-disable \
    --no-mmap \
    &

LLAMA_PID=$!
echo "llama-server PID: $LLAMA_PID"

# ── Step 3: llama-server ready হওয়ার জন্য অপেক্ষা ──────────
echo ""
echo "⏳ Step 3: llama-server প্রস্তুত হওয়ার জন্য অপেক্ষা করছি..."

MAX_WAIT=300   # 5 মিনিট সর্বোচ্চ অপেক্ষা
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s -f http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "✅ llama-server চালু আছে! (${WAITED}s অপেক্ষার পর)"
        break
    fi

    # llama-server process মরে গেলে exit
    if ! kill -0 $LLAMA_PID 2>/dev/null; then
        echo "❌ llama-server বন্ধ হয়ে গেছে!"
        exit 1
    fi

    sleep 5
    WAITED=$((WAITED + 5))
    echo "  ... অপেক্ষা করছি (${WAITED}/${MAX_WAIT}s)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "❌ llama-server timeout! ${MAX_WAIT}s এর মধ্যে চালু হয়নি"
    kill $LLAMA_PID 2>/dev/null || true
    exit 1
fi

# ── Step 4: API test ──────────────────────────────────────────
echo ""
echo "🧪 Step 4: API test করছি..."
TEST_RESPONSE=$(curl -s \
    -X POST http://127.0.0.1:8080/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"gemma","messages":[{"role":"user","content":"Hi"}],"max_tokens":10}' \
    2>&1 || true)

if echo "$TEST_RESPONSE" | grep -q "choices"; then
    echo "✅ API test সফল!"
else
    echo "⚠️  API test সম্পূর্ণ সফল হয়নি, তবে সার্ভার চলছে"
    echo "Response: $TEST_RESPONSE"
fi

# ── Step 5: Proxy server চালু করা (port 7860) ───────────────
echo ""
echo "🌐 Step 5: Proxy server চালু হচ্ছে (port 7860 - public)..."
echo "======================================"
echo "  সার্ভার সম্পূর্ণ প্রস্তুত!"
echo "  API: POST /v1/chat/completions"
echo "  Health: GET /health"
echo "======================================"

# Trap SIGTERM to cleanup
cleanup() {
    echo "🛑 Shutting down..."
    kill $LLAMA_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Proxy চালু (foreground — এটাই main process)
exec python3 /app/health_proxy.py
