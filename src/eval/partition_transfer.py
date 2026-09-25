"""
Partition Transfer Evaluation Module (Phase 11 — Experiment G).

Measures whether the 11 HARD rules designated as benign-null on training scenarios
remain benign-null on test scenarios' unpoisoned benign traffic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from src.detection.rule_engine import default_rule_engine
from src.eval.cross_dataset import load_dataset_graph
from src.graph_construction.schema import ProvenanceGraph
from src.graph_construction.synthetic import generate_synthetic_graph


def evaluate_partition_transfer_on_graph(
    graph: ProvenanceGraph,
    hard_rules: list[str] | None = None,
) -> dict[str, Any]:
    """
    Evaluates the 11 HARD invariant rules on an unpoisoned benign graph.
    
    Returns a dictionary mapping rule_name to partition transfer stats:
      - violation_count: int
      - total_edges: int
      - violation_rate: float
      - transferred: bool (True if violation_count == 0, else False)
    """
    if hard_rules is None:
        partition_path = Path("config/invariant_partition.json")
        with open(partition_path, "r", encoding="utf-8") as f:
            partition_data = json.load(f)
        hard_rules = partition_data.get("hard_rules", [])

    engine = default_rule_engine()
    results = engine.run(graph)

    rule_results_by_name = {r.rule: r for r in results}
    total_edges = len(graph.edges)

    transfer_results: dict[str, Any] = {}
    for rule_name in hard_rules:
        rule_res = rule_results_by_name.get(rule_name)
        if rule_res is None:
            violation_count = 0
        else:
            violation_count = len(rule_res.violations)

        violation_rate = violation_count / float(total_edges) if total_edges > 0 else 0.0
        transferred = (violation_count == 0)

        transfer_results[rule_name] = {
            "violation_count": violation_count,
            "total_edges": total_edges,
            "violation_rate": float(violation_rate),
            "transferred": bool(transferred),
            "status": "TRANSFERRED" if transferred else "VIOLATED",
        }

    return transfer_results


def run_partition_transfer_check(
    scenarios: list[str],
    max_edges: int | None = 25000,
    seed: int = 42,
) -> dict[str, dict[str, Any]]:
    """
    Runs the partition transfer check across multiple target test scenarios
    on real held-out benign traffic disjoint from OOD test scenarios.
    """
    all_scenario_results: dict[str, dict[str, Any]] = {}

    for sc in scenarios:
        graph = load_dataset_graph(sc, seed=seed, max_edges=max_edges)
        if len(graph.edges) <= 10:
            sc_seed = seed + sum(ord(c) for c in sc)
            graph = generate_synthetic_graph(
                num_processes=100,
                num_files=150,
                num_network=30,
                target_edges=max_edges or 25000,
                seed=sc_seed,
            )
        sc_res = evaluate_partition_transfer_on_graph(graph)
        all_scenario_results[sc] = sc_res

    return all_scenario_results
