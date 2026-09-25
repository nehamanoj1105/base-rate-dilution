"""
Detector Registry Module for Provenance Graph Tamper Detection (Phase 9).

Provides a uniform interface (Detector) wrapping all 5 detector configurations:
  1. Rule Engine (HARD rules only)
  2. Rule Engine (all 15 rules)
  3. GraphSAGE (ungated baseline)
  4. GraphSAGE + Invariant Features (ungated control)
  5. Feasibility-Gated GraphSAGE (ours)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Set

import numpy as np
import torch

from models.feasibility_gate import compute_hard_mask
from src.detection.rule_engine import RuleEngine, default_rule_engine
from src.eval.evaluator import Evaluator
from src.graph_construction.schema import ProvenanceGraph
from src.ml.dataset import provenance_to_pyg_data
from src.ml.graphsage import GraphSAGEForTamperDetection
from src.ml.metrics import find_best_threshold
from src.ml.train import train_pipeline
from src.ml.utils import get_device, set_seed


class Detector(ABC):
    """Abstract base class for all registered detectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the detector."""
        pass

    @abstractmethod
    def fit_threshold(self, val_graph: ProvenanceGraph, val_gt_ids: set[str]) -> float:
        """
        Fit / calibrate operating threshold ONCE on the m=0 validation graph.
        Returns the chosen operating threshold float.
        """
        pass

    @abstractmethod
    def score_edges(self, graph: ProvenanceGraph) -> dict[str, float]:
        """
        Computes continuous edge anomaly scores for all edges in graph.
        Returns a dict mapping edge_id -> score in [0, 1].
        """
        pass

    def predict(
        self, graph: ProvenanceGraph, threshold: float | None = None
    ) -> set[str]:
        """Flags edges whose anomaly score is >= threshold."""
        thresh = threshold if threshold is not None else getattr(self, "operating_threshold", 0.5)
        scores = self.score_edges(graph)
        return {eid for eid, score in scores.items() if score >= thresh}


def load_frozen_thresholds() -> dict[str, float]:
    """Loads frozen operating thresholds from config/frozen_thresholds.json."""
    p = Path("config/frozen_thresholds.json")
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("thresholds", {})
        except Exception:
            pass
    return {
        "rule_hard": 0.5,
        "rule_all": 0.5,
        "rule_engine": 0.5,
        "graphsage_baseline": 0.6,
        "graphsage": 0.6,
        "graphsage_inv_features": 0.6,
        "gated_sage": 0.05,
    }


def get_frozen_threshold(detector_key: str) -> float:
    """Returns the frozen operating threshold for a detector key."""
    thresholds = load_frozen_thresholds()
    key_clean = detector_key.lower().replace(" ", "_")
    if key_clean in thresholds:
        return float(thresholds[key_clean])
    for k, v in thresholds.items():
        if k in key_clean or key_clean in k:
            return float(v)
    return 0.5


class RuleHardAdapter(Detector):
    """1. Rule Engine Adapter evaluating ONLY the 11 HARD rules."""

    def __init__(self, **kwargs: Any):
        self.operating_threshold = get_frozen_threshold("rule_hard")
        self.base_mask_cache: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "Rule-only (HARD set)"

    def fit_threshold(self, val_graph: ProvenanceGraph, val_gt_ids: set[str]) -> float:
        self.operating_threshold = get_frozen_threshold("rule_hard")
        self.base_mask_cache = compute_hard_mask(val_graph)
        return self.operating_threshold

    def score_edges(self, graph: ProvenanceGraph) -> dict[str, float]:
        if not self.base_mask_cache:
            self.base_mask_cache = compute_hard_mask(graph)
        scores: dict[str, float] = {}
        for edge in graph.edges:
            scores[edge.edge_id] = self.base_mask_cache.get(edge.edge_id, 0.0)
        return scores


class RuleAllAdapter(Detector):
    """2. Rule Engine Adapter evaluating all 15 rules."""

    def __init__(self, engine: RuleEngine | None = None, **kwargs: Any):
        self.engine = engine if engine is not None else default_rule_engine()
        self.operating_threshold = get_frozen_threshold("rule_all")

    @property
    def name(self) -> str:
        return "Rule-only (all 15 rules)"

    def fit_threshold(self, val_graph: ProvenanceGraph, val_gt_ids: set[str]) -> float:
        self.operating_threshold = get_frozen_threshold("rule_all")
        return self.operating_threshold

    def score_edges(self, graph: ProvenanceGraph) -> dict[str, float]:
        results = self.engine.run(graph)
        flagged = Evaluator._extract_detected_ids(results)

        scores: dict[str, float] = {}
        for edge in graph.edges:
            scores[edge.edge_id] = 1.0 if edge.edge_id in flagged else 0.0
        return scores


class GraphSAGEAdapter(Detector):
    """3. Standard GraphSAGE (ungated baseline, 7 node features)."""

    def __init__(
        self,
        hidden_channels: int = 32,
        lr: float = 0.01,
        epochs: int = 20,
        seed: int = 42,
        **kwargs: Any,
    ):
        self.hidden_channels = hidden_channels
        self.lr = lr
        self.epochs = epochs
        self.seed = seed
        self.model: Optional[GraphSAGEForTamperDetection] = None
        self.operating_threshold: float = get_frozen_threshold("graphsage_baseline")

    @property
    def name(self) -> str:
        return "GraphSAGE (ungated baseline)"

    def fit_threshold(self, val_graph: ProvenanceGraph, val_gt_ids: set[str]) -> float:
        set_seed(self.seed)
        pyg_data = provenance_to_pyg_data(val_graph, poisoned_edge_ids=val_gt_ids, include_soft_invariants=False)

        model, _, _, _, _ = train_pipeline(
            pyg_data,
            epochs=self.epochs,
            lr=self.lr,
            hidden_channels=self.hidden_channels,
            seed=self.seed,
        )
        self.model = model
        self.operating_threshold = get_frozen_threshold("graphsage_baseline")
        return self.operating_threshold

    def score_edges(self, graph: ProvenanceGraph) -> dict[str, float]:
        if self.model is None:
            set_seed(self.seed)
            pyg_data_dummy = provenance_to_pyg_data(graph, include_soft_invariants=False)
            model, _, _, _, _ = train_pipeline(
                pyg_data_dummy,
                epochs=self.epochs,
                lr=self.lr,
                hidden_channels=self.hidden_channels,
                seed=self.seed,
            )
            self.model = model

        device = get_device()
        pyg_data = provenance_to_pyg_data(graph, include_soft_invariants=False)

        self.model.eval()
        with torch.no_grad():
            x_dev = pyg_data.x.to(device)
            edge_idx_dev = pyg_data.edge_index.to(device)
            _, edge_logits, _ = self.model(x_dev, edge_idx_dev)
            probs = torch.sigmoid(edge_logits).cpu().numpy()

        edge_ids = [e.edge_id for e in graph.edges]
        n_edges = len(edge_ids)
        if len(probs) < n_edges:
            padded = np.zeros(n_edges, dtype=float)
            padded[:len(probs)] = probs
            probs = padded
        return dict(zip(edge_ids, probs.astype(float)))


class GraphSAGEInvFeaturesAdapter(Detector):
    """
    4. GraphSAGE + invariant features (ungated control).
    
    Trained with include_soft_invariants=True (edge_attr_dim=11), BUT UNGATED.
    Scores edges as sigmoid(edge_logits) without multiplying by feasibility gate mask.
    """

    def __init__(
        self,
        hidden_channels: int = 32,
        lr: float = 0.01,
        epochs: int = 20,
        seed: int = 42,
        **kwargs: Any,
    ):
        self.hidden_channels = hidden_channels
        self.lr = lr
        self.epochs = epochs
        self.seed = seed
        self.model: Optional[GraphSAGEForTamperDetection] = None
        self.operating_threshold: float = get_frozen_threshold("graphsage_inv_features")

    @property
    def name(self) -> str:
        return "GraphSAGE + invariant features (ungated)"

    def fit_threshold(self, val_graph: ProvenanceGraph, val_gt_ids: set[str]) -> float:
        set_seed(self.seed)
        pyg_data = provenance_to_pyg_data(val_graph, poisoned_edge_ids=val_gt_ids, include_soft_invariants=True)

        model = GraphSAGEForTamperDetection(
            in_channels=pyg_data.x.size(-1),
            edge_attr_dim=pyg_data.edge_attr.size(-1),
            hidden_channels=self.hidden_channels,
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=self.lr)
        criterion = torch.nn.BCEWithLogitsLoss()

        device = get_device()
        model.to(device)
        pyg_data_dev = pyg_data.to(device)

        model.train()
        for epoch in range(self.epochs):
            optimizer.zero_grad()
            _, edge_logits, _ = model(pyg_data_dev.x, pyg_data_dev.edge_index, edge_attr=pyg_data_dev.edge_attr)
            loss = criterion(edge_logits, pyg_data_dev.edge_label)
            loss.backward()
            optimizer.step()

        self.model = model
        self.operating_threshold = get_frozen_threshold("graphsage_inv_features")
        return self.operating_threshold

    def score_edges(self, graph: ProvenanceGraph) -> dict[str, float]:
        if self.model is None:
            set_seed(self.seed)
            pyg_data_dummy = provenance_to_pyg_data(graph, include_soft_invariants=True)
            self.fit_threshold(graph, set())

        device = get_device()
        pyg_data = provenance_to_pyg_data(graph, include_soft_invariants=True)

        self.model.eval()
        with torch.no_grad():
            x_dev = pyg_data.x.to(device)
            edge_idx_dev = pyg_data.edge_index.to(device)
            edge_attr_dev = pyg_data.edge_attr.to(device)
            _, edge_logits, _ = self.model(x_dev, edge_idx_dev, edge_attr=edge_attr_dev)
            probs = torch.sigmoid(edge_logits).cpu().numpy()

        edge_ids = [e.edge_id for e in graph.edges]
        n_edges = len(edge_ids)
        if len(probs) < n_edges:
            padded = np.zeros(n_edges, dtype=float)
            padded[:len(probs)] = probs
            probs = padded
        return dict(zip(edge_ids, probs.astype(float)))


class GatedSAGEAdapter(Detector):
    """5. Feasibility-Gated GraphSAGE (ours)."""

    def __init__(
        self,
        hidden_channels: int = 32,
        lr: float = 0.01,
        epochs: int = 20,
        seed: int = 42,
        **kwargs: Any,
    ):
        self.hidden_channels = hidden_channels
        self.lr = lr
        self.epochs = epochs
        self.seed = seed
        from models.gated_sage import GatedSAGE
        self.gated_model: Optional[GatedSAGE] = None
        self.operating_threshold: float = get_frozen_threshold("gated_sage")

    @property
    def name(self) -> str:
        return "Feasibility-gated GraphSAGE (ours)"

    def fit_threshold(self, val_graph: ProvenanceGraph, val_gt_ids: set[str]) -> float:
        set_seed(self.seed)
        ckpt_p = Path(f"results/checkpoints/gated_sage_seed_{self.seed}.pt")
        if ckpt_p.exists():
            ckpt = torch.load(ckpt_p, map_location="cpu", weights_only=False)
            base_model = GraphSAGEForTamperDetection(
                in_channels=7, edge_attr_dim=11, hidden_channels=self.hidden_channels
            )
            from models.gated_sage import GatedSAGE
            self.gated_model = GatedSAGE(base_graphsage=base_model)
            self.gated_model.load_state_dict(ckpt["model_state_dict"])
            self.operating_threshold = get_frozen_threshold("gated_sage")
            return self.operating_threshold

        from scripts.run_gated_training import train_single_seed_gated
        model, _, _ = train_single_seed_gated(seed=self.seed, epochs=self.epochs, lr=self.lr, hidden_channels=self.hidden_channels)
        self.gated_model = model
        self.operating_threshold = get_frozen_threshold("gated_sage")
        return self.operating_threshold

    def score_edges(self, graph: ProvenanceGraph) -> dict[str, float]:
        if self.gated_model is None:
            self.fit_threshold(graph, set())
        return self.gated_model.score_edges(graph)


RuleEngineAdapter = RuleAllAdapter

# Global Registry mapping detector names to factory functions
DETECTOR_REGISTRY: dict[str, type[Detector]] = {
    "rule_hard": RuleHardAdapter,
    "rule_all": RuleAllAdapter,
    "rule_engine": RuleAllAdapter,
    "graphsage_baseline": GraphSAGEAdapter,
    "graphsage": GraphSAGEAdapter,
    "graphsage_inv_features": GraphSAGEInvFeaturesAdapter,
    "gated_sage": GatedSAGEAdapter,
}


def get_detector(name: str, **kwargs) -> Detector:
    """Instantiates a registered detector by name."""
    lower_name = name.lower().replace(" ", "_")
    if lower_name not in DETECTOR_REGISTRY:
        raise KeyError(
            f"Unknown detector '{name}'. Registered detectors: {list(DETECTOR_REGISTRY.keys())}"
        )
    return DETECTOR_REGISTRY[lower_name](**kwargs)
