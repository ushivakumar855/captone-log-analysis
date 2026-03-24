# agents/state.py  —  single shared state definition
# Was duplicated in logresp_agent.py AND ir_copilot.py — now defined once.

from typing import TypedDict, Optional

class LogRESPState(TypedDict):
    raw_log:           dict
    process_id:        str
    anomaly_score:     float
    neo4j_context:     str
    ttp_analysis:      str
    ir_strategy:       str
    raw_commands:      str
    verified_commands: str
    final_analysis:    str
