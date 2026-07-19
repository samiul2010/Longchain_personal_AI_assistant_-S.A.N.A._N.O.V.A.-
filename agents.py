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
    

