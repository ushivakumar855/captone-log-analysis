import json
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from neo4j import GraphDatabase

# --- 1. Configuration ---
MODEL_NAME = "qwen2.5:32b" 
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "capstone123")

# --- 2. Define the Graph State ---
class AgentState(TypedDict):
    raw_log: dict
    process_id: str
    neo4j_context: str
    final_analysis: str

# --- 3. Define the Agent Nodes ---

def context_retriever_node(state: AgentState):
    """Agent 2: Multi-Hop Graph RAG. Reaches deep into Neo4j for full attack provenance."""
    print(f"[*] Agent 2 (Retriever): Fetching Deep Multi-Hop context for Process {state['process_id']}...")
    
    # UPGRADED CYPHER QUERY: Grandparent -> Parent -> Target + Files + Network
    query = """
    MATCH (p:Process {id: $pid})
    OPTIONAL MATCH (parent:Process)-[:SPAWNED]->(p)
    OPTIONAL MATCH (grandparent:Process)-[:SPAWNED]->(parent)
    OPTIONAL MATCH (p)-[:ACCESSED]->(f:File)
    OPTIONAL MATCH (p)-[:CONNECTED_TO]->(n:Network)
    RETURN 
        grandparent.cmdLine AS Grandparent,
        parent.cmdLine AS Parent,
        p.cmdLine AS TargetCmd,
        collect(DISTINCT f.path) AS TouchedFiles,
        collect(DISTINCT n.ip) AS NetworkConnections
    """
    
    context_str = "No extended graph context found."
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session() as session:
            result = session.run(query, pid=state['process_id']).single()
            if result:
                g_parent = result.get("Grandparent") or "Unknown"
                parent = result.get("Parent") or "Unknown"
                target_cmd = result.get("TargetCmd") or "Unknown"
                files = result.get("TouchedFiles", [])
                networks = result.get("NetworkConnections", [])
                
                # Build a rich, multi-dimensional prompt for the LLM
                context_str = (
                    f"--- EXECUTION CHAIN ---\n"
                    f"Grandparent Process: {g_parent}\n"
                    f"  └── Spawned Parent: {parent}\n"
                    f"        └── Spawned Target: {target_cmd}\n\n"
                    f"--- ARTIFACTS TOUCHED ---\n"
                    f"Files: {', '.join(files[:5]) if files else 'None'}\n"
                    f"Network IPs: {', '.join(networks[:3]) if networks else 'None'}"
                )
        driver.close()
    except Exception as e:
        print(f"[-] Neo4j retrieval failed: {e}")

    return {"neo4j_context": context_str}


def ttp_analyzer_node(state: AgentState):
    """Agent 4: Uses local Ollama to analyze the multi-hop context and map to MITRE ATT&CK."""
    # print(f"[*] Agent 4 (Analyzer): Asking local Ollama ({MODEL_NAME}) for analysis...")
    
    # Explicitly set base_url to bypass Windows IPv6 localhost bug
    llm = ChatOllama(
        model=MODEL_NAME, 
        base_url="http://127.0.0.1:11434", 
        temperature=0.1
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert Linux cybersecurity analyst. You map system logs to the MITRE ATT&CK framework. "
                   "Pay close attention to the execution chain. If a benign tool (like 'curl' or 'tar') is spawned by a "
                   "suspicious parent or connects to an external IP, it is likely Malicious."),
        ("human", """
        Analyze this Linux system event and its deep graph context. 
        
        Raw Log Event:
        {log}
        
        Extended Graph Context (Provenance):
        {context}
        
        Task:
        1. Identify if this is Benign or Malicious.
        2. If malicious, provide the likely MITRE ATT&CK Tactic and Technique.
        3. Give a 2-sentence explanation of what the attacker is doing.
        """)
    ])
    
    chain = prompt | llm
    
    response = chain.invoke({
        "log": json.dumps(state['raw_log'], indent=2),
        "context": state['neo4j_context']
    })
    
    return {"final_analysis": response.content}


# --- 4. Build and Compile the LangGraph ---
workflow = StateGraph(AgentState)
workflow.add_node("context_retriever", context_retriever_node)
workflow.add_node("ttp_analyzer", ttp_analyzer_node)

workflow.set_entry_point("context_retriever")
workflow.add_edge("context_retriever", "ttp_analyzer")
workflow.add_edge("ttp_analyzer", END)

logresp_app = workflow.compile()