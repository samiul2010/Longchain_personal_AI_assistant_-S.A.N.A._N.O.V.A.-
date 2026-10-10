"""
GuiBackend — drives the in-container Ubuntu+XFCE desktop via AT-SPI2 (the
Linux accessibility tree), not pixel coordinates. This is WHY the
Dockerfile installs a full desktop stack instead of just a headless
browser: AT-SPI2 lets you ask "find the button labeled 'Submit'" and get
back a real, clickable object - far more reliable than "click at
(482, 310) and hope the layout didn't shift."

ARCHITECTURE NOTE: this slots into the SAME tools/computer_use package as
your earlier bash LocalBackend - think of GuiBackend as a second backend
for a different capability (GUI apps) sitting next to the first one
(shell commands), not a replacement. A sub-agent could have both tools
available and pick whichever fits the task.

READ FIRST (before filling in the TODOs):
    https://gnome.pages.gitlab.gnome.org/at-spi2-core/at-spi2-doc/doxygen/index.html
    (the AT-SPI2 C/GObject docs - the Python bindings via
    `gi.repository.Atspi` mirror this API closely)

Also worth 10 minutes BEFORE writing any code: run `accerciser` (an
accessibility tree INSPECTOR, installable via `apt install accerciser`)
against a running XFCE session once, locally or in this container, and
just look at a real tree for Firefox or a simple GTK app. Seeing the
actual role names ("push button", "entry", "frame") and how deep text
fields nest will make every TODO below much faster to write correctly.
"""

import os
import subprocess
import time

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi


class GuiBackend:
    def __init__(self):
        # TODO 0: decide where this backend keeps its own working files
        # (e.g. downloaded files from a browser session, screenshots if
        # you ever add those). Same pattern as LocalBackend's
        # WORKSPACE_DIR - use agent_dir("agent_pc") from storage_paths.py,
        # NOT a path you construct by hand, so it lands in the real
        # persistent bucket regardless of restarts.
        self.workspace_dir = None  # <-- from storage_paths import agent_dir; agent_dir("agent_pc")

    # -------------------------------------------------------------------
    # Launching applications
    # -------------------------------------------------------------------
    def open_application(self, command: str) -> str:
        """
        TODO 1: launch a GUI application (e.g. "firefox-esr") as a
        background subprocess with the container's virtual display.

        Key detail: the subprocess needs DISPLAY set to whatever the
        entrypoint script exported (os.environ should already have it
        inherited - just confirm you're not overriding env= in a way
        that drops it). Use subprocess.Popen (NOT subprocess.run) since
        a GUI app is long-running and you don't want to block waiting
        for it to exit.

        Give the app a moment (time.sleep) after launching before trying
        to find its window via AT-SPI2 - it needs time to register on
        the accessibility bus. A fixed sleep is the simple version; a
        retry loop polling find_window() (TODO 2) is the more robust one
        - worth upgrading to once the simple version works.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------
    # Reading the accessibility tree
    # -------------------------------------------------------------------
    def find_window(self, app_name_substring: str):
        """
        TODO 2: walk Atspi's desktop/application list and return the
        first top-level window whose application name contains
        app_name_substring (case-insensitive). This is your starting
        point for everything else - every other method below takes a
        window (or an element found within one) as input.

        Rough shape (check the real API - names may differ slightly by
        pyatspi/Atspi version, this is to orient you, not to paste
        verbatim):
            desktop = Atspi.get_desktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app_name_substring.lower() in (app.get_name() or "").lower():
                    return app
            return None
        """
        raise NotImplementedError

    def describe_screen(self, window) -> str:
        """
        TODO 3: this is the GUI equivalent of a "screenshot description"
        for an agent that can't see pixels - recursively walk the
        accessibility tree under `window` and return a readable text
        outline of what's on screen: each element's role (button, entry,
        label, ...), its accessible name/label, and whether it's
        visible/enabled. This is what the LLM will actually read to
        decide what to click next, so make it concise - skip invisible
        or redundant container elements, don't dump every pixel of
        layout info.

        Think about a recursive helper:
            def _walk(element, depth=0) -> list[str]:
                lines = [f"{'  '*depth}{element.get_role_name()}: {element.get_name()}"]
                for i in range(element.get_child_count()):
                    lines += _walk(element.get_child_at_index(i), depth + 1)
                return lines
        """
        raise NotImplementedError

    def find_element(self, window, role: str, name_substring: str):
        """
        TODO 4: search the tree under `window` for the first element
        whose role matches `role` (e.g. "push button", "entry", "frame" -
        check Atspi.Role for the exact constant names) AND whose
        accessible name contains name_substring (case-insensitive).
        Reuse the same recursive-walk idea as describe_screen, but
        return the matching element object itself instead of text.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------
    # Acting on elements
    # -------------------------------------------------------------------
    def click(self, element) -> str:
        """
        TODO 5: invoke the element's default "click" action. AT-SPI2
        elements that support actions expose an Action interface - look
        at `element.get_action_iface()` (or similar - exact accessor
        name depends on binding version) and call do_action(0) for the
        first/default action, which is "click"/"press" for buttons.
        Return a short confirmation string.
        """
        raise NotImplementedError

    def type_text(self, element, text: str) -> str:
        """
        TODO 6: focus `element` first (elements usually expose a
        Component interface with grab_focus()), THEN set its text via
        the Text/EditableText interface rather than trying to simulate
        individual keystrokes - much more reliable. Look at
        Atspi.EditableText / element's editable-text interface methods
        like set_text_contents(text) or insert_text(...).
        """
        raise NotImplementedError

    def read_text(self, element) -> str:
        """
        TODO 7: read back an element's current text content (for reading
        a result, confirming what got typed, scraping a page's visible
        text via its accessible tree, etc.) via the Text interface's
        get_text(0, -1) (start/end character offsets, -1 means "to the
        end").
        """
        raise NotImplementedError
