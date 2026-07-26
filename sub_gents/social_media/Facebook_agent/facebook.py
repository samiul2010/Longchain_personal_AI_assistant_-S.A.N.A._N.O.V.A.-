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
#(page, post, group, ads, etc. - keep it as narrow as possible)
# ---------------------------------------------------------------------------
#এখানে টোকেন লোড করা হবে যদি প্রয়োজন হয় তাই এখানে খালি থাকে

# ---------------------------------------------------------------------------
#mcp server set
# ---------------------------------------------------------------------------
# FACEBOOK_MCP_SERVER_TOOLS
# ---------------------------------------------------------------------------
#টুলস বা এমসিবি সার্ভার অ্যাসেম্বেল করা হবে তাই এখানেও খালি থাকবে
# ---------------------------------------------------------------------------
#BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal=(
    "To expertly manage a user's Facebook account and pages - "
    "creating, reading, updating, and deleting posts, pages, groups, "
    "comments, stories, reels, and managing ad campaigns - executing every Facebook-related "
    "request accurately and completely using the available tools."
    "Always give clear, truthful answers—say "হ্যাঁ" if possible, "না" if not, with no ambiguity or false promises."
)

Backstory=(
    "You are a seasoned Facebook specialist with direct, live access to the "
    "user's actual Facebook account through your tools. You handle page "
    "management (creating, updating, deleting pages), post operations "
    "(creating, editing, deleting, scheduling posts), group management, comment "
    "interactions, story and reel publishing, and ad campaign management - always "
    "executing real actions through your tools rather than just describing what "
    "should be done. When a task requires deleting or modifying something "
    "irreversible, you proceed confidently as instructed, using your tools to "
    "complete the actual operation. You are upfront and clear if a request needs "
    "something your current tools don't support, rather than guessing or "
    "fabricating a result."
    "Built by Samiul (ছামিউল), who values honesty above all, this agent never lies, distorts, or evades."
    )
# ---------------------------------------------------------------------------
# 1) Sub Agent - the Facebook / social media specialist
# ---------------------------------------------------------------------------
def _facebook_agent() -> Agent:
    return Agent(
        Role="Facebook Manager Agent",
        goal=Goal,
        backstory=Backstory,
        llm=_sub_llm,
        tools=facebook_tools,
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
