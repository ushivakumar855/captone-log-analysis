# pipelines/ir_pipeline.py  —  Incident Response pipeline
# Strategist → Command Generator → Safety Auditor

import time
from langgraph.graph import StateGraph, END
from agents.state import LogRESPState
from agents.context_retriever import context_retriever_node
from agents.ttp_analyzer import ttp_analyzer_node
from agents.ir_agents import ir_strategist_node, command_generator_node, safety_auditor_node
from utils.logger import get_logger

logger = get_logger(__name__)

logger.debug("[IR Pipeline] Building incident response pipeline")
wf = StateGraph(LogRESPState)
wf.add_node("retriever",  context_retriever_node)
wf.add_node("analyzer",   ttp_analyzer_node)
wf.add_node("strategist", ir_strategist_node)
wf.add_node("cmd_gen",    command_generator_node)
wf.add_node("auditor",    safety_auditor_node)

logger.debug("[IR Pipeline] Connecting nodes: retriever->analyzer->strategist->cmd_gen->auditor->END")
wf.set_entry_point("retriever")
wf.add_edge("retriever",  "analyzer")
wf.add_edge("analyzer",   "strategist")
wf.add_edge("strategist", "cmd_gen")
wf.add_edge("cmd_gen",    "auditor")
wf.add_edge("auditor",    END)

logger.debug("[IR Pipeline] Compiling state graph")
ir_app = wf.compile()
logger.info("[IR Pipeline] Incident response pipeline ready")

def run_ir(process_id: str, anomaly_score: float, raw_log: dict) -> dict:
    logger.info("[IR Pipeline] run_ir() invoked with PID=%s, score=%.3f", process_id, anomaly_score)
    
    try:
        # Initialize state with all fields
        logger.debug("[IR Pipeline] Initializing state with LogRESPState defaults")
        state = {k: "" for k in LogRESPState.__annotations__}
        state.update({
            "process_id": str(process_id),
            "anomaly_score": anomaly_score,
            "raw_log": raw_log
        })
        logger.debug("[IR Pipeline] State initialized: %d fields set", len(state))
        
        # Invoke pipeline
        logger.info("[IR Pipeline] Invoking pipeline (retriever->analyzer->strategist->cmd_gen->auditor)")
        start = time.time()
        result = ir_app.invoke(state)
        elapsed = time.time() - start
        logger.info("[IR Pipeline] Pipeline complete in %.2fs", elapsed)
        
        # Log result summary
        logger.debug("[IR Pipeline] Result fields:",)
        for key in ["neo4j_context", "final_analysis", "ir_strategy", "raw_commands", "verified_commands"]:
            val = result.get(key, "")
            logger.debug("  - %s: %d chars", key, len(val) if isinstance(val, str) else 0)
        
        return result
        
    except Exception as e:
        logger.error("[IR Pipeline] run_ir() failed: %s", e, exc_info=True)
        raise
