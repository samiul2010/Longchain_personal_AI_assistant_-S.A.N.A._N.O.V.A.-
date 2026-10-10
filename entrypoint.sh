#!/bin/bash
# Starts the background "desktop" services the agent_pc needs, then execs
# whatever CMD was passed (uvicorn) as the container's real foreground
# process - that's the process HF Spaces/Docker actually tracks the
# container's lifecycle by, and the one that receives signals on shutdown.
set -e

echo "[agent_pc] starting dbus..."
mkdir -p /var/run/dbus
dbus-daemon --system --fork || echo "[agent_pc] system dbus already running or unavailable, continuing"
eval "$(dbus-launch --sh-syntax)"
export DBUS_SESSION_BUS_ADDRESS

echo "[agent_pc] starting Xvfb on display $DISPLAY..."
Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp &
XVFB_PID=$!

# give Xvfb a moment to actually open the display before anything else
# tries to connect to it
for i in $(seq 1 20); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        break
    fi
    sleep 0.3
done

echo "[agent_pc] starting XFCE session..."
startxfce4 >/tmp/xfce4.log 2>&1 &
XFCE_PID=$!

echo "[agent_pc] desktop ready, starting app: $*"
# exec (not just "run") replaces this shell process with uvicorn, so
# uvicorn becomes PID 1's direct child and receives SIGTERM correctly on
# container stop/restart.
exec "$@"
