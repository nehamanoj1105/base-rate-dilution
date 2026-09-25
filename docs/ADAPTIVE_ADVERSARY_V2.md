# Adaptive Adversary & Capability Certificate (Phase 10 — Broadened V2 Evaluation)

> [!NOTE]
> **Revision Note (Issue C Reconciliation)**: Corrected executive summary text and Section 6 to match raw search log trial count of 5/50 (10.0% achievement rate) for `backdated_timestamp_tampering`, resolving the table-vs-summary contradiction. Backdating succeeds in ~10% of attempts specifically when targeting root processes lacking parent spawn edges, while being strictly blocked on spawned child processes by `ProcessActivityTemporalRule`.

## Executive Summary & Scientific Findings

This evaluation establishes **Experiment H**: the formal capability boundary imposed on an adaptive adversary possessing full structural knowledge of the 11 HARD invariant rules.

> [!IMPORTANT]
> **Key Findings & Honest Limitation Assessment**:
> 1. **Per-Objective HARD Rule Applicability**: Objectives 1–4 (`credential_access`, `lateral_movement`, `exfiltration`, `log_tampering`) avoid all 11 HARD rules **by construction** because executing operations from valid active processes at monotonic current timestamps is inherently invariant-compliant. The search did not find a 'clever bypass'; these objectives never required violating a HARD rule.
> 2. **Structural Enforcement on Invariant-Violating Objectives**: For objectives that inherently attempt to violate hard invariants in naive form:
>    - `unspawned_stealth_exec`: Attacker is forced to insert a valid process spawn tree, imposing a **2.0x edge overhead cost**.
>    - `backdated_timestamp_tampering`: **PARTIALLY ACHIEVABLE (5/50 trials, 10.0%)** — achievable in approximately 10% of attempts when targeting root processes lacking parent spawn edges, but strictly blocked on spawned child processes by `ProcessActivityTemporalRule`.
>    - `self_loop_execution`: **UNACHIEVABLE (0/50 trials)** — strictly blocked by `SelfLoopRule` and `ExecutionConsistencyRule`.
> 3. **Zero Detection on Feasible Attacks**: For all achieved attack sequences (Objectives 1–6), the feasibility-gated detector assigns score $s(e) = 0.0000$ (0% flagged). Gated detection cannot detect attacks that satisfy all HARD invariants.

---

## Broadened Per-Objective Capability Certificate Table

| Objective Name | Inherent Rule Risk? | Achieved? | Trials Achieved | Infeasible Edge Cost | Feasible Edge Cost (Min/Max/Mean) | Effort Overhead (Min/Max/Mean) | Blocking HARD Rule(s) | Gated Score Max | Formal Certificate Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :--- |
| `credential_access` | NO | **YES** ✅ | 50/50 | 1.0 | 1 / 1 / 1.0 | 1.0x / 1.0x / 1.0x | None | **0.0000** | Feasible realization achieved with 1.0x edge overhead cost (range [1.0x, 1.0x]) |
| `lateral_movement` | NO | **YES** ✅ | 50/50 | 2.0 | 2 / 2 / 2.0 | 1.0x / 1.0x / 1.0x | None | **0.0000** | Feasible realization achieved with 1.0x edge overhead cost (range [1.0x, 1.0x]) |
| `exfiltration` | NO | **YES** ✅ | 50/50 | 2.0 | 2 / 2 / 2.0 | 1.0x / 1.0x / 1.0x | None | **0.0000** | Feasible realization achieved with 1.0x edge overhead cost (range [1.0x, 1.0x]) |
| `log_tampering` | NO | **YES** ✅ | 50/50 | 1.0 | 1 / 1 / 1.0 | 1.0x / 1.0x / 1.0x | None | **0.0000** | Feasible realization achieved with 1.0x edge overhead cost (range [1.0x, 1.0x]) |
| `unspawned_stealth_exec` | YES | **YES** ✅ | 50/50 | 1.0 | 2 / 2 / 2.0 | 2.0x / 2.0x / 2.0x | None | **0.0000** | Feasible realization achieved with 2.0x edge overhead cost (range [2.0x, 2.0x]) |
| `backdated_timestamp_tampering` | YES | **YES** ✅ | 5/50 | 1.0 | 1 / 1 / 1.0 | 1.0x / 1.0x / 1.0x | None | **0.0000** | Feasible realization achieved with 1.0x edge overhead cost (range [1.0x, 1.0x]) |
| `self_loop_execution` | YES | **NO** ❌ | 0/50 | 1.0 | N/A | N/A | `ExecutionConsistencyRule`, `SelfLoopRule` | **0.0000** | UNACHIEVABLE without violating rule(s): ExecutionConsistencyRule, SelfLoopRule |

---

## Per-Objective HARD Rule Applicability & Bypass Breakdown

### 1. Credential Access (`credential_access`)
- **HARD Rules Potentially Triggered**: `UnspawnedProcessRule`, `TimestampRule`, `ProcessActivityTemporalRule`.
- **Search Realization**: Process reads `/etc/shadow` from an active spawned process tree at a timestamp $t > t_{\text{spawn}}$.
- **Why Avoided**: Objective never required violating a HARD rule; reading a file from an active process is a valid OS operation.
- **Effort Cost**: 1.0x (1 edge required). Gated score = $0.0000$.

### 2. Lateral Movement (`lateral_movement`)
- **HARD Rules Potentially Triggered**: `SpawnConsistencyRule`, `ParentChildTemporalRule`, `NetworkConsistencyRule`.
- **Search Realization**: Spawns `sshd_child` and opens socket `192.168.1.100:22` at $t_{\text{connect}} > t_{\text{spawn}}$.
- **Why Avoided**: Inherently invariant-compliant when executed in chronological sequence.
- **Effort Cost**: 1.0x (2 edges required). Gated score = $0.0000$.

### 3. Exfiltration (`exfiltration`)
- **HARD Rules Potentially Triggered**: `TimestampRule`, `SequenceGapRule`, `ReadWriteConsistencyRule`.
- **Search Realization**: Sequential read of sensitive data followed by network connect.
- **Why Avoided**: Inherently invariant-compliant.
- **Effort Cost**: 1.0x (2 edges required). Gated score = $0.0000$.

### 4. Log Tampering (`log_tampering`)
- **HARD Rules Potentially Triggered**: `DeleteConsistencyRule`, `MissingNodeRule`.
- **Search Realization**: Process unlinks `/var/log/audit.log`.
- **Why Avoided**: Inherently invariant-compliant provided process and file node exist.
- **Effort Cost**: 1.0x (1 edge required). Gated score = $0.0000$.

### 5. Unspawned Stealth Execution (`unspawned_stealth_exec`)
- **HARD Rules Triggered in Naive Form**: `UnspawnedProcessRule`, `SpawnConsistencyRule`.
- **Attacker Remediation**: Attacker must insert a valid `SPAWN` edge from `proc_0` prior to execution.
- **Why Avoided after Repair**: Attacker incurs a **2.0x edge overhead cost** (1 naive edge + 1 repair spawn edge).
- **Effort Cost**: 2.0x (2 edges required). Gated score = $0.0000$.

### 6. Backdated Timestamp Tampering (`backdated_timestamp_tampering`)
- **HARD Rules Triggered**: `ProcessActivityTemporalRule`, `ParentChildTemporalRule`.
- **Search Outcome**: **PARTIALLY ACHIEVABLE (5/50 trials, 10.0%)**.
- **Why Blocked / Permitted**: Backdating is strictly blocked on spawned child processes where $t < t_{\text{spawn}}$ violates `ProcessActivityTemporalRule`. However, backdating succeeds in 5/50 trials (10.0%) when targeting root processes lacking parent spawn edges, where no $t_{\text{spawn}}$ bound exists.

### 7. Self-Loop Execution (`self_loop_execution`)
- **HARD Rules Triggered**: `SelfLoopRule`, `ExecutionConsistencyRule`.
- **Search Outcome**: **UNACHIEVABLE (0/50 trials)**.
- **Why Blocked**: Self-referential execution (`source_id == target_id`) is strictly forbidden by `SelfLoopRule`.

---

## Recommended Paper Limitations Section Framing

> **Recommended Limitations Framing Sentence**:
> *"Limitation: The hard feasibility gate enforces a strict zero-FPR guarantee by masking out all feasible (hard-invariant-satisfying) graph edges. As a consequence, the detector cannot flag adaptive adversaries who execute attack objectives entirely through valid, chronologically monotonic operations from legitimate process contexts (0/5 achieved objectives detected once feasible). Feasibility gating hardens anomaly detectors specifically against base-rate dilution; it does not replace general intrusion detection against stealthy, invariant-compliant adversaries."*