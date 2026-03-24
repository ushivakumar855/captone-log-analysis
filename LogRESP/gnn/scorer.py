# gnn/scorer.py  —  Honest GNN anomaly scoring
# The +0.90 heuristic hack has been removed entirely.
# The model output is the score. Period.

import hashlib
import torch
import torch.nn.functional as F
from torch_geometric.nn import GCNConv
from config import GNN_MODEL_PATH, GNN_INPUT_DIM, GNN_HIDDEN_DIM, ANOMALY_THRESHOLD
from utils.logger import get_logger

logger = get_logger(__name__)

class GraphAutoencoder(torch.nn.Module):
    def __init__(self, in_dim=GNN_INPUT_DIM, hidden_dim=GNN_HIDDEN_DIM):
        super().__init__()
        self.conv1 = GCNConv(in_dim, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, hidden_dim // 2)

    def encode(self, x, edge_index):
        return self.conv2(self.conv1(x, edge_index).relu(), edge_index)

    def decode(self, z, edge_index):
        return (z[edge_index[0]] * z[edge_index[1]]).sum(dim=1)

_model = None
_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def _load_model():
    global _model
    if _model is None:
        _model = GraphAutoencoder().to(_device)
        _model.load_state_dict(
            torch.load(GNN_MODEL_PATH, map_location=_device, weights_only=True)
        )
        _model.eval()
        logger.info("GNN model loaded from %s on %s", GNN_MODEL_PATH, _device)
    return _model

def _hash_feature(text: str, dim: int = GNN_INPUT_DIM) -> torch.Tensor:
    text = text or "unknown"
    seed = int(hashlib.sha256(str(text).encode()).hexdigest(), 16) % 100_000
    torch.manual_seed(seed)
    return torch.rand(dim).to(_device)

def score_log(log: dict) -> float:
    """
    Returns an anomaly score in [0, 1].
    High score = more anomalous.
    No artificial boosting — the model speaks for itself.
    """
    model = _load_model()
    parent_id   = str(log.get("parentProcessId", "unknown_parent"))
    process_name = log.get("processName", log.get("cmdLine", "unknown"))
    user_id     = str(log.get("userId", "unknown"))
    child_fp    = f"{process_name}_{user_id}"

    x = torch.stack([_hash_feature(parent_id), _hash_feature(child_fp)])
    edge_index = torch.tensor([[0], [1]], dtype=torch.long).to(_device)

    with torch.no_grad():
        z    = model.encode(x, edge_index)
        pred = model.decode(z, edge_index)
        score = 1.0 - torch.sigmoid(pred).item()

    return round(score, 4)

def is_anomalous(log: dict, threshold: float = ANOMALY_THRESHOLD) -> tuple[bool, float]:
    """Returns (is_anomalous, score)."""
    s = score_log(log)
    return s > threshold, s
