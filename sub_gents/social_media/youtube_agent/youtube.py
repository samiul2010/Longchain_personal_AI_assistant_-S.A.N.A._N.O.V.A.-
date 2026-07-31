import os
import logging
from dotenv import load_dotenv
from crewai import Agent, LLM
from crewai_tools import MCPServerAdapter 
from crewai.mcp import MCPServerSSE,MCPServerStdio,MCPServerHTTP
from mcp import StdioServerParameters

load_dotenv()

# ---------------------------------------------------------------------------# SUB AGENT LLM
# ---------------------------------------------------------------------------
_sub_llm = LLM(
    api_key=os.getenv("SUB_LLM_API_KEY"),
    model=os.getenv("SUB_LLM_MODEL"),
)
# ---------------------------------------------------------------------------
#(video, channel, playlist, shorts, live, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
_YOUTUBE_CID=os.getenv("YOUTUBE_CID")
_YOUTUBE_PCS=os.getenv("YOUTUBE_CLIENT_SECRET")
_YOUTUBE_MCP_TRANSPORT=os.getenv("YOUTUBE_MCP_TRANSPORT", "stdio")
    

# ---------------------------------------------------------------------------
# YOUTUBE_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
_youtube_mcp_server_params = StdioServerParameters(
    command="npx",
    args=["-y", "maagpi-youtube-mcp"],
    env={
        "YOUTUBE_CLIENT_ID":_YOUTUBE_CID,
        "YOUTUBE_CLIENT_SECRET":_YOUTUBE_PCS,
        "YOUTUBE_MCP_TRANSPORT":_YOUTUBE_MCP_TRANSPORT,
        **os.environ,
    },
)
_youtube_mcp_adapter = MCPServerAdapter(_youtube_mcp_server_params)
youtube_tools = _youtube_mcp_adapter.tools

# ---------------------------------------------------------------------------
#BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal=(
    "To expertly manage a user's YouTube channel - "
    "creating, reading, updating, and deleting videos, shorts, playlists, "
    "community posts, live streams, and managing channel settings - executing every YouTube-related "
    "request accurately and completely using the available tools."
    "Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises."
)

Backstory=(
    "You are a seasoned YouTube specialist with direct, live access to the "
    "user's actual YouTube channel through your tools. You handle video "
    "management (uploading, editing, deleting videos and shorts), playlist "
    "creation and curation, community post management, live stream scheduling, "
    "comment moderation, analytics review, and channel customization - always "
    "executing real actions through your tools rather than just describing what "
    "should be done. When a task requires deleting or modifying something "
    "irreversible, you proceed confidently as instructed, using your tools to "
    "complete the actual operation. You are upfront and clear if a request needs "
    "something your current tools don't support, rather than guessing or "
    "fabricating a result."
    "Built by Samiul (ছামিউল), who values honesty above all, this agent never lies, distorts, or evades."
    )
# ---------------------------------------------------------------------------
# 1) Sub Agent - the YouTube / video platform specialist
# ---------------------------------------------------------------------------
def _youtube_agent() -> Agent:
    return Agent(
        role="YouTube Manager Agent",
        goal=Goal,
        backstory=Backstory,
        llm=_sub_llm,
        tools=youtube_tools,
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
