import os
import asyncio
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from storage_paths import agent_dir, open_agent_sqlite

load_dotenv()

# ---------------------------------------------------------------------------
# AGENT IDENTITY / MEMORY LOCATION -> /agent/youtube_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "youtube_agent"
ROLE = "YouTube Manager Agent"
MEMORY_DIR = agent_dir(AGENT_NAME)
DB_PATH = os.path.join(MEMORY_DIR, "state.db")

# ---------------------------------------------------------------------------
# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm = init_chat_model(
    model_provider=os.getenv("SUB_LLM_MODEL_PROVIDER"),
    model=os.getenv("SUB_LLM_MODEL"),
    api_key=os.getenv("SUB_LLM_API_KEY"),
)

# ---------------------------------------------------------------------------
# (video, channel, playlist, shorts, live, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_YOUTUBE_CID = os.getenv("YOUTUBE_CID")
_YOUTUBE_PCS = os.getenv("YOUTUBE_CLIENT_SECRET")
_YOUTUBE_MCP_TRANSPORT = os.getenv("YOUTUBE_MCP_TRANSPORT", "stdio")

# ---------------------------------------------------------------------------
# mcp server set
# ---------------------------------------------------------------------------
# YOUTUBE_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
_youtube_mcp = MultiServerMCPClient(
    {
        "youtube": {
            "transport": "stdio",
            "command": "maagpi-youtube-mcp",
            "args": [],
            "env": {
                "YOUTUBE_CLIENT_ID": _YOUTUBE_CID or "",
                "YOUTUBE_CLIENT_SECRET": _YOUTUBE_PCS or "",
                "YOUTUBE_MCP_TRANSPORT": _YOUTUBE_MCP_TRANSPORT,
                **os.environ,
            },
        }
    }
)
youtube_tools = asyncio.run(_youtube_mcp.get_tools(server_name="youtube"))

# ---------------------------------------------------------------------------
# STATE / MEMORY (sqlite, kept for this agent's whole lifetime, tuned to be
# safe on S3-style / object-storage persistent buckets — see storage_paths.py)
# ---------------------------------------------------------------------------
_checkpointer = open_agent_sqlite(DB_PATH)

# ---------------------------------------------------------------------------
# BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal = (
    "To expertly manage a user's YouTube channel - "
    "creating, reading, updating, and deleting videos, shorts, playlists, "
    "community posts, live streams, and managing channel settings - executing "
    "every YouTube-related request accurately and completely using the "
    "available tools. "
    'Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises.'
)

Backstory = (
    "You are a seasoned YouTube specialist with direct, live access to the "
    "user's actual YouTube channel through your tools. You handle video "
    "management (uploading, editing, deleting videos and shorts), playlist "
    "creation and curation, community post management, live stream scheduling, "
    "comment moderation, analytics review, and channel customization - always "
    "executing real actions through your tools rather than just describing what "
    "should be done. When a task requires deleting or modifying something "
    "irreversible, you proceed confidently as instructed, using your tools to "
    "complete the actual operation. You are upfront and clear if a request needs "
    "something your current tools don't support, rather than guessing or "
    "fabricating a result. "
    "Built by Samiul (ছামিউল), who values honesty above all, this agent never lies, distorts, or evades."
)

SYSTEM_PROMPT = f"You are the {ROLE}.\n\n" + Goal + "\n\n" + Backstory


# ---------------------------------------------------------------------------
# 1) Sub Agent - the YouTube specialist
# ---------------------------------------------------------------------------
def _youtube_agent():
    return create_agent(
        model=_sub_llm,
        tools=youtube_tools,
        system_prompt=SYSTEM_PROMPT,
        name=AGENT_NAME,
        checkpointer=_checkpointer,
    )
