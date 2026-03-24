# pipelines/ir_pipeline.py  —  Incident Response pipeline
# Strategist → Command Generator → Safety Auditor

from langgraph.graph import StateGraph, END
from agents.state import LogRESPState
from agents.context_retriever import context_retriever_node
from agents.ttp_analyzer import ttp_analyzer_node
from agents.ir_agents import ir_strategist_node, command_generator_node, safety_auditor_node

wf = StateGraph(LogRESPState)
wf.add_node("retriever",  context_retriever_node)
wf.add_node("analyzer",   ttp_analyzer_node)
wf.add_node("strategist", ir_strategist_node)
wf.add_node("cmd_gen",    command_generator_node)
wf.add_node("auditor",    safety_auditor_node)

wf.set_entry_point("retriever")
wf.add_edge("retriever",  "analyzer")
wf.add_edge("analyzer",   "strategist")
wf.add_edge("strategist", "cmd_gen")
wf.add_edge("cmd_gen",    "auditor")
wf.add_edge("auditor",    END)

ir_app = wf.compile()

def run_ir(process_id: str, anomaly_score: float) -> dict:
    state = {k: "" for k in LogRESPState.__annotations__}
    state.update({"process_id": str(process_id), "anomaly_score": anomaly_score})
    return ir_app.invoke(state)
