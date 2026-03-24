# agents/ir_agents.py  —  IR Strategist, Command Generator, Safety Auditor
# Three agents in one file (they are tightly coupled by design — the pipeline
# chains them sequentially and they share the same LLM config).

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import OLLAMA_BASE_URL, DEFAULT_MODEL, LLM_TEMPERATURE
from utils.logger import get_logger

logger = get_logger(__name__)

def _llm():
    return ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL, temperature=LLM_TEMPERATURE)

def ir_strategist_node(state: dict) -> dict:
    logger.info("[IR Strategist] Drafting containment strategy")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an IR Lead. Provide EXACTLY 3 short bullet points "
                   "(max 10 words each) for immediate containment. No explanations."),
        ("human",  "TTP Analysis:\n{analysis}\n\nDraft 3-step strategy:"),
    ])
    response = (_llm() | (lambda r: r)).invoke  # lazy; full call below
    chain = prompt | _llm()
    result = chain.invoke({"analysis": state.get("ttp_analysis", "")})
    return {"ir_strategy": result.content}

def command_generator_node(state: dict) -> dict:
    logger.info("[Cmd Generator] Generating containment commands")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Linux Systems Engineer. Output ONLY raw Bash commands. "
                   "Maximum 3 commands. No comments or explanations."),
        ("human",  "Target PID: {pid}\nStrategy:\n{strategy}\n\nBash Commands:"),
    ])
    chain = prompt | _llm()
    result = chain.invoke({"pid": state.get("process_id", ""), "strategy": state.get("ir_strategy", "")})
    clean = result.content.replace("```bash", "").replace("```", "").strip()
    return {"raw_commands": clean}

def safety_auditor_node(state: dict) -> dict:
    logger.info("[Safety Auditor] Reviewing commands for safety")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Senior Linux Security Auditor. Review proposed IR commands. "
                   "Ensure they do not contain catastrophic operations (rm -rf /, "
                   "database wipes, full shutdowns). Ensure kill signals target only "
                   "the malicious PID. Output ONLY the final safe Bash commands — "
                   "no markdown, no explanations."),
        ("human",  "Threat Context:\n{analysis}\n\nProposed Commands:\n{cmds}\n\nVerified Safe Commands:"),
    ])
    chain = prompt | _llm()
    result = chain.invoke({"analysis": state.get("ttp_analysis", ""), "cmds": state.get("raw_commands", "")})
    clean = result.content.replace("```bash", "").replace("```", "").strip()
    return {"verified_commands": clean}
