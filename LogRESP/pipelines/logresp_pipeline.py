# pipelines/logresp_pipeline.py  —  Detection pipeline
# Combines context retrieval + TTP analysis into a compiled LangGraph app.

from langgraph.graph import StateGraph, END
from agents.state import LogRESPState
from agents.context_retriever import context_retriever_node
from agents.ttp_analyzer import ttp_analyzer_node

def build_logresp_pipeline(model_name: str | None = None):
    """
    Factory function — call with a model_name for benchmarking,
    or without for the default model.
    """
    def _ttp_node(state):
        return ttp_analyzer_node(state, model_name=model_name)

    wf = StateGraph(LogRESPState)
    wf.add_node("retriever", context_retriever_node)
    wf.add_node("analyzer",  _ttp_node)
    wf.set_entry_point("retriever")
    wf.add_edge("retriever", "analyzer")
    wf.add_edge("analyzer", END)
    return wf.compile()

logresp_app = build_logresp_pipeline()
