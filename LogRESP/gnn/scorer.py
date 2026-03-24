# gnn/scorer.py  —  Honest GNN anomaly scoring
# The +0.90 heuristic hack has been removed entirely.
# The model output is the score. Period.

import hashlib
import time
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
logger.info("[GNN] Device selected: %s", _device)

def _load_model():
    global _model
    if _model is None:
        logger.info("[GNN] Loading model from %s onto %s (first-time initialization)", GNN_MODEL_PATH, _device)
        try:
            _model = GraphAutoencoder().to(_device)
            load_start = time.time()
            _model.load_state_dict(
                torch.load(GNN_MODEL_PATH, map_location=_device, weights_only=True)
            )
            load_time = time.time() - load_start
            _model.eval()
            logger.info("[GNN] Model loaded successfully in %.3fs (eval mode enabled)", load_time)
        except Exception as e:
            logger.error("[GNN] Model load failed: %s", e, exc_info=True)
            raise
    else:
        logger.debug("[GNN] Using cached model")
    return _model

def _hash_feature(text: str, dim: int = GNN_INPUT_DIM) -> torch.Tensor:
    text = text or "unknown"
    seed = int(hashlib.sha256(str(text).encode()).hexdigest(), 16) % 100_000
    torch.manual_seed(seed)
    feat = torch.rand(dim).to(_device)
    logger.debug("[GNN] Feature hashed: %s -> hash_seed=%d, dim=%d", text[:50], seed, dim)
    return feat

def score_log(log: dict) -> float:
    """
    Returns an anomaly score in [0, 1].
    High score = more anomalous.
    No artificial boosting — the model speaks for itself.
    """
    logger.debug("[GNN] score_log() invoked for log entry")
    
    try:
        model = _load_model()
        parent_id   = str(log.get("parentProcessId", "unknown_parent"))
        process_name = log.get("processName", log.get("cmdLine", "unknown"))
        user_id     = str(log.get("userId", "unknown"))
        child_fp    = f"{process_name}_{user_id}"
        
        logger.debug("[GNN] Extracted features: parent_id=%s, process=%s, user=%s",
                     parent_id[:40], process_name[:40], user_id[:40])

        # Feature hashing
        feat_start = time.time()
        parent_feat = _hash_feature(parent_id)
        child_feat = _hash_feature(child_fp)
        feat_time = time.time() - feat_start
        logger.debug("[GNN] Features hashed in %.3fs", feat_time)
        
        # Build execution edge
        x = torch.stack([parent_feat, child_feat])
        edge_index = torch.tensor([[0], [1]], dtype=torch.long).to(_device)
        logger.debug("[GNN] Edge constructed: 2 nodes, 1 edge")

        # GNN encoding and decoding
        with torch.no_grad():
            encode_start = time.time()
            z    = model.encode(x, edge_index)
            encode_time = time.time() - encode_start
            logger.debug("[GNN] Encoding complete in %.3fs (latent_dim=%d)", encode_time, z.shape[1])
            
            decode_start = time.time()
            pred = model.decode(z, edge_index)
            decode_time = time.time() - decode_start
            logger.debug("[GNN] Decoding complete in %.3fs (pred_val=%.4f)", decode_time, pred.item())
            
            sig_start = time.time()
            sigmoid_val = torch.sigmoid(pred).item()
            score = 1.0 - sigmoid_val
            sig_time = time.time() - sig_start
            logger.debug("[GNN] Sigmoid(pred)=%.4f -> anomaly_score=%.4f (inverted) (time=%.3fs)",
                        sigmoid_val, score, sig_time)

        final_score = round(score, 4)
        logger.debug("[GNN] Final score: %.4f", final_score)
        return final_score
        
    except Exception as e:
        logger.error("[GNN] score_log() failed: %s", e, exc_info=True)
        raise

def is_anomalous(log: dict, threshold: float = ANOMALY_THRESHOLD) -> tuple[bool, float]:
    """Returns (is_anomalous, score)."""
    s = score_log(log)
    is_anom = s > threshold
    logger.debug("[GNN] Threshold comparison: score=%.4f > threshold=%.3f? %s",
                 s, threshold, "YES" if is_anom else "NO")
    return is_anom, s
