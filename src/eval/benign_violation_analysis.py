"""
Benign Violation Rate Analysis for Provenance Graph Invariants.

Measures per-invariant violation rates on benign-only provenance graphs
to partition the 15 rules into HARD (zero benign violations) and SOFT
(non-zero benign violations) sets.

Two evaluation tiers:
  Tier 1 — Synthetic clean: graphs from generate_synthetic_graph() (perfect).
  Tier 2 — Realistic benign: graphs with real-world audit artifacts
           (pre-audit daemons, timestamp collisions, duplicate records).

The HARD/SOFT partition determines which invariants are safe to use as
zero-false-positive detectors under base-rate dilution attacks.
"""

from __future__ import annotations

import copy
import json
import random
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from src.graph_construction.schema import (
    EdgeType,
    NodeType,
    ProvenanceEdge,
    ProvenanceGraph,
    ProvenanceNode,
)
from src.graph_construction.synthetic import generate_synthetic_graph
from src.detection.rule_engine import (
    Rule,
    RuleEngine,
    RuleResult,
    RuleViolation,
    default_rule_engine,
)


# =====================================================================
# Data structures
# =====================================================================

@dataclass
class ViolationStats:
    """Per-rule violation statistics for a single graph evaluation."""
    rule_name: str
    num_violations: int
    num_edges_flagged: int
    total_edges: int
    violation_rate: float  # num_edges_flagged / total_edges
    violating_edge_ids: list[str] = field(default_factory=list)


@dataclass
class EvaluationRow:
    """Single row in the benign evaluation results table."""
    tier: str  # "synthetic_clean" or "realistic_benign"
    rule_name: str
    graph_size: int  # target_edges used
    seed: int
    total_edges: int
    total_nodes: int
    num_violations: int
    num_edges_flagged: int
    violation_rate: float


# =====================================================================
# Realistic benign graph generator
# =====================================================================

def generate_realistic_benign_graph(
    num_processes: int = 20,
    num_files: int = 30,
    num_network: int = 8,
    target_edges: int | None = None,
    seed: int | None = None,
    pre_audit_daemons: int = 5,
    ts_collision_rate: float = 0.05,
    duplicate_event_rate: float = 0.01,
) -> ProvenanceGraph:
    """
    Generates a benign provenance graph with realistic audit artifacts.

    Unlike generate_synthetic_graph(), this introduces:
      1. Pre-audit daemons: processes with activity but no SPAWN edge.
      2. Timestamp collisions: edges sharing timestamps with neighbors.
      3. Duplicate event records: exact (src, tgt, type, ts) duplicates.

    These are NOT attacks — they are known real-world artifacts of OS
    audit logging (e.g., daemons started before auditd, clock quantization,
    duplicate audit records).
    """
    rng = random.Random(seed)

    # -------------------------------------------------------------------
    # Step 1: Start with a clean synthetic graph
    # -------------------------------------------------------------------
    graph = ProvenanceGraph()
    t = 1_700_000_000.0

    # Root process (init)
    graph.add_node(
        ProvenanceNode("proc_0", NodeType.PROCESS, "init", {"pid": 1})
    )

    # -------------------------------------------------------------------
    # Step 2: Create pre-audit daemon processes (NO spawn edges)
    # These simulate daemons like sshd, crond, etc. that were running
    # before audit logging started.
    # -------------------------------------------------------------------
    daemon_ids = []
    for i in range(1, pre_audit_daemons + 1):
        daemon_id = f"proc_{i}"
        daemon_name = rng.choice([
            "sshd", "crond", "systemd-journal", "dbus-daemon",
            "rsyslogd", "NetworkManager", "polkitd", "udevd",
        ])
        graph.add_node(
            ProvenanceNode(
                daemon_id, NodeType.PROCESS, daemon_name,
                {"pid": i + 1, "pre_audit": True, "parent": "proc_0"},
            )
        )
        daemon_ids.append(daemon_id)
    # NOTE: No SPAWN edges for daemons — this is the key artifact.
    # UnspawnedProcessRule should flag these.

    # -------------------------------------------------------------------
    # Step 3: Create normally-spawned processes
    # -------------------------------------------------------------------
    process_ids = ["proc_0"] + daemon_ids
    spawned_start = pre_audit_daemons + 1
    for i in range(spawned_start, spawned_start + num_processes):
        parent = rng.choice(process_ids)
        pid = f"proc_{i}"
        graph.add_node(
            ProvenanceNode(pid, NodeType.PROCESS, f"process_{i}", {"parent": parent})
        )
        t += rng.uniform(0.01, 2.0)
        graph.add_edge(
            ProvenanceEdge(f"e_spawn_{i}", parent, pid, EdgeType.SPAWN, t)
        )
        process_ids.append(pid)

    # -------------------------------------------------------------------
    # Step 4: Create files and network nodes
    # -------------------------------------------------------------------
    file_ids = []
    for i in range(num_files):
        fid = f"file_{i}"
        graph.add_node(
            ProvenanceNode(fid, NodeType.FILE, f"/var/tmp/file_{i}.dat")
        )
        file_ids.append(fid)

    net_ids = []
    for i in range(num_network):
        nid = f"net_{i}"
        graph.add_node(
            ProvenanceNode(nid, NodeType.NETWORK, f"10.0.0.{i}:443")
        )
        net_ids.append(nid)

    # -------------------------------------------------------------------
    # Step 5: Generate activity edges (with timestamp collisions)
    # -------------------------------------------------------------------
    spawn_count = len(graph.edges)  # edges so far = spawn edges
    if target_edges is not None:
        num_activity_edges = max(1, target_edges - spawn_count)
    else:
        num_activity_edges = (num_files + num_network) * 3

    activity_edges = []
    prev_timestamps = []

    for i in range(num_activity_edges):
        proc = rng.choice(process_ids)
        t += rng.uniform(0.001, 1.0)

        # Timestamp collision: reuse a previous timestamp
        if prev_timestamps and rng.random() < ts_collision_rate:
            t = rng.choice(prev_timestamps)

        if rng.random() < 0.7 and file_ids:
            target = rng.choice(file_ids)
            edge_type = rng.choice([EdgeType.READ, EdgeType.WRITE])
        elif net_ids:
            target = rng.choice(net_ids)
            edge_type = EdgeType.CONNECT
        else:
            continue

        edge = ProvenanceEdge(f"e_activity_{i}", proc, target, edge_type, t)
        graph.add_edge(edge)
        activity_edges.append(edge)
        prev_timestamps.append(t)

    # -------------------------------------------------------------------
    # Step 6: Inject duplicate event records
    # These are genuine duplicates from the audit subsystem, not attacks.
    # -------------------------------------------------------------------
    num_duplicates = max(0, int(len(activity_edges) * duplicate_event_rate))
    for d in range(num_duplicates):
        if not activity_edges:
            break
        original = rng.choice(activity_edges)
        dup_edge = ProvenanceEdge(
            edge_id=f"e_dup_{d}",
            source_id=original.source_id,
            target_id=original.target_id,
            edge_type=original.edge_type,
            timestamp=original.timestamp,
            attributes={"duplicate_of": original.edge_id},
        )
        graph.add_edge(dup_edge)

    # -------------------------------------------------------------------
    # Step 7: Generate daemon activity edges (from pre-audit daemons)
    # These are normal operations by the daemons.
    # -------------------------------------------------------------------
    for daemon_id in daemon_ids:
        num_daemon_ops = rng.randint(2, 8)
        for j in range(num_daemon_ops):
            t += rng.uniform(0.001, 0.5)
            if rng.random() < 0.6 and file_ids:
                target = rng.choice(file_ids)
                edge_type = rng.choice([EdgeType.READ, EdgeType.WRITE])
            elif net_ids:
                target = rng.choice(net_ids)
                edge_type = EdgeType.CONNECT
            else:
                continue
            graph.add_edge(
                ProvenanceEdge(
                    f"e_daemon_{daemon_id}_{j}",
                    daemon_id, target, edge_type, t,
                    attributes={"daemon_activity": True},
                )
            )

    return graph


# =====================================================================
# Measurement functions
# =====================================================================

def measure_violation_rates(
    graph: ProvenanceGraph,
    engine: RuleEngine,
) -> list[ViolationStats]:
    """
    Run all rules in the engine against the graph and compute per-rule
    violation statistics.
    """
    results = engine.run(graph)
    total_edges = len(graph.edges)
    stats = []

    for rr in results:
        flagged_edge_ids = set()
        for v in rr.violations:
            if v.edge_id is not None:
                flagged_edge_ids.add(v.edge_id)

        stats.append(ViolationStats(
            rule_name=rr.rule,
            num_violations=len(rr.violations),
            num_edges_flagged=len(flagged_edge_ids),
            total_edges=total_edges,
            violation_rate=len(flagged_edge_ids) / total_edges if total_edges > 0 else 0.0,
            violating_edge_ids=sorted(flagged_edge_ids),
        ))

    return stats


def run_benign_evaluation(
    num_trials_per_size: int = 5,
    graph_sizes: list[int] = [500, 2000, 10000, 50000],
    seeds: list[int] | None = None,
    tiers: list[str] | None = None,
) -> list[EvaluationRow]:
    """
    Run the full benign evaluation across multiple graph sizes and seeds.

    Returns a flat list of EvaluationRow records.
    """
    if seeds is None:
        seeds = [1, 7, 13, 21, 42, 99, 123, 256, 512, 1024]
    if tiers is None:
        tiers = ["synthetic_clean", "realistic_benign"]

    engine = default_rule_engine()
    rows: list[EvaluationRow] = []

    for tier in tiers:
        for size in graph_sizes:
            for trial_idx in range(min(num_trials_per_size, len(seeds))):
                seed = seeds[trial_idx]

                if tier == "synthetic_clean":
                    graph = generate_synthetic_graph(
                        num_processes=max(5, size // 50),
                        num_files=max(5, size // 30),
                        num_network=max(2, size // 200),
                        target_edges=size,
                        seed=seed,
                    )
                else:  # realistic_benign
                    graph = generate_realistic_benign_graph(
                        num_processes=max(5, size // 50),
                        num_files=max(5, size // 30),
                        num_network=max(2, size // 200),
                        target_edges=size,
                        seed=seed,
                        pre_audit_daemons=5,
                        ts_collision_rate=0.05,
                        duplicate_event_rate=0.01,
                    )

                stats = measure_violation_rates(graph, engine)

                for s in stats:
                    rows.append(EvaluationRow(
                        tier=tier,
                        rule_name=s.rule_name,
                        graph_size=size,
                        seed=seed,
                        total_edges=s.total_edges,
                        total_nodes=len(graph.nodes),
                        num_violations=s.num_violations,
                        num_edges_flagged=s.num_edges_flagged,
                        violation_rate=s.violation_rate,
                    ))

    return rows


def partition_invariants(
    rows: list[EvaluationRow],
    tier_filter: str | None = None,
) -> tuple[list[str], list[str]]:
    """
    Partition invariants into HARD and SOFT based on evaluation results.

    HARD: violation_rate == 0.0 across ALL trials (for the given tier).
    SOFT: violation_rate > 0.0 on ANY trial.

    Returns (hard_rules, soft_rules) sorted alphabetically.
    """
    # Aggregate max violation rate per rule
    max_violation: dict[str, float] = defaultdict(float)

    for row in rows:
        if tier_filter is not None and row.tier != tier_filter:
            continue
        max_violation[row.rule_name] = max(
            max_violation[row.rule_name],
            row.violation_rate,
        )

    hard = sorted(r for r, v in max_violation.items() if v == 0.0)
    soft = sorted(r for r, v in max_violation.items() if v > 0.0)

    return hard, soft


def format_results_table(
    rows: list[EvaluationRow],
    tier_filter: str | None = None,
) -> str:
    """Format results as a markdown table summarizing per-rule violations."""
    # Aggregate per rule
    rule_agg: dict[str, dict] = {}

    for row in rows:
        if tier_filter is not None and row.tier != tier_filter:
            continue
        if row.rule_name not in rule_agg:
            rule_agg[row.rule_name] = {
                "total_trials": 0,
                "trials_with_violations": 0,
                "max_violations": 0,
                "max_rate": 0.0,
                "total_violations": 0,
                "total_edges_checked": 0,
            }
        agg = rule_agg[row.rule_name]
        agg["total_trials"] += 1
        if row.num_violations > 0:
            agg["trials_with_violations"] += 1
        agg["max_violations"] = max(agg["max_violations"], row.num_violations)
        agg["max_rate"] = max(agg["max_rate"], row.violation_rate)
        agg["total_violations"] += row.num_violations
        agg["total_edges_checked"] += row.total_edges

    lines = [
        "| # | Rule | Trials w/ Violations | Max Violations | Max Rate | Avg Rate | Verdict |",
        "|---|------|---------------------|----------------|----------|----------|---------|",
    ]

    for idx, (rule, agg) in enumerate(sorted(rule_agg.items()), 1):
        avg_rate = (
            agg["total_violations"] / agg["total_edges_checked"]
            if agg["total_edges_checked"] > 0 else 0.0
        )
        verdict = "**HARD** ✅" if agg["max_rate"] == 0.0 else "**SOFT** ⚠️"
        lines.append(
            f"| {idx} | `{rule}` | {agg['trials_with_violations']}/{agg['total_trials']} "
            f"| {agg['max_violations']} | {agg['max_rate']:.6f} | {avg_rate:.6f} | {verdict} |"
        )

    return "\n".join(lines)


def save_results_json(
    rows: list[EvaluationRow],
    output_path: str | Path,
) -> None:
    """Save evaluation results to JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = []
    for row in rows:
        data.append({
            "tier": row.tier,
            "rule_name": row.rule_name,
            "graph_size": row.graph_size,
            "seed": row.seed,
            "total_edges": row.total_edges,
            "total_nodes": row.total_nodes,
            "num_violations": row.num_violations,
            "num_edges_flagged": row.num_edges_flagged,
            "violation_rate": row.violation_rate,
        })

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
