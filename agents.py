import os 
os.environ.setdefault("HF_HOME", "/tmp/hf_cache")
os.makedirs(os.environ["HF_HOME"], exist_ok=True)
import time
import logging
from dotenv import load_dotenv
import threading
from crewai import Agent, LLM, Crew, Task, Process
from crewai.tools import tool

load_dotenv()
logger = logging.getLogger(__name__)


_llm=LLM(
    api_key=os.getenv("LLM_API_KEY"),
    model=os.getenv("LLM_MODEL")
)

def main_agent():
    # Create an agent with all available parameters
    agent = Agent(
        role="Senior Data Scientist",
        goal="Analyze and interpret complex datasets to provide actionable insights",
        backstory="With over 10 years of experience in data science and machine learning, ",
        llm="gpt-4",  # Default: OPENAI_MODEL_NAME or "gpt-4"
        function_calling_llm=None,  # Optional: Separate LLM for tool calling
        verbose=False,  # Default: False
        allow_delegation=False,  # Default: False
        max_iter=20,  # Default: 20 iterations
        max_rpm=None,  # Optional: Rate limit for API calls
        max_execution_time=None,  # Optional: Maximum execution time in seconds
        max_retry_limit=2,  # Default: 2 retries on error
        allow_code_execution=False,  # Default: False
        code_execution_mode="safe",  # Default: "safe" (options: "safe", "unsafe")
        respect_context_window=True,  # Default: True
        use_system_prompt=True,  # Default: True
        multimodal=False,  # Default: False
        inject_date=False,  # Default: False
        date_format="%Y-%m-%d",  # Default: ISO format
        reasoning=False,  # Default: False
        max_reasoning_attempts=None,  # Default: None
        tools=[SerperDevTool()],  # Optional: List of tools
        knowledge_sources=None,  # Optional: List of knowledge sources
        embedder=None,  # Optional: Custom embedder configuration
        system_template=None,  # Optional: Custom system prompt template
        prompt_template=None,  # Optional: Custom prompt template
        response_template=None,  # Optional: Custom response template
        step_callback=None,  # Optional: Callback function for monitoring
    )


 
    


