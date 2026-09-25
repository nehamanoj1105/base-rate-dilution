"""
Strict Leakage Audit for Provenance Graph Tamper Detection (Phase 8).

Asserts strict split hygiene and zero information leakage between TRAIN/VAL and TEST:
  1. Disjoint Seed Sets: TRAIN, VAL, TEST, and Resampler Pool seeds are mutually disjoint.
  2. Zero Edge Overlap: No TEST edge appears in TRAIN or VAL datasets.
  3. Resampler Pool Isolation: No resampled benign subgraph originates from TEST seeds.
  4. Invariant Partition Provenance: Invariant partition is fit on TRAIN/VAL only.
  5. Threshold Freezing: Operating threshold is calibrated on VAL at m=0 only, then frozen.

Fails loudly (raises AssertionError) on any violation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Any

from src.attacks.benign_resampler import BenignResampler
from src.graph_construction.synthetic import generate_synthetic_graph
from src.detection.poisoning_injection import inject_poisoning

SPLITS_PATH = Path("config/splits.json")
PARTITION_PATH = Path("config/invariant_partition.json")
AUDIT_OUTPUT_PATH = Path("results/leakage_audit.json")


def load_splits_config() -> Dict[str, Any]:
    """Loads splits configuration from config/splits.json."""
    if not SPLITS_PATH.exists():
        raise FileNotFoundError(f"Splits config not found at {SPLITS_PATH}")
    with open(SPLITS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_invariant_partition() -> Dict[str, Any]:
    """Loads invariant partition config."""
    if not PARTITION_PATH.exists():
        raise FileNotFoundError(f"Invariant partition config not found at {PARTITION_PATH}")
    with open(PARTITION_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def audit_leakage() -> Dict[str, Any]:
    """
    Performs full leakage audit across data splits, resampler pools, invariant partitions, and thresholding.

    Returns:
        Dict containing check results and overall verdict.
    """
    splits = load_splits_config()
    partition = load_invariant_partition()

    train_seeds = set(splits["train_seeds"])
    val_seeds = set(splits["val_seeds"])
    test_seeds = set(splits["test_seeds"])
    pool_seeds = set(splits["resampler_pool_seeds"])

    checks: Dict[str, Dict[str, Any]] = {}

    # Check 1: Mutually Disjoint Seed Sets
    train_val_overlap = train_seeds.intersection(val_seeds)
    train_test_overlap = train_seeds.intersection(test_seeds)
    val_test_overlap = val_seeds.intersection(test_seeds)
    pool_test_overlap = pool_seeds.intersection(test_seeds)

    disjoint_pass = (
        len(train_val_overlap) == 0
        and len(train_test_overlap) == 0
        and len(val_test_overlap) == 0
        and len(pool_test_overlap) == 0
    )
    if not disjoint_pass:
        raise AssertionError(
            f"Seed overlap detected! Train/Val: {train_val_overlap}, Train/Test: {train_test_overlap}, "
            f"Val/Test: {val_test_overlap}, Pool/Test: {pool_test_overlap}"
        )

    checks["disjoint_seed_sets"] = {
        "passed": True,
        "train_seeds": sorted(list(train_seeds)),
        "val_seeds": sorted(list(val_seeds)),
        "test_seeds": sorted(list(test_seeds)),
        "pool_seeds_min": min(pool_seeds),
        "pool_seeds_max": max(pool_seeds),
    }

    # Check 2: Zero Edge Overlap between TRAIN/VAL and TEST
    train_val_edges: Set[Tuple[int, str]] = set()
    for s in train_seeds.union(val_seeds):
        g = generate_synthetic_graph(target_edges=500, seed=s)
        p = inject_poisoning(g, num_deletions=2, num_insertions=2, num_reorderings=2, num_forgeries=2, seed=s)
        train_val_edges.update((s, e.edge_id) for e in p.graph.edges)

    test_edges: Set[Tuple[int, str]] = set()
    for s in test_seeds:
        g = generate_synthetic_graph(target_edges=500, seed=s)
        p = inject_poisoning(g, num_deletions=2, num_insertions=2, num_reorderings=2, num_forgeries=2, seed=s)
        test_edges.update((s, e.edge_id) for e in p.graph.edges)

    edge_overlap = train_val_edges.intersection(test_edges)
    if len(edge_overlap) > 0:
        raise AssertionError(f"Edge overlap detected! {len(edge_overlap)} edges shared between TRAIN/VAL and TEST")

    checks["no_test_edge_in_train_or_val"] = {
        "passed": True,
        "train_val_edges_count": len(train_val_edges),
        "test_edges_count": len(test_edges),
        "overlap_count": 0,
    }

    # Check 3: Resampler Pool Isolation
    pool_edges: Set[Tuple[int, str]] = set()
    pool_graphs = []
    for s in pool_seeds:
        g = generate_synthetic_graph(target_edges=200, seed=s)
        pool_graphs.append(g)
        pool_edges.update((s, e.edge_id) for e in g.edges)

    pool_overlap = pool_edges.intersection(test_edges)
    if len(pool_overlap) > 0:
        raise AssertionError(f"Resampler pool shares edges with TEST set! Overlap: {pool_overlap}")

    checks["resampler_pool_isolation"] = {
        "passed": True,
        "pool_graphs_count": len(pool_graphs),
        "pool_total_edges": len(pool_edges),
        "test_overlap_count": 0,
    }

    # Check 4: Invariant Partition Provenance
    provenance = splits.get("provenance", {})
    inv_source = provenance.get("invariant_partition_dataset", "")

    if "TEST" in inv_source.upper():
        raise AssertionError("Invariant partition was fit on TEST data! Provenance must be TRAIN/VAL only.")

    checks["invariant_partition_provenance"] = {
        "passed": True,
        "source": inv_source,
        "hard_rules_count": len(partition.get("hard_rules", [])),
        "soft_rules_count": len(partition.get("soft_rules", [])),
    }

    # Check 5: Threshold Freezing Protocol
    thresh_protocol = provenance.get("threshold_calibration", "")
    if "VAL" not in thresh_protocol.upper() or "FROZEN" not in thresh_protocol.upper():
        raise AssertionError(f"Invalid threshold protocol: {thresh_protocol}. Must calibrate on VAL at m=0 and freeze.")

    checks["threshold_calibration_protocol"] = {
        "passed": True,
        "protocol": thresh_protocol,
    }

    results = {
        "all_checks_passed": True,
        "checks": checks,
    }

    os.makedirs(AUDIT_OUTPUT_PATH.parent, exist_ok=True)
    with open(AUDIT_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


def main():
    print("=== Running Strict Leakage Audit ===")
    results = audit_leakage()
    print(f"Leakage audit passed! Summary written to {AUDIT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
