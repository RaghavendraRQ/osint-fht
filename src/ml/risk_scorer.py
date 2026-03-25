"""GNN-based risk scorer – integrates GraphSAGE with the OSINT pipeline.

Workflow:
    1. Extract 2-hop subgraph from Neo4j for the target phone
    2. Build PyG Data object with 7-dim node features
    3. Run GraphSAGE → get P(HIGH_RISK)
    4. Blend GNN score with traditional composite score
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch_geometric.data import Data

import config
from .graph_features import build_pyg_data, normalize_features
from .model import GraphSAGERiskModel

logger = logging.getLogger(__name__)


class GNNRiskScorer:
    """Manages the GraphSAGE model lifecycle: load/train/predict."""

    def __init__(self, model_path: Path | None = None):
        self.model_path = model_path or config.GNN_MODEL_PATH
        self.model = GraphSAGERiskModel(
            in_channels=config.GNN_NUM_FEATURES,
            hidden_channels=config.GNN_HIDDEN_DIM,
        )
        self._loaded = False
        self._try_load()

    def _try_load(self):
        if self.model_path.exists():
            try:
                state = torch.load(self.model_path, map_location="cpu", weights_only=True)
                self.model.load_state_dict(state)
                self.model.eval()
                self._loaded = True
                logger.info("Loaded GNN model from %s", self.model_path)
            except Exception as exc:
                logger.warning("Failed to load GNN model: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self._loaded

    async def score(self, neo4j_handler, phone: str) -> dict[str, Any]:
        """Score a phone number using the GNN.

        Returns dict with ``gnn_score``, ``gnn_risk_level``, ``embedding``, and
        ``blended_score`` (combination of GNN + traditional).
        """
        try:
            subgraph = await neo4j_handler.get_subgraph_for_gnn(phone)
            if not subgraph["nodes"]:
                return self._fallback("No nodes in subgraph")

            data = build_pyg_data(subgraph, target_phone=phone)
            data.x = normalize_features(data.x)

            self.model.eval()
            with torch.no_grad():
                proba = self.model.predict_proba(data.x, data.edge_index)
                embeddings = self.model.get_embeddings(data.x, data.edge_index)

            target_idx = getattr(data, "target_idx", 0)
            gnn_score = float(proba[target_idx])
            embedding = embeddings[target_idx].tolist()

            gnn_risk_level = config.get_risk_level(gnn_score)

            traditional_score = self._get_traditional_score(subgraph, phone)
            blended = 0.6 * gnn_score + 0.4 * traditional_score

            return {
                "gnn_score": round(gnn_score, 4),
                "gnn_risk_level": gnn_risk_level,
                "embedding": embedding,
                "traditional_score": round(traditional_score, 4),
                "blended_score": round(blended, 4),
                "blended_risk_level": config.get_risk_level(blended),
                "model_loaded": self._loaded,
                "num_nodes": len(subgraph["nodes"]),
                "num_edges": len(subgraph["edges"]),
            }
        except Exception as exc:
            logger.exception("GNN scoring failed for %s", phone)
            return self._fallback(str(exc))

    def train(self, data_list: list[Data], epochs: int | None = None) -> dict[str, float]:
        """Train the GraphSAGE model on a list of PyG Data objects.

        Each Data should have ``y`` labels (0=low risk, 1=high risk).
        Returns training metrics.
        """
        epochs = epochs or config.GNN_EPOCHS
        optimizer = torch.optim.Adam(self.model.parameters(), lr=config.GNN_LEARNING_RATE)
        criterion = torch.nn.BCEWithLogitsLoss()

        self.model.train()
        total_loss = 0.0
        total_correct = 0
        total_nodes = 0

        for epoch in range(epochs):
            epoch_loss = 0.0
            for data in data_list:
                if data.x.shape[0] == 0:
                    continue
                data.x = normalize_features(data.x)
                optimizer.zero_grad()
                logits = self.model(data.x, data.edge_index)
                loss = criterion(logits, data.y.float())
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

                preds = (torch.sigmoid(logits) > 0.5).long()
                total_correct += (preds == data.y).sum().item()
                total_nodes += data.y.shape[0]

            total_loss = epoch_loss

        self._save_model()
        accuracy = total_correct / max(total_nodes, 1)
        return {"final_loss": total_loss, "accuracy": accuracy, "epochs": epochs}

    def _save_model(self):
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), self.model_path)
        self._loaded = True
        logger.info("Saved GNN model to %s", self.model_path)

    @staticmethod
    def _get_traditional_score(subgraph: dict, phone: str) -> float:
        for node in subgraph["nodes"]:
            if node.get("node_key") == phone:
                return float(node.get("keyword_score", 0.0))
        return 0.0

    @staticmethod
    def _fallback(reason: str) -> dict[str, Any]:
        return {
            "gnn_score": None,
            "gnn_risk_level": None,
            "embedding": None,
            "traditional_score": None,
            "blended_score": None,
            "blended_risk_level": None,
            "model_loaded": False,
            "error": reason,
        }
