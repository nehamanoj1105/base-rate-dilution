"""
Out-of-Domain (OOD) Evaluation & Cross-Scenario Generalization (Phase 11 — Experiment G).

Evaluates generalisation across DARPA scenario shifts:
  - Direction 1: Train on {1r, 3}, Test on {5m, 6r}
  - Direction 2: Train on {5m, 6r}, Test on {1r, 3}

Measures model precision decay under dilution m, fits dilution exponent alpha_hat,
and assesses partition transferability of the 11 HARD rules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch

from src.attacks.benign_resampler import inject_resampled_benign_noise
from src.detection.mimicry_attack import inject_mimicry_attack
from src.detection.poisoning_injection import inject_poisoning
from src.eval.alpha_estimator import AlphaFitResult, fit_alpha_exponent
from src.eval.cross_dataset import load_dataset_graph
from src.eval.detector_registry import GatedSAGEAdapter, GraphSAGEAdapter
from src.eval.partition_transfer import run_partition_transfer_check
from src.graph_construction.schema import EdgeType, NodeType, ProvenanceEdge, ProvenanceGraph, ProvenanceNode


def merge_provenance_graphs(
    graphs: list[ProvenanceGraph],
    prefixes: list[str] | None = None,
) -> ProvenanceGraph:
    """Merges multiple ProvenanceGraphs into a single graph with prefix-isolated IDs."""
    merged = ProvenanceGraph()
    for idx, g in enumerate(graphs):
        pfx = f"{prefixes[idx]}_" if prefixes and idx < len(prefixes) else ""
        node_id_map: dict[str, str] = {}
        for nid, node in g.nodes.items():
            new_id = f"{pfx}{nid}" if pfx else nid
            node_id_map[nid] = new_id
            merged.add_node(
                ProvenanceNode(
                    node_id=new_id,
                    node_type=node.node_type,
                    label=node.label,
                    attributes=dict(node.attributes),
                )
            )
        for edge in g.edges:
            new_eid = f"{pfx}{edge.edge_id}" if pfx else edge.edge_id
            new_src = node_id_map.get(edge.source_id, edge.source_id)
            new_tgt = node_id_map.get(edge.target_id, edge.target_id)
            merged.add_edge(
                ProvenanceEdge(
                    edge_id=new_eid,
                    source_id=new_src,
                    target_id=new_tgt,
                    edge_type=edge.edge_type,
                    timestamp=edge.timestamp,
                    attributes=dict(edge.attributes),
                )
            )
    return merged


def load_combined_scenario_graph(
    scenarios: Sequence[str],
    seed: int = 42,
    max_edges_per_scenario: int | None = 25000,
) -> ProvenanceGraph:
    """Loads and merges graphs for a given list of scenario names."""
    subgraphs = [
        load_dataset_graph(sc, seed=seed, max_edges=max_edges_per_scenario)
        for sc in scenarios
    ]
    return merge_provenance_graphs(subgraphs, prefixes=list(scenarios))


def run_ood_experiment(
    directions: list[dict[str, list[str]]] | None = None,
    m_grid: Sequence[int] = (0, 1000, 2000, 5000, 10000, 20000, 50000, 100000),
    seeds: Sequence[int] = (0, 1, 2, 3, 4),
    noise_models: Sequence[str] = ("resampled", "synthetic"),
    poison_intensity: int = 5,
    max_edges_per_scenario: int | None = 25000,
    output_json_path: Path | str = "results/ood_crossscenario.json",
) -> dict[str, Any]:
    """
    Executes Experiment G: Cross-scenario OOD evaluation across directions.

    Directions default:
      1. train: ["1r", "3"], test: ["5m", "6r"]
      2. train: ["5m", "6r"], test: ["1r", "3"]
    """
    if directions is None:
        directions = [
            {"name": "Dir1_1r3_to_5m6r", "train": ["1r", "3"], "test": ["5m", "6r"]},
            {"name": "Dir2_5m6r_to_1r3", "train": ["5m", "6r"], "test": ["1r", "3"]},
        ]

    print("[*] Starting Experiment G: OOD Generalization & Partition Transfer Sweep...")

    # 1. Run Partition Transfer Check on Benign Traffic of Test Scenarios
    all_test_scenarios = sorted(
        list({sc for d in directions for sc in d["test"]})
    )
    print(f"[*] Running Partition Transfer Check on test scenarios: {all_test_scenarios}")
    partition_transfer_report = run_partition_transfer_check(
        scenarios=all_test_scenarios,
        max_edges=max_edges_per_scenario,
    )

    sweep_records: list[dict[str, Any]] = []

    for d_idx, d_info in enumerate(directions, 1):
        dir_name = d_info.get("name", f"Dir_{d_idx}")
        train_scenarios = d_info["train"]
        test_scenarios = d_info["test"]

        print(f"\n[+] Direction {d_idx}: Train {train_scenarios} -> Test {test_scenarios}")

        # Load Source (Train) Combined Graph
        train_graph = load_combined_scenario_graph(
            train_scenarios, seed=42, max_edges_per_scenario=max_edges_per_scenario
        )
        # Load Target (Test) Combined Graph
        test_base_graph = load_combined_scenario_graph(
            test_scenarios, seed=42, max_edges_per_scenario=max_edges_per_scenario
        )

        # For each seed, fit detectors ONCE on Train Graph, then evaluate on Test Graph
        for seed in seeds:
            print(f"  --> Processing Seed {seed}...")

            # Inject poison into train graph for threshold calibration on Train
            train_poison_res = inject_poisoning(
                train_graph,
                num_deletions=poison_intensity,
                num_insertions=poison_intensity,
                num_reorderings=poison_intensity,
                num_forgeries=poison_intensity,
                seed=seed,
            )
            train_gt_ids = {e.edge_id for e in train_poison_res.events}

            # Instantiate & calibrate detectors ONCE on Train graph
            # 1. Ungated GraphSAGE
            gs_det = GraphSAGEAdapter(seed=seed, epochs=15)
            gs_det.fit_threshold(train_poison_res.graph, train_gt_ids)

            # 2. Feasibility-Gated GraphSAGE
            gated_det = GatedSAGEAdapter(seed=seed, epochs=15)
            gated_det.fit_threshold(train_poison_res.graph, train_gt_ids)

            detectors = {
                "graphsage_baseline": gs_det,
                "gated_sage": gated_det,
            }

            # Evaluate over dilution sweep on Target (Test) Graph
            for noise_model in noise_models:
                for m in m_grid:
                    # Create base target graph copy
                    target_graph = load_combined_scenario_graph(
                        test_scenarios, seed=seed, max_edges_per_scenario=max_edges_per_scenario
                    )
                    # Inject poison into target graph
                    target_poison = inject_poisoning(
                        target_graph,
                        num_deletions=poison_intensity,
                        num_insertions=poison_intensity,
                        num_reorderings=poison_intensity,
                        num_forgeries=poison_intensity,
                        seed=seed,
                    )
                    eval_graph = target_poison.graph
                    poison_ids = {e.edge_id for e in target_poison.events}

                    # Inject dilution noise
                    if m > 0:
                        if noise_model == "resampled":
                            # Use source scenarios benign graph as pool to ensure no leakage from test
                            eval_graph = inject_resampled_benign_noise(
                                eval_graph,
                                donor_graph=train_graph,
                                target_added_edges=m,
                                seed=seed + m,
                            )
                        else:  # synthetic
                            mimic_res = inject_mimicry_attack(
                                eval_graph,
                                base_poisoning=target_poison,
                                noise_model="synthetic",
                                seed=seed + m,
                            )
                            eval_graph = mimic_res.graph

                    # Evaluate each detector with frozen threshold
                    for det_key, det in detectors.items():
                        flagged = det.predict(eval_graph)
                        tp = len(flagged.intersection(poison_ids))
                        fp = len(flagged - poison_ids)
                        fn = len(poison_ids - flagged)

                        precision = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
                        recall = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
                        f1 = (
                            2.0 * precision * recall / (precision + recall)
                            if (precision + recall) > 0
                            else 0.0
                        )

                        sweep_records.append({
                            "direction": dir_name,
                            "train_scenarios": train_scenarios,
                            "test_scenarios": test_scenarios,
                            "detector": det_key,
                            "detector_name": det.name,
                            "noise_model": noise_model,
                            "seed": seed,
                            "m": m,
                            "tp": tp,
                            "fp": fp,
                            "fn": fn,
                            "poison_edges": len(poison_ids),
                            "precision": round(precision, 6),
                            "recall": round(recall, 6),
                            "f1": round(f1, 6),
                        })

    # Compute dilution exponent alpha_hat per (direction, detector, noise_model)
    alpha_results: list[dict[str, Any]] = []
    unique_dirs = sorted(list({r["direction"] for r in sweep_records}))
    unique_dets = sorted(list({r["detector"] for r in sweep_records}))

    for dir_name in unique_dirs:
        for det_key in unique_dets:
            for nm in noise_models:
                sub = [
                    r for r in sweep_records
                    if r["direction"] == dir_name
                    and r["detector"] == det_key
                    and r["noise_model"] == nm
                ]
                if not sub:
                    continue

                m_vals = [r["m"] for r in sub]
                precs = [r["precision"] for r in sub]
                seeds_list = [r["seed"] for r in sub]

                fit_res = fit_alpha_exponent(m_vals=m_vals, precisions=precs, seeds=seeds_list)
                alpha_dict = fit_res.to_dict()
                alpha_dict.update({
                    "direction": dir_name,
                    "detector": det_key,
                    "noise_model": nm,
                })
                alpha_results.append(alpha_dict)

    out_data = {
        "directions": directions,
        "m_grid": list(m_grid),
        "seeds": list(seeds),
        "noise_models": list(noise_models),
        "partition_transfer_check": partition_transfer_report,
        "alpha_fits": alpha_results,
        "sweep_results": sweep_records,
    }

    out_p = Path(output_json_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    print(f"\n[+] Experiment G complete! Results saved to {output_json_path}")
    return out_data
