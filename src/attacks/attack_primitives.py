"""
Attack Primitives & Pattern Definitions for Adaptive Adversary Search (Phase 10 — Broadened V2).

Defines 7 cyber attack objectives as required provenance graph subgraph patterns:
  1. Credential Access: Process reads a credential file (/etc/shadow).
  2. Lateral Movement: Process spawns a remote management child process which opens a network socket.
  3. Exfiltration: Process reads a sensitive data file followed by writing to a network socket.
  4. Log Tampering: Process writes to or unlinks/deletes an active audit log file (/var/log/audit.log).
  5. Unspawned Stealth Exec: Process without an explicit spawn parent attempts to perform file write.
  6. Backdated Timestamp Tampering: Process attempts to backdate an attack event prior to its spawn time.
  7. Self-Loop Execution: Process attempts to issue a self-referential execution event to itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from src.graph_construction.schema import EdgeType, NodeType, ProvenanceEdge, ProvenanceNode, ProvenanceGraph


@dataclass
class PatternStep:
    """Specification of a single required edge in an attack pattern."""
    source_type: NodeType
    target_type: NodeType
    edge_type: EdgeType
    target_label: str
    description: str
    timestamp_offset: float = 0.0  # Relative offset from current timestamp (negative for backdating)
    force_unspawned_source: bool = False  # If True, source process has no SPAWN parent
    force_self_loop: bool = False  # If True, target_id == source_id


@dataclass
class AttackObjective:
    """Cyber attack objective expressed as a pattern over edge types and node labels."""
    name: str
    description: str
    steps: List[PatternStep]
    infeasible_edge_count: int  # Minimal naive edge count required to commit the attack directly
    plausibly_violates_hard_rule: bool = False
    naive_expected_blocking_rules: List[str] = field(default_factory=list)


def get_default_attack_objectives() -> List[AttackObjective]:
    """Returns standard set of 7 broadened attack objectives for evaluation."""
    return [
        AttackObjective(
            name="credential_access",
            description="Process reads sensitive credential file (/etc/shadow)",
            steps=[
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.FILE,
                    edge_type=EdgeType.READ,
                    target_label="/etc/shadow",
                    description="Read credential file /etc/shadow",
                )
            ],
            infeasible_edge_count=1,
            plausibly_violates_hard_rule=False,
            naive_expected_blocking_rules=[],
        ),
        AttackObjective(
            name="lateral_movement",
            description="Process spawns remote execution daemon which opens remote connection",
            steps=[
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.PROCESS,
                    edge_type=EdgeType.SPAWN,
                    target_label="sshd_child",
                    description="Spawn child process sshd_child",
                ),
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.NETWORK,
                    edge_type=EdgeType.CONNECT,
                    target_label="192.168.1.100:22",
                    description="Open remote socket to internal target",
                ),
            ],
            infeasible_edge_count=2,
            plausibly_violates_hard_rule=False,
            naive_expected_blocking_rules=[],
        ),
        AttackObjective(
            name="exfiltration",
            description="Process reads sensitive data file and writes data to external socket",
            steps=[
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.FILE,
                    edge_type=EdgeType.READ,
                    target_label="/data/customer_db.csv",
                    description="Read customer DB data",
                ),
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.NETWORK,
                    edge_type=EdgeType.CONNECT,
                    target_label="203.0.113.50:443",
                    description="Exfiltrate payload over HTTPS socket",
                ),
            ],
            infeasible_edge_count=2,
            plausibly_violates_hard_rule=False,
            naive_expected_blocking_rules=[],
        ),
        AttackObjective(
            name="log_tampering",
            description="Process modifies or unlinks system audit logging file (/var/log/audit.log)",
            steps=[
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.FILE,
                    edge_type=EdgeType.DELETE,
                    target_label="/var/log/audit.log",
                    description="Delete or unlink audit log file",
                )
            ],
            infeasible_edge_count=1,
            plausibly_violates_hard_rule=False,
            naive_expected_blocking_rules=[],
        ),
        AttackObjective(
            name="unspawned_stealth_exec",
            description="Orphan process with no SPAWN parent attempts resource write",
            steps=[
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.FILE,
                    edge_type=EdgeType.WRITE,
                    target_label="/var/log/system.log",
                    description="Orphan process writes to log file",
                    force_unspawned_source=True,
                )
            ],
            infeasible_edge_count=1,
            plausibly_violates_hard_rule=True,
            naive_expected_blocking_rules=["UnspawnedProcessRule"],
        ),
        AttackObjective(
            name="backdated_timestamp_tampering",
            description="Process attempts to backdate attack event prior to process spawn time",
            steps=[
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.FILE,
                    edge_type=EdgeType.READ,
                    target_label="/etc/passwd",
                    description="Backdated read event predating process spawn time",
                    timestamp_offset=-500.0,
                )
            ],
            infeasible_edge_count=1,
            plausibly_violates_hard_rule=True,
            naive_expected_blocking_rules=["ProcessActivityTemporalRule"],
        ),
        AttackObjective(
            name="self_loop_execution",
            description="Process issues self-referential execution event (source == target)",
            steps=[
                PatternStep(
                    source_type=NodeType.PROCESS,
                    target_type=NodeType.PROCESS,
                    edge_type=EdgeType.EXECUTE,
                    target_label="self",
                    description="Self-loop process execution",
                    force_self_loop=True,
                )
            ],
            infeasible_edge_count=1,
            plausibly_violates_hard_rule=True,
            naive_expected_blocking_rules=["ExecutionConsistencyRule", "SelfLoopRule"],
        ),
    ]
