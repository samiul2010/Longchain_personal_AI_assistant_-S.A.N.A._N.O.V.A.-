import os
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai_tools import MCPServerAdapter

load_dotenv()


# ---------------------------------------------------------------------------# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm = LLM(
    api_key=os.getenv("SUB_LLM_API_KEY"),
    model=os.getenv("SUB_LLM_MODEL"),
)


# ---------------------------------------------------------------------------
# MCP connection to GitHub's own remote MCP server.
#
# This is hosted and maintained by GitHub itself (https://api.githubcopilot.com/mcp/)
# - not a third-party relay - and stays available regardless of whether any
# codespace is open. It gives repo-level tools (read/write files, commits,
# branches, pull requests, issues, Actions, code search, etc.) via the GitHub
# API. It does NOT give arbitrary shell/terminal access inside a running
# container - for that you'd still need an always-on server of your own.
#
# Required env var (set as an HF Space secret):
#   GITHUB_PAT  - a GitHub Personal Access Token with the scopes you need
#                 (repo, project, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_GITHUB_PAT = os.getenv("GITHUB_PAT")

# GitHub's "projects" toolset currently returns a tool with a multi-type JSON
# schema (["string", "number", "boolean"]) that CrewAI's schema converter
# can't parse yet, which crashes MCPServerAdapter at startup. So we leave
# "projects" out and try the rest of the toolsets from most-complete to
# least, falling back automatically if any set still fails to load - this
# way we always end up with whatever the largest *working* set of tools is,
# instead of the whole app crashing.
_TOOLSET_FALLBACK_CHAIN = [
    # 1) Everything except "projects" and the license-gated / remote-only extras
    "context,repos,issues,pull_requests,users,actions,code_security,dependabot,"
    "discussions,gists,git,labels,notifications,orgs,secret_protection,"
    "security_advisories,stargazers",
    # 2) A safer, smaller set in case one of the above still misbehaves
    "context,repos,issues,pull_requests,users,actions,code_security",
    # 3) GitHub's own documented default - the safest possible fallback
    "context,repos,issues,pull_requests,users",
]

# Allow a manual override (e.g. once you know exactly which set works, or to
# add "projects" back once CrewAI fixes the schema bug upstream).
_manual_override = os.getenv("GITHUB_MCP_TOOLSETS")
if _manual_override:
    _TOOLSET_FALLBACK_CHAIN = [_manual_override] + _TOOLSET_FALLBACK_CHAIN

_mcp_adapter = None
_vs_ide_tools = []

if _GITHUB_PAT:
    for _toolsets in _TOOLSET_FALLBACK_CHAIN:
        _server_params = {
            "url": "https://api.githubcopilot.com/mcp/",
            "transport": "streamable-http",
            "headers": {
                "Authorization": f"Bearer {_GITHUB_PAT}",
                "X-MCP-Toolsets": _toolsets,
            },
        }
        try:
            _mcp_adapter = MCPServerAdapter(_server_params)
            _mcp_adapter.start()
            _vs_ide_tools = _mcp_adapter.tools
            print(f"GitHub MCP connected with toolsets: {_toolsets}")
            print(f"Loaded {len(_vs_ide_tools)} tool(s): {[t.name for t in _vs_ide_tools]}")
            break
        except Exception as e:
            print(f"GitHub MCP toolset set failed ({_toolsets}): {e}")
            _mcp_adapter = None
            _vs_ide_tools = []
    else:
        print(
            "WARNING: every GitHub MCP toolset combination failed to load - "
            "the VS IDE sub-agent will run without any GitHub/repo tools."
        )
else:
    print(
        "WARNING: GITHUB_PAT not set - the VS IDE sub-agent will run without "
        "any GitHub/repo tools."
    )


# ---------------------------------------------------------------------------
# 1) Sub Agent - the VS Code / GitHub repo specialist
# ---------------------------------------------------------------------------
def _vs_ide_sub_agent() -> Agent:
    return Agent(
        role="vs IDE manager",
        goal=(
            "To expertly manage a developer's VS Code / GitHub workflow - reading and "
            "editing repository files, managing branches, commits, pull requests, "
            "issues, and workflows - handling extensions, settings, keybindings, "
            "snippets, themes, and workspace configuration questions, and "
            "troubleshooting IDE or repo-related issues to ensure a seamless and "
            "productive development experience."
        ),
        backstory=(
            "You are a seasoned VS Code and GitHub specialist with deep expertise in "
            "managing development environments and repositories across multiple "
            "programming languages and frameworks. With years of hands-on experience "
            "configuring VS Code for maximum productivity, you possess intimate "
            "knowledge of the editor's internals, extension ecosystem, and "
            "customization capabilities, as well as GitHub's branching, review, and "
            "automation workflows."
            " You've helped countless developers transform their cluttered, inefficient "
            "editors and repos into streamlined, well-organized workflows tailored to "
            "their specific needs. Your approach is methodical yet adaptable - you "
            "analyze the developer's tech stack, preferences, and pain points before "
            "recommending the perfect blend of extensions, keyboard shortcuts, "
            "settings, or repo changes. You stay constantly updated with the latest "
            "VS Code and GitHub features and community best practices."
            " Whether it's debugging extension conflicts, crafting custom snippets, "
            "reading or editing a file in the repo, opening a pull request, or "
            "triaging an issue, you handle it all with precision and clear "
            "communication. You have direct, live access to the developer's actual "
            "GitHub repository through your tools, and you use them whenever a task "
            "requires reading, editing, or changing something for real rather than "
            "just describing it. You are upfront when a request needs terminal/shell "
            "execution that your current tools don't support."
        ),
        llm=_sub_llm,
        inject_date=True,
        verbose=True,
        allow_delegation=False,
        max_iter=6,
        max_retry_limit=3,
        respect_context_window=True,
        use_system_prompt=True,
        multimodal=True,
        reasoning=True,
        max_reasoning_attempts=2,
        memory=True,
        tools=_vs_ide_tools,
    )