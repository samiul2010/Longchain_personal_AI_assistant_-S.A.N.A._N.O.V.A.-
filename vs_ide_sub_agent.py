import os
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai_tools import MCPServerAdapter 
from crewai.mcp import MCPServerSSE,MCPServerStdio


load_dotenv()


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
git_hub=MCPServerStdio(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": f"{_GITHUB_PAT}"},
    cache_tools_list=True,
    tool_filter=None
)
# ------------------------------------------------------------------------
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
        mcps=[git_hub],
        tools=[],
        inject_date=True,
        verbose=True,
        allow_delegation=False,
        max_iter=2,
        max_retry_limit=1,
        respect_context_window=True,
        use_system_prompt=True,
        multimodal=True,
        reasoning=True,
        max_reasoning_attempts=1,
        #memory=True,
        
    )