"""Extract subgraph and build node feature tensors from Neo4j for GraphSAGE.

Node feature vector (7 dimensions):
    [0] has_darkweb_mention   (bool → 0/1)
    [1] keyword_score         (float, normalized)
    [2] num_emails            (int)
    [3] num_usernames         (int)
    [4] carrier_type          (one-hot encoded → float)
    [5] mention_count         (int)
    [6] cross_entity_count    (int)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch_geometric.data import Data

CARRIER_ENCODING = {
    "mobile": 1.0,
    "fixed_line": 0.5,
    "fixed_line_or_mobile": 0.75,
    "voip": 0.3,
    "toll_free": 0.1,
    "premium_rate": 0.2,
    "unknown": 0.0,
}

RISK_LABEL = {
    "MINIMAL": 0,
    "LOW": 0,
    "MEDIUM": 0,
    "HIGH": 1,
    "CRITICAL": 1,
}


def build_pyg_data(subgraph: dict[str, Any], target_phone: str | None = None) -> Data:
    """Convert a Neo4j subgraph dict into a PyG ``Data`` object.

    Parameters
    ----------
    subgraph : dict
        Output of ``Neo4jHandler.get_subgraph_for_gnn`` with 'nodes' and 'edges'.
    target_phone : str, optional
        If provided, return the index of this phone node as ``data.target_idx``.

    Returns
    -------
    torch_geometric.data.Data
    """
    nodes = subgraph["nodes"]
    edges = subgraph["edges"]

    if not nodes:
        return Data(
            x=torch.zeros((1, 7)),
            edge_index=torch.zeros((2, 0), dtype=torch.long),
        )

    neo_id_to_idx: dict[int, int] = {}
    features: list[list[float]] = []
    labels: list[int] = []
    target_idx = 0

    for i, node in enumerate(nodes):
        neo_id = node["node_id"]
        neo_id_to_idx[neo_id] = i

        feat = [
            1.0 if node.get("has_darkweb_mention") else 0.0,
            float(node.get("keyword_score", 0.0)),
            float(node.get("num_emails", 0)),
            float(node.get("num_usernames", 0)),
            CARRIER_ENCODING.get(str(node.get("carrier_type", "unknown")), 0.0),
            float(node.get("mention_count", 0)),
            float(node.get("cross_entity_count", 0)),
        ]
        features.append(feat)

        risk = node.get("risk_level", "MINIMAL")
        labels.append(RISK_LABEL.get(risk, 0))

        if target_phone and node.get("node_key") == target_phone:
            target_idx = i

    x = torch.tensor(features, dtype=torch.float)

    src_list, tgt_list = [], []
    for edge in edges:
        s = neo_id_to_idx.get(edge["source"])
        t = neo_id_to_idx.get(edge["target"])
        if s is not None and t is not None:
            src_list.append(s)
            tgt_list.append(t)

    if src_list:
        edge_index = torch.tensor([src_list, tgt_list], dtype=torch.long)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)

    y = torch.tensor(labels, dtype=torch.long)

    data = Data(x=x, edge_index=edge_index, y=y)
    data.target_idx = target_idx
    return data


def normalize_features(x: torch.Tensor) -> torch.Tensor:
    """Per-feature min-max normalization."""
    mins = x.min(dim=0).values
    maxs = x.max(dim=0).values
    denom = maxs - mins
    denom[denom == 0] = 1.0
    return (x - mins) / denom
