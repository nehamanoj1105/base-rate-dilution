"""
Constrained Adversary Search Module for Provenance Graph Tamper Detection (Phase 10 — Broadened V2).

Executes bounded multi-trial greedy/beam search to construct feasible attack subgraphs that
realize cyber attack objectives while strictly satisfying all 11 HARD invariants.

Scientific Guarantees:
  - Adversary has full knowledge of the 11 HARD invariant rule definitions.
  - Adversary has NO knowledge of GNN parameters, test labels, or evaluator code.
  - Output is a formal certificate detailing:
      (a) Achieved under feasibility constraint with edge cost overhead ratio range [min, max], OR
      (b) Unachievable certificate identifying the specific blocking HARD rule(s).
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from models.feasibility_gate import compute_hard_mask
from src.attacks.attack_primitives import AttackObjective, PatternStep
from src.detection.rule_engine import default_rule_engine
from src.graph_construction.schema import (
    EdgeType,
    NodeType,
    ProvenanceEdge,
    ProvenanceGraph,
    ProvenanceNode,
)


@dataclass
class SearchResult:
    """Output certificate of constrained adversary search for a single attack objective."""
    objective_name: str
    description: str
    achieved: bool
    trials_achieved: str
    total_trials: int
    infeasible_edge_cost: int
    feasible_edge_cost_min: int
    feasible_edge_cost_max: int
    feasible_edge_cost_mean: float
    effort_ratio_min: float
    effort_ratio_max: float
    effort_ratio_mean: float
    inserted_edge_ids: List[str]
    blocking_hard_rules: List[str]
    gated_detector_flagged: bool
    gated_detector_score_max: float
    certificate_verdict: str


class ConstrainedAttackerSearch:
    """
    Greedy/beam search for constructing feasibility-bounded attack sequences across multi-trial restarts.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.engine = default_rule_engine()

    def attempt_objective(
        self,
        base_graph: ProvenanceGraph,
        objective: AttackObjective,
        gated_detector: Any | None = None,
        n_trials: int = 10,
    ) -> SearchResult:
        """
        Attempts to realize attack objective on base_graph over n_trials random restarts.

        Returns:
            SearchResult certificate detailing achievement status, edge cost ranges, and blocking rules.
        """
        trial_achieved: List[bool] = []
        trial_edge_costs: List[int] = []
        trial_blocking_rules: Set[str] = set()
        trial_inserted_eids: List[List[str]] = []
        trial_max_gated_scores: List[float] = []

        # Find existing process nodes in base_graph
        valid_procs = [
            n.node_id for n in base_graph.nodes.values()
            if n.node_type == NodeType.PROCESS
        ]

        for trial_idx in range(n_trials):
            graph = copy.deepcopy(base_graph)
            max_ts = max((e.timestamp for e in graph.edges), default=1_700_000_000.0)
            curr_ts = max_ts + 1.0 + float(trial_idx * 2.0)

            inserted_edges: List[ProvenanceEdge] = []
            blocking_rules_trial: Set[str] = set()

            # Select target process for this trial
            if valid_procs:
                attacker_proc = self.rng.choice(valid_procs)
            else:
                attacker_proc = "proc_0"

            proc_spawn_ts = min(
                (e.timestamp for e in graph.edges if e.target_id == attacker_proc and e.edge_type == EdgeType.SPAWN),
                default=1_700_000_000.0,
            )

            trial_success = True

            for step in objective.steps:
                curr_ts += self.rng.uniform(0.1, 1.0)

                # Determine source node ID
                if step.force_unspawned_source:
                    source_proc_id = f"proc_unspawned_trial_{trial_idx}_{len(inserted_edges)}"
                    if source_proc_id not in graph.nodes:
                        graph.add_node(ProvenanceNode(source_proc_id, NodeType.PROCESS, f"/tmp/orphan_proc_{trial_idx}"))
                else:
                    source_proc_id = attacker_proc

                # Determine target node ID
                if step.force_self_loop:
                    target_node_id = source_proc_id
                else:
                    target_node_id = f"node_obj_{step.target_label.replace('/', '_').replace(':', '_')}_{trial_idx}"
                    if target_node_id not in graph.nodes:
                        graph.add_node(ProvenanceNode(target_node_id, step.target_type, step.target_label))

                # Determine timestamp
                if step.timestamp_offset != 0.0:
                    candidate_ts = proc_spawn_ts + step.timestamp_offset
                else:
                    candidate_ts = curr_ts

                candidate_edge_id = f"e_adv_{objective.name}_{trial_idx}_{len(inserted_edges)}"
                candidate_edge = ProvenanceEdge(
                    edge_id=candidate_edge_id,
                    source_id=source_proc_id,
                    target_id=target_node_id,
                    edge_type=step.edge_type,
                    timestamp=candidate_ts,
                )

                # Test candidate edge against HARD rules
                temp_graph = copy.deepcopy(graph)
                temp_graph.add_edge(candidate_edge)

                mask_dict = compute_hard_mask(temp_graph)
                has_violation = (mask_dict.get(candidate_edge_id, 0.0) == 1.0)

                if not has_violation:
                    # Check if unspawned process rule was triggered on node level
                    rule_results = self.engine.run(temp_graph)
                    for rr in rule_results:
                        for v in rr.violations:
                            if v.node_id == source_proc_id or v.edge_id == candidate_edge_id:
                                has_violation = True
                                blocking_rules_trial.add(rr.rule)

                if has_violation:
                    # Log blocking rules
                    rule_results = self.engine.run(temp_graph)
                    for rr in rule_results:
                        for v in rr.violations:
                            if v.edge_id == candidate_edge_id or v.node_id == source_proc_id:
                                blocking_rules_trial.add(rr.rule)

                    # Attempt candidate remediation (e.g. inserting SPAWN for orphan process)
                    remediated, repair_edges = self._attempt_remediation(graph, candidate_edge, proc_spawn_ts)
                    if remediated:
                        for r_edge in repair_edges:
                            graph.add_edge(r_edge)
                            inserted_edges.append(r_edge)
                        graph.add_edge(candidate_edge)
                        inserted_edges.append(candidate_edge)
                    else:
                        trial_success = False
                        break
                else:
                    graph.add_edge(candidate_edge)
                    inserted_edges.append(candidate_edge)

            # Final whole-graph verification
            if trial_success:
                final_mask = compute_hard_mask(graph)
                for e in inserted_edges:
                    if final_mask.get(e.edge_id, 0.0) == 1.0:
                        trial_success = False
                        rule_results = self.engine.run(graph)
                        for rr in rule_results:
                            for v in rr.violations:
                                if v.edge_id == e.edge_id:
                                    blocking_rules_trial.add(rr.rule)

            trial_achieved.append(trial_success)
            if trial_success:
                trial_edge_costs.append(len(inserted_edges))
                trial_inserted_eids.append([e.edge_id for e in inserted_edges])

                if gated_detector is not None:
                    scores = gated_detector.score_edges(graph)
                    adv_scores = [scores.get(e.edge_id, 0.0) for e in inserted_edges]
                    trial_max_gated_scores.append(max(adv_scores) if adv_scores else 0.0)
                else:
                    trial_max_gated_scores.append(0.0)
            else:
                trial_blocking_rules.update(blocking_rules_trial)

        achieved_count = sum(1 for a in trial_achieved if a)
        achieved_bool = achieved_count > 0

        infeasible_cost = objective.infeasible_edge_count
        if achieved_bool and trial_edge_costs:
            cost_min = int(np.min(trial_edge_costs))
            cost_max = int(np.max(trial_edge_costs))
            cost_mean = float(np.mean(trial_edge_costs))

            ratio_min = cost_min / infeasible_cost
            ratio_max = cost_max / infeasible_cost
            ratio_mean = cost_mean / infeasible_cost
            sample_inserted = trial_inserted_eids[0]
            max_score = float(max(trial_max_gated_scores)) if trial_max_gated_scores else 0.0
        else:
            cost_min, cost_max, cost_mean = 0, 0, 0.0
            ratio_min, ratio_max, ratio_mean = 0.0, 0.0, 0.0
            sample_inserted = []
            max_score = 0.0

        thresh = getattr(gated_detector, "operating_threshold", 0.05) if gated_detector else 0.05
        gated_flagged = max_score >= thresh
        sorted_blocking = sorted(list(trial_blocking_rules))

        if achieved_bool:
            verdict = f"Feasible realization achieved with {ratio_mean:.1f}x edge overhead cost (range [{ratio_min:.1f}x, {ratio_max:.1f}x])"
        else:
            verdict = f"UNACHIEVABLE without violating rule(s): {', '.join(sorted_blocking)}"

        return SearchResult(
            objective_name=objective.name,
            description=objective.description,
            achieved=achieved_bool,
            trials_achieved=f"{achieved_count}/{n_trials}",
            total_trials=n_trials,
            infeasible_edge_cost=infeasible_cost,
            feasible_edge_cost_min=cost_min,
            feasible_edge_cost_max=cost_max,
            feasible_edge_cost_mean=round(cost_mean, 2),
            effort_ratio_min=round(ratio_min, 2),
            effort_ratio_max=round(ratio_max, 2),
            effort_ratio_mean=round(ratio_mean, 2),
            inserted_edge_ids=sample_inserted,
            blocking_hard_rules=sorted_blocking if not achieved_bool else [],
            gated_detector_flagged=gated_flagged,
            gated_detector_score_max=round(max_score, 6),
            certificate_verdict=verdict,
        )

    def _attempt_remediation(
        self,
        graph: ProvenanceGraph,
        candidate_edge: ProvenanceEdge,
        proc_spawn_ts: float,
    ) -> Tuple[bool, List[ProvenanceEdge]]:
        """
        Attempts structural repairs (e.g. inserting SPAWN for orphan process) to make candidate_edge feasible.
        """
        repair_edges: List[ProvenanceEdge] = []
        proc_id = candidate_edge.source_id

        # Check if process has a SPAWN edge or is root
        is_root = proc_id in {"init", "proc_0", "1"}
        has_spawn = any(e.target_id == proc_id and e.edge_type == EdgeType.SPAWN for e in graph.edges)

        if not has_spawn and not is_root:
            # Cannot repair if timestamp is backdated before graph min timestamp
            t_spawn = candidate_edge.timestamp - 0.5
            if t_spawn < 0:
                return False, []

            spawn_edge = ProvenanceEdge(
                edge_id=f"e_repair_spawn_{proc_id}",
                source_id="proc_0",
                target_id=proc_id,
                edge_type=EdgeType.SPAWN,
                timestamp=t_spawn,
            )
            repair_edges.append(spawn_edge)

        # Test candidate graph with repairs
        test_graph = copy.deepcopy(graph)
        for r_e in repair_edges:
            test_graph.add_edge(r_e)
        test_graph.add_edge(candidate_edge)

        mask_dict = compute_hard_mask(test_graph)
        all_passed = all(mask_dict.get(e.edge_id, 0.0) == 0.0 for e in repair_edges + [candidate_edge])

        if all_passed:
            # Check for node-level unspawned process violations
            rule_res = self.engine.run(test_graph)
            for rr in rule_res:
                for v in rr.violations:
                    if v.node_id == proc_id or v.edge_id == candidate_edge.edge_id:
                        all_passed = False
                        break

        return all_passed, repair_edges
