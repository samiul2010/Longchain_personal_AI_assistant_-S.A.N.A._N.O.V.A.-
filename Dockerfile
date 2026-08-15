# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    nodejs \
    npm \
    golang-go \
    && rm -rf /var/lib/apt/lists/*

#-------git_hub_mcp_server_install---------------
RUN git clone --depth 1 https://github.com/github/github-mcp-server.git /tmp/github-mcp-server \
    && cd /tmp/github-mcp-server \
    && go build -o /usr/local/bin/github-mcp-server ./cmd/github-mcp-server \
    && chmod +x /usr/local/bin/github-mcp-server \
    && rm -rf /tmp/github-mcp-server
#-------ALL_MCP_GLOBALE_INSTALL_COMAND---------------
RUN npm install -g \
  @zereight/mcp-gitlab \
  maagpi-youtube-mcp \
  @justanothermldude/mcp-exec \

# ── Persistent memory directory shared by every agent ─────────────────────────
# NOTE: on Hugging Face Spaces, attach your Persistent Storage volume at this
# exact path (/agent). This mkdir/chmod is only a fallback for local/dev runs
# where no volume is mounted — once HF's storage bucket is mounted at /agent,
# its own permissions apply and this app writes only inside it.
RUN mkdir -p /agent && chmod -R 777 /agent

# ── Non-root user (required by Hugging Face Spaces) ──────────────────────────
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR $HOME/app

# ── Install Python dependencies BEFORE copying code (layer cache) ─────────────
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────────────────────────
COPY --chown=user . .

# ── Switch to non-root user ───────────────────────────────────────────────────
USER user

# ── Expose web UI port (HF Spaces default) ─────────────────────────────────────
EXPOSE 7860

# ── Healthcheck ────────────────────────────────────────────────────────────────
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s \
    CMD curl -f http://localhost:7860/ || exit 1

# ── Launch app (FastAPI + Manus-style UI) ───────────────────────────────────────
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
