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
memory = Memory(embedder={
    "provider": "google-generativeai",
    "config": {
        "model_name": "gemini-embedding-001",
        "api_key": f"{os.getenv("LLM_API_KEY")}",  # or set GOOGLE_API_KEY env var
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
    ),
    llm=_llm,
    inject_date=True,
    verbose=True,
    allow_delegation=True,
    max_iter=10,
    max_retry_limit=3,
    respect_context_window=True,
    use_system_prompt=True,
    multimodal=True,
    reasoning=True,
    max_reasoning_attempts=1,
    memory=True,
)

# --------------------------------------------------------------------------
#all sub agent object ()
# --------------------------------------------------------------------------
_mcp_vs_ide_code=_vs_ide_sub_agent()


# --------------------------------------------------------------------------
#all sub agent list []
# --------------------------------------------------------------------------
ALL_SUB_AGENT=[
    _mcp_vs_ide_code

]

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
        agents=ALL_SUB_AGENT,
        manager_agent=main_assistant_agent,
        tasks=[main_task],
        process=Process.hierarchical,
        verbose=True,
    )   
    # ---------------------------------------------------------------------------
    return str(main_crew.kickoff())
  
  
if __name__ == "__main__":
    from app import chat_agent
    chat_agent()
  
