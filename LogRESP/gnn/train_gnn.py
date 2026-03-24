# gnn/train_gnn.py
# Trains the Graph Autoencoder on the benign provenance graph.
# Run after extract_pyg.py: python -m gnn.train_gnn

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
    logger.info("[train_gnn] Loading %s ...", BENIGN_GRAPH_PT)
    data = torch.load(BENIGN_GRAPH_PT, weights_only=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data   = data.to(device)

    model     = GraphAutoencoder(GNN_INPUT_DIM, GNN_HIDDEN_DIM).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    logger.info("[train_gnn] Training on %s for %d epochs...", device, GNN_TRAIN_EPOCHS)
    model.train()

    for epoch in range(1, GNN_TRAIN_EPOCHS + 1):
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

        if epoch % 10 == 0:
            logger.info("  Epoch %03d  loss=%.4f", epoch, loss.item())

    torch.save(model.state_dict(), GNN_MODEL_PATH)
    logger.info("[train_gnn] Model saved → %s", GNN_MODEL_PATH)


if __name__ == "__main__":
    train()
