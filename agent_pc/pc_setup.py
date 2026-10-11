#!/usr/bin/env python3
"""
agent_pc.pc_setup — এজেন্টের পার্সোনাল কম্পিউটারের ফাইটার রুট।

এই ফাইল যা করে:
  ১. Environment verify (packages, modules, AT-SPI)
  ২. ভার্চুয়াল ডিসপ্লে (Xvfb), dbus, AT-SPI, XFCE চালু
  ৩. always_ready apps চালু (Firefox, Files)
  ৪. Backup থেকে restore (backup_&_restore.py)
  ৫. Periodic backup loop শুরু
  ৬. Tool instances initialize (pc_to_agent + tools)
  ৭. LangChain tools export (AGENT_PC_TOOLS)

ব্যবহার:
  # main() — bootstrap + exec uvicorn:
  python3 -m agent_pc.pc_setup --serve uvicorn app:app --host 0.0.0.0 --port 7860

  # agent.py-তে — শুধু tools import:
  from agent_pc.pc_setup import AGENT_PC_TOOLS
  tools = [*existing_tools, *AGENT_PC_TOOLS]
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
META_PATH = HERE / "pc_setup_meta.json"
LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Track child processes for cleanup
PROCS: list[subprocess.Popen] = []


# ═══════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════
def log(msg: str) -> None:
    print(f"[pc_setup] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════
# ১. Load meta
# ═══════════════════════════════════════════════════════════════════
def load_meta() -> dict:
    if not META_PATH.exists():
        log(f"⚠️ meta not found: {META_PATH} — using defaults")
        return {
            "desktop": {"display": ":99", "resolution": "1440x900x24"},
            "accessibility": {
                "at_spi_bus": "/usr/libexec/at-spi-bus-launcher",
                "at_spi_registry": "/usr/libexec/at-spi2-registryd",
                "wait_after_launch": 2,
            },
            "apps": {
                "always_ready": [
                    {"name": "Firefox", "command": "firefox-esr", "start_delay": 5},
                    {"name": "Files", "command": "thunar", "start_delay": 2},
                ],
                "on_demand": [],
            },
            "persistence": {
                "enabled": True,
                "backup_interval_seconds": 300,
            },
            "verification": {
                "required_commands": [
                    "Xvfb", "startxfce4", "firefox-esr", "dbus-launch", "xdotool"
                ],
                "required_python_modules": ["gi", "gi.repository.Atspi"],
            },
        }
    meta = json.loads(META_PATH.read_text())
    log(f"meta loaded: display={meta['desktop']['display']}, "
        f"apps_ready={len(meta['apps']['always_ready'])}")
    return meta


# ═══════════════════════════════════════════════════════════════════
# ২. Verify environment
# ═══════════════════════════════════════════════════════════════════
def verify_environment(meta: dict) -> None:
    log("verifying environment...")
    missing: list[str] = []

    from shutil import which
    for cmd in meta["verification"]["required_commands"]:
        if not which(cmd):
            missing.append(f"command: {cmd}")

    for mod in meta["verification"]["required_python_modules"]:
        try:
            if "." in mod:
                parts = mod.split(".")
                m = __import__(parts[0])
                for p in parts[1:]:
                    m = getattr(m, p)
            else:
                __import__(mod)
        except Exception as e:
            missing.append(f"python: {mod} ({e})")

    if missing:
        log("❌ MISSING DEPENDENCIES:")
        for m in missing:
            log(f"   - {m}")
        raise SystemExit(1)

    log("✅ all dependencies present")


# ═══════════════════════════════════════════════════════════════════
# ৩. Xvfb
# ═══════════════════════════════════════════════════════════════════
def start_xvfb(meta: dict) -> None:
    disp = meta["desktop"]["display"]
    res = meta["desktop"]["resolution"]

    if subprocess.run(["xdpyinfo", "-display", disp],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0:
        log(f"Xvfb already running on {disp}")
        return

    log(f"starting Xvfb on {disp} ({res})...")
    PROCS.append(subprocess.Popen(
        ["Xvfb", disp, "-screen", "0", res, "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ))

    for _ in range(30):
        if subprocess.run(["xdpyinfo", "-display", disp],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            log(f"✅ Xvfb ready on {disp}")
            return
        time.sleep(0.3)
    raise RuntimeError("Xvfb failed to start")


# ═══════════════════════════════════════════════════════════════════
# ৪. DBus session
# ═══════════════════════════════════════════════════════════════════
def start_dbus_session() -> None:
    log("starting dbus session bus...")
    out = subprocess.check_output(["dbus-launch", "--sh-syntax"], text=True)
    for line in out.splitlines():
        if line.startswith("DBUS_SESSION_BUS_ADDRESS="):
            addr = line.split("=", 1)[1].rstrip(";").strip("'\"")
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = addr
            log("✅ DBUS_SESSION_BUS_ADDRESS set")
            return
    raise RuntimeError("failed to parse dbus-launch output")


# ═══════════════════════════════════════════════════════════════════
# ৫. AT-SPI
# ═══════════════════════════════════════════════════════════════════
def start_atspi(meta: dict) -> None:
    log("starting AT-SPI services...")
    bus = meta["accessibility"]["at_spi_bus"]
    reg = meta["accessibility"]["at_spi_registry"]

    PROCS.append(subprocess.Popen(
        [bus, "--launch-immediately"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ))
    time.sleep(1)
    PROCS.append(subprocess.Popen(
        [reg],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ))
    time.sleep(meta["accessibility"]["wait_after_launch"])

    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
        d = Atspi.get_desktop(0)
        log(f"✅ AT-SPI desktop reachable (children={d.get_child_count()})")
    except Exception as e:
        log(f"⚠️ AT-SPI verify: {e}")


# ═══════════════════════════════════════════════════════════════════
# ৬. XFCE
# ═══════════════════════════════════════════════════════════════════
def start_xfce(meta: dict) -> None:
    log("starting XFCE session...")
    logfile = open(LOG_DIR / "xfce4.log", "w")
    PROCS.append(subprocess.Popen(
        ["startxfce4"], stdout=logfile, stderr=subprocess.STDOUT,
    ))
    time.sleep(4)
    log("✅ XFCE started")


# ═══════════════════════════════════════════════════════════════════
# ৭. Backup restore (startup)
# ═══════════════════════════════════════════════════════════════════
def restore_from_backup() -> bool:
    log("checking for previous backup...")
    try:
        from agent_pc.backup_restore import restore as restore_fn
    except ImportError:
        try:
            # fallback: dynamic import (backup_&_restore has & in name)
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "agent_pc_backup",
                HERE / "backup_&_restore.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            restore_fn = mod.restore
        except Exception as e:
            log(f"⚠️ backup module not loadable: {e}")
            return False

    try:
        ok = restore_fn()
        if ok:
            log("✅ restored from previous session")
        else:
            log("🆕 first boot — no backup to restore")
        return ok
    except Exception as e:
        log(f"⚠️ restore failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# ৮. Launch always_ready apps
# ═══════════════════════════════════════════════════════════════════
def launch_always_ready(meta: dict) -> None:
    log("launching always_ready apps...")
    for app in meta["apps"]["always_ready"]:
        cmd = shlex.split(app["command"])
        log(f"  → {app['name']}: {' '.join(cmd)}")
        try:
            PROCS.append(subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ))
            time.sleep(app.get("start_delay", 2))
        except Exception as e:
            log(f"  ⚠️ {app['name']} failed: {e}")
    log(f"✅ {len(meta['apps']['always_ready'])} apps launched")


# ═══════════════════════════════════════════════════════════════════
# ৯. Backup loop
# ═══════════════════════════════════════════════════════════════════
def start_backup_loop(meta: dict) -> None:
    p = meta.get("persistence", {})
    if not p.get("enabled", False):
        log("persistence disabled — skipping backup loop")
        return

    try:
        from agent_pc.backup_restore import start_periodic_backup
    except ImportError:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "agent_pc_backup", HERE / "backup_&_restore.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            start_periodic_backup = mod.start_periodic_backup
        except Exception as e:
            log(f"⚠️ backup loop not available: {e}")
            return

    interval = p.get("backup_interval_seconds", 300)
    try:
        start_periodic_backup(interval_seconds=interval)
        log(f"✅ backup loop started (every {interval}s)")
    except Exception as e:
        log(f"⚠️ backup loop failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# ১০. TOOLS INITIALIZATION
# ═══════════════════════════════════════════════════════════════════
def _build_tools():
    """
    সব tool instance initialize করো এবং LangChain tool list বানাও।

    Returns:
        (all_tools, instances) — 
          all_tools: LangChain @tool list
          instances:  dict of raw instances (PCAgent, ReminderTool, etc.)
    """
    log("initializing agent tools...")

    from langchain_core.tools import tool

    # ─── PC core (pc_to_agent.py) ─────────────────────────────
    from agent_pc.pc_to_agent import get_pc
    pc = get_pc()
    log("  ✓ PCAgent initialized")

    @tool
    def pc_open_application(command: str) -> str:
        """Launches a GUI app (e.g. 'firefox-esr', 'libreoffice --writer')."""
        return pc.open_application(command)

    @tool
    def pc_see(app_name: str = "") -> str:
        """Returns what the agent sees (AT-SPI text tree). Call this FIRST and before every click."""
        return pc.see(app_name or None)

    @tool
    def pc_click(role: str, name: str) -> str:
        """Clicks an element. role='push button'/'entry'/'link'. name=visible label."""
        return pc.click(role, name)

    @tool
    def pc_type(text: str) -> str:
        """Types text into the currently focused field."""
        return pc.type_text(text)

    @tool
    def pc_type_into(role: str, name: str, text: str) -> str:
        """Finds an element by role+name, then types text into it."""
        return pc.type_into(role, name, text)

    @tool
    def pc_press_key(key: str) -> str:
        """Presses a key — 'Return', 'Tab', 'Escape', 'ctrl+c', 'F5'."""
        return pc.press_key(key)

    @tool
    def pc_wait_for(role: str, name: str, timeout: int = 15) -> str:
        """Waits for an element to appear (e.g. after page load)."""
        ok = pc.wait_for(role, name, timeout)
        return "found" if ok else f"timeout after {timeout}s"

    @tool
    def pc_scroll(direction: str = "down", amount: int = 3) -> str:
        """Scrolls the screen — direction='up'/'down'."""
        return pc.scroll(direction, amount)

    @tool
    def pc_close_application(name: str = "") -> str:
        """Closes a GUI app by name."""
        return pc.close_application(name or None)

    @tool
    def pc_switch_to(name: str) -> str:
        """Brings a GUI app to focus."""
        return pc.switch_to(name)

    @tool
    def pc_list_applications() -> str:
        """Lists running GUI apps."""
        import json as _json
        return _json.dumps(pc.list_applications(), ensure_ascii=False)

    @tool
    def pc_state() -> str:
        """Returns the agent's current PC state — which apps, active window."""
        import json as _json
        return _json.dumps(pc.get_state(), ensure_ascii=False)

    # ─── Extra tools (tools.py) ───────────────────────────────
    from agent_pc.tools import (
        get_reminder_tool, get_script_tool, get_recorder_tool,
    )

    reminder = get_reminder_tool()
    script_exec = get_script_tool()
    recorder = get_recorder_tool()
    log("  ✓ Reminder + Script + Recorder tools initialized")

    @tool
    def set_reminder(when: str, text: str) -> str:
        """Sets a reminder. Example: set_reminder('in 30 minutes', 'Check emails').
        Time formats: '2026-10-11 10:00', 'in 5 minutes', 'in 2h'."""
        return reminder.add(when, text)

    @tool
    def list_reminders() -> str:
        """Lists all pending reminders."""
        import json as _json
        return _json.dumps(reminder.list(), ensure_ascii=False)

    @tool
    def cancel_reminder(reminder_id: str) -> str:
        """Cancels a reminder by its ID."""
        return reminder.cancel(reminder_id)

    @tool
    def run_script(script_json: str, resume_from: int = 0) -> str:
        """Runs a GUI automation script (JSON DSL) step-by-step without LLM.
        Script format: {"name": "x", "steps": [{"action": "click", "role": "push button", "name": "OK"}]}
        Supported actions: open_app, click, type, type_into, press_key, wait_for, scroll, sleep."""
        import json as _json
        try:
            data = _json.loads(script_json) if isinstance(script_json, str) else script_json
        except Exception as e:
            return f"❌ invalid script JSON: {e}"
        result = script_exec.execute(data, resume_from=resume_from)
        return _json.dumps(result, ensure_ascii=False)

    @tool
    def validate_script(script_json: str) -> str:
        """Validates a script's structure before running."""
        import json as _json
        try:
            data = _json.loads(script_json)
        except Exception as e:
            return f"❌ invalid JSON: {e}"
        return _json.dumps(script_exec.validate(data), ensure_ascii=False)

    @tool
    def save_script(script_json: str, name: str = "") -> str:
        """Saves a script to disk for reuse."""
        import json as _json
        try:
            data = _json.loads(script_json)
        except Exception as e:
            return f"❌ invalid JSON: {e}"
        return script_exec.save_script(data, name or None)

    @tool
    def load_script(name: str) -> str:
        """Loads a saved script by name."""
        import json as _json
        s = script_exec.load_script(name)
        return _json.dumps(s, ensure_ascii=False) if s else f"❌ not found: {name}"

    @tool
    def list_scripts() -> str:
        """Lists all saved scripts."""
        import json as _json
        return _json.dumps(script_exec.list_scripts(), ensure_ascii=False)

    @tool
    def start_recording(name: str) -> str:
        """Starts recording the agent's manual GUI actions into a reusable script."""
        return recorder.start(name)

    @tool
    def stop_recording_and_save(tags: str = "") -> str:
        """Stops recording and saves the workflow to the knowledge base.
        tags = comma-separated, e.g. 'login,gmail'."""
        recorder.stop()
        script = recorder.build_script()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        path = recorder.save_knowledge(script["name"], script, tags=tag_list)
        return f"✅ saved workflow: {path}"

    @tool
    def search_knowledge(tag: str) -> str:
        """Searches saved workflows by tag."""
        import json as _json
        return _json.dumps(recorder.search_knowledge(tag), ensure_ascii=False)

    @tool
    def list_knowledge() -> str:
        """Lists all saved workflows."""
        import json as _json
        return _json.dumps(recorder.list_knowledge(), ensure_ascii=False)

    # ─── Combine ──────────────────────────────────────────────
    all_tools = [
        # PC core
        pc_open_application, pc_see, pc_click, pc_type, pc_type_into,
        pc_press_key, pc_wait_for, pc_scroll, pc_close_application,
        pc_switch_to, pc_list_applications, pc_state,
        # Reminder
        set_reminder, list_reminders, cancel_reminder,
        # Scripts
        run_script, validate_script, save_script, load_script, list_scripts,
        # Knowledge
        start_recording, stop_recording_and_save,
        search_knowledge, list_knowledge,
    ]

    instances = {
        "pc": pc,
        "reminder": reminder,
        "script_exec": script_exec,
        "recorder": recorder,
    }

    log(f"✅ {len(all_tools)} tools assembled")
    return all_tools, instances


# ═══════════════════════════════════════════════════════════════════
# GLOBAL TOOL LIST (import-able)
# ═══════════════════════════════════════════════════════════════════
# লেজি — প্রথম import-এ তৈরি হয় না, `get_agent_pc_tools()` কল করলে হয়।

_TOOLS_CACHE: tuple | None = None


def get_agent_pc_tools():
    """
    সব tools + instances return করো (cached)।

    Returns:
        (tools, instances)
    """
    global _TOOLS_CACHE
    if _TOOLS_CACHE is None:
        _TOOLS_CACHE = _build_tools()
    return _TOOLS_CACHE


# agent.py-তে convenience import-এর জন্যে
# এটা lazy load করে — agent.py import করার সময় tools বানায় না,
# শুধু property access-এ বানায়।
class _ToolProxy:
    def __iter__(self):
        tools, _ = get_agent_pc_tools()
        return iter(tools)

    def __len__(self):
        tools, _ = get_agent_pc_tools()
        return len(tools)

    def __getitem__(self, idx):
        tools, _ = get_agent_pc_tools()
        return tools[idx]


AGENT_PC_TOOLS = _ToolProxy()


# ═══════════════════════════════════════════════════════════════════
# ১১. Exec final
# ═══════════════════════════════════════════════════════════════════
def exec_final(cmd: list[str]) -> None:
    log(f"exec: {' '.join(cmd)}")
    os.execvp(cmd[0], cmd)


# ═══════════════════════════════════════════════════════════════════
# ১২. Cleanup
# ═══════════════════════════════════════════════════════════════════
def cleanup(*_):
    log("shutting down child processes...")
    for p in PROCS:
        try:
            p.terminate()
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)


# ═══════════════════════════════════════════════════════════════════
# ১৩. Main
# ═══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="agent_pc bootstrap")
    parser.add_argument("--serve", nargs=argparse.REMAINDER,
                        help="command to exec after setup")
    parser.add_argument("--tools-only", action="store_true",
                        help="only init tools (skip desktop)")
    args = parser.parse_args()

    if args.tools_only:
        tools, _ = get_agent_pc_tools()
        print(f"✅ {len(tools)} tools ready:")
        for t in tools:
            print(f"   - {t.name}: {t.description[:70]}")
        return

    # ── Full desktop bootstrap ──
    meta = load_meta()
    verify_environment(meta)
    start_xvfb(meta)
    start_dbus_session()
    start_atspi(meta)
    start_xfce(meta)
    restore_from_backup()
    launch_always_ready(meta)
    start_backup_loop(meta)

    log("═══════════════════════════════════════════")
    log("   🖥️   agent_pc is READY                  ")
    log("═══════════════════════════════════════════")

    # Tools lazy — uvicorn (app.py) import করলে হবে
    if args.serve:
        serve_cmd = args.serve
        if serve_cmd and serve_cmd[0] == "--":
            serve_cmd = serve_cmd[1:]
        exec_final(serve_cmd)
    else:
        log("no --serve; sleeping forever")
        while True:
            time.sleep(60)


if __name__ == "__main__":
    main()