#!/usr/bin/env python3
"""
agent_pc.pc_to_agent — এজেন্ট ও PC-র মধ্যে সেতু।

এই ফাইলটা হলো এজেন্টের:
  👁️  চোখ    — GUI-র অবস্থা text আকারে দেখা (AT-SPI)
  ✋  হাত     — ক্লিক, টাইপ, কী চাপা (xdotool)
  🧠  কন্ট্রোল — কোন উইন্ডোতে কাজ, অপেক্ষা, state

ডিজাইন:
  এজেন্ট পিক্সেল দেখে না। সে AT-SPI tree থেকে "text" দেখে বুঝে
  কোথায় কি আছে। তারপর হুবহু সেই এলিমেন্টে ক্লিক/টাইপ করে।

কীভাবে ব্যবহার:
  from agent_pc.pc_to_agent import PCAgent

  pc = PCAgent()
  pc.open_application("firefox-esr")
  print(pc.see())                      # এজেন্ট যা দেখে
  pc.click("entry", "Search")
  pc.type_text("hello world")
  pc.press_key("Return")
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# AT-SPI bindings
try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    ATSPI_AVAILABLE = True
except Exception as e:
    ATSPI_AVAILABLE = False
    _ATSPI_ERROR = str(e)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

DISPLAY = os.environ.get("DISPLAY", ":99")


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[pc↔agent {ts}] {msg}", flush=True)


def _run(cmd: list[str], timeout: int = 10, check: bool = False) -> tuple[bool, str]:
    """Subprocess চালাও, (success, output) return করো।"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "DISPLAY": DISPLAY},
        )
        output = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def _xdotool(args: list[str], timeout: int = 5) -> tuple[bool, str]:
    """xdotool command চালাও।"""
    return _run(["xdotool"] + args, timeout=timeout)


# ═══════════════════════════════════════════════════════════════════
# Main class
# ═══════════════════════════════════════════════════════════════════

class PCAgent:
    """
    এজেন্ট ও PC-র মধ্যে সেতু — এজেন্টের হাত, চোখ, কন্ট্রোল।

    Lifecycle:
      pc = PCAgent()
      pc.open_application("firefox-esr")
      tree = pc.see()
      pc.click("entry", "Search")
      pc.type_text("hello")
      pc.press_key("Return")
      pc.close_application("firefox-esr")
    """

    def __init__(self, workspace_dir: str | Path | None = None):
        if not ATSPI_AVAILABLE:
            raise RuntimeError(f"AT-SPI bindings unavailable: {_ATSPI_ERROR}")

        self.workspace_dir = Path(workspace_dir or "/tmp/agent_pc_workspace")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.current_app: str | None = None      # "Firefox"
        self.current_window: Any | None = None    # Atspi element
        self._last_tree: dict | None = None       # cache for wait_for_element
        self._screenshot_counter = 0

        _log(f"PCAgent initialized (workspace={self.workspace_dir})")

    # ═══════════════════════════════════════════════════════════════
    # 👁️  PERCEPTION — এজেন্ট যা দেখে
    # ═══════════════════════════════════════════════════════════════

    def see(self, app_name: str | None = None, max_depth: int = 12) -> str:
        """
        এজেন্ট যা "দেখে" — AT-SPI tree থেকে টেক্সট আকারে।

        Args:
            app_name: নির্দিষ্ট app; None হলে current_app
            max_depth: tree কত depth পর্যন্ত দেখবে

        Returns:
            Readable text tree (এজেন্ট LLM-কে এটাই পাঠাবে)
        """
        target = app_name or self.current_app
        if not target:
            return "❌ কোনো সক্রিয় উইন্ডো নেই — আগে open_application() কল করুন"

        window = self._find_app_window(target)
        if window is None:
            return f"❌ {target} window পাওয়া যায়নি"

        self.current_window = window
        self.current_app = target

        lines = [f"┌─ {target}"]
        self._walk_tree(window, lines, depth=0, max_depth=max_depth)
        lines.append("└─")

        return "\n".join(lines)

    def see_tree(self, app_name: str | None = None, max_depth: int = 12) -> dict:
        """
        একই তথ্য — কিন্তু structured dict আকারে (programmatic ব্যবহারের জন্যে)।

        Returns:
            {"apps": [{"name": "...", "nodes": [...]}, ...]}
        """
        target = app_name or self.current_app
        if not target:
            return {"apps": []}

        window = self._find_app_window(target)
        if window is None:
            return {"apps": []}

        nodes = []
        self._walk_nodes(window, nodes, depth=0, max_depth=max_depth)

        return {
            "apps": [{"name": target, "nodes": nodes}],
            "captured_at": datetime.now().isoformat(),
        }

    def see_all_apps(self, max_depth: int = 8) -> dict:
        """সব app-এর tree — একবারে সব দেখা।"""
        desktop = Atspi.get_desktop(0)
        apps = []
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            name = app.get_name() or ""
            if not name:
                continue
            nodes = []
            self._walk_nodes(app, nodes, depth=0, max_depth=max_depth)
            if nodes:
                apps.append({"name": name, "nodes": nodes})
        return {
            "apps": apps,
            "captured_at": datetime.now().isoformat(),
        }

    def _walk_tree(self, element, lines: list, depth: int, max_depth: int) -> None:
        """Recursive text walk।"""
        if depth > max_depth:
            return
        try:
            role = element.get_role_name() or "unknown"
            name = element.get_name() or ""
            states = element.get_state_set()
            visible = states.contains(Atspi.StateType.SHOWING)

            if not visible:
                return

            focused = states.contains(Atspi.StateType.FOCUSED)
            enabled = states.contains(Atspi.StateType.ENABLED)

            # শুধু interesting দেখাও
            interesting = (
                name
                or role in ("push button", "entry", "link", "text",
                            "check box", "combo box", "menu item",
                            "tab", "frame", "window")
            )

            if interesting:
                indent = "  " * depth
                markers = []
                if focused:
                    markers.append("●focused")
                if not enabled:
                    markers.append("✗disabled")
                marker_str = f" [{', '.join(markers)}]" if markers else ""
                name_str = name if name else "(no name)"
                lines.append(f"{indent}├─ {role}: {name_str}{marker_str}")

            for i in range(element.get_child_count()):
                child = element.get_child_at_index(i)
                self._walk_tree(child, lines, depth + 1, max_depth)
        except Exception:
            pass

    def _walk_nodes(self, element, out: list, depth: int, max_depth: int) -> None:
        """Recursive dict walk।"""
        if depth > max_depth:
            return
        try:
            role = element.get_role_name() or "unknown"
            name = element.get_name() or ""
            states = element.get_state_set()
            if not states.contains(Atspi.StateType.SHOWING):
                return

            interesting = (
                name or role in ("push button", "entry", "link", "text",
                                 "check box", "combo box", "menu item",
                                 "tab", "frame", "window")
            )

            if interesting:
                out.append({
                    "depth": depth,
                    "role": role,
                    "name": name,
                    "enabled": states.contains(Atspi.StateType.ENABLED),
                    "focused": states.contains(Atspi.StateType.FOCUSED),
                })

            for i in range(element.get_child_count()):
                self._walk_nodes(element.get_child_at_index(i),
                                 out, depth + 1, max_depth)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    # 🎯 FINDING — এলিমেন্ট খোঁজা
    # ═══════════════════════════════════════════════════════════════

    def find(self, role: str, name_substring: str,
             app_name: str | None = None) -> Any | None:
        """
        Role + name দিয়ে এলিমেন্ট খোঁজো।

        Args:
            role: AT-SPI role — "push button", "entry", "link"
            name_substring: নামের অংশ (case-insensitive)
            app_name: নির্দিষ্ট app

        Returns:
            Atspi element or None
        """
        target = app_name or self.current_app
        if not target:
            return None

        root = self._find_app_window(target)
        if root is None:
            return None

        return self._search_element(root, role.lower(), name_substring.lower())

    def _search_element(self, element, role: str, name_sub: str) -> Any | None:
        """Recursive search।"""
        try:
            r = (element.get_role_name() or "").lower()
            n = (element.get_name() or "").lower()
            if role in r and name_sub in n:
                return element
            for i in range(element.get_child_count()):
                found = self._search_element(
                    element.get_child_at_index(i), role, name_sub
                )
                if found is not None:
                    return found
        except Exception:
            pass
        return None

    def find_all(self, role: str, name_substring: str = "",
                 app_name: str | None = None) -> list:
        """সব matching এলিমেন্ট।"""
        target = app_name or self.current_app
        if not target:
            return []
        root = self._find_app_window(target)
        if root is None:
            return []
        results = []
        self._search_all(root, role.lower(), name_substring.lower(), results)
        return results

    def _search_all(self, element, role: str, name_sub: str, out: list) -> None:
        try:
            r = (element.get_role_name() or "").lower()
            n = (element.get_name() or "").lower()
            if role in r and name_sub in n:
                out.append(element)
            for i in range(element.get_child_count()):
                self._search_all(element.get_child_at_index(i),
                                 role, name_sub, out)
        except Exception:
            pass

    def wait_for(self, role: str, name_substring: str,
                 timeout: int = 15, app_name: str | None = None) -> bool:
        """
        এলিমেন্ট আসা পর্যন্ত অপেক্ষা — page load ইত্যাদির জন্যে।

        Returns:
            True যদি সময়মতো পাওয়া যায়
        """
        start = time.time()
        while time.time() - start < timeout:
            el = self.find(role, name_substring, app_name)
            if el is not None:
                _log(f"✅ element found: {role}/{name_substring}")
                return True
            time.sleep(0.5)
        _log(f"⏰ timeout: {role}/{name_substring} after {timeout}s")
        return False

    # ═══════════════════════════════════════════════════════════════
    # ✋ ACTION — এজেন্ট যা করে
    # ═══════════════════════════════════════════════════════════════

    def click(self, role: str, name_substring: str,
              app_name: str | None = None) -> str:
        """Role + name দিয়ে এলিমেন্টে ক্লিক করো।"""
        el = self.find(role, name_substring, app_name)
        if el is None:
            return f"❌ not found: {role}/{name_substring}"
        return self.click_element(el)

    def click_element(self, element) -> str:
        """সরাসরি এলিমেন্ট object-এ ক্লিক।"""
        try:
            action = element.get_action_iface()
            if action and action.get_n_actions() > 0:
                action.do_action(0)
                name = element.get_name() or ""
                return f"✅ clicked: {name}"
            return "❌ no action interface"
        except Exception as e:
            return f"❌ click failed: {e}"

    def type_text(self, text: str, app_name: str | None = None) -> str:
        """
        Focused element-এ টেক্সট টাইপ করো।

        দুটো পথ:
          ১. Focused element-এর EditableText interface (clean)
          ২. xdotool type (fallback)
        """
        # ১. Focused element খুঁজি
        el = self._get_focused_element(app_name)
        if el is not None:
            try:
                editable = el.get_editable_text_iface()
                if editable:
                    editable.set_text_contents(text)
                    return f"✅ typed (editable): {text!r}"
            except Exception:
                pass

        # ২. xdotool fallback
        ok, msg = _xdotool(["type", "--delay", "30", text], timeout=10)
        if ok:
            return f"✅ typed (xdotool): {text!r}"
        return f"❌ type failed: {msg}"

    def type_into(self, role: str, name_substring: str, text: str,
                  app_name: str | None = None) -> str:
        """নির্দিষ্ট এলিমেন্টে টেক্সট টাইপ (focus + type)।"""
        el = self.find(role, name_substring, app_name)
        if el is None:
            return f"❌ not found: {role}/{name_substring}"
        try:
            comp = el.get_component_iface()
            if comp:
                comp.grab_focus()
            editable = el.get_editable_text_iface()
            if editable:
                editable.set_text_contents(text)
                return f"✅ typed into {name_substring}: {text!r}"
            # fallback xdotool
            _xdotool(["type", "--delay", "30", text])
            return f"✅ typed (xdotool): {text!r}"
        except Exception as e:
            return f"❌ type_into failed: {e}"

    def press_key(self, key: str) -> str:
        """
        কী চাপো — Enter, Escape, Tab, ctrl+c ইত্যাদি।

        Examples:
            pc.press_key("Return")
            pc.press_key("Tab")
            pc.press_key("Escape")
            pc.press_key("ctrl+c")
            pc.press_key("F5")
        """
        ok, msg = _xdotool(["key", key])
        if ok:
            return f"✅ pressed: {key}"
        return f"❌ key failed: {msg}"

    def scroll(self, direction: str = "down", amount: int = 3) -> str:
        """স্ক্রল করো (direction: 'up' or 'down')।"""
        btn = "5" if direction == "down" else "4"
        for _ in range(amount):
            _xdotool(["click", btn])
        return f"✅ scrolled {direction} × {amount}"

    def click_at(self, x: int, y: int) -> str:
        """নির্দিষ্ট coordinate-এ ক্লিক (pixel-based, rarely needed)।"""
        ok, msg = _xdotool(["mousemove", str(x), str(y), "click", "1"])
        if ok:
            return f"✅ clicked at ({x}, {y})"
        return f"❌ click_at failed: {msg}"

    # ═══════════════════════════════════════════════════════════════
    # 📱 APPLICATION LIFECYCLE
    # ═══════════════════════════════════════════════════════════════

    def open_application(self, command: str,
                         wait_for_window: bool = True,
                         timeout: int = 20) -> str:
        """
        GUI application চালু করো।

        Args:
            command: "firefox-esr", "libreoffice --writer"
            wait_for_window: window খোলা পর্যন্ত অপেক্ষা
            timeout: কত সেকেন্ড অপেক্ষা

        Returns:
            Status message
        """
        _log(f"launching: {command}")
        try:
            proc = subprocess.Popen(
                shlex.split(command),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "DISPLAY": DISPLAY},
            )
        except FileNotFoundError:
            return f"❌ executable not found: {command}"
        except Exception as e:
            return f"❌ launch failed: {e}"

        # app name অনুমান
        app_guess = self._guess_app_name(command)

        if wait_for_window and app_guess:
            start = time.time()
            while time.time() - start < timeout:
                window = self._find_app_window(app_guess)
                if window is not None:
                    self.current_app = app_guess
                    self.current_window = window
                    return f"✅ {command} launched (pid={proc.pid})"
                time.sleep(0.5)

        return f"✅ {command} launched (pid={proc.pid}, window not yet found)"

    def close_application(self, app_name: str | None = None) -> str:
        """Application বন্ধ করো — window close event পাঠিয়ে।"""
        target = app_name or self.current_app
        if not target:
            return "❌ no target app"

        el = self._find_app_window(target)
        if el is None:
            return f"❌ {target} window not found"

        # window close action
        try:
            for i in range(el.get_child_count()):
                child = el.get_child_at_index(i)
                # "close" নামের button খুঁজি
                if (child.get_name() or "").lower() == "close":
                    action = child.get_action_iface()
                    if action and action.get_n_actions() > 0:
                        action.do_action(0)
                        return f"✅ closed {target}"
        except Exception:
            pass

        # fallback: pkill
        try:
            _run(["pkill", "-f", target.lower()])
            return f"✅ killed {target}"
        except Exception:
            return f"❌ could not close {target}"

    def switch_to(self, app_name: str) -> str:
        """নির্দিষ্ট app-এ focus নিয়ে যাও।"""
        window = self._find_app_window(app_name)
        if window is None:
            return f"❌ {app_name} not found"
        try:
            comp = window.get_component_iface()
            if comp:
                comp.grab_focus()
            self.current_app = app_name
            self.current_window = window
            return f"✅ switched to {app_name}"
        except Exception as e:
            return f"❌ switch failed: {e}"

    def list_applications(self) -> list[str]:
        """চলমান GUI app-গুলো list করো।"""
        desktop = Atspi.get_desktop(0)
        apps = []
        for i in range(desktop.get_child_count()):
            name = desktop.get_child_at_index(i).get_name() or ""
            if name:
                apps.append(name)
        return apps

    # ═══════════════════════════════════════════════════════════════
    # 🖼️  SCREENSHOT (pixel fallback)
    # ═══════════════════════════════════════════════════════════════

    def screenshot(self, save_path: str | Path | None = None) -> str | None:
        """
        পুরো স্ক্রিনের screenshot নাও (fallback — normal-এ দরকার হয় না)।

        Returns:
            Saved file path or None
        """
        if save_path is None:
            self._screenshot_counter += 1
            save_path = self.workspace_dir / f"screenshot_{self._screenshot_counter}.png"
        save_path = Path(save_path)

        ok, msg = _run(["import", "-window", "root", str(save_path)], timeout=10)
        if ok and save_path.exists():
            return str(save_path)

        # fallback xwd
        xwd_path = save_path.with_suffix(".xwd")
        _run(["xwd", "-root", "-display", DISPLAY, "-out", str(xwd_path)], timeout=10)
        if xwd_path.exists():
            _run(["convert", str(xwd_path), str(save_path)], timeout=10)
            xwd_path.unlink(missing_ok=True)
            if save_path.exists():
                return str(save_path)

        return None

    # ═══════════════════════════════════════════════════════════════
    # 🧠 STATE / CONTROL
    # ═══════════════════════════════════════════════════════════════

    def get_state(self) -> dict:
        """এজেন্টের সম্যক অবস্থা — এটা সবসময় task-এর শুরুতে দেখবে।"""
        return {
            "current_app": self.current_app,
            "current_window": (self.current_window.get_name()
                               if self.current_window else None),
            "applications": self.list_applications(),
            "captured_at": datetime.now().isoformat(),
        }

    def focus_input(self, app_name: str | None = None) -> bool:
        """Focused element-কে input focus দাও।"""
        el = self._get_focused_element(app_name)
        if el is None:
            return False
        try:
            comp = el.get_component_iface()
            if comp:
                comp.grab_focus()
                return True
        except Exception:
            pass
        return False

    # ═══════════════════════════════════════════════════════════════
    # 🔧 Internal helpers
    # ═══════════════════════════════════════════════════════════════

    def _find_app_window(self, app_name_substring: str):
        """AT-SPI tree থেকে app-এর top-level window।"""
        desktop = Atspi.get_desktop(0)
        needle = app_name_substring.lower()

        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            name = (app.get_name() or "").lower()
            if needle in name:
                # প্রথম frame
                for j in range(app.get_child_count()):
                    frame = app.get_child_at_index(j)
                    if frame.get_role_name() == "frame":
                        return frame
                return app
        return None

    def _get_focused_element(self, app_name: str | None = None):
        """বর্তমানে focused element।"""
        target = app_name or self.current_app
        if not target:
            return None
        root = self._find_app_window(target)
        if root is None:
            return None
        return self._find_focused(root)

    def _find_focused(self, element):
        try:
            states = element.get_state_set()
            if states.contains(Atspi.StateType.FOCUSED):
                return element
            for i in range(element.get_child_count()):
                found = self._find_focused(element.get_child_at_index(i))
                if found is not None:
                    return found
        except Exception:
            pass
        return None

    def _guess_app_name(self, command: str) -> str | None:
        """Command থেকে app name অনুমান।"""
        cmd = command.lower()
        if "firefox" in cmd:
            return "Firefox"
        if "code" in cmd:
            return "Code"
        if "libreoffice" in cmd or "soffice" in cmd:
            return "LibreOffice"
        if "thunar" in cmd:
            return "Thunar"
        if "terminal" in cmd:
            return "Terminal"
        # প্রথম token
        return command.split()[0].split("/")[-1]


# ═══════════════════════════════════════════════════════════════════
# Convenience instance (module-level)
# ═══════════════════════════════════════════════════════════════════

_pc: PCAgent | None = None


def get_pc() -> PCAgent:
    """Singleton PCAgent — সব tool একই state শেয়ার করবে।"""
    global _pc
    if _pc is None:
        _pc = PCAgent()
    return _pc


# ═══════════════════════════════════════════════════════════════════
# CLI (test করার জন্যে)
# ═══════════════════════════════════════════════════════════════════

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="PC ↔ Agent bridge test")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("state", help="এজেন্টের সম্যক অবস্থা")
    sub.add_parser("apps", help="চলমান apps")

    see = sub.add_parser("see", help="এজেন্ট যা দেখে")
    see.add_argument("--app", default=None)

    click = sub.add_parser("click", help="এলিমেন্টে ক্লিক")
    click.add_argument("role")
    click.add_argument("name")

    typ = sub.add_parser("type", help="টেক্সট টাইপ")
    typ.add_argument("text")

    key = sub.add_parser("key", help="কী চাপো")
    key.add_argument("key")

    open_p = sub.add_parser("open", help="অ্যাপ খোলো")
    open_p.add_argument("command")

    args = parser.parse_args()

    pc = get_pc()

    if args.cmd == "state":
        print(json.dumps(pc.get_state(), ensure_ascii=False, indent=2))
    elif args.cmd == "apps":
        for a in pc.list_applications():
            print(" -", a)
    elif args.cmd == "see":
        print(pc.see(args.app))
    elif args.cmd == "click":
        print(pc.click(args.role, args.name))
    elif args.cmd == "type":
        print(pc.type_text(args.text))
    elif args.cmd == "key":
        print(pc.press_key(args.key))
    elif args.cmd == "open":
        print(pc.open_application(args.command))
    else:
        parser.print_help()


if __name__ == "__main__":
    import json  # noqa
    _cli()