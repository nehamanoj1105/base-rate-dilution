"""
GatedSAGE Model for Provenance Graph Tamper Detection.

Combines standard 2-layer GraphSAGE with the Hard Feasibility Gate:
    s(e) = mask(e) * f_SAGE(e, x, edge_index, v_soft)

Scientific Principles:
    1. Candidate Set Boundedness: The hard feasibility gate restricts the candidate set strictly
       to invariant-violating edges. GraphSAGE CANNOT increase recall beyond the HARD rule set.
    2. Learned Discrimination: The sole job of the GNN is to classify violations WITHIN the
       candidate set — distinguishing benign invariant violations (pre-audit daemons, log rotation,
       clock skew) from true adversarial tampering.
    3. Feature Partitioning: v_soft (4 dims) is included in edge_attr to provide domain signals.
       v_hard (11 dims) is EXCLUDED from features so the GNN learns domain semantics rather than
       memorizing the gate.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import torch
import torch.nn as nn

from models.feasibility_gate import GatedDetector, compute_hard_mask
from src.graph_construction.schema import ProvenanceGraph
from src.ml.dataset import provenance_to_pyg_data
from src.ml.graphsage import GraphSAGEForTamperDetection
from src.ml.utils import get_device


class GatedSAGE(GatedDetector):
    """
    GatedSAGE Architecture wrapping GraphSAGE with the Hard Feasibility Gate.
    """

    def __init__(
        self,
        in_channels: int = 7,
        edge_attr_dim: int = 11,
        hidden_channels: int = 64,
        dropout: float = 0.1,
        base_graphsage: Optional[GraphSAGEForTamperDetection] = None,
    ):
        if base_graphsage is None:
            base_graphsage = GraphSAGEForTamperDetection(
                in_channels=in_channels,
                edge_attr_dim=edge_attr_dim,
                hidden_channels=hidden_channels,
                dropout=dropout,
            )
        super().__init__(base_model=base_graphsage)
        self.graphsage = base_graphsage

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
        mask: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.

        Returns:
            (gated_scores [E], raw_edge_logits [E])
        """
        _, edge_logits, _ = self.graphsage(x, edge_index, edge_attr=edge_attr)
        f_scores = torch.sigmoid(edge_logits)
        gated_scores = super().forward(f_scores, mask)
        return gated_scores, edge_logits

    def score_edges(self, graph: ProvenanceGraph) -> Dict[str, float]:
        """
        Computes gated anomaly probabilities for all edges in graph.

        Args:
            graph: Input ProvenanceGraph.

        Returns:
            Dict mapping edge_id -> gated score float in [0, 1].
        """
        # Step 1: Compute hard binary mask constant OUTSIDE autograd
        mask_dict = compute_hard_mask(graph)

        # Step 2: Convert graph to PyG Data including v_soft edge features
        pyg_data = provenance_to_pyg_data(graph, include_soft_invariants=True)
        device = get_device()

        self.eval()
        with torch.no_grad():
            x_dev = pyg_data.x.to(device)
            edge_idx_dev = pyg_data.edge_index.to(device)
            edge_attr_dev = pyg_data.edge_attr.to(device)

            _, edge_logits, _ = self.graphsage(x_dev, edge_idx_dev, edge_attr=edge_attr_dev)
            f_scores = torch.sigmoid(edge_logits).cpu().numpy()

        # Step 3: Final multiplication s(e) = mask(e) * f(e)
        gated_scores: Dict[str, float] = {}
        for idx, edge in enumerate(graph.edges):
            eid = edge.edge_id
            m_val = mask_dict.get(eid, 0.0)
            f_val = float(f_scores[idx]) if idx < len(f_scores) else 0.0
            gated_scores[eid] = float(m_val * f_val)

        return gated_scores
