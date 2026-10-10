#!/bin/bash
# ──────────────────────────────────────────────────────────────
# entrypoint.sh — agent_pc bootstrap
#
# Container-এর প্রবেশদ্বার: dbus + Xvfb + AT-SPI + XFCE চালু করে,
# তারপর CMD (uvicorn) exec করে।
# ──────────────────────────────────────────────────────────────
set -e

# ── ১. Session dbus ───────────────────────────────────────────
echo "[agent_pc] starting session dbus..."
eval "$(dbus-launch --sh-syntax)"
export DBUS_SESSION_BUS_ADDRESS
echo "[agent_pc] DBUS_SESSION_BUS_ADDRESS set"

# ── ২. Virtual display ────────────────────────────────────────
echo "[agent_pc] starting Xvfb on display $DISPLAY..."
Xvfb "$DISPLAY" -screen 0 1440x900x24 -nolisten tcp &
XVFB_PID=$!

# wait for Xvfb ready
for i in $(seq 1 20); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        echo "[agent_pc] Xvfb ready"
        break
    fi
    sleep 0.3
done

# ── ৩. AT-SPI daemons (এজেন্টের চোখ) ────────────────────────
echo "[agent_pc] starting AT-SPI services..."
/usr/libexec/at-spi-bus-launcher --launch-immediately &
sleep 1
/usr/libexec/at-spi2-registryd &
sleep 1
echo "[agent_pc] AT-SPI services started"

# ── ৪. XFCE window manager ────────────────────────────────────
echo "[agent_pc] starting XFCE session..."
startxfce4 >/tmp/xfce4.log 2>&1 &
XFCE_PID=$!
sleep 3
echo "[agent_pc] XFCE ready"

# ── ৫. Firefox (optional, এজেন্টের প্রাথমিক browsing) ────────
echo "[agent_pc] launching Firefox..."
firefox-esr >/tmp/firefox.log 2>&1 &
sleep 5
echo "[agent_pc] Firefox launched"

# ── ৬. Main app (uvicorn) ────────────────────────────────────
echo "[agent_pc] desktop ready, starting app: $*"
exec "$@"