import os
import asyncio
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from model_utils import load_chat_model
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from storage_paths import agent_dir, open_agent_sqlite

load_dotenv()

# ---------------------------------------------------------------------------
# AGENT IDENTITY / MEMORY LOCATION -> /agent/facebook_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "facebook_agent"
ROLE = "Facebook Manager Agent"
MEMORY_DIR = agent_dir(AGENT_NAME)
DB_PATH = os.path.join(MEMORY_DIR, "state.db")

# ---------------------------------------------------------------------------
# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm = load_chat_model(
    model=os.getenv("SUB_LLM_MODEL"),
    api_key=os.getenv("SUB_LLM_API_KEY"),
)

# ---------------------------------------------------------------------------
# (page, post, group, ads, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_FACEBOOK_PAT = os.getenv("FACEBOOK_PAT")
_FACEBOOK_PID = os.getenv("FACEBOOK_PID")

# ---------------------------------------------------------------------------
# mcp server set
# ---------------------------------------------------------------------------
# FACEBOOK_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
_facebook_mcp = MultiServerMCPClient(
    {
        "facebook": {
            "transport": "stdio",
            "command": "just_facebook_mcp",
            "args": [],
            "env": {
                "FACEBOOK_ACCESS_TOKEN": _FACEBOOK_PAT or "",
                "FACEBOOK_PAGE_ID": _FACEBOOK_PID or "",
                **os.environ,
            },
        }
    }
)
facebook_tools = asyncio.run(_facebook_mcp.get_tools(server_name="facebook"))

# ---------------------------------------------------------------------------
# STATE / MEMORY (sqlite, kept for this agent's whole lifetime, tuned to be
# safe on S3-style / object-storage persistent buckets — see storage_paths.py)
# ---------------------------------------------------------------------------
_checkpointer = open_agent_sqlite(DB_PATH)

# ---------------------------------------------------------------------------
# BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal = (
    "To expertly manage a user's Facebook account and pages - "
    "creating, reading, updating, and deleting posts, pages, groups, "
    "comments, stories, reels, and managing ad campaigns - executing every "
    "Facebook-related request accurately and completely using the available "
    "tools. "
    'Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises.'
)

Backstory = (
    "You are a seasoned Facebook specialist with direct, live access to the "
    "user's actual Facebook account through your tools. You handle page "
    "management (creating, updating, deleting pages), post operations "
    "(creating, editing, deleting, scheduling posts), group management, comment "
    "interactions, story and reel publishing, and ad campaign management - always "
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
# 1) Sub Agent - the Facebook specialist
# ---------------------------------------------------------------------------
def _facebook_agent():
    return create_agent(
        model=_sub_llm,
        tools=facebook_tools,
        system_prompt=SYSTEM_PROMPT,
        name=AGENT_NAME,
        checkpointer=_checkpointer,
    )
