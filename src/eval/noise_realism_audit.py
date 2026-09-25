"""
Noise Realism Audit: measures per-rule violation rates on synthetic mimicry
noise edges and compares against real-benign baseline rates from Phase 2.

Establishes whether the existing mimicry generator's output is OS-plausible
or whether the precision collapse it causes is a generator artifact.
"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.detection.mimicry_attack import inject_mimicry_attack
from src.detection.poisoning_injection import inject_poisoning
from src.detection.rule_engine import (
    Rule,
    RuleEngine,
    RuleResult,
    default_rule_engine,
)
from src.graph_construction.schema import (
    EdgeType,
    NodeType,
    ProvenanceEdge,
    ProvenanceGraph,
    ProvenanceNode,
)
from src.graph_construction.synthetic import generate_synthetic_graph


# =====================================================================
# Data structures
# =====================================================================

@dataclass
class NoiseAuditRow:
    """One row: rule × noise source × graph config."""
    source: str          # "synthetic_noise" | "resampled_noise" | "real_benign"
    strength: str        # "light" | "medium" | "heavy" | "n/a"
    rule_name: str
    total_noise_edges: int
    num_violations: int
    num_edges_flagged: int
    violation_rate: float


# =====================================================================
# Core functions
# =====================================================================

def extract_noise_subgraph(
    full_graph: ProvenanceGraph,
    noise_edge_ids: set[str],
) -> ProvenanceGraph:
    """
    Extract only the noise edges from a graph, along with
    ALL nodes they reference, to create an isolated subgraph
    that can be evaluated by the rule engine.

    We include ALL nodes from the full graph so that type-consistency
    rules can look up node types. This is conservative: it means
    MissingNodeRule will NOT fire on noise edges (since nodes exist),
    but type-consistency rules WILL fire if a noise edge connects
    wrong node types.
    """
    subgraph = ProvenanceGraph()

    # Collect node IDs referenced by noise edges
    referenced_nodes: set[str] = set()
    noise_edges: list[ProvenanceEdge] = []
    for edge in full_graph.edges:
        if edge.edge_id in noise_edge_ids:
            noise_edges.append(edge)
            referenced_nodes.add(edge.source_id)
            referenced_nodes.add(edge.target_id)

    # Add referenced nodes
    for nid in referenced_nodes:
        if nid in full_graph.nodes:
            subgraph.add_node(full_graph.nodes[nid])

    # Add noise edges (bypass add_edge validation since we already
    # ensured nodes exist)
    for edge in noise_edges:
        if edge.source_id in subgraph.nodes and edge.target_id in subgraph.nodes:
            subgraph.edges.append(edge)

    return subgraph


def measure_noise_violations(
    full_graph: ProvenanceGraph,
    noise_edge_ids: set[str],
    engine: RuleEngine | None = None,
) -> list[NoiseAuditRow]:
    """
    Run all rules on the noise subgraph and report per-rule violations.
    """
    if engine is None:
        engine = default_rule_engine()

    subgraph = extract_noise_subgraph(full_graph, noise_edge_ids)
    results = engine.run(subgraph)
    total_noise = len(subgraph.edges)

    rows: list[NoiseAuditRow] = []
    for rr in results:
        flagged = set()
        for v in rr.violations:
            if v.edge_id is not None:
                flagged.add(v.edge_id)

        rows.append(NoiseAuditRow(
            source="synthetic_noise",
            strength="n/a",
            rule_name=rr.rule,
            total_noise_edges=total_noise,
            num_violations=len(rr.violations),
            num_edges_flagged=len(flagged),
            violation_rate=len(flagged) / total_noise if total_noise > 0 else 0.0,
        ))

    return rows


def audit_synthetic_noise(
    graph_size: int = 2000,
    seed: int = 42,
    strengths: list[str] | None = None,
    intensity: int = 5,
) -> list[NoiseAuditRow]:
    """
    Generate mimicry noise at each strength level and measure its
    per-rule violation rate.
    """
    if strengths is None:
        strengths = ["light", "medium", "heavy"]

    graph = generate_synthetic_graph(
        num_processes=max(5, graph_size // 50),
        num_files=max(5, graph_size // 30),
        num_network=max(2, graph_size // 200),
        target_edges=graph_size,
        seed=seed,
    )

    base_poisoning = inject_poisoning(
        graph,
        num_deletions=intensity,
        num_insertions=intensity,
        num_reorderings=intensity,
        num_forgeries=intensity,
        seed=seed,
    )

    engine = default_rule_engine()
    all_rows: list[NoiseAuditRow] = []

    for strength in strengths:
        mimicry_res = inject_mimicry_attack(
            graph,
            base_poisoning=base_poisoning,
            strength=strength,
            intensity=intensity,
            seed=seed,
            noise_model="synthetic",
        )

        noise_ids = set(mimicry_res.camouflaged_edge_ids)
        rows = measure_noise_violations(mimicry_res.graph, noise_ids, engine)

        # Update source and strength
        for r in rows:
            r.source = "synthetic_noise"
            r.strength = strength

        all_rows.extend(rows)

    return all_rows


def audit_resampled_noise(
    graph_size: int = 2000,
    seed: int = 42,
    m_values: list[int] | None = None,
) -> list[NoiseAuditRow]:
    """
    Generate resampled benign noise and measure its per-rule violation rate.
    """
    # Import here to avoid circular imports at module load
    from src.attacks.benign_resampler import BenignResampler

    if m_values is None:
        m_values = [100, 500, 1000]

    graph = generate_synthetic_graph(
        num_processes=max(5, graph_size // 50),
        num_files=max(5, graph_size // 30),
        num_network=max(2, graph_size // 200),
        target_edges=graph_size,
        seed=seed,
    )

    pool = BenignResampler.create_default_pool(num_graphs=10, edges_per_graph=500)
    resampler = BenignResampler(pool, seed=seed)
    engine = default_rule_engine()

    all_rows: list[NoiseAuditRow] = []

    for m in m_values:
        injected_graph, injected_ids = resampler.inject(graph, m=m, seed=seed)

        if not injected_ids:
            continue

        rows = measure_noise_violations(injected_graph, injected_ids, engine)

        for r in rows:
            r.source = "resampled_noise"
            r.strength = f"m={m}"

        all_rows.extend(rows)

    return all_rows


def get_benign_baseline_rates() -> dict[str, float]:
    """
    Return the real-benign violation rates from Phase 2.

    These are the max violation rates measured on realistic benign graphs
    across all trials. We compute them fresh using a small evaluation.
    """
    from src.eval.benign_violation_analysis import (
        run_benign_evaluation,
    )

    rows = run_benign_evaluation(
        num_trials_per_size=3,
        graph_sizes=[2000],
        tiers=["realistic_benign"],
    )

    # Aggregate max rate per rule
    max_rates: dict[str, float] = defaultdict(float)
    for row in rows:
        max_rates[row.rule_name] = max(max_rates[row.rule_name], row.violation_rate)

    return dict(max_rates)


def build_comparison_table(
    benign_rates: dict[str, float],
    synthetic_rows: list[NoiseAuditRow],
    resampled_rows: list[NoiseAuditRow] | None = None,
) -> list[dict]:
    """
    Build the three-column comparison table:
    rule | real benign rate | synthetic noise rate | resampled noise rate
    """
    # Aggregate max rate per rule for synthetic noise
    synth_max: dict[str, float] = defaultdict(float)
    for r in synthetic_rows:
        synth_max[r.rule_name] = max(synth_max[r.rule_name], r.violation_rate)

    # Aggregate max rate per rule for resampled noise
    resamp_max: dict[str, float] = defaultdict(float)
    if resampled_rows:
        for r in resampled_rows:
            resamp_max[r.rule_name] = max(resamp_max[r.rule_name], r.violation_rate)

    all_rules = sorted(set(benign_rates.keys()) | set(synth_max.keys()) | set(resamp_max.keys()))

    table = []
    for rule in all_rules:
        benign = benign_rates.get(rule, 0.0)
        synth = synth_max.get(rule, 0.0)
        resamp = resamp_max.get(rule, 0.0) if resampled_rows else None

        row = {
            "rule": rule,
            "benign_rate": benign,
            "synthetic_noise_rate": synth,
            "gap_synthetic": synth - benign,
        }
        if resamp is not None:
            row["resampled_noise_rate"] = resamp
            row["gap_resampled"] = resamp - benign

        table.append(row)

    return table


def format_comparison_table_md(table: list[dict]) -> str:
    """Format comparison table as markdown."""
    has_resampled = "resampled_noise_rate" in table[0] if table else False

    if has_resampled:
        header = "| # | Rule | Real Benign | Synthetic Noise | Gap (Synth) | Resampled Noise | Gap (Resamp) |"
        sep = "|---|------|-------------|-----------------|-------------|-----------------|--------------|"
    else:
        header = "| # | Rule | Real Benign | Synthetic Noise | Gap (Synth) |"
        sep = "|---|------|-------------|-----------------|-------------|"

    lines = [header, sep]

    for idx, row in enumerate(table, 1):
        gap_s = row["gap_synthetic"]
        gap_emoji = "✅" if abs(gap_s) < 0.001 else "⚠️" if gap_s < 0.05 else "🔴"

        line = (
            f"| {idx} | `{row['rule']}` "
            f"| {row['benign_rate']:.6f} "
            f"| {row['synthetic_noise_rate']:.6f} "
            f"| {gap_s:+.6f} {gap_emoji} "
        )

        if has_resampled:
            gap_r = row.get("gap_resampled", 0.0)
            gap_r_emoji = "✅" if abs(gap_r) < 0.001 else "⚠️" if abs(gap_r) < 0.05 else "🔴"
            line += f"| {row.get('resampled_noise_rate', 0.0):.6f} | {gap_r:+.6f} {gap_r_emoji} |"
        else:
            line += "|"

        lines.append(line)

    return "\n".join(lines)


def save_audit_json(
    table: list[dict],
    synthetic_rows: list[NoiseAuditRow],
    resampled_rows: list[NoiseAuditRow] | None,
    output_path: str | Path,
) -> None:
    """Save full audit data to JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "comparison_table": table,
        "synthetic_noise_detail": [
            {
                "source": r.source,
                "strength": r.strength,
                "rule_name": r.rule_name,
                "total_noise_edges": r.total_noise_edges,
                "num_violations": r.num_violations,
                "num_edges_flagged": r.num_edges_flagged,
                "violation_rate": r.violation_rate,
            }
            for r in synthetic_rows
        ],
    }

    if resampled_rows:
        data["resampled_noise_detail"] = [
            {
                "source": r.source,
                "strength": r.strength,
                "rule_name": r.rule_name,
                "total_noise_edges": r.total_noise_edges,
                "num_violations": r.num_violations,
                "num_edges_flagged": r.num_edges_flagged,
                "violation_rate": r.violation_rate,
            }
            for r in resampled_rows
        ]

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
