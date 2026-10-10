#!/usr/bin/env python3
"""
agent_pc.tools — এজেন্টের জন্যে অতিরিক্ত টুলস।

─────────────────────────────────────────────────────────────────
  📹 ভিডিও কল / ডেমো লিংক (এখানে আপনার লিংক বসান):
  ─────────────────────────────────────────────────────────────
  ►  [VIDEO CALL URL / DEMO VIDEO] — এখানে আপনার লিংক/নোট বসান
  ►  [FILL LATER] — প্রয়োজন হলে পরিবর্তন করুন
─────────────────────────────────────────────────────────────────

এই ফাইলে ৩টা টুলস আছে:

  ১. ReminderTool         — "এই সময়ে এই কাজ মনে করাও"
                            → সময় হলে এজেন্টের ইনপুটে মেসেজ আসে

  ২. ScriptExecutorTool   — "এই স্ক্রিপ্ট ধাপে ধাপে চালাও (LLM ছাড়াই)"
                            → GUI action-এর step-by-step JSON/DSL exec

  ৩. WorkflowRecorderTool — এজেন্ট যখন free-hand ক্লিক করে,
                            → সেই ধাপগুলো লক করে script বানায়
                            → knowledge base-এ রাখে পরবর্তী استخدامের জন্যে
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .pc_to_agent import get_pc


# ═══════════════════════════════════════════════════════════════════
# Storage locations
# ═══════════════════════════════════════════════════════════════════

STORAGE_ROOT = Path(os.environ.get("AGENT_STORAGE", "/agent"))
TOOLS_DIR = STORAGE_ROOT / "agent_pc_tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

REMINDERS_FILE    = TOOLS_DIR / "reminders.json"
SCRIPTS_DIR       = TOOLS_DIR / "scripts"
KNOWLEDGE_DIR     = TOOLS_DIR / "knowledge"
RECORDINGS_DIR    = TOOLS_DIR / "recordings"

SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[tools {ts}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════
# ১️⃣  REMINDER TOOL
# ═══════════════════════════════════════════════════════════════════

class ReminderTool:
    """
    এজেন্ট একটা সময় + কাজের বিবরণ দেবে। সেই সময় হলে এজেন্টের
    ইনপুটে মেসেজ আসবে (যেমন ব্যবহারকারী নিজে মেসেজ দিলে আসে)।

    ব্যবহার:
        rt = ReminderTool(on_fire=my_callback)
        rt.add(
            when="2026-10-11 10:00",
            text="Check emails and reply to Samiul",
        )
        rt.add(
            when="in 30 minutes",
            text="Take a break",
        )
    """

    def __init__(self, on_fire: Callable[[dict], None] | None = None):
        """
        Args:
            on_fire: কলব্যাক — reminder সময় হলে ডাকা হবে।
                     arg = {"id": ..., "when": ..., "text": ...}
        """
        self.on_fire = on_fire
        self._reminders: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._load()
        self.start()

    # ─── persistence ───────────────────────────────────────────
    def _load(self):
        if REMINDERS_FILE.exists():
            try:
                self._reminders = json.loads(REMINDERS_FILE.read_text())
                _log(f"loaded {len(self._reminders)} reminders")
            except Exception as e:
                _log(f"⚠️ load failed: {e}")
                self._reminders = []

    def _save(self):
        try:
            REMINDERS_FILE.write_text(
                json.dumps(self._reminders, ensure_ascii=False, indent=2)
            )
        except Exception as e:
            _log(f"⚠️ save failed: {e}")

    # ─── public API ────────────────────────────────────────────
    def add(self, when: str, text: str) -> str:
        """
        নতুন reminder।

        Args:
            when: "2026-10-11 10:00" | "in 30 minutes" | "in 2 hours" | "in 3 days"
            text: কাজের বিবরণ

        Returns:
            Confirmation message
        """
        dt = self._parse_when(when)
        if dt is None:
            return f"❌ could not parse time: {when!r}"

        rid = str(uuid.uuid4())[:8]
        item = {
            "id": rid,
            "when": dt.isoformat(),
            "when_raw": when,
            "text": text,
            "created_at": datetime.now().isoformat(),
            "fired": False,
        }
        self._reminders.append(item)
        self._save()
        _log(f"⏰ reminder added [{rid}] at {dt} — {text!r}")
        return f"✅ reminder set for {dt.strftime('%Y-%m-%d %H:%M')} — {text}"

    def list(self) -> list[dict]:
        """সব pending reminders।"""
        now = datetime.now()
        return [
            r for r in self._reminders
            if not r.get("fired") and self._to_dt(r["when"]) > now
        ]

    def cancel(self, rid: str) -> str:
        """Reminder বাতিল।"""
        for r in self._reminders:
            if r["id"] == rid:
                r["fired"] = True
                self._save()
                return f"✅ cancelled {rid}"
        return f"❌ not found: {rid}"

    def clear_all(self) -> str:
        """সব বাতিল।"""
        n = 0
        for r in self._reminders:
            if not r.get("fired"):
                r["fired"] = True
                n += 1
        self._save()
        return f"✅ cancelled {n} reminders"

    # ─── scheduler ─────────────────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="reminder-loop"
        )
        self._thread.start()
        _log("reminder scheduler started")

    def stop(self):
        self._stop.set()
        _log("reminder scheduler stopped")

    def _loop(self):
        while not self._stop.wait(5):  # check every 5 sec
            now = datetime.now()
            changed = False
            for r in self._reminders:
                if r.get("fired"):
                    continue
                try:
                    when = self._to_dt(r["when"])
                except Exception:
                    continue
                if when <= now:
                    r["fired"] = True
                    changed = True
                    self._fire(r)
            if changed:
                self._save()

    def _fire(self, reminder: dict):
        _log(f"🔔 REMINDER: {reminder['text']}")
        if self.on_fire:
            try:
                self.on_fire(reminder)
            except Exception as e:
                _log(f"⚠️ on_fire callback error: {e}")

    # ─── parsing ───────────────────────────────────────────────
    def _parse_when(self, when: str) -> datetime | None:
        """বিভিন্ন format থেকে datetime।"""
        when = when.strip()

        # Absolute: "2026-10-11 10:00"
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(when, fmt)
            except ValueError:
                pass

        # Relative: "in 30 minutes"
        m = re.match(r"^in\s+(\d+)\s+(second|minute|hour|day)s?$", when, re.I)
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            delta = {
                "second": timedelta(seconds=n),
                "minute": timedelta(minutes=n),
                "hour":   timedelta(hours=n),
                "day":    timedelta(days=n),
            }[unit]
            return datetime.now() + delta

        # "in 30m" / "in 2h" / "in 3d" / "in 45s"
        m = re.match(r"^in\s+(\d+)(s|m|h|d)$", when, re.I)
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            delta = {
                "s": timedelta(seconds=n),
                "m": timedelta(minutes=n),
                "h": timedelta(hours=n),
                "d": timedelta(days=n),
            }[unit]
            return datetime.now() + delta

        return None

    def _to_dt(self, iso: str) -> datetime:
        return datetime.fromisoformat(iso)


# ═══════════════════════════════════════════════════════════════════
# ২️⃣  SCRIPT EXECUTOR TOOL
# ═══════════════════════════════════════════════════════════════════

class ScriptExecutorTool:
    """
    এজেন্ট একটা JSON/DSL আকারে স্ক্রিপ্ট দেবে — এই টুলস LLM ছাড়াই
    সেই স্ক্রিপ্ট ধাপে ধাপে চালাবে। মাঝখানে আটকে গেলে এজেন্টকে
    ফেরত দেবে "current step" state সহ।

    স্ক্রিপ্ট DSL:
    {
      "name": "gmail_login",
      "steps": [
        {"action": "open_app", "command": "firefox-esr"},
        {"action": "wait_for", "role": "entry", "name": "Email"},
        {"action": "type_into", "role": "entry", "name": "Email", "text": "me@x.com"},
        {"action": "click", "role": "push button", "name": "Next"},
        {"action": "wait_for", "role": "entry", "name": "Password", "timeout": 10},
        {"action": "type_into", "role": "entry", "name": "Password", "text": "secret"},
        {"action": "click", "role": "push button", "name": "Sign in"},
        {"action": "wait_for", "role": "link", "name": "Inbox"}
      ]
    }

    চালানোর নিয়ম:
      - step-by-step execute করবে
      - কোনো step fail করলে থেমে যাবে, state save করবে,
        এজেন্টকে জানাবে
      - এজেন্ট চাইলে "resume from step N" করতে পারবে
    """

    SUPPORTED_ACTIONS = {
        "open_app", "click", "type", "type_into",
        "press_key", "wait_for", "scroll", "see",
        "sleep", "switch_to", "close_app",
    }

    def __init__(self):
        self._current_run: dict | None = None
        self._stop_requested = False

    # ─── public API ────────────────────────────────────────────
    def execute(self, script: dict, resume_from: int = 0,
                max_steps: int | None = None) -> dict:
        """
        স্ক্রিপ্ট চালাও।

        Args:
            script: JSON/dict — {"name": ..., "steps": [...]}
            resume_from: কোন step থেকে শুরু (0 = শুরু)
            max_steps: কত step চালাবে (None = সব)

        Returns:
            {"ok": bool, "completed": int, "total": int,
             "current_step": int, "message": str,
             "failed_step": dict | None}
        """
        pc = get_pc()
        steps = script.get("steps", [])
        if not steps:
            return {"ok": False, "message": "no steps in script"}

        script_name = script.get("name", "unnamed")
        self._stop_requested = False

        _log(f"▶️  running script '{script_name}' from step {resume_from}")
        self._current_run = {
            "name": script_name,
            "started_at": datetime.now().isoformat(),
            "total_steps": len(steps),
        }

        completed = resume_from
        end = len(steps) if max_steps is None else min(len(steps), resume_from + max_steps)

        for idx in range(resume_from, end):
            if self._stop_requested:
                return {
                    "ok": False, "completed": completed, "total": len(steps),
                    "current_step": idx, "message": "stopped by user",
                    "failed_step": None,
                }

            step = steps[idx]
            _log(f"  step {idx+1}/{len(steps)}: {step.get('action')}")

            try:
                result = self._run_step(pc, step)
            except Exception as e:
                return {
                    "ok": False, "completed": completed, "total": len(steps),
                    "current_step": idx, "message": f"step {idx+1} error: {e}",
                    "failed_step": step,
                }

            if not result.get("ok"):
                _log(f"  ❌ step {idx+1} failed: {result.get('message')}")
                return {
                    "ok": False, "completed": completed, "total": len(steps),
                    "current_step": idx,
                    "message": result.get("message", "step failed"),
                    "failed_step": step,
                }

            completed = idx + 1

        self._current_run = None
        return {
            "ok": True, "completed": completed, "total": len(steps),
            "current_step": len(steps),
            "message": f"✅ script '{script_name}' complete ({completed}/{len(steps)})",
            "failed_step": None,
        }

    def stop(self):
        self._stop_requested = True

    def validate(self, script: dict) -> dict:
        """স্ক্রিপ্ট সঠিক আছে কি না।"""
        errors = []
        steps = script.get("steps", [])
        if not steps:
            return {"ok": False, "errors": ["no steps"]}

        for i, s in enumerate(steps):
            a = s.get("action")
            if a not in self.SUPPORTED_ACTIONS:
                errors.append(f"step {i+1}: unknown action {a!r}")
            if a in ("click", "wait_for", "type_into"):
                if not s.get("role"):
                    errors.append(f"step {i+1}: missing role")
                if not s.get("name"):
                    errors.append(f"step {i+1}: missing name")
            if a in ("type", "type_into"):
                if "text" not in s:
                    errors.append(f"step {i+1}: missing text")

        return {"ok": len(errors) == 0, "errors": errors}

    def save_script(self, script: dict, name: str | None = None) -> str:
        """স্ক্রিপ্ট ফাইল হিসেবে save।"""
        script_name = name or script.get("name") or f"script-{int(time.time())}"
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", script_name)
        path = SCRIPTS_DIR / f"{safe}.json"
        path.write_text(json.dumps(script, ensure_ascii=False, indent=2))
        _log(f"💾 script saved: {path.name}")
        return str(path)

    def load_script(self, name: str) -> dict | None:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        path = SCRIPTS_DIR / f"{safe}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list_scripts(self) -> list[str]:
        return [p.stem for p in sorted(SCRIPTS_DIR.glob("*.json"))]

    # ─── step runner ───────────────────────────────────────────
    def _run_step(self, pc, step: dict) -> dict:
        action = step.get("action")

        if action == "open_app":
            r = pc.open_application(step["command"])
            return {"ok": "❌" not in r, "message": r}

        if action == "close_app":
            r = pc.close_application(step.get("name"))
            return {"ok": "❌" not in r, "message": r}

        if action == "switch_to":
            r = pc.switch_to(step["name"])
            return {"ok": "❌" not in r, "message": r}

        if action == "click":
            r = pc.click(step["role"], step["name"])
            return {"ok": "❌" not in r, "message": r}

        if action == "type":
            r = pc.type_text(step["text"])
            return {"ok": "❌" not in r, "message": r}

        if action == "type_into":
            r = pc.type_into(step["role"], step["name"], step["text"])
            return {"ok": "❌" not in r, "message": r}

        if action == "press_key":
            r = pc.press_key(step["key"])
            return {"ok": "❌" not in r, "message": r}

        if action == "wait_for":
            timeout = int(step.get("timeout", 15))
            ok = pc.wait_for(step["role"], step["name"], timeout)
            return {"ok": ok, "message": f"waited {step['name']}: {'found' if ok else 'timeout'}"}

        if action == "scroll":
            r = pc.scroll(step.get("direction", "down"), int(step.get("amount", 3)))
            return {"ok": True, "message": r}

        if action == "see":
            r = pc.see(step.get("app"))
            return {"ok": True, "message": r[:500]}

        if action == "sleep":
            time.sleep(float(step.get("seconds", 1)))
            return {"ok": True, "message": f"slept {step.get('seconds')}s"}

        return {"ok": False, "message": f"unknown action: {action}"}


# ═══════════════════════════════════════════════════════════════════
# ৩️⃣  WORKFLOW RECORDER TOOL
# ═══════════════════════════════════════════════════════════════════

class WorkflowRecorderTool:
    """
    এজেন্ট যখন ScriptExecutor ছাড়াই free-hand কাজ করে (এলএলএম-এর
    সিদ্ধান্তে ক্লিক/টাইপ করে), তখন এই টুলস সেই ধাপগুলো রেকর্ড করে।

    শেষে:
      → রেকর্ড করা ধাপ থেকে একটা script বানায়
      → knowledge base-এ রাখে
      → পরবর্তীতে একই কাজ ScriptExecutor দিয়ে চালানো যাবে

    ব্যবহার:
        rec = WorkflowRecorderTool()
        rec.start("gmail_login")
        rec.record_click("entry", "Email")
        rec.record_type_into("entry", "Email", "me@x.com")
        rec.record_click("push button", "Next")
        rec.record_press_key("Return")
        rec.stop()
        script = rec.build_script()
        rec.save_knowledge("gmail_login", script, notes="Login flow")
    """

    def __init__(self):
        self._recording: dict | None = None
        self._steps: list[dict] = []
        self._lock = threading.Lock()

    # ─── recording lifecycle ──────────────────────────────────
    def start(self, name: str = "workflow") -> str:
        with self._lock:
            self._recording = {
                "name": name,
                "started_at": datetime.now().isoformat(),
            }
            self._steps = []
        _log(f"⏺️  recording started: {name}")
        return f"✅ recording started: {name}"

    def stop(self) -> str:
        with self._lock:
            if not self._recording:
                return "❌ not recording"
            self._recording["stopped_at"] = datetime.now().isoformat()
            self._recording["step_count"] = len(self._steps)
        _log(f"⏹️  recording stopped ({len(self._steps)} steps)")
        return f"✅ recording stopped — {len(self._steps)} steps"

    def is_recording(self) -> bool:
        return self._recording is not None

    # ─── step recorders ────────────────────────────────────────
    def record_click(self, role: str, name: str) -> None:
        self._push({"action": "click", "role": role, "name": name})

    def record_type(self, text: str) -> None:
        self._push({"action": "type", "text": text})

    def record_type_into(self, role: str, name: str, text: str) -> None:
        self._push({"action": "type_into", "role": role, "name": name, "text": text})

    def record_press_key(self, key: str) -> None:
        self._push({"action": "press_key", "key": key})

    def record_wait_for(self, role: str, name: str, timeout: int = 15) -> None:
        self._push({"action": "wait_for", "role": role, "name": name, "timeout": timeout})

    def record_open_app(self, command: str) -> None:
        self._push({"action": "open_app", "command": command})

    def record_close_app(self, name: str) -> None:
        self._push({"action": "close_app", "name": name})

    def record_switch_to(self, name: str) -> None:
        self._push({"action": "switch_to", "name": name})

    def record_scroll(self, direction: str = "down", amount: int = 3) -> None:
        self._push({"action": "scroll", "direction": direction, "amount": amount})

    def record_custom(self, step: dict) -> None:
        self._push(step)

    def _push(self, step: dict):
        with self._lock:
            if not self._recording:
                return
            self._steps.append(step)

    # ─── build & save ─────────────────────────────────────────
    def build_script(self) -> dict:
        """রেকর্ড করা ধাপ থেকে একটা executable script।"""
        with self._lock:
            name = self._recording["name"] if self._recording else "unnamed"
            steps = list(self._steps)
        return {
            "name": name,
            "source": "recorded",
            "created_at": datetime.now().isoformat(),
            "steps": steps,
        }

    def save_knowledge(self, name: str, script: dict | None = None,
                       notes: str = "", tags: list[str] | None = None) -> str:
        """Knowledge base-এ save।"""
        script = script or self.build_script()
        entry = {
            "name": name,
            "script": script,
            "notes": notes,
            "tags": tags or [],
            "saved_at": datetime.now().isoformat(),
            "step_count": len(script.get("steps", [])),
        }
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        path = KNOWLEDGE_DIR / f"{safe}.json"
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=2))
        _log(f"📚 knowledge saved: {path.name} ({entry['step_count']} steps)")
        return str(path)

    def list_knowledge(self) -> list[dict]:
        """Knowledge base-এ কী আছে।"""
        out = []
        for p in sorted(KNOWLEDGE_DIR.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                out.append({
                    "name": data.get("name"),
                    "step_count": data.get("step_count"),
                    "tags": data.get("tags", []),
                    "saved_at": data.get("saved_at"),
                })
            except Exception:
                pass
        return out

    def load_knowledge(self, name: str) -> dict | None:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        path = KNOWLEDGE_DIR / f"{safe}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def search_knowledge(self, tag: str) -> list[dict]:
        """Tag দিয়ে খোঁজো।"""
        out = []
        for p in KNOWLEDGE_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                if tag in data.get("tags", []):
                    out.append(data)
            except Exception:
                pass
        return out


# ═══════════════════════════════════════════════════════════════════
# Singletons
# ═══════════════════════════════════════════════════════════════════

_reminder_tool: ReminderTool | None = None
_script_tool: ScriptExecutorTool | None = None
_recorder_tool: WorkflowRecorderTool | None = None


def get_reminder_tool(on_fire=None) -> ReminderTool:
    global _reminder_tool
    if _reminder_tool is None:
        _reminder_tool = ReminderTool(on_fire=on_fire)
    elif on_fire is not None:
        _reminder_tool.on_fire = on_fire
    return _reminder_tool


def get_script_tool() -> ScriptExecutorTool:
    global _script_tool
    if _script_tool is None:
        _script_tool = ScriptExecutorTool()
    return _script_tool


def get_recorder_tool() -> WorkflowRecorderTool:
    global _recorder_tool
    if _recorder_tool is None:
        _recorder_tool = WorkflowRecorderTool()
    return _recorder_tool


# ═══════════════════════════════════════════════════════════════════
# CLI — test করার জন্যে
# ═══════════════════════════════════════════════════════════════════

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="agent_pc tools")
    sub = parser.add_subparsers(dest="cmd")

    # reminder
    r = sub.add_parser("remind", help="Add reminder")
    r.add_argument("when", help='"in 5 minutes" or "2026-10-11 10:00"')
    r.add_argument("text")
    sub.add_parser("reminders", help="List reminders")

    # script
    s = sub.add_parser("run_script", help="Run a script by name")
    s.add_argument("name")

    s2 = sub.add_parser("save_script", help="Save a script JSON")
    s2.add_argument("file")

    sub.add_parser("list_scripts", help="List saved scripts")

    # knowledge
    sub.add_parser("list_knowledge", help="List knowledge entries")

    args = parser.parse_args()

    if args.cmd == "remind":
        rt = get_reminder_tool(on_fire=lambda r: print(f"🔔 FIRE: {r['text']}"))
        print(rt.add(args.when, args.text))
    elif args.cmd == "reminders":
        rt = get_reminder_tool()
        for r in rt.list():
            print(f"  [{r['id']}] {r['when']} — {r['text']}")
    elif args.cmd == "run_script":
        st = get_script_tool()
        script = st.load_script(args.name)
        if not script:
            print(f"❌ not found: {args.name}")
            return
        result = st.execute(script)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "save_script":
        st = get_script_tool()
        script = json.loads(Path(args.file).read_text())
        print(st.save_script(script))
    elif args.cmd == "list_scripts":
        for s in get_script_tool().list_scripts():
            print(" -", s)
    elif args.cmd == "list_knowledge":
        for k in get_recorder_tool().list_knowledge():
            print(f"  {k['name']} ({k['step_count']} steps) tags={k['tags']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()