import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_mcp_adapters.client import MultiServerMCPClient

from storage_paths import agent_dir

load_dotenv()

# ---------------------------------------------------------------------------
# AGENT IDENTITY / MEMORY LOCATION -> /agent/git_hub_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "git_hub_agent"
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
# (repo, project, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_GITHUB_PAT = os.getenv("GITHUB_PAT")

# ---------------------------------------------------------------------------
# GIT_HUB_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
_mcp_client = MultiServerMCPClient(
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

# ---------------------------------------------------------------------------
# BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
GOAL = (
    "To expertly manage a developer's GitHub account and repositories - "
    "creating, reading, updating, and deleting repositories, files, branches, "
    "commits, pull requests, and issues - executing every GitHub-related "
    "request accurately and completely using the available tools. "
    'Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises.'
)

BACKSTORY = (
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

SYSTEM_PROMPT = GOAL + "\n\n" + BACKSTORY


async def build_git_hub_agent():
    """
    Builds the compiled GitHub sub-agent graph with its own persistent
    sqlite-backed memory at /agent/git_hub_agent/state.db.

    Returns (compiled_graph, checkpointer_context_manager).
    The caller is responsible for keeping the context manager alive for the
    lifetime of the app and closing it on shutdown.
    """
    tools = await _mcp_client.get_tools(server_name="github")

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
