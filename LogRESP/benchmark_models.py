import json
import random
import time
import os
import ast
import csv  # Added for CSV export
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from neo4j import GraphDatabase

# --- 1. Configuration & Models ---
DATASET_PATH = r"C:\Users\Student\Downloads\FINAL_DATASETS\BETH_final_dataset\beth_testing.json"
SAMPLE_SIZE_PER_CLASS = 20 
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "capstone123")

MODELS_TO_TEST = [
    "phi4-mini",
    "qwen2.5-coder:7b",
    "llama3.1:8b",
    "deepseek-r1:14b",
    "codestral",
    "qwen3:32b"
]

# --- 2. Define the Graph State ---
class AgentState(TypedDict):
    raw_log: dict
    process_id: str
    neo4j_context: str
    model_name: str
    final_analysis: str

# --- 3. Define the Agent Nodes ---
def context_retriever_node(state: AgentState):
    """Agent 2: Multi-Hop Graph RAG. Reaches deep into Neo4j for full attack provenance."""
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
        pass 

    return {"neo4j_context": context_str}

def ttp_analyzer_node(state: AgentState):
    """Agent 4: Uses local Ollama to analyze the multi-hop context."""
    current_model = state.get("model_name", "llama3.1:8b") 
    
    llm = ChatOllama(
        model=current_model, 
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

# --- 5. Data Loading & Evaluation Logic ---
def load_balanced_dataset(filepath, sample_size):
    benign_logs, malicious_logs = [], []
    print(f"[*] Reading dataset from {filepath}...")
    
    if not os.path.exists(filepath):
        print(f"[!] ERROR: Cannot find file at {filepath}")
        return []
        
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        file_content = f.read()

    logs = []
    try:
        logs = json.loads(file_content)
    except json.JSONDecodeError:
        try:
            decoder = json.JSONDecoder()
            pos = 0
            file_content = file_content.lstrip()
            while pos < len(file_content):
                obj, index = decoder.raw_decode(file_content, pos)
                logs.append(obj)
                pos = index
                while pos < len(file_content) and file_content[pos].isspace():
                    pos += 1
        except Exception:
            try:
                logs = ast.literal_eval(file_content)
            except Exception as e:
                print(f"[!] Critical Error parsing file format: {e}")
                return []

    for log in logs:
        if isinstance(log, dict):
            if int(log.get("is_evil", 0)) == 1:
                malicious_logs.append(log)
            else:
                benign_logs.append(log)

    print(f"    -> Successfully loaded {len(benign_logs)} Benign and {len(malicious_logs)} Malicious logs.")
    
    if len(benign_logs) == 0 and len(malicious_logs) == 0:
        return []
    
    sampled_benign = random.sample(benign_logs, min(sample_size, len(benign_logs)))
    sampled_malicious = random.sample(malicious_logs, min(sample_size, len(malicious_logs)))
    combined_test_set = sampled_benign + sampled_malicious
    random.shuffle(combined_test_set) 
    return combined_test_set

def run_benchmark():
    test_logs = load_balanced_dataset(DATASET_PATH, SAMPLE_SIZE_PER_CLASS)
    if not test_logs:
        return

    results_matrix = {}

    for model in MODELS_TO_TEST:
        print("\n" + "="*70)
        print(f"🚀 INITIATING EVALUATION FOR MODEL: {model.upper()}")
        print("="*70)
        
        TP, TN, FP, FN = 0, 0, 0, 0
        start_time = time.time()

        for i, log in enumerate(test_logs, 1):
            actual_is_evil = log.get("is_evil", 0)
            actual_label = "Malicious" if actual_is_evil == 1 else "Benign"
            
            initial_state = {
                "raw_log": log,
                "process_id": str(log.get("process_id", "UNKNOWN")),
                "neo4j_context": "",
                "model_name": model, 
                "final_analysis": ""
            }
            
            print(f"\n[Test {i}/{len(test_logs)}] Model: {model} | Analyzing Process {initial_state['process_id']} (Ground Truth: {actual_label})")
            
            try:
                result = logresp_app.invoke(initial_state)
                ai_analysis = result["final_analysis"].lower()
                
                ai_predicted_malicious = "malicious" in ai_analysis and "benign" not in ai_analysis
                
                if actual_is_evil == 1:
                    if ai_predicted_malicious:
                        TP += 1
                        print("    -> ✅ TRUE POSITIVE (AI Caught the Attack!)")
                    else:
                        FN += 1
                        print("    -> ❌ FALSE NEGATIVE (AI Missed the Attack!)")
                else:
                    if ai_predicted_malicious:
                        FP += 1
                        print("    -> ❌ FALSE POSITIVE (AI Hallucinated an Attack!)")
                    else:
                        TN += 1
                        print("    -> ✅ TRUE NEGATIVE (AI Correctly Ignored Normalcy)")
                        
            except Exception as e:
                print(f"    -> ⚠️ ERROR analyzing log with {model}: {e}")

        # --- CALCULATE METRICS FOR THE CURRENT MODEL ---
        duration = round(time.time() - start_time, 2)
        precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
        recall = TP / (TP + FN) if (TP + FN) > 0 else 0.0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        accuracy = (TP + TN) / len(test_logs) if len(test_logs) > 0 else 0.0

        print("\n" + "="*50)
        print(f"🏆 FINAL RESEARCH METRICS: {model.upper()} 🏆")
        print("="*50)
        print(f"Total Logs Tested: {len(test_logs)}")
        print(f"Time Taken:        {duration} seconds")
        print("-" * 30)
        print(f"True Positives (TP):  {TP}")
        print(f"True Negatives (TN):  {TN}")
        print(f"False Positives (FP): {FP}")
        print(f"False Negatives (FN): {FN}")
        print("-" * 30)
        print(f"🎯 ACCURACY:  {accuracy * 100:.2f}%")
        print(f"🎯 PRECISION: {precision * 100:.2f}%")
        print(f"🎯 RECALL:    {recall * 100:.2f}%")
        print(f"🎯 F1-SCORE:  {f1_score * 100:.2f}%")
        print("="*50)

        # Store results for the final matrix
        results_matrix[model] = {
            "Accuracy": accuracy * 100,
            "Precision": precision * 100,
            "Recall": recall * 100,
            "F1-Score": f1_score * 100,
            "Time (s)": duration
        }

    # --- FINAL COMPARISON TABLE ---
    print("\n\n" + "="*85)
    print("🏆 FINAL MULTI-MODEL BENCHMARK RESULTS MATRIX 🏆")
    print("="*85)
    print(f"{'Model Name':<20} | {'Accuracy':<10} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Time (s)'}")
    print("-" * 85)
    for model, metrics in results_matrix.items():
        print(f"{model:<20} | {metrics['Accuracy']:<9.2f}% | {metrics['Precision']:<9.2f}% | {metrics['Recall']:<9.2f}% | {metrics['F1-Score']:<9.2f}% | {metrics['Time (s)']}")
    print("="*85)

    # --- 6. EXPORT TO CSV ---
    csv_filename = "benchmark_results.csv"
    try:
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            # Write headers
            writer.writerow(["Model Name", "Accuracy (%)", "Precision (%)", "Recall (%)", "F1-Score (%)", "Time (s)"])
            # Write data rows
            for model, metrics in results_matrix.items():
                writer.writerow([
                    model, 
                    f"{metrics['Accuracy']:.2f}", 
                    f"{metrics['Precision']:.2f}", 
                    f"{metrics['Recall']:.2f}", 
                    f"{metrics['F1-Score']:.2f}", 
                    metrics['Time (s)']
                ])
        print(f"\n💾 Results successfully saved to: {os.path.abspath(csv_filename)}")
    except Exception as e:
        print(f"\n[!] Failed to save CSV: {e}")

if __name__ == "__main__":
    run_benchmark()