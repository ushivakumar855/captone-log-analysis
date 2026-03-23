import json
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from neo4j import GraphDatabase

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "capstone123")
MODEL_NAME = "qwen2.5-coder:7b" 

# --- 1. Define the Multi-Agent State ---
class AgentState(TypedDict):
    process_id: str
    anomaly_score: float
    neo4j_context: str
    ttp_analysis: str
    ir_strategy: str
    raw_commands: str       # Agent 4's initial draft
    verified_commands: str  # Agent 5's safe output

# --- 2. Define the 5 Agents ---

def agent1_context_retriever(state: AgentState):
    query = """
    MATCH (p:Process {id: $pid})
    OPTIONAL MATCH (parent:Process)-[:SPAWNED]->(p)
    OPTIONAL MATCH (grandparent:Process)-[:SPAWNED]->(parent)
    RETURN 
        grandparent.cmdLine AS Grandparent,
        parent.cmdLine AS Parent,
        p.cmdLine AS TargetCmd
    """
    context_str = "No extended context found."
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session() as session:
            result = session.run(query, pid=state['process_id']).single()
            if result:
                g_parent = result.get("Grandparent") or "None"
                parent = result.get("Parent") or "Unknown"
                target = result.get("TargetCmd") or "Unknown"
                context_str = f"Grandparent: {g_parent}\n  └── Parent: {parent}\n        └── Target: {target}"
        driver.close()
    except Exception:
        pass 
    return {"neo4j_context": context_str}

def agent2_ttp_analyst(state: AgentState):
    llm = ChatOllama(model=MODEL_NAME, base_url="http://127.0.0.1:11434", temperature=0.0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a concise SOC Analyst. Provide EXACTLY 2 sentences. Sentence 1: Root Cause. Sentence 2: MITRE ATT&CK Tactic and Technique. Do not add any conversational filler."),
        ("human", "Process ID: {pid}\nExecution Chain:\n{context}\n\nAnalysis:")
    ])
    response = (prompt | llm).invoke({"pid": state['process_id'], "context": state['neo4j_context']})
    return {"ttp_analysis": response.content}

def agent3_ir_strategist(state: AgentState):
    llm = ChatOllama(model=MODEL_NAME, base_url="http://127.0.0.1:11434", temperature=0.0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an IR Lead. Provide EXACTLY 3 short bullet points (maximum 10 words each) for immediate containment. No explanations."),
        ("human", "Analysis:\n{analysis}\n\nDraft 3-step strategy:")
    ])
    response = (prompt | llm).invoke({"analysis": state['ttp_analysis']})
    return {"ir_strategy": response.content}

def agent4_command_generator(state: AgentState):
    """Generates the initial draft of the Bash commands."""
    llm = ChatOllama(model=MODEL_NAME, base_url="http://127.0.0.1:11434", temperature=0.0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Linux Systems Engineer. Output ONLY raw, exact Bash commands. Maximum 3 commands. Do not write any explanations or comments."),
        ("human", "Target PID: {pid}\nStrategy:\n{strategy}\n\nDraft Bash Commands:")
    ])
    response = (prompt | llm).invoke({"pid": state['process_id'], "strategy": state['ir_strategy']})
    clean_cmds = response.content.replace("```bash", "").replace("```", "").strip()
    return {"raw_commands": clean_cmds}

def agent5_safety_auditor(state: AgentState):
    """AGENT 5: The Critic. Reviews the commands for safety before final output."""
    llm = ChatOllama(model=MODEL_NAME, base_url="http://127.0.0.1:11434", temperature=0.0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a strict Senior Linux Security Auditor. Your job is to review proposed incident response commands. "
                   "1. Ensure they do not contain catastrophic commands (e.g., rm -rf /, wiping critical databases, or shutting down the entire server). "
                   "2. Ensure they use safe kill signals (e.g., kill -STOP or kill -9) targeting ONLY the malicious PID. "
                   "If the commands are safe, output them exactly as provided. If they are dangerous, modify them to be safe. "
                   "Output ONLY the final raw Bash commands. No explanations, no markdown."),
        ("human", "Threat Context:\n{analysis}\n\nProposed Commands by Junior Engineer:\n{raw_commands}\n\nVerified Safe Bash Commands:")
    ])
    response = (prompt | llm).invoke({
        "analysis": state['ttp_analysis'],
        "raw_commands": state['raw_commands']
    })
    clean_cmds = response.content.replace("```bash", "").replace("```", "").strip()
    return {"verified_commands": clean_cmds}

# --- 3. Compile the 5-Agent LangGraph ---
workflow = StateGraph(AgentState)

workflow.add_node("agent1_retriever", agent1_context_retriever)
workflow.add_node("agent2_analyst", agent2_ttp_analyst)
workflow.add_node("agent3_strategist", agent3_ir_strategist)
workflow.add_node("agent4_executioner", agent4_command_generator)
workflow.add_node("agent5_auditor", agent5_safety_auditor) # Add the Auditor

workflow.set_entry_point("agent1_retriever")
workflow.add_edge("agent1_retriever", "agent2_analyst")
workflow.add_edge("agent2_analyst", "agent3_strategist")
workflow.add_edge("agent3_strategist", "agent4_executioner")
workflow.add_edge("agent4_executioner", "agent5_auditor")  # Draft goes to Auditor
workflow.add_edge("agent5_auditor", END)                   # Auditor has the final say

copilot_app = workflow.compile()

# --- 4. The Callable API ---
def trigger_copilot(process_id, anomaly_score):
    initial_state = {
        "process_id": str(process_id),
        "anomaly_score": anomaly_score,
        "neo4j_context": "", 
        "ttp_analysis": "", 
        "ir_strategy": "", 
        "raw_commands": "",
        "verified_commands": ""
    }
    result = copilot_app.invoke(initial_state)
    
    final_report = (
        f"--- 1. GRAPH CONTEXT ---\n{result['neo4j_context']}\n\n"
        f"--- 2. THREAT ANALYSIS ---\n{result['ttp_analysis'].strip()}\n\n"
        f"--- 3. STRATEGY ---\n{result['ir_strategy'].strip()}\n\n"
        f"--- 4. VERIFIED COMMANDS (Audited) ---\n{result['verified_commands'].strip()}"
    )
    return final_report