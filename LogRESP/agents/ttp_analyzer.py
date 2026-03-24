# agents/ttp_analyzer.py  —  MITRE ATT&CK analysis agent
# Single definition, used by both detection and benchmark pipelines.

import json
import time
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
    effective_model = model_name or DEFAULT_MODEL
    try:
        logger.debug("[TTP Analyzer] Initializing LLM with model=%s", effective_model)
        llm = ChatOllama(
            model=effective_model,
            base_url=OLLAMA_BASE_URL,
            temperature=LLM_TEMPERATURE,
        )
        logger.debug("[TTP Analyzer] LLM initialized successfully")
        return llm
    except Exception as e:
        logger.error("[TTP Analyzer] LLM init failed: %s", e, exc_info=True)
        raise

def ttp_analyzer_node(state: dict, model_name: str | None = None) -> dict:
    effective_model = model_name or DEFAULT_MODEL
    logger.info("[TTP Analyzer] Starting analysis with model=%s", effective_model)
    
    try:
        llm = _build_llm(model_name)
        prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
        chain = prompt | llm
        
        log_json = json.dumps(state.get("raw_log", {}), indent=2)
        context_text = state.get("neo4j_context", "")
        logger.debug("[TTP Analyzer] Input log len=%d, context len=%d", 
                     len(log_json), len(context_text))
        
        invoke_start = time.time()
        response = chain.invoke({
            "log":     log_json,
            "context": context_text,
        })
        invoke_time = time.time() - invoke_start
        
        response_text = response.content
        logger.debug("[TTP Analyzer] LLM response in %.2fs (len=%d)", invoke_time, len(response_text))
        
        classification = "Unknown"
        if "Benign" in response_text:
            classification = "Benign"
        elif "Malicious" in response_text:
            classification = "Malicious"
        logger.info("[TTP Analyzer] Classification: %s (time=%.2fs)", classification, invoke_time)
        return {"final_analysis": response_text}
        
    except Exception as e:
        logger.error("[TTP Analyzer] Analysis failed: %s", e, exc_info=True)
        raise
