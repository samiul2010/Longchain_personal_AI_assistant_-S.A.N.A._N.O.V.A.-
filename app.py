import os
import json
import uuid
import asyncio
import shutil
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agents import main_assistant_agent, AGENT_NAME
from all_sub_agents import SUB_AGENT_NAMES
from storage_paths import agent_dir

# ---------------------------------------------------------------------------
# Resolve paths relative to THIS file, not the process's current working
# directory (which may differ from the project root depending on how the
# platform/container launches uvicorn) — avoids "Directory does not exist"
# errors when mounting /static.
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ---------------------------------------------------------------------------
# PERSISTENCE PATHS — everything (thread index + uploaded files) lives inside
# the persistent /agent storage bucket, under this agent's own folder, so a
# Space restart/redeploy never loses conversation history or attachments.
# ---------------------------------------------------------------------------
MAIN_MEMORY_DIR = agent_dir(AGENT_NAME)
THREADS_INDEX_PATH = os.path.join(MAIN_MEMORY_DIR, "threads.json")
UPLOADS_DIR = os.path.join(MAIN_MEMORY_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

_threads_lock = asyncio.Lock()

app = FastAPI(title="Personal Assistant")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# THREAD INDEX HELPERS (so the sidebar / history survive a page refresh)
# ---------------------------------------------------------------------------
def _read_threads():
    if not os.path.exists(THREADS_INDEX_PATH):
        return []
    try:
        with open(THREADS_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write_threads(threads):
    with open(THREADS_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(threads, f, ensure_ascii=False, indent=2)


async def _touch_thread(thread_id: str, title: str | None = None):
    async with _threads_lock:
        threads = _read_threads()
        now = datetime.now(timezone.utc).isoformat()
        found = None
        for t in threads:
            if t["id"] == thread_id:
                found = t
                break
        if found is None:
            found = {
                "id": thread_id,
                "title": title or "নতুন কথোপকথন",
                "created_at": now,
                "updated_at": now,
            }
            threads.insert(0, found)
        else:
            found["updated_at"] = now
            if title and found.get("title") == "নতুন কথোপকথন":
                found["title"] = title
            threads.remove(found)
            threads.insert(0, found)
        _write_threads(threads)


# ---------------------------------------------------------------------------
# API: index page
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---------------------------------------------------------------------------
# API: list conversation threads (sidebar)
# ---------------------------------------------------------------------------
@app.get("/api/threads")
async def list_threads():
    return JSONResponse(_read_threads())


@app.post("/api/threads")
async def create_thread():
    thread_id = str(uuid.uuid4())
    await _touch_thread(thread_id)
    return JSONResponse({"thread_id": thread_id})


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str):
    async with _threads_lock:
        threads = [t for t in _read_threads() if t["id"] != thread_id]
        _write_threads(threads)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# API: file upload (attachment)
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = os.path.join(UPLOADS_DIR, safe_name)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return JSONResponse({"path": dest_path, "filename": file.filename})


# ---------------------------------------------------------------------------
# HELPERS: turn LangGraph's saved message state into a UI-friendly transcript
# ---------------------------------------------------------------------------
def _stringify(value) -> str:
    try:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)[:4000]
        return str(value)[:4000]
    except Exception:
        return str(value)[:4000]


def _agent_from_tool_name(tool_name: str) -> str | None:
    if tool_name and tool_name.startswith("transfer_to_"):
        candidate = tool_name[len("transfer_to_"):]
        if candidate in SUB_AGENT_NAMES:
            return candidate
    return None


def _messages_to_turns(messages):
    """
    Walk a flattened LangGraph message history (as produced by
    langgraph_supervisor with output_mode='full_history') and rebuild
    Manus-style turns: {role: user, text} and
    {role: assistant, steps: [...], text: final_answer}.
    """
    turns = []
    current = None
    pending_tool_calls = {}  # tool_call_id -> step dict

    def _new_assistant_turn():
        return {"role": "assistant", "steps": [], "text": ""}

    for msg in messages:
        if isinstance(msg, HumanMessage):
            turns.append({"role": "user", "text": msg.content if isinstance(msg.content, str) else _stringify(msg.content)})
            current = _new_assistant_turn()
            turns.append(current)

        elif isinstance(msg, AIMessage):
            if current is None:
                current = _new_assistant_turn()
                turns.append(current)

            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get("name")
                    agent_name = _agent_from_tool_name(tool_name)
                    if agent_name:
                        step = {"type": "agent_start", "agent": agent_name}
                    else:
                        step = {
                            "type": "tool",
                            "tool": tool_name,
                            "input": _stringify(tc.get("args")),
                            "output": None,
                        }
                    current["steps"].append(step)
                    pending_tool_calls[tc.get("id")] = step
            elif msg.content:
                text = msg.content if isinstance(msg.content, str) else _stringify(msg.content)
                if text.strip():
                    current["text"] = text

        elif isinstance(msg, ToolMessage):
            step = pending_tool_calls.get(msg.tool_call_id)
            if step is not None and step.get("type") == "tool":
                step["output"] = _stringify(msg.content)

    return turns


# ---------------------------------------------------------------------------
# API: load full history for a thread (used on page refresh)
# ---------------------------------------------------------------------------
@app.get("/api/history")
async def history(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await main_assistant_agent.aget_state(config)
    except Exception:
        return JSONResponse({"turns": []})

    if not state or not state.values:
        return JSONResponse({"turns": []})

    messages = state.values.get("messages", [])
    turns = _messages_to_turns(messages)
    return JSONResponse({"turns": turns})


# ---------------------------------------------------------------------------
# API: streaming chat endpoint (NDJSON stream of Manus-style events)
# ---------------------------------------------------------------------------
def _sse(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


@app.post("/api/chat")
async def chat(
    thread_id: str = Form(...),
    text: str = Form(""),
    attachment_path: str | None = Form(None),
):
    graph = main_assistant_agent
    config = {"configurable": {"thread_id": thread_id}}

    user_text = text or ""
    if attachment_path:
        user_text = f"{user_text}\n\n[সংযুক্ত ফাইল: {attachment_path}]"

    await _touch_thread(thread_id, title=(text or "নতুন কথোপকথন")[:60])

    inputs = {"messages": [HumanMessage(content=user_text)]}

    async def event_stream():
        try:
            async for event in graph.astream_events(inputs, config=config, version="v2"):
                kind = event.get("event")
                node = (event.get("metadata") or {}).get("langgraph_node")
                name = event.get("name")

                if kind == "on_chain_start" and name in SUB_AGENT_NAMES and node == name:
                    yield _sse({"type": "agent_start", "agent": name})

                elif kind == "on_tool_start":
                    yield _sse({
                        "type": "tool_start",
                        "agent": node,
                        "tool": name,
                        "input": _stringify((event.get("data") or {}).get("input")),
                    })

                elif kind == "on_tool_end":
                    output = (event.get("data") or {}).get("output")
                    yield _sse({
                        "type": "tool_end",
                        "agent": node,
                        "tool": name,
                        "output": _stringify(output),
                    })

                elif kind == "on_chat_model_stream" and node == AGENT_NAME:
                    chunk = (event.get("data") or {}).get("chunk")
                    text_piece = getattr(chunk, "content", "") if chunk else ""
                    if isinstance(text_piece, list):
                        text_piece = "".join(
                            part.get("text", "") if isinstance(part, dict) else str(part)
                            for part in text_piece
                        )
                    if text_piece:
                        yield _sse({"type": "token", "text": text_piece})

            yield _sse({"type": "done"})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860)
