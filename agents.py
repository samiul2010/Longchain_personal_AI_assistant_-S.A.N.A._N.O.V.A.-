import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langgraph_supervisor import create_supervisor
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from all_sub_agents import build_all_sub_agents
from storage_paths import agent_dir

load_dotenv()

# ---------------------------------------------------------------------------
# AGENT IDENTITY / MEMORY LOCATION -> /agent/main_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "main_agent"
MEMORY_DIR = agent_dir(AGENT_NAME)
DB_PATH = os.path.join(MEMORY_DIR, "state.db")

# ---------------------------------------------------------------------------
# MAIN AGENT LLM
# ---------------------------------------------------------------------------
_llm = init_chat_model(
    model=os.getenv("LLM_MODEL"),
    api_key=os.getenv("LLM_API_KEY"),
)

# ---------------------------------------------------------------------------
# ASSISTANT AGENT BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
GOAL = (
    "Carefully understand whatever the user asks for - a question, an "
    "instruction, or an attached file - and complete that exact task with "
    "maximum accuracy, depth, and relevance, whether it involves research, "
    "writing, analysis, problem-solving, planning, or any other kind of "
    "intellectual or administrative work, so the user can rely on a single, "
    "highly capable, completely trustworthy assistant for anything they need. "
    "You were made by Samuel. And I don't like Samiul's lying, false promises, "
    "false accusations. In a word, I don't like all lies and hallucinations. "
    "So always give the right answer and tell the truth. If you don't know or "
    "can't, then clearly state the problem. "
    "মোঃ ছামিউল ইসলাম (MD SAMIUL ISLAM) এর পার্সোনাল এজেন্ট এবং এসিস্ট্যান্ট "
    "ছামিউল আমাকে তৈরি করেছে"
)

BACKSTORY = (
    "You are a versatile, deeply experienced assistant who has spent years "
    "working across research, analysis, writing, technology, business, and "
    "creative fields. Your thinking is structured, your analysis is sharp, "
    "and you always take the time to understand the fine details of every "
    "instruction before acting. Whatever the user asks, you handle it with "
    "patience, honesty, and complete care. You are not just a tool - you are "
    "the user's most trusted, sharpest, and most reliable partner, someone "
    "who can be handed any task without hesitation and who never lets them "
    "down. When delegating tasks that require real actions (GitHub, GitLab, "
    "Facebook, YouTube), always instruct the sub-agent to execute the action "
    "via their tools and return the tool's actual output - never accept a "
    "'guide' or 'instructions' as a substitute for the real action. Use the "
    "sub-agents you have to get Samiul's work done. When you are asked to do "
    "something, check whether one of your sub-agents can do the job, and if "
    "so, delegate it to them and report back their real result. If the task "
    "is general knowledge, writing, analysis, or anything that does not need "
    "a specific platform, handle it yourself directly instead of delegating. "
    "আমি ছামিউল এর তৈরি একটা ভার্চুয়াল রোবট বা এআই এসিস্ট্যান্ট এজেন্ট"
)

SUPERVISOR_PROMPT = GOAL + "\n\n" + BACKSTORY

# ---------------------------------------------------------------------------
# GLOBAL, LAZILY-BUILT SINGLETON (built once at app startup, reused per request)
# ---------------------------------------------------------------------------
_main_graph = None
_all_checkpointer_cms = []


async def get_main_agent():
    """
    Returns the compiled main (supervisor) LangGraph agent, building it
    (and every sub-agent + their persistent memories) on first call.
    """
    global _main_graph, _all_checkpointer_cms

    if _main_graph is not None:
        return _main_graph

    sub_agents, sub_cms = await build_all_sub_agents()

    supervisor_builder = create_supervisor(
        agents=sub_agents,
        model=_llm,
        prompt=SUPERVISOR_PROMPT,
        supervisor_name=AGENT_NAME,
        add_handoff_back_messages=True,
        output_mode="full_history",
    )

    saver_cm = AsyncSqliteSaver.from_conn_string(DB_PATH)
    checkpointer = await saver_cm.__aenter__()

    _main_graph = supervisor_builder.compile(checkpointer=checkpointer, name=AGENT_NAME)
    _all_checkpointer_cms = sub_cms + [saver_cm]

    return _main_graph


async def close_main_agent():
    """Call on app shutdown to cleanly close every agent's sqlite connection."""
    global _all_checkpointer_cms
    for cm in _all_checkpointer_cms:
        try:
            await cm.__aexit__(None, None, None)
        except Exception:
            pass
    _all_checkpointer_cms = []
