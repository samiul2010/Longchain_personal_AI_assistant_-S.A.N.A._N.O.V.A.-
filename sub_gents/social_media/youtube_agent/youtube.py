import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_mcp_adapters.client import MultiServerMCPClient

from storage_paths import agent_dir

load_dotenv()

# ---------------------------------------------------------------------------
# AGENT IDENTITY / MEMORY LOCATION -> /agent/youtube_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "youtube_agent"
MEMORY_DIR = agent_dir(AGENT_NAME)
DB_PATH = os.path.join(MEMORY_DIR, "state.db")

# ---------------------------------------------------------------------------
# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm = init_chat_model(
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
# YOUTUBE_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
_mcp_client = MultiServerMCPClient(
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

# ---------------------------------------------------------------------------
# BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
GOAL = (
    "To expertly manage a user's YouTube channel - "
    "creating, reading, updating, and deleting videos, shorts, playlists, "
    "community posts, live streams, and managing channel settings - executing "
    "every YouTube-related request accurately and completely using the "
    "available tools. "
    'Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises.'
)

BACKSTORY = (
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

SYSTEM_PROMPT = GOAL + "\n\n" + BACKSTORY


async def build_youtube_agent():
    """
    Builds the compiled YouTube sub-agent graph with its own persistent
    sqlite-backed memory at /agent/youtube_agent/state.db.
    """
    tools = await _mcp_client.get_tools(server_name="youtube")

    saver_cm = AsyncSqliteSaver.from_conn_string(DB_PATH)
    checkpointer = await saver_cm.__aenter__()

    agent = create_agent(
        model=_sub_llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        name=AGENT_NAME,
        checkpointer=checkpointer,
    )
    return agent, saver_cm
