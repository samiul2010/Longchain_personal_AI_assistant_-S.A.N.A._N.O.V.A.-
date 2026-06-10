#!/bin/bash
set -euo pipefail

echo "======================================"
echo "  HFS_1 v8: Gemma 4 12B"
echo "======================================"

echo "llama-server খুঁজছি..."
find / -name "llama-server" 2>/dev/null || echo "কোথাও নেই!"
which llama-server 2>/dev/null || echo "PATH এ নেই"
ls /app/ 2>/dev/null || echo "/app নেই"
ls /usr/local/bin/ 2>/dev/null | grep llama || echo "/usr/local/bin এ নেই"

echo "সব শেষ — উপরের output দেখে path জানাও"
sleep 3600