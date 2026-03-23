import torch
import torch.nn.functional as F
from torch_geometric.nn import GCNConv
from torch_geometric.data import Data
from torch_geometric.utils import negative_sampling  # <-- THE MAGIC FIX

class GraphAutoencoder(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels):
        super(GraphAutoencoder, self).__init__()
        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, hidden_channels // 2)

    def encode(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        return self.conv2(x, edge_index)

    def decode(self, z, edge_index):
        return (z[edge_index[0]] * z[edge_index[1]]).sum(dim=1)

def train_one_class_gnn():
    print("[*] Loading benign_graph.pt...")
    data = torch.load('benign_graph.pt', weights_only=False)
    
    model = GraphAutoencoder(in_channels=16, hidden_channels=32)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    
    model.train()
    print("[*] Training OCR-APT Model with Negative Sampling...")
    
    for epoch in range(1, 51):
        optimizer.zero_grad()
        z = model.encode(data.x, data.edge_index)
        
        # 1. Positive Edges (Real benign execution chains -> Label 1)
        pos_pred = model.decode(z, data.edge_index)
        pos_label = torch.ones_like(pos_pred)
        loss_pos = F.binary_cross_entropy_with_logits(pos_pred, pos_label)
        
        # 2. Negative Edges (Fake/Anomalous execution chains -> Label 0)
        neg_edge_index = negative_sampling(
            edge_index=data.edge_index, num_nodes=data.num_nodes,
            num_neg_samples=data.edge_index.size(1)
        )
        neg_pred = model.decode(z, neg_edge_index)
        neg_label = torch.zeros_like(neg_pred)
        loss_neg = F.binary_cross_entropy_with_logits(neg_pred, neg_label)
        
        # 3. Combine and learn the difference!
        loss = loss_pos + loss_neg
        loss.backward()
        optimizer.step()
        
        if epoch % 10 == 0:
            print(f"    -> Epoch {epoch:03d}, Loss: {loss.item():.4f}")

    torch.save(model.state_dict(), 'ocr_apt_model.pth')
    print("[+] Model saved to ocr_apt_model.pth")

if __name__ == "__main__":
    train_one_class_gnn()