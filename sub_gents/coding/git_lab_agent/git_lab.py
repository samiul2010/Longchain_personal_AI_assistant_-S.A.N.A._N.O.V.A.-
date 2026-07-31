import os
import logging
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai_tools import MCPServerAdapter 
from mcp import StdioServerParameters

load_dotenv()

# ---------------------------------------------------------------------------# SUB AGENT LLM
#llm api setup and configuration
# ---------------------------------------------------------------------------
_sub_llm = LLM(
    api_key=os.getenv("SUB_LLM_API_KEY"),
    model=os.getenv("SUB_LLM_MODEL"),
)
# ---------------------------------------------------------------------------
#(project, repo, pipeline, issue, merge_request, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_GITLAB_PAT=os.getenv("GITLAB_PAT")
_GITLAB_API_URL= os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
_GITLAB_READ_ONLY_MODE=os.getenv("GITLAB_READ_ONLY_MODE", "false")

# ---------------------------------------------------------------------------
# GIT_LAB_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
gitlab_server_params = StdioServerParameters(
    command="zereight-mcp-gitlab",
    args=[],  # version pin করা থাকলে HF Space-এ predictable বিল্ড হয়
    env={
        "GITLAB_PERSONAL_ACCESS_TOKEN":_GITLAB_PAT,
        "GITLAB_API_URL": _GITLAB_API_URL,
        "GITLAB_READ_ONLY_MODE":_GITLAB_READ_ONLY_MODE,
        "GITLAB_DISABLE_VERSION_CHECK": "true",
        **os.environ,
    },
)

_gitlab_adapter = MCPServerAdapter(gitlab_server_params)
git_lab_tools = _gitlab_adapter.tools


# ---------------------------------------------------------------------------
#BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal=(
    "To expertly manage a developer's GitLab account and projects - "
    "creating, reading, updating, and deleting projects, repositories, "
    "merge requests, issues, pipelines, snippets, and CI/CD configurations - executing every GitLab-related "
    "request accurately and completely using the available tools."
    "Always give clear, truthful answers—say \"হ্যা\" if possible, \"না\" if not, with no ambiguity or false promises."
)

Backstory=(
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
    "rather than guessing or fabricating a result."
    "Built by Samiul (ছামিউল), who values honesty above all, this agent never lies, distorts, or evades."
    )
# ---------------------------------------------------------------------------
# 1) Sub Agent - the GitLab / DevOps platform specialist
# ---------------------------------------------------------------------------
def _git_lab_agent() -> Agent:
    return Agent(
        role="GitLab Manager Agent",
        goal=Goal,
        backstory=Backstory,
        llm=_sub_llm,
        max_rpm=12,
        tools=git_lab_tools,
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
