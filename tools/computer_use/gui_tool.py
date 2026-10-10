"""
LangChain tool wrappers around GuiBackend.

DESIGN NOTE: unlike the bash tool, GUI steps are usually a SEQUENCE
("open Firefox, find the search box, type the query, press the button")
rather than one self-contained call. Think about whether the agent should
get one tool per primitive action (open_app, find_element, click,
type_text, read_screen) and chain several tool calls together itself in
a ReAct loop - OR whether you want a single higher-level tool like
"search_the_web(query)" that internally calls several GuiBackend methods
in sequence and only returns the final result. The first is more
flexible (the agent can recover from an element not being where
expected); the second is simpler to reason about and cheaper (fewer LLM
round-trips). Given everything else in this project so far has leaned
toward giving agents real tool-level control (not pre-baked macros),
the per-primitive approach is probably more consistent - but this is
worth deciding deliberately, not by default.
"""

from langchain_core.tools import tool

from .gui_backend import GuiBackend

_backend = None  # <-- replace with GuiBackend()

# TODO: keep track of "the currently relevant window" between tool calls
# within one task. A plain module-level variable is the simplest version
# (same pattern as _backend above); think about whether that's good
# enough or whether this needs to live in the graph's own state instead,
# the same way data_task_agent threads its scratchpad through state - the
# tradeoff is the same one you already reasoned through there.
_current_window = None


@tool
def open_application(command: str) -> str:
    """Launches a GUI application (e.g. 'firefox-esr') on the agent's desktop."""
    raise NotImplementedError


@tool
def describe_current_screen() -> str:
    """Returns a text outline of what's currently visible in the active application window."""
    raise NotImplementedError


@tool
def click_on(role: str, name: str) -> str:
    """Finds an element by its role (e.g. 'push button') and visible name/label, and clicks it."""
    raise NotImplementedError


@tool
def type_into(role: str, name: str, text: str) -> str:
    """Finds an element (e.g. a text entry) by role and name, and types text into it."""
    raise NotImplementedError
