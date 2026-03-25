"""GraphSAGE model for node-level risk classification.

Architecture:
    Input features (7-dim)
        → GraphSAGE layer 1 (7 → hidden_dim) + ReLU + Dropout
        → GraphSAGE layer 2 (hidden_dim → hidden_dim) + ReLU + Dropout
        → Linear classifier (hidden_dim → 1)
        → Sigmoid → P(HIGH_RISK) ∈ [0, 1]
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv


class GraphSAGERiskModel(nn.Module):
    def __init__(self, in_channels: int = 7, hidden_channels: int = 64, dropout: float = 0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.classifier = nn.Linear(hidden_channels, 1)
        self.dropout = dropout

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """Full forward pass – returns logits (pre-sigmoid) for all nodes."""
        h = self.conv1(x, edge_index)
        h = F.relu(h)
        h = F.dropout(h, p=self.dropout, training=self.training)

        h = self.conv2(h, edge_index)
        h = F.relu(h)
        h = F.dropout(h, p=self.dropout, training=self.training)

        return self.classifier(h).squeeze(-1)

    def get_embeddings(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """Return 64-dim node embeddings (before the classifier head)."""
        h = self.conv1(x, edge_index)
        h = F.relu(h)
        h = self.conv2(h, edge_index)
        h = F.relu(h)
        return h

    def predict_proba(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """Return P(HIGH_RISK) for every node."""
        logits = self.forward(x, edge_index)
        return torch.sigmoid(logits)
