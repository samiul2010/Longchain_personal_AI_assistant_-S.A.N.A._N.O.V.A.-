---
title: HFS1 Gemma4 12B API
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
app_port: 7860
---

# HFS_1 — Gemma 4 12B LLM API Server

এই Space টি একটি **OpenAI-compatible REST API** সার্ভার যা **Gemma 4 12B** মডেল চালায়।

## 🧠 মডেল তথ্য
- **Model**: Google Gemma 4 12B Instruction-tuned
- **Format**: GGUF Q4_K_M quantization (~7.4GB)
- **Engine**: llama.cpp (CPU optimized)
- **API Style**: OpenAI-compatible

## 📡 API Endpoints

### Chat Completion
```
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "gemma-4-12b",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "আপনার প্রশ্ন এখানে"}
  ],
  "max_tokens": 512,
  "temperature": 0.7,
  "stream": false
}
```

### Available Models
```
GET /v1/models
```

### Health Check
```
GET /health
```

## 🔗 HFS_2 (CrewAI Agent) সংযোগ
```python
from crewai import LLM

llm = LLM(
    model="openai/gemma-4-12b",
    base_url="https://YOUR-USERNAME-hfs1-gemma4-12b-api.hf.space/v1",
    api_key="not-required"
)
```

## ⚙️ Environment Variables (Secrets)
| Variable | বিবরণ | প্রয়োজন |
|----------|--------|----------|
| `HF_TOKEN` | HuggingFace access token (gated model এর জন্য) | Optional |
| `CPU_THREADS` | CPU thread count (default: 2) | Optional |
| `CTX_SIZE` | Context window size (default: 4096) | Optional |

## 📝 নোট
- Free tier: 2 vCPU, 16GB RAM — inference ধীর হবে (~5-15 tokens/sec)
- প্রথম start এ মডেল ডাউনলোড হয় (~7.4GB) — সময় লাগবে
- Space idle থাকলে sleep হবে — প্রথম request এ জাগতে সময় নেবে
