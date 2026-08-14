# ---------------------------------------------------------------------------
# IMPORT_ALL_SUB_AGENT_BUILDERS
# ---------------------------------------------------------------------------
from sub_agents.coding.git_hub_agent.git_hub import build_git_hub_agent, AGENT_NAME as GITHUB_NAME
from sub_agents.coding.git_lab_agent.git_lab import build_git_lab_agent, AGENT_NAME as GITLAB_NAME
from sub_agents.social_media.facebook_agent.facebook import build_facebook_agent, AGENT_NAME as FACEBOOK_NAME
from sub_agents.social_media.youtube_agent.youtube import build_youtube_agent, AGENT_NAME as YOUTUBE_NAME

SUB_AGENT_NAMES = [GITHUB_NAME, GITLAB_NAME, FACEBOOK_NAME, YOUTUBE_NAME]


async def build_all_sub_agents():
    """
    Builds every sub agent (each with its own compiled LangGraph react-agent
    and its own persistent sqlite memory under /agent/<agent_name>/).

    Returns:
        agents: list[CompiledStateGraph]  -> handed to the supervisor
        checkpointer_cms: list            -> async context managers to close on shutdown
    """
    git_hub_agent, gh_cm = await build_git_hub_agent()
    git_lab_agent, gl_cm = await build_git_lab_agent()
    facebook_agent, fb_cm = await build_facebook_agent()
    youtube_agent, yt_cm = await build_youtube_agent()

    agents = [git_hub_agent, git_lab_agent, facebook_agent, youtube_agent]
    checkpointer_cms = [gh_cm, gl_cm, fb_cm, yt_cm]

    return agents, checkpointer_cms
