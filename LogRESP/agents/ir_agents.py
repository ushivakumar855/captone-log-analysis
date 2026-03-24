# agents/ir_agents.py  —  IR Strategist, Command Generator, Safety Auditor
# Three agents in one file (they are tightly coupled by design — the pipeline
# chains them sequentially and they share the same LLM config).

import time
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from config import OLLAMA_BASE_URL, DEFAULT_MODEL, LLM_TEMPERATURE
from utils.logger import get_logger

logger = get_logger(__name__)

def _llm():
    try:
        logger.debug("[IR] Initializing LLM (model=%s)", DEFAULT_MODEL)
        llm = ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL, temperature=LLM_TEMPERATURE)
        logger.debug("[IR] LLM initialized successfully")
        return llm
    except Exception as e:
        logger.error("[IR] LLM initialization failed: %s", e, exc_info=True)
        raise

def ir_strategist_node(state: dict) -> dict:
    logger.info("[IR Strategist] Drafting containment strategy")
    
    try:
        analysis_input = state.get("ttp_analysis", "")
        logger.debug("[IR Strategist] Input analysis len=%d", len(analysis_input))
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an IR Lead. Provide EXACTLY 3 short bullet points "
                       "(max 10 words each) for immediate containment. No explanations."),
            ("human",  "TTP Analysis:\n{analysis}\n\nDraft 3-step strategy:"),
        ])
        
        start = time.time()
        chain = prompt | _llm()
        result = chain.invoke({"analysis": analysis_input})
        elapsed = time.time() - start
        
        strategy = result.content
        logger.debug("[IR Strategist] Strategy generated in %.2fs (len=%d)", elapsed, len(strategy))
        logger.info("[IR Strategist] Strategy: %s", strategy[:150])
        return {"ir_strategy": strategy}
        
    except Exception as e:
        logger.error("[IR Strategist] Strategy generation failed: %s", e, exc_info=True)
        raise

def command_generator_node(state: dict) -> dict:
    logger.info("[Cmd Generator] Generating containment commands")
    
    try:
        pid = state.get("process_id", "")
        strategy = state.get("ir_strategy", "")
        logger.debug("[Cmd Generator] Input PID=%s, strategy len=%d", pid, len(strategy))
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Linux Systems Engineer. Output ONLY raw Bash commands. "
                       "Maximum 3 commands. No comments or explanations."),
            ("human",  "Target PID: {pid}\nStrategy:\n{strategy}\n\nBash Commands:"),
        ])
        
        start = time.time()
        chain = prompt | _llm()
        result = chain.invoke({"pid": pid, "strategy": strategy})
        elapsed = time.time() - start
        
        raw_response = result.content
        logger.debug("[Cmd Generator] Raw response in %.2fs (len=%d)", elapsed, len(raw_response))
        
        # Clean markdown
        clean = raw_response.replace("```bash", "").replace("```", "").strip()
        logger.debug("[Cmd Generator] After markdown removal: len=%d", len(clean))
        
        # Validate output
        if not clean:
            logger.warning("[Cmd Generator] No commands generated after cleanup")
        else:
            cmd_lines = [c.strip() for c in clean.split("\n") if c.strip() and not c.strip().startswith("#")]
            logger.info("[Cmd Generator] Generated %d commands (time=%.2fs)", len(cmd_lines), elapsed)
            for i, cmd in enumerate(cmd_lines[:3], 1):
                logger.debug("  Cmd %d: %s", i, cmd[:80])
        
        return {"raw_commands": clean}
        
    except Exception as e:
        logger.error("[Cmd Generator] Command generation failed: %s", e, exc_info=True)
        raise

def safety_auditor_node(state: dict) -> dict:
    logger.info("[Safety Auditor] Reviewing commands for safety")
    
    try:
        analysis = state.get("ttp_analysis", "")
        commands = state.get("raw_commands", "")
        logger.debug("[Safety Auditor] Input analysis len=%d, commands len=%d", len(analysis), len(commands))
        
        # Pre-audit check for catastrophic operations
        catastrophic_keywords = ["rm -rf /", "rm -rf*", "shutdown -h", "poweroff", "DROP DATABASE", "TRUNCATE"]
        dangerous = [kw for kw in catastrophic_keywords if kw.lower() in commands.lower()]
        if dangerous:
            logger.warning("[Safety Auditor] Detected catastrophic keywords: %s", dangerous)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Senior Linux Security Auditor. Review proposed IR commands. "
                       "Ensure they do not contain catastrophic operations (rm -rf /, "
                       "database wipes, full shutdowns). Ensure kill signals target only "
                       "the malicious PID. Output ONLY the final safe Bash commands — "
                       "no markdown, no explanations."),
            ("human",  "Threat Context:\n{analysis}\n\nProposed Commands:\n{cmds}\n\nVerified Safe Commands:"),
        ])
        
        start = time.time()
        chain = prompt | _llm()
        result = chain.invoke({"analysis": analysis, "cmds": commands})
        elapsed = time.time() - start
        
        raw_response = result.content
        logger.debug("[Safety Auditor] LLM response in %.2fs (len=%d)", elapsed, len(raw_response))
        
        # Clean markdown
        clean = raw_response.replace("```bash", "").replace("```", "").strip()
        logger.debug("[Safety Auditor] After cleanup: len=%d", len(clean))
        
        if clean != commands:
            logger.info("[Safety Auditor] Commands modified during audit")
        else:
            logger.info("[Safety Auditor] Commands approved (time=%.2fs)", elapsed)
        
        if not clean:
            logger.warning("[Safety Auditor] All commands blocked by safety auditor")
        else:
            cmd_lines = [c.strip() for c in clean.split("\n") if c.strip() and not c.strip().startswith("#")]
            logger.debug("[Safety Auditor] Final approved command count: %d", len(cmd_lines))
        
        return {"verified_commands": clean}
        
    except Exception as e:
        logger.error("[Safety Auditor] Audit failed: %s", e, exc_info=True)
        raise
