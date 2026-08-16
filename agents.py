import os
import asyncio
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langgraph_supervisor import create_supervisor

from all_sub_agents import ALL_SUB_AGENTS
from storage_paths import agent_dir, open_agent_sqlite

load_dotenv()

# ---------------------------------------------------------------------------
# AGENT IDENTITY / MEMORY LOCATION -> /agent/main_agent/ (persistent bucket)
# ---------------------------------------------------------------------------
AGENT_NAME = "main_agent"
ROLE = "Chief Personal Assistant"
MEMORY_DIR = agent_dir(AGENT_NAME)
DB_PATH = os.path.join(MEMORY_DIR, "state.db")

# ---------------------------------------------------------------------------
# MAIN AGENT LLM
# ---------------------------------------------------------------------------
_llm = init_chat_model(
    model_provider="google_genai",
    model=os.getenv("LLM_MODEL"),
    api_key=os.getenv("LLM_API_KEY"),
)

# ---------------------------------------------------------------------------
# STATE / MEMORY (sqlite, kept for this agent's whole lifetime, tuned to be
# safe on S3-style / object-storage persistent buckets — see storage_paths.py)
# ---------------------------------------------------------------------------

async def _make_checkpointer(db_path: str) -> AsyncSqliteSaver:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    return AsyncSqliteSaver(conn)

_checkpointer = asyncio.run(_make_checkpointer(DB_PATH))

# ---------------------------------------------------------------------------
# ASSISTANT AGENT BACKSTORY AND GOAL
# ---------------------------------------------------------------------------
Goal = (
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

Backstory = (
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

SUPERVISOR_PROMPT = f"You are the {ROLE}.\n\n" + Goal + "\n\n" + Backstory

# ---------------------------------------------------------------------------
# 1) Main Agent - the personal, trusted, all-purpose assistant
#    (built once, at import time, exactly like the sub agents)
# ---------------------------------------------------------------------------
_supervisor_builder = create_supervisor(
    agents=ALL_SUB_AGENTS,
    model=_llm,
    prompt=SUPERVISOR_PROMPT,
    supervisor_name=AGENT_NAME,
    add_handoff_back_messages=True,
    output_mode="full_history",
)

main_assistant_agent = _supervisor_builder.compile(
    checkpointer=_checkpointer,
    name=AGENT_NAME,
)


# ---------------------------------------------------------------------------
# MAIN ASSISTANT AGENTING SYSTEM
# ---------------------------------------------------------------------------
def main_agent(
    user_command: str,
    user_attachment: str | None = None,
    thread_id: str = "default",
) -> str:
    """
    Single-shot, synchronous entry point - same call shape as the original
    main_agent(user_command, user_attachment) -> str. `thread_id` is optional
    and only used so multiple separate conversations (as shown in the app's
    sidebar) each keep their own persisted history inside the same
    main_assistant_agent graph/state.
    """
    text = user_command
    if user_attachment:
        text = f"{text}\n\n[সংযুক্ত ফাইল: {user_attachment}]"

    config = {"configurable": {"thread_id": thread_id}}
    result = main_assistant_agent.invoke(
        {"messages": [{"role": "user", "content": text}]},
        config=config,
    )
    final_message = result["messages"][-1]
    return getattr(final_message, "content", str(final_message))
