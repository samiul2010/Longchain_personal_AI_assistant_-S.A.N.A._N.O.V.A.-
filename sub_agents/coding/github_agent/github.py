import os
import asyncio
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_community.chat_models import ChatLiteLLM

from storage_paths import agent_dir, open_agent_sqlite

load_dotenv()

# ---------------------------------------------------------------------------
# AGENT IDENTITY / MEMORY LOCATION -> /agent/git_hub_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "git_hub_agent"
ROLE = "GitHub Manager Agent"
MEMORY_DIR = agent_dir(AGENT_NAME)
DB_PATH = os.path.join(MEMORY_DIR, "state.db")

# ---------------------------------------------------------------------------
# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm =ChatLiteLLM(
    model=os.getenv("SUB_LLM_MODEL"),
    api_key=os.getenv("SUB_LLM_API_KEY"),
)

# ---------------------------------------------------------------------------
# (repo, project, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_GITHUB_PAT = os.getenv("GITHUB_PAT")

# ---------------------------------------------------------------------------
# mcp server set
# ---------------------------------------------------------------------------
# GIT_HUB_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
_git_hub_mcp = MultiServerMCPClient(
    {
        "github": {
            "transport": "stdio",
            "command": "github-mcp-server",
            "args": ["stdio"],
            "env": {
                "GITHUB_PERSONAL_ACCESS_TOKEN": _GITHUB_PAT or "",
                "GITHUB_TOOLSETS": "all",
                **os.environ,
            },
        }
    }
)
# Loaded once, synchronously, at import time - same moment the original
# file loaded git_hub_tools = git_hub.tools at module scope.
git_hub_tools = asyncio.run(_git_hub_mcp.get_tools(server_name="github"))

# ---------------------------------------------------------------------------
# STATE / MEMORY (sqlite, kept for this agent's whole lifetime, tuned to be
# safe on S3-style / object-storage persistent buckets — see storage_paths.py)
# ---------------------------------------------------------------------------
_checkpointer = open_agent_sqlite(DB_PATH)

# ---------------------------------------------------------------------------
# BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal = (
    "To expertly manage a developer's GitHub account and repositories - "
    "creating, reading, updating, and deleting repositories, files, branches, "
    "commits, pull requests, and issues - executing every GitHub-related "
    "request accurately and completely using the available tools. "
    'Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises.'
)

Backstory = (
    "You are a seasoned GitHub specialist with direct, live access to the "
    "user's actual GitHub account through your tools. You handle repository "
    "management (creating, deleting, forking, archiving), file operations "
    "(reading, editing, committing), branch and pull request workflows, and "
    "issue tracking - always executing real actions through your tools rather "
    "than just describing what should be done. When a task requires deleting "
    "or modifying something irreversible, you proceed confidently as "
    "instructed, using your tools to complete the actual operation. You are "
    "upfront and clear if a request needs something your current tools don't "
    "support, rather than guessing or fabricating a result. "
    "Built by Samiul (ছামিউল), who values honesty above all, this agent never lies, distorts, or evades."
)

SYSTEM_PROMPT = f"You are the {ROLE}.\n\n" + Goal + "\n\n" + Backstory


# ---------------------------------------------------------------------------
# 1) Sub Agent - the GitHub specialist
# ---------------------------------------------------------------------------
def _git_hub_agent():
    return create_agent(
        model=_sub_llm,
        tools=git_hub_tools,
        system_prompt=SYSTEM_PROMPT,
        name=AGENT_NAME,
        checkpointer=_checkpointer,
    )
