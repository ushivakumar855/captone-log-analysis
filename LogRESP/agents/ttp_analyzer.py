# agents/ttp_analyzer.py  —  MITRE ATT&CK analysis agent
# Single definition, used by both detection and benchmark pipelines.

import json
import time
from typing import Any, Dict, Optional, Literal

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from config import (
    OLLAMA_BASE_URL,
    DEFAULT_MODEL,
    LLM_TEMPERATURE,
)
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PROMPT_MODE: Literal["cot"] = "cot"


# -----------------------------------------
# Prompt: JSON-only "CoT-style" (auditable)
# -----------------------------------------
_SYSTEM_COT_JSON = (
    "You are an expert Linux cybersecurity analyst. You map system logs to the MITRE ATT&CK framework.\n"
    "Follow a step-by-step approach internally, but do NOT reveal hidden chain-of-thought.\n"
    "Instead, output concise high-level steps and evidence.\n"
    "If a benign tool (curl/tar/bash/python) is spawned by suspicious parents or connects to external IPs, treat as suspicious.\n"
    "Output MUST be valid JSON only (no markdown, no extra text)."
)

_HUMAN_COT_JSON = """
Analyze this Linux system event and its deep graph provenance.

Raw Log Event:
{log}

Extended Graph Context (Provenance):
{context}

Task:
Return JSON with EXACT keys:
{{
  "mode": "cot",
  "verdict": "Benign|Malicious|Suspicious",
  "confidence": 0.0,
  "mitre": {{
    "tactic": "string or empty",
    "technique": "string or empty",
    "technique_id": "string or empty"
  }},
  "analysis_steps": ["3-6 short bullets describing your reasoning at a high level"],
  "key_evidence": {{
    "execution_chain": "short string",
    "files": ["..."],
    "network_ips": ["..."],
    "suspicious_indicators": ["..."]
  }},
  "two_sentence_summary": "exactly two sentences"
}}

Rules:
- confidence must be between 0 and 1.
- If insufficient data, use verdict=Suspicious with low confidence.
- technique_id should look like Txxxx (e.g., T1059) or be empty.
"""


def _build_llm(model_name: str | None = None) -> ChatOllama:
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


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """
    If the model accidentally adds extra text, try to extract the JSON object.
    """
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def ttp_analyzer_node(state: Dict[str, Any], model_name: str | None = None) -> Dict[str, Any]:
    """
    Analyzer: JSON-only output suitable for evaluation pipelines.

    Inputs expected in state:
      - raw_log (dict)
      - neo4j_context (string) [optional but recommended]
      - prompt_mode (currently only 'cot' supported)
    Outputs:
      - final_analysis (raw model text)
      - final_analysis_json (parsed JSON when possible)
    """
    effective_model = model_name or DEFAULT_MODEL
    mode = state.get("prompt_mode", DEFAULT_PROMPT_MODE)

    logger.info("[TTP Analyzer] Starting analysis with model=%s mode=%s", effective_model, mode)

    try:
        llm = _build_llm(model_name)

        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_COT_JSON),
            ("human", _HUMAN_COT_JSON),
        ])

        chain = prompt | llm | StrOutputParser()

        log_json = json.dumps(state.get("raw_log", {}), indent=2)
        context_text = state.get("neo4j_context", "No extended graph context found.")
        logger.debug("[TTP Analyzer] Input log len=%d, context len=%d", len(log_json), len(context_text))

        invoke_start = time.time()
        response_text = chain.invoke({
            "log": log_json,
            "context": context_text,
        })
        invoke_time = time.time() - invoke_start

        logger.debug("[TTP Analyzer] LLM response in %.2fs (len=%d)", invoke_time, len(response_text or ""))

        out: Dict[str, Any] = {"final_analysis": response_text}

        parsed: Optional[dict] = None
        try:
            parsed = _safe_json_loads(response_text)
        except Exception as e:
            logger.warning("[TTP Analyzer] Failed to parse model output as JSON (mode=%s): %s", mode, e)

        if parsed is not None:
            out["final_analysis_json"] = parsed

            # Optional: quick log signal
            verdict = str(parsed.get("verdict", "")).strip()
            conf = parsed.get("confidence", None)
            logger.info("[TTP Analyzer] Verdict=%s confidence=%s (time=%.2fs)", verdict, conf, invoke_time)

        return out

    except Exception as e:
        logger.error("[TTP Analyzer] Analysis failed: %s", e, exc_info=True)
        raise