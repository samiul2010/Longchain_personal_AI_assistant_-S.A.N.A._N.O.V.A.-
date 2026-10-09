"""Agent PC body: perception, actions, skills, persistence, and live events.
Optional system integrations (pyatspi/xdotool/wmctrl) are detected at runtime so
local development still works when the virtual desktop is not installed.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hf_persistence import HFDatasetPersistence

try:
    import pyatspi  # type: ignore
except Exception:  # pragma: no cover - optional system dependency
    pyatspi = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventBus:
    def __init__(self, max_events: int = 300):
        self.history: deque[dict[str, Any]] = deque(maxlen=max_events)
        self.subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: dict[str, Any]) -> None:
        event = {"id": uuid.uuid4().hex, "timestamp": now_iso(), **event}
        async with self._lock:
            self.history.append(event)
            for queue in list(self.subscribers):
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                await queue.put(event)

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self.subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self.subscribers.discard(queue)


class AgentPC:
    def __init__(self, data_dir: str | None = None):
        self.root = Path(data_dir or os.getenv("AGENT_PC_DATA_DIR", "~/.agent_pc")).expanduser()
        self.skills_dir = self.root / "skills"
        self.files_dir = self.root / "files"
        self.root.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.memory_path = self.root / "memory.json"
        self.actions_path = self.root / "actions.jsonl"
        self.events = EventBus()
        self.hf = HFDatasetPersistence(self.root)
        self._state = self._read_json(self.state_path, {"tracked_files": [], "last_sync": None})

    def restore_from_hf(self) -> dict[str, Any]:
        """Restore the complete local Agent PC directory from the private Dataset."""
        result = self.hf.restore()
        if result.get("ok"):
            self._state = self._read_json(self.state_path, self._state)
        return result

    def sync_to_hf(self) -> dict[str, Any]:
        """Upload memory, skills, files, state, and action history to Dataset."""
        result = self.hf.sync()
        if result.get("ok"):
            self._state["last_sync"] = now_iso()
            self._write_json(self.state_path, self._state)
        return result

    async def auto_sync_loop(self, interval: int = 120) -> None:
        """Keep the private Dataset current without blocking the event loop."""
        while True:
            await asyncio.sleep(max(30, interval))
            await asyncio.to_thread(self.sync_to_hf)

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _write_json(self, path: Path, value: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    async def emit(self, kind: str, **payload: Any) -> dict[str, Any]:
        event = {"type": kind, **payload}
        await self.events.publish(event)
        with self.actions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def _command(self, name: str) -> str | None:
        return shutil.which(name)

    def _run(self, args: list[str], timeout: float = 8) -> tuple[int, str, str]:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, "", str(exc)

    def _walk_accessible(self, node: Any, depth: int = 0, limit: int = 300):
        if depth > 12:
            return []
        rows = []
        try:
            role = node.getRoleName() or "unknown"
            name = node.name or ""
            if role != "unknown" or name:
                rows.append({"role": role, "name": name, "depth": depth})
            if len(rows) < limit:
                for index in range(min(node.childCount, 80)):
                    rows.extend(self._walk_accessible(node.getChildAtIndex(index), depth + 1, limit - len(rows)))
                    if len(rows) >= limit:
                        break
        except Exception:
            return rows
        return rows

    def get_ui_tree(self, app: str | None = None) -> dict[str, Any]:
        """Return a compact AT-SPI2 tree; fall back to window listing when unavailable."""
        if pyatspi is not None:
            try:
                desktop = pyatspi.Registry.getDesktop(0)
                apps = []
                for index in range(desktop.childCount):
                    candidate = desktop.getChildAtIndex(index)
                    name = candidate.name or ""
                    if app and app.lower() not in name.lower():
                        continue
                    apps.append({"app": name, "elements": self._walk_accessible(candidate)})
                return {"source": "at-spi2", "apps": apps, "updated_at": now_iso()}
            except Exception as exc:
                atspi_error = str(exc)
        else:
            atspi_error = "pyatspi unavailable"

        windows = []
        if self._command("wmctrl"):
            _, stdout, _ = self._run(["wmctrl", "-l"])
            windows = [line for line in stdout.splitlines() if line.strip()]
        return {"source": "fallback", "apps": windows, "warning": atspi_error, "updated_at": now_iso()}

    async def click_element(self, app: str, role: str, name: str) -> dict[str, Any]:
        tree = self.get_ui_tree(app)
        for item in tree.get("apps", []):
            if isinstance(item, dict):
                for element in item.get("elements", []):
                    if element.get("role") == role and element.get("name") == name:
                        result = {"ok": False, "method": "at-spi2", "element": element, "message": "AT-SPI2 element found; action adapter required for this role"}
                        await self.emit("action", action="click_element", args={"app": app, "role": role, "name": name}, result=result)
                        return result
        result = {"ok": False, "method": "at-spi2", "message": "Element not found"}
        await self.emit("action", action="click_element", args={"app": app, "role": role, "name": name}, result=result)
        return result

    async def click(self, x: int, y: int) -> dict[str, Any]:
        if not self._command("xdotool"):
            result = {"ok": False, "message": "xdotool is not installed"}
        else:
            code, _, error = self._run(["xdotool", "mousemove", str(x), str(y), "click", "1"])
            result = {"ok": code == 0, "message": error or "clicked", "x": x, "y": y}
        await self.emit("action", action="click", args={"x": x, "y": y}, result=result)
        return result

    async def type_text(self, text: str) -> dict[str, Any]:
        if not self._command("xdotool"):
            result = {"ok": False, "message": "xdotool is not installed"}
        else:
            code, _, error = self._run(["xdotool", "type", "--clearmodifiers", text])
            result = {"ok": code == 0, "message": error or "typed"}
        await self.emit("action", action="type", args={"text": text[:200]}, result=result)
        return result

    async def key(self, combo: str) -> dict[str, Any]:
        if not self._command("xdotool"):
            result = {"ok": False, "message": "xdotool is not installed"}
        else:
            code, _, error = self._run(["xdotool", "key", combo])
            result = {"ok": code == 0, "message": error or "key pressed"}
        await self.emit("action", action="key", args={"combo": combo}, result=result)
        return result

    def list_skills(self) -> list[dict[str, Any]]:
        skills = []
        for path in sorted(self.skills_dir.glob("*.skill.json")):
            data = self._read_json(path, {})
            if data:
                skills.append(data)
        return skills

    def save_skill(self, name: str, description: str, params: list[str], steps: list[dict[str, Any]]) -> dict[str, Any]:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
        if not safe_name:
            raise ValueError("skill name is required")
        skill = {"schema_version": 1, "name": safe_name, "description": description, "params": params, "created": now_iso(), "success_count": 0, "failure_count": 0, "steps": steps}
        self._write_json(self.skills_dir / f"{safe_name}.skill.json", skill)
        return skill

    def load_skill(self, name: str) -> dict[str, Any] | None:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
        path = self.skills_dir / f"{safe_name}.skill.json"
        data = self._read_json(path, None)
        return data if isinstance(data, dict) else None

    def remember(self, role: str, text: str) -> None:
        memory = self._read_json(self.memory_path, [])
        if not isinstance(memory, list):
            memory = []
        memory.append({"role": role, "text": text, "created": now_iso()})
        self._write_json(self.memory_path, memory[-500:])

    def state(self) -> dict[str, Any]:
        return {**self._state, "skills": len(self.list_skills()), "data_dir": str(self.root), "hf_dataset": {"enabled": self.hf.enabled, "repo_id": self.hf.repo_id, "last_error": self.hf.last_error}}


agent_pc = AgentPC()
