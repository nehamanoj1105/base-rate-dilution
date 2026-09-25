"""
Unit tests for Phase 11 — Experiment G: OOD Generalization & Partition Transfer.
"""

import json
from pathlib import Path
import pytest

from src.eval.ood_evaluation import (
    load_combined_scenario_graph,
    merge_provenance_graphs,
    run_ood_experiment,
)
from src.eval.partition_transfer import (
    evaluate_partition_transfer_on_graph,
    run_partition_transfer_check,
)
from src.graph_construction.schema import EdgeType, NodeType, ProvenanceEdge, ProvenanceGraph, ProvenanceNode


def test_merge_provenance_graphs():
    g1 = ProvenanceGraph()
    g1.add_node(ProvenanceNode("n1", NodeType.PROCESS, "proc1"))
    g1.add_node(ProvenanceNode("n2", NodeType.FILE, "file1"))
    g1.add_edge(ProvenanceEdge("e1", "n1", "n2", EdgeType.READ, 100.0))

    g2 = ProvenanceGraph()
    g2.add_node(ProvenanceNode("n1", NodeType.PROCESS, "proc2"))
    g2.add_node(ProvenanceNode("n3", NodeType.FILE, "file2"))
    g2.add_edge(ProvenanceEdge("e1", "n1", "n3", EdgeType.WRITE, 200.0))

    merged = merge_provenance_graphs([g1, g2], prefixes=["p1", "p2"])

    assert len(merged.nodes) == 4
    assert len(merged.edges) == 2
    assert "p1_n1" in merged.nodes
    assert "p2_n1" in merged.nodes
    assert "p1_e1" in [e.edge_id for e in merged.edges]
    assert "p2_e1" in [e.edge_id for e in merged.edges]


def test_partition_transfer_check():
    g = ProvenanceGraph()
    g.add_node(ProvenanceNode("proc1", NodeType.PROCESS, "proc1"))
    g.add_node(ProvenanceNode("file1", NodeType.FILE, "file1"))
    g.add_edge(ProvenanceEdge("e1", "proc1", "file1", EdgeType.READ, 100.0))

    res = evaluate_partition_transfer_on_graph(g)
    assert isinstance(res, dict)
    assert len(res) == 11  # 11 HARD rules
    for rule_name, info in res.items():
        assert "violation_count" in info
        assert "violation_rate" in info
        assert "transferred" in info
        assert "status" in info


def test_small_scale_ood_experiment(tmp_path):
    output_json = tmp_path / "ood_test.json"

    directions = [
        {"name": "TestDir", "train": ["1r"], "test": ["3"]},
    ]

    data = run_ood_experiment(
        directions=directions,
        m_grid=[0, 100],
        seeds=[42],
        noise_models=["synthetic"],
        poison_intensity=2,
        max_edges_per_scenario=500,
        output_json_path=output_json,
    )

    assert output_json.exists()
    assert "partition_transfer_check" in data
    assert "alpha_fits" in data
    assert "sweep_results" in data
    assert len(data["sweep_results"]) > 0
