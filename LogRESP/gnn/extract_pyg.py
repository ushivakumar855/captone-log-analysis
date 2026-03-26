# gnn/extract_pyg.py
# Pulls Process nodes + SPAWNED edges from Neo4j and saves a PyG Data object.
# Run this once before training: python -m gnn.extract_pyg

import sys
import hashlib
import torch
from pathlib import Path
from torch_geometric.data import Data

# Add parent directory to sys.path so relative imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.neo4j_pool import neo4j_session, close_driver
from config import BENIGN_GRAPH_PT, GNN_INPUT_DIM
from utils.logger import get_logger

logger = get_logger(__name__)


def _hash_feature(text: str | None, dim: int = GNN_INPUT_DIM) -> torch.Tensor:
    text = text or "unknown"
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % 100_000
    torch.manual_seed(seed)
    return torch.rand(dim)


def extract_graph() -> Data:
    node_map:  dict[str, int] = {}
    features:  list[torch.Tensor] = []
    src_list:  list[int] = []
    dst_list:  list[int] = []

    logger.info("[extract_pyg] Querying Neo4j for Process nodes...")
    with neo4j_session() as session:
        for i, rec in enumerate(session.run(
            "MATCH (n:Process) RETURN n.id AS id, n.cmdLine AS cmd"
        )):
            node_map[rec["id"]] = i
            features.append(_hash_feature(rec["cmd"]))

        logger.info("[extract_pyg] %d nodes loaded. Querying edges...", len(node_map))
        for rec in session.run(
            "MATCH (a:Process)-[:SPAWNED]->(b:Process) RETURN a.id AS src, b.id AS dst"
        ):
            s, d = rec["src"], rec["dst"]
            if s in node_map and d in node_map:
                src_list.append(node_map[s])
                dst_list.append(node_map[d])

    close_driver()

    x          = torch.stack(features)
    edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
    data       = Data(x=x, edge_index=edge_index)

    torch.save(data, BENIGN_GRAPH_PT)
    logger.info("[extract_pyg] Saved %s  nodes=%d  edges=%d",
                BENIGN_GRAPH_PT, data.num_nodes, data.num_edges)
    return data


if __name__ == "__main__":
    extract_graph()
