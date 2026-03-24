# pipelines/logresp_pipeline.py  —  Detection pipeline
# Combines context retrieval + TTP analysis into a compiled LangGraph app.

import time
from langgraph.graph import StateGraph, END
from agents.state import LogRESPState
from agents.context_retriever import context_retriever_node
from agents.ttp_analyzer import ttp_analyzer_node
from utils.logger import get_logger

logger = get_logger(__name__)

def build_logresp_pipeline(model_name: str | None = None):
    """
    Factory function — call with a model_name for benchmarking,
    or without for the default model.
    """
    logger.info("[LogRESP Pipeline] Building detection pipeline (model=%s)", model_name or "default")
    start = time.time()
    
    try:
        def _ttp_node(state):
            return ttp_analyzer_node(state, model_name=model_name)
        
        logger.debug("[LogRESP Pipeline] Creating state graph")
        wf = StateGraph(LogRESPState)
        
        logger.debug("[LogRESP Pipeline] Adding nodes: retriever, analyzer")
        wf.add_node("retriever", context_retriever_node)
        wf.add_node("analyzer",  _ttp_node)
        
        logger.debug("[LogRESP Pipeline] Setting entry point: retriever")
        wf.set_entry_point("retriever")
        
        logger.debug("[LogRESP Pipeline] Adding edges: retriever->analyzer->END")
        wf.add_edge("retriever", "analyzer")
        wf.add_edge("analyzer", END)
        
        logger.debug("[LogRESP Pipeline] Compiling state graph")
        compiled = wf.compile()
        
        elapsed = time.time() - start
        logger.info("[LogRESP Pipeline] Pipeline built successfully (%.3fs)", elapsed)
        return compiled
        
    except Exception as e:
        logger.error("[LogRESP Pipeline] Pipeline build failed: %s", e, exc_info=True)
        raise

logger.info("[LogRESP Pipeline] Instantiating default detection pipeline")
logresp_app = build_logresp_pipeline()
logger.debug("[LogRESP Pipeline] Default pipeline ready")
