# agents/ttp_analyzer.py  —  MITRE ATT&CK analysis agent
# Single definition, used by both detection and benchmark pipelines.

import json
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import OLLAMA_BASE_URL, DEFAULT_MODEL, LLM_TEMPERATURE
from utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM = (
    "You are an expert Linux cybersecurity analyst who maps system logs to "
    "the MITRE ATT&CK framework. Pay close attention to the execution chain. "
    "If a benign tool is spawned by a suspicious parent or connects to an "
    "external IP, classify it as Malicious."
)

_HUMAN = """
Analyze this Linux system event and its graph provenance context.

Raw Log:
{log}

Graph Context:
{context}

Respond with:
1. Classification: Benign or Malicious
2. MITRE ATT&CK Tactic and Technique (if malicious)
3. Two-sentence explanation of attacker intent
"""

def _build_llm(model_name: str | None = None):
    return ChatOllama(
        model=model_name or DEFAULT_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=LLM_TEMPERATURE,
    )

def ttp_analyzer_node(state: dict, model_name: str | None = None) -> dict:
    logger.info("[TTP Analyzer] Running analysis with model=%s", model_name or DEFAULT_MODEL)
    llm = _build_llm(model_name)
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
    chain = prompt | llm
    response = chain.invoke({
        "log":     json.dumps(state.get("raw_log", {}), indent=2),
        "context": state.get("neo4j_context", ""),
    })
    return {"final_analysis": response.content}
