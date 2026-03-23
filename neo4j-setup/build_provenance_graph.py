# import json
# import os
# import time
# from neo4j import GraphDatabase

# # --- 1. Configuration ---
# # Make sure Neo4j Desktop is running!
# URI = "neo4j://localhost:7687"
# AUTH = ("neo4j", "capstone123") # Update this if you chose a different password

# # Pointing directly to your Windows folders
# TARGET_FILES = [
#     r"C:\Users\Student\Downloads\FINAL_DATASETS\Trace_final_dataset\trace_testing.json",
#     r"C:\Users\Student\Downloads\FINAL_DATASETS\Theia_final_dataset\theia_testing.json",
#     r"C:\Users\Student\Downloads\LogMEND_BETH_Splits\beth_testing.json",
# ]

# BATCH_SIZE = 5000  # Pushing logs in batches is much faster

# # --- 2. Cypher Queries ---
# INGEST_QUERY = """
# UNWIND $batch AS log

# // 1. Always create/merge the primary Process node
# MERGE (p:Process {id: coalesce(log.process_id, log.thread_id, 'UNKNOWN')})
# ON CREATE SET p.cmdLine = log.cmdLine, 
#               p.user_id = log.user_id, 
#               p.is_evil = log.is_evil

# // 2. If it's a process spawning another process (Fork/Clone/Exec)
# FOREACH (_ IN CASE WHEN log.parent_process_id IS NOT NULL THEN [1] ELSE [] END |
#     MERGE (parent:Process {id: log.parent_process_id})
#     MERGE (parent)-[:SPAWNED {timestamp: coalesce(log.timestamp_ns, log.timestamp, 0), type: coalesce(log.event_type, 'UNKNOWN')}]->(p)
# )

# // 3. If the process touches a file (Open/Write/Modify)
# FOREACH (_ IN CASE WHEN log.file_path IS NOT NULL AND log.event_type IN ['EVENT_OPEN', 'EVENT_WRITE', 'EVENT_MODIFY_FILE_ATTRIBUTES', 'openat', 'security_file_open'] THEN [1] ELSE [] END |
#     MERGE (f:File {path: log.file_path})
#     MERGE (p)-[:ACCESSED {timestamp: coalesce(log.timestamp_ns, log.timestamp, 0), type: coalesce(log.event_type, 'UNKNOWN')}]->(f)
# )

# // 4. If the process connects to a network (Connect/Accept/Socket)
# FOREACH (_ IN CASE WHEN log.remote_ip IS NOT NULL OR log.event_type IN ['EVENT_CONNECT', 'EVENT_ACCEPT', 'socket', 'connect'] THEN [1] ELSE [] END |
#     MERGE (n:Network {ip: coalesce(log.remote_ip, 'LOCAL_SOCKET'), port: coalesce(log.remote_port, 'ANY')})
#     MERGE (p)-[:CONNECTED_TO {timestamp: coalesce(log.timestamp_ns, log.timestamp, 0), type: coalesce(log.event_type, 'UNKNOWN')}]->(n)
# )
# """

# # --- 3. The Ingestor Class ---
# class ProvenanceGraphBuilder:
#     def __init__(self, uri, auth):
#         self.driver = GraphDatabase.driver(uri, auth=auth)
#         self.setup_database()

#     def close(self):
#         self.driver.close()

#     def setup_database(self):
#         """Creates indexes to make ingestion and LLM querying lightning fast."""
#         print("[*] Setting up Graph Indexes...")
#         with self.driver.session() as session:
#             session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Process) REQUIRE p.id IS UNIQUE")
#             session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE")

#     def ingest_batch(self, batch):
#         with self.driver.session() as session:
#             session.execute_write(lambda tx: tx.run(INGEST_QUERY, batch=batch))

#     def process_file(self, filepath):
#         if not os.path.exists(filepath):
#             print(f"[-] File not found: {filepath}")
#             return

#         print(f"\n[*] Ingesting {os.path.basename(filepath)} into Neo4j...")
#         start_time = time.time()
#         batch = []
#         total_ingested = 0

#         with open(filepath, 'r', encoding='utf-8') as f:
#             for line in f:
#                 try:
#                     log = json.loads(line.strip())
#                     batch.append(log)

#                     if len(batch) >= BATCH_SIZE:
#                         self.ingest_batch(batch)
#                         total_ingested += len(batch)
#                         batch = []
#                         print(f"    -> {total_ingested} logs pushed to graph...")
#                 except json.JSONDecodeError:
#                     continue

#             # Push any remaining logs
#             if batch:
#                 self.ingest_batch(batch)
#                 total_ingested += len(batch)

#         duration = round(time.time() - start_time, 2)
#         print(f"[+] Finished! Ingested {total_ingested} logs into the graph in {duration}s.")

# # --- 4. Main Execution ---
# if __name__ == "__main__":
#     print("=== LogMEND Neo4j Provenance Graph Builder ===")
#     graph_builder = ProvenanceGraphBuilder(URI, AUTH)
    
#     for file in TARGET_FILES:
#         graph_builder.process_file(file)
        
#     graph_builder.close()
#     print("\n=== GRAPH CONSTRUCTION COMPLETE ===")
#     print("Open Neo4j Desktop to view your unified attack graph!")


import json
import ast
from neo4j import GraphDatabase

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "capstone123")
DATASET_PATH = r"C:\Users\Student\Downloads\FINAL_DATASETS\BETH_final_dataset\beth_training.json"

def load_robust_json(filepath):
    """Reads both standard JSON arrays and multi-line JSON formats."""
    print(f"[*] Loading data from {filepath}...")
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        file_content = f.read()

    logs = []
    try:
        logs = json.loads(file_content)
    except json.JSONDecodeError:
        print("    -> Standard array failed. Attempting consecutive multi-line JSON parsing...")
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
    return logs

def build_graph():
    print("[*] Connecting to Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session() as session:
        print("[*] Wiping old database...")
        session.run("MATCH (n) DETACH DELETE n")
        
        print("[*] Setting up schema constraints...")
        try:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Process) REQUIRE p.id IS UNIQUE")
        except Exception:
            pass

        logs = load_robust_json(DATASET_PATH)
        if not logs:
            print("[!] No logs loaded. Exiting.")
            return

        print(f"[*] Inserting {len(logs)} logs into Neo4j (This may take a minute)...")
        
        # The Bulletproof Cypher Query
        query = """
        UNWIND $batch AS log
        
        // 1. Safely extract IDs, falling back to 'UNKNOWN' to prevent null errors
        WITH log, 
             coalesce(toString(log.processId), toString(log.process_id), toString(log.threadId), 'UNKNOWN') AS safe_pid,
             coalesce(toString(log.parentProcessId), toString(log.parent_process_id)) AS safe_ppid
        
        // 2. Merge the child node
        MERGE (child:Process {id: safe_pid})
        SET child.cmdLine = coalesce(log.args, log.processName, log.cmdLine, 'unknown')
        
        // 3. Merge the parent and link them ONLY if parent ID actually exists
        WITH child, safe_ppid
        WHERE safe_ppid IS NOT NULL AND safe_ppid <> 'null' AND safe_ppid <> 'None'
        MERGE (parent:Process {id: safe_ppid})
        MERGE (parent)-[:SPAWNED]->(child)
        """
        
        batch_size = 5000 # Increased batch size to match your old fast script
        for i in range(0, len(logs), batch_size):
            batch = logs[i:i+batch_size]
            session.run(query, batch=batch)
            print(f"    -> Processed {min(i+batch_size, len(logs))} / {len(logs)} logs")

    driver.close()
    print("[+] Database successfully rebuilt with full Provenance Graphs!")

if __name__ == "__main__":
    build_graph()