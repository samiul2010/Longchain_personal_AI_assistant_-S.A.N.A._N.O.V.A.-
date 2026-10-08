# ---------------------------------------------------------------------------
#IMPORT_ALL_SUB_AGENTS
# ---------------------------------------------------------------------------
from sub_agents.coding.github_agent.github import _git_hub_agent, AGENT_NAME as GITHUB_NAME
from sub_agents.coding.gitlab_agent.gitlab import _git_lab_agent, AGENT_NAME as GITLAB_NAME
from sub_agents.social_media.facebook_agent.facebook import _facebook_agent, AGENT_NAME as FACEBOOK_NAME
from sub_agents.social_media.youtube_agent.youtube import _youtube_agent, AGENT_NAME as YOUTUBE_NAME

# ---------------------------------------------------------------------------
#CREATE_OBJECT_ALL_SUB_AGENTS
# ---------------------------------------------------------------------------
_git_hub=_git_hub_agent()
_git_lab=_git_lab_agent()
_facebook=_facebook_agent()
_youtube=_youtube_agent()


# ---------------------------------------------------------------------------
#ALL_SUB_AGENTS_LIST
# ---------------------------------------------------------------------------
ALL_SUB_AGENTS=[
    _git_hub,
    _git_lab,
    _facebook,
    _youtube,
]

# Agent names, in the same order, used by app.py to label the Manus-style
# action timeline (agent handoffs / tool calls) in the UI.
SUB_AGENT_NAMES = [
    GITHUB_NAME,
    GITLAB_NAME,
    FACEBOOK_NAME,
    YOUTUBE_NAME,
]
