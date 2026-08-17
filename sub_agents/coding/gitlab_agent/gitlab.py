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
# AGENT IDENTITY / MEMORY LOCATION -> /agent/git_lab_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "git_lab_agent"
ROLE = "GitLab Manager Agent"
MEMORY_DIR = agent_dir(AGENT_NAME)
DB_PATH = os.path.join(MEMORY_DIR, "state.db")

# ---------------------------------------------------------------------------
# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm = ChatLiteLLM(
    model=os.getenv("SUB_LLM_MODEL"),
    api_key=os.getenv("SUB_LLM_API_KEY"),
)

# ---------------------------------------------------------------------------
# (project, repo, pipeline, issue, merge_request, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_GITLAB_PAT = os.getenv("GITLAB_PAT")
_GITLAB_API_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
_GITLAB_READ_ONLY_MODE = os.getenv("GITLAB_READ_ONLY_MODE", "false")

# ---------------------------------------------------------------------------
# mcp server set
# ---------------------------------------------------------------------------
# GIT_LAB_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
_git_lab_mcp = MultiServerMCPClient(
    {
        "gitlab": {
            "transport": "stdio",
            "command": "zereight-mcp-gitlab",
            "args": [],
            "env": {
                "GITLAB_PERSONAL_ACCESS_TOKEN": _GITLAB_PAT or "",
                "GITLAB_API_URL": _GITLAB_API_URL,
                "GITLAB_READ_ONLY_MODE": _GITLAB_READ_ONLY_MODE,
                "GITLAB_DISABLE_VERSION_CHECK": "true",
                **os.environ,
            },
        }
    }
)
git_lab_tools = asyncio.run(_git_lab_mcp.get_tools(server_name="gitlab"))

# ---------------------------------------------------------------------------
# STATE / MEMORY (sqlite, kept for this agent's whole lifetime, tuned to be
# safe on S3-style / object-storage persistent buckets — see storage_paths.py)
# ---------------------------------------------------------------------------
_checkpointer = open_agent_sqlite(DB_PATH)

# ---------------------------------------------------------------------------
# BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal = (
    "To expertly manage a developer's GitLab account and projects - "
    "creating, reading, updating, and deleting projects, repositories, "
    "merge requests, issues, pipelines, snippets, and CI/CD configurations - "
    "executing every GitLab-related request accurately and completely using "
    "the available tools. "
    'Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises.'
)

Backstory = (
    "You are a seasoned GitLab specialist with direct, live access to the "
    "user's actual GitLab account through your tools. You handle project "
    "management (creating, deleting, archiving projects), repository operations "
    "(reading, editing, committing files), merge request workflows, issue "
    "tracking, CI/CD pipeline management, container registry, and snippet "
    "creation - always executing real actions through your tools rather than "
    "just describing what should be done. When a task requires deleting or "
    "modifying something irreversible, you proceed confidently as instructed, "
    "using your tools to complete the actual operation. You are upfront and "
    "clear if a request needs something your current tools don't support, "
    "rather than guessing or fabricating a result. "
    "Built by Samiul (ছামিউল), who values honesty above all, this agent never lies, distorts, or evades."
)

SYSTEM_PROMPT = f"You are the {ROLE}.\n\n" + Goal + "\n\n" + Backstory


# ---------------------------------------------------------------------------
# 1) Sub Agent - the GitLab specialist
# ---------------------------------------------------------------------------
def _git_lab_agent():
    return create_agent(
        model=_sub_llm,
        tools=git_lab_tools,
        system_prompt=SYSTEM_PROMPT,
        name=AGENT_NAME,
        checkpointer=_checkpointer,
    )
