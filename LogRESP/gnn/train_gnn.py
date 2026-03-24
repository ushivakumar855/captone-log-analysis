# gnn/train_gnn.py
# Trains the Graph Autoencoder on the benign provenance graph.
# Run after extract_pyg.py: python -m gnn.train_gnn

import time
import torch
import torch.nn.functional as F
from torch_geometric.utils import negative_sampling
from gnn.scorer import GraphAutoencoder
from config import (
    BENIGN_GRAPH_PT, GNN_MODEL_PATH,
    GNN_INPUT_DIM, GNN_HIDDEN_DIM, GNN_TRAIN_EPOCHS,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def train():
    logger.info("="*70)
    logger.info("=== GNN Training Pipeline ===")
    logger.info("="*70)
    
    # Load data
    logger.info("[train_gnn] Loading graph data from %s ...", BENIGN_GRAPH_PT)
    load_start = time.time()
    data = torch.load(BENIGN_GRAPH_PT, weights_only=False)
    load_time = time.time() - load_start
    
    logger.info("[train_gnn] Graph loaded in %.2fs", load_time)
    logger.info("  - Nodes: %d", data.num_nodes)
    logger.info("  - Edges: %d", data.edge_index.size(1))
    logger.info("  - Features per node: %d", data.x.size(1))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("[train_gnn] Device selected: %s", device)
    if device.type == "cuda":
        try:
            gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
            logger.info("[train_gnn] Available GPU memory: %.2f GB", gpu_mem)
        except:
            pass
    
    data   = data.to(device)
    logger.debug("[train_gnn] Graph moved to %s", device)

    # Initialize model
    logger.info("[train_gnn] Initializing GraphAutoencoder")
    logger.debug("  - Input dim: %d", GNN_INPUT_DIM)
    logger.debug("  - Hidden dim: %d", GNN_HIDDEN_DIM)
    model = GraphAutoencoder(GNN_INPUT_DIM, GNN_HIDDEN_DIM).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    logger.info("[train_gnn] Model initialized with %d parameters", total_params)
    
    # Optimizer
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    logger.info("[train_gnn] Optimizer: Adam (lr=0.01)")

    logger.info("="*70)
    logger.info("[train_gnn] Starting training for %d epochs...", GNN_TRAIN_EPOCHS)
    logger.info("="*70)
    
    model.train()
    
    loss_history = []
    epoch_times = []
    training_start = time.time()

    for epoch in range(1, GNN_TRAIN_EPOCHS + 1):
        epoch_start = time.time()
        
        optimizer.zero_grad()
        z = model.encode(data.x, data.edge_index)

        # Positive edges — real benign execution chains
        pos_pred  = model.decode(z, data.edge_index)
        loss_pos  = F.binary_cross_entropy_with_logits(
            pos_pred, torch.ones_like(pos_pred)
        )

        # Negative edges — synthetic anomalous chains
        neg_idx   = negative_sampling(
            edge_index=data.edge_index,
            num_nodes=data.num_nodes,
            num_neg_samples=data.edge_index.size(1),
        )
        neg_pred  = model.decode(z, neg_idx)
        loss_neg  = F.binary_cross_entropy_with_logits(
            neg_pred, torch.zeros_like(neg_pred)
        )

        loss = loss_pos + loss_neg
        loss.backward()
        optimizer.step()
        
        epoch_time = time.time() - epoch_start
        epoch_times.append(epoch_time)
        loss_val = loss.item()
        loss_history.append(loss_val)

        # Log every 10 epochs with detailed stats
        if epoch % 10 == 0:
            avg_pos_loss = F.binary_cross_entropy_with_logits(
                pos_pred, torch.ones_like(pos_pred)
            ).item()
            avg_neg_loss = F.binary_cross_entropy_with_logits(
                neg_pred, torch.zeros_like(neg_pred)
            ).item()
            
            # Convergence metrics
            epoch_window = loss_history[-10:]
            min_loss_window = min(epoch_window) if epoch_window else loss_val
            max_loss_window = max(epoch_window) if epoch_window else loss_val
            
            logger.info("[Epoch %03d] Loss=%.4f | Pos=%.4f Neg=%.4f | Window:[%.4f-%.4f] | Time=%.2fs",
                       epoch, loss_val, avg_pos_loss, avg_neg_loss, 
                       min_loss_window, max_loss_window, epoch_time)
            
            # Check convergence direction
            if len(loss_history) >= 20:
                recent_avg = sum(loss_history[-10:]) / 10
                older_avg = sum(loss_history[-20:-10]) / 10
                trend = "DECREASING" if recent_avg < older_avg else "STABLE/INCREASING"
                logger.debug("[Epoch %03d] Convergence trend: %s (recent=%.4f, older=%.4f)",
                            epoch, trend, recent_avg, older_avg)
        
        # Log every epoch at DEBUG level for full visibility
        else:
            logger.debug("[Epoch %03d] Loss=%.4f (time=%.3fs)", epoch, loss_val, epoch_time)

    total_training_time = time.time() - training_start
    logger.info("="*70)
    logger.info("[train_gnn] Training complete in %.2fs", total_training_time)
    logger.info("  - Total epochs: %d", GNN_TRAIN_EPOCHS)
    logger.info("  - Avg time per epoch: %.3fs", sum(epoch_times) / len(epoch_times) if epoch_times else 0)
    logger.info("  - Initial loss: %.6f", loss_history[0] if loss_history else "N/A")
    logger.info("  - Final loss:   %.6f", loss_history[-1] if loss_history else "N/A")
    logger.info("  - Min loss:     %.6f", min(loss_history) if loss_history else "N/A")
    logger.info("  - Convergence:  %s", "YES" if loss_history[-1] < loss_history[0] else "NO")
    
    # Save model
    logger.info("[train_gnn] Saving model to %s", GNN_MODEL_PATH)
    save_start = time.time()
    torch.save(model.state_dict(), GNN_MODEL_PATH)
    save_time = time.time() - save_start
    logger.info("[train_gnn] Model saved successfully (%.3fs)", save_time)
    logger.info("="*70)


if __name__ == "__main__":
    train()
