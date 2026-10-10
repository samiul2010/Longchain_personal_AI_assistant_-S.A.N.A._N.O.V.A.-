# ── Base image ────────────────────────────────────────────────────────────────
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99
ENV HOME=/home/user
ENV PYTHONUNBUFFERED=1

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    nodejs \
    npm \
    golang-go \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    ca-certificates \
    rsync \
    && rm -rf /var/lib/apt/lists/*
   
#-------------------agent_PC------------------------------
# ⚠️ PPA যোগ করুন প্রথমে — firefox-esr এর জন্যে
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:mozillateam/ppa \
    && apt-get update \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xfce4 \
    xfce4-terminal \
    thunar \
    dbus-x11 \
    at-spi2-core \
    python3-pyatspi \
    gir1.2-atspi-2.0 \
    python3-gi \
    firefox-esr \
    x11-utils \
    x11-xserver-utils \
    xdotool \
    libreoffice-writer \
    libreoffice-calc \
    fonts-liberation \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*
#------------PC_permission-------------  
ENV NO_AT_BRIDGE=0
ENV GTK_MODULES=gail:atk-bridge
ENV ACCESSIBILITY_ENABLED=1
ENV MOZ_ACCESSIBILITY_HANDLER=1
ENV QT_ACCESSIBILITY=1
ENV DISPLAY=:99
#-------git_hub_mcp_server_install---------------
RUN git clone --depth 1 https://github.com/github/github-mcp-server.git /tmp/github-mcp-server \
    && cd /tmp/github-mcp-server \
    && go build -o /usr/local/bin/github-mcp-server ./cmd/github-mcp-server \
    && chmod +x /usr/local/bin/github-mcp-server \
    && rm -rf /tmp/github-mcp-server
#-------ALL_MCP_GLOBALE_INSTALL_COMAND---------------
RUN npm install -g \
  @zereight/mcp-gitlab \
  maagpi-youtube-mcp

# ── Non-root user (required by Hugging Face Spaces) ──────────────────────────
RUN userdel -r ubuntu 2>/dev/null || true \
    && groupdel ubuntu 2>/dev/null || true \
    && useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
# ── Persistent memory directory shared by every agent ─────────────────────────
# NOTE: on Hugging Face Spaces, attach your Persistent Storage volume at this
# exact path (/agent). This mkdir/chmod is only a fallback for local/dev runs
# where no volume is mounted — once HF's storage bucket is mounted at /agent,
# its own permissions apply and this app writes only inside it.
RUN mkdir -p /agent && chown -R user:user /agent

# ── Python: single interpreter, symlink for 'python' ──
RUN ln -sf /usr/bin/python3 /usr/local/bin/python && \
    python3 -m pip install --no-cache-dir --upgrade pip
# ── Install Python dependencies BEFORE copying code (layer cache) ─────────────
COPY --chown=user requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────────────────────────
COPY --chown=user . .
#--------coppy_pc-----------------------
COPY --chown=user entrypoint.sh /home/user/entrypoint.sh
RUN chmod +x /home/user/entrypoint.sh
# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR $HOME/app
RUN chown -R user:user $HOME/app

# ── Switch to non-root user ───────────────────────────────────────────────────

USER user

# ── Expose web UI port (HF Spaces default) ─────────────────────────────────────
EXPOSE 7860

# ── Healthcheck ────────────────────────────────────────────────────────────────
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s \
    CMD curl -f http://localhost:7860/ || exit 1

# ── Launch app (FastAPI + Manus-style UI) ───────────────────────────────────────
#CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
ENTRYPOINT ["/home/user/entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
