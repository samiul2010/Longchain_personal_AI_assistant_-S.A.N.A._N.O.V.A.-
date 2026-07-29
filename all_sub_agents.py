# ---------------------------------------------------------------------------
#IMPORT_ALL_SUB_AGENTS
# ---------------------------------------------------------------------------
from sub_gents.coding.git_hub_agent.git_hub import _git_hub_agent
from sub_gents.coding.git_lab_agent.git_lab import _git_lab_agent
from sub_gents.social_media.Facebook_agent.facebook import _facebook_agent

# ---------------------------------------------------------------------------
#CREATE_OBJECT_ALL_SUB_AGENTS
# ---------------------------------------------------------------------------
_git_hub=_git_hub_agent()
_git_lab=_git_lab_agent()
_facebook=_facebook_agent()


# ---------------------------------------------------------------------------
#ALL_SUB_AGENTS_LIST
# ---------------------------------------------------------------------------
ALL_SUB_AGENTS=[
    _git_hub,
    _git_lab,
    _facebook,
]