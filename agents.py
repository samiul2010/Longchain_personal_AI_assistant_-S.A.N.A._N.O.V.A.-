import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process,LLM,Memory
from crewai_tools import SerperDevTool
from crewai_files import File, FileBytes
from vs_ide_sub_agent import _vs_ide_sub_agent

load_dotenv()


# ---------------------------------------------------------------------------# MAIN AGENT LLM
# ---------------------------------------------------------------------------
_llm=LLM(
    api_key=os.getenv("LLM_API_KEY"),
    model=os.getenv("LLM_MODEL")

)
lmmn=os.getenv("LLM_API_KEY")
_memory = Memory(embedder={
    "provider": "google-generativeai",
    "config": {
        "model_name": "gemini-embedding-001",
        "api_key": f"{lmmn}",  # or set GOOGLE_API_KEY env var
    },
})


# ---------------------------------------------------------------------------
# 1) Main Agent - the personal, trusted, all-purpose assistant
# ---------------------------------------------------------------------------
main_assistant_agent= Agent(
    role="Chief Personal Assistant",
    goal=(
        "Carefully understand whatever the user asks for - a question, an "
        "instruction, or an attached file - and complete that exact task with "
        "maximum accuracy, depth, and relevance, whether it involves research, "
        "writing, analysis, problem-solving, planning, or any other kind of "
        "intellectual or administrative work, so the user can rely on a single, "
        "highly capable, completely trustworthy assistant for anything they need."
        "You were made by Samuel.And I don't like Samiul's lying, false promises, false accusations. In a word, I don't like all lies and hallucinations."
        "So always give the right answer and tell the truth. If you don't know or can't, then clearly state the problem."
    ),
    backstory=(
        "You are a versatile, deeply experienced assistant who has spent years "
        "working across research, analysis, writing, technology, business, and "
        "creative fields. Your thinking is structured, your analysis is sharp, "
        "and you always take the time to understand the fine details of every "
        "instruction before acting. Whatever the user asks, you handle it with "
        "patience, honesty, and complete care. You are not just a tool - you are "
        "the user's most trusted, sharpest, and most reliable partner, someone "
        "who can be handed any task without hesitation and who never lets them down."
        "When delegating tasks that require real GitHub actions, always instruct the coworker to execute the action via their tools and return the tool's actual output — never accept a 'guide' or 'instructions' as a substitute for the real action."
        "Use the snake agents you have to make Samuel work for the one who created you."
        "When you are asked to do something, you search your entire system to see if anyone can do the job. If they can, get it done."
        "The agents you have have some special features, use them to complete the task, they have tools or MCP is added so they can use them and work with them if they want."
        "If you are Samiul's main agent, then when Samiul asks you to work, you will do his work. You don't need to use your own tools because Samiul has put a snake agent under you to work."
    ),
    llm=_llm,
    inject_date=True,
    verbose=True,
    allow_delegation=True,
    max_iter=10,
    max_retry_limit=6,
    respect_context_window=False,
    use_system_prompt=False,
    multimodal=False,
    reasoning=False,
    #max_reasoning_attempts=4,
    #memory=_memory,
)

# --------------------------------------------------------------------------
#all sub agent object ()
# --------------------------------------------------------------------------
_mcp_vs_ide_code=_vs_ide_sub_agent()


# --------------------------------------------------------------------------
#all sub agent list []
# --------------------------------------------------------------------------
ALL_SUB_AGENT=_mcp_vs_ide_code



def main_agent(user_command: str,user_attachment: str | None = None) -> str:
    
    attachment_files = {}
    
    if user_attachment is not None:
        attachment_files["attached_file"] = File(source=user_attachment)
    # ---------------------------------------------------------------------------
    main_task = Task(
        description=user_command,
        expected_output=(
            "A complete, clear, accurate, and directly usable result for whatever "
            "task is described in the instruction."
        ),
        input_files=attachment_files
    )


    # ---------------------------------------------------------------------------      
    main_crew = Crew(
        agents=[],
        manager_agent=ALL_SUB_AGENT,
        tasks=[main_task],
        process=Process.hierarchical,
        verbose=True,
        tracing=True,
    )
    agent_instance = _vs_ide_sub_agent()
    logger.info(f"[MCP-DIAG] Agent tools count: {len(agent_instance.tools or [])}")
    logger.info(f"[MCP-DIAG] Agent tool names: {[t.name for t in (agent_instance.tools or [])]}")
    # ---------------------------------------------------------------------------
    return str(main_crew.kickoff())
  
  
if __name__ == "__main__":
    from app import chat_agent
    import mcp_diagnostic
    chat_agent()
  
