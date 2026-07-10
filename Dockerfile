# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user (required by Hugging Face Spaces) ──────────────────────────
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# ── Install Python dependencies ───────────────────────────────────────────────
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────────────────────────
COPY --chown=user . .

USER user

EXPOSE 7860

HEALTHCHECK --interval=60s --timeout=10s --start-period=15s \
    CMD curl -f http://localhost:7860/health || exit 1

CMD ["python", "app.py"]
