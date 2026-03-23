import torch
from neo4j import GraphDatabase
from torch_geometric.data import Data
import hashlib

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "capstone123")

def hash_feature(text_feature, dim=16):
    """Converts a text string (like cmdLine) into a numerical vector."""
    if not text_feature: text_feature = "unknown"
    h = int(hashlib.sha256(text_feature.encode('utf-8')).hexdigest(), 16)
    # Simple deterministic pseudo-random vector based on the hash
    torch.manual_seed(h % 100000)
    return torch.rand(dim)

def extract_graph_to_pyg():
    print("[*] Connecting to Neo4j to extract the Benign Graph...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    node_mapping = {} # Maps Neo4j string IDs to PyG integer indices
    node_features = []
    edges_src = []
    edges_dst = []

    with driver.session() as session:
        # 1. Extract all Process Nodes (For this baseline, we just use Processes)
        print("    -> Extracting Nodes...")
        nodes_result = session.run("MATCH (n:Process) RETURN n.id AS id, n.cmdLine AS cmd")
        for i, record in enumerate(nodes_result):
            node_mapping[record["id"]] = i
            node_features.append(hash_feature(record["cmd"]))
            
        # 2. Extract SPAWNED Edges
        print("    -> Extracting Edges...")
        edges_result = session.run("""
            MATCH (a:Process)-[:SPAWNED]->(b:Process) 
            RETURN a.id AS src, b.id AS dst
        """)
        for record in edges_result:
            if record["src"] in node_mapping and record["dst"] in node_mapping:
                edges_src.append(node_mapping[record["src"]])
                edges_dst.append(node_mapping[record["dst"]])

    driver.close()

    # 3. Build the PyTorch Geometric Data Object
    x = torch.stack(node_features)
    edge_index = torch.tensor([edges_src, edges_dst], dtype=torch.long)
    
    data = Data(x=x, edge_index=edge_index)
    torch.save(data, 'benign_graph.pt')
    print(f"[+] Successfully saved benign_graph.pt! Nodes: {data.num_nodes}, Edges: {data.num_edges}")

if __name__ == "__main__":
    extract_graph_to_pyg()