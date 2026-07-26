import os
import logging
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai_tools import MCPServerAdapter 
from crewai.mcp import MCPServerSSE,MCPServerStdio,MCPServerHTTP
from mcp import StdioServerParameters

load_dotenv()
import crewai.utilities.pydantic_schema_utils as _schema_utils

_original_type_fn = _schema_utils._json_schema_to_pydantic_type

def _patched_json_schema_to_pydantic_type(json_schema, *args, **kwargs):
    if isinstance(json_schema.get("type"), list):
        json_schema = {**json_schema, "type": "string"}
    return _original_type_fn(json_schema, *args, **kwargs)

_schema_utils._json_schema_to_pydantic_type = _patched_json_schema_to_pydantic_type



# ---------------------------------------------------------------------------# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm = LLM(
    api_key=os.getenv("SUB_LLM_API_KEY"),
    model=os.getenv("SUB_LLM_MODEL"),
)
# ---------------------------------------------------------------------------
#(repo, project, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_GITHUB_PAT = os.getenv("GITHUB_PAT")

# ---------------------------------------------------------------------------
#mcp server set
# ---------------------------------------------------------------------------
# GIT_HUB_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
git_hub_api = StdioServerParameters(
    command="github-mcp-server",   # ✅ অফিসিয়াল Go বাইনারি (Dockerfile-এ বিল্ড করা)
    args=["stdio"],
    env={
        "GITHUB_PERSONAL_ACCESS_TOKEN": _GITHUB_PAT,
        "GITHUB_TOOLSETS": "repos,issues,pull_requests,code_security",
        **os.environ
    }
)
git_hub =MCPServerAdapter(git_hub_api)
git_hub_tools=git_hub.tools

# ---------------------------------------------------------------------------
#BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal=(
    "To expertly manage a developer's GitHub account and repositories - "
    "creating, reading, updating, and deleting repositories, files, branches, "
    "commits, pull requests, and issues - executing every GitHub-related "
    "request accurately and completely using the available tools."
    "Always give clear, truthful answers—say \"হ্যাঁ\" if possible, \"না\" if not, with no ambiguity or false promises."
)

Backstory=(
    "You are a seasoned GitHub specialist with direct, live access to the "
    "user's actual GitHub account through your tools. You handle repository "
    "management (creating, deleting, forking, archiving), file operations "
    "(reading, editing, committing), branch and pull request workflows, and "
    "issue tracking - always executing real actions through your tools rather "
    "than just describing what should be done. When a task requires deleting "
    "or modifying something irreversible, you proceed confidently as "
    "instructed, using your tools to complete the actual operation. You are "
    "upfront and clear if a request needs something your current tools don't "
    "support, rather than guessing or fabricating a result."
    "Built by Samiul (ছামিউল), who values honesty above all, this agent never lies, distorts, or evades."
    )
# ---------------------------------------------------------------------------
# 1) Sub Agent - the VS Code / GitHub repo specialist
# ---------------------------------------------------------------------------
def _git_hub_agent() -> Agent:
    return Agent(
        Role="GitHub Manager Agent",
        goal=Goal,
        backstory=Backstory,
        llm=_sub_llm,
        tools=git_hub_tools,
        inject_date=True,
        verbose=True,
        allow_delegation=False,
        max_iter=12,
        max_retry_limit=9,
        respect_context_window=False,
        use_system_prompt=False,
        multimodal=False,
        reasoning=False,
        #max_reasoning_attempts=8,
        #memory=True,
        
    )
  