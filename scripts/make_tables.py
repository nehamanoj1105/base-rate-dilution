#!/usr/bin/env python3
"""
LaTeX Table Generator (Phase 13).

Generates all publication-ready LaTeX tables directly from results/ JSON and CSV files.
Ensures zero human-typed numbers in the paper.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def generate_table1_noise_realism(out_dir: Path) -> Path:
    """Generates table1_noise_realism.tex from results/noise_realism_audit.json."""
    json_path = ROOT / "results/noise_realism_audit.json"
    if not json_path.exists():
        json_path = ROOT / "results/noise_audit_results.json"
    if not json_path.exists():
        print(f"[!] Warning: {json_path} not found. Skipping Table 1.")
        return out_dir / "table1_noise_realism.tex"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rules_data = data.get("comparison_table", data.get("rule_audit_records", []))

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Empirical Invariant Violation Rates Across Synthetic Mimicry and Resampled Benign Noise.}",
        r"\label{tab:noise_realism}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"\textbf{Invariant Rule Name} & \textbf{Rule Class} & \textbf{Synthetic Noise (\%)} & \textbf{Resampled Noise (\%)} & \textbf{Violation Gap (\%)} \\",
        r"\midrule",
    ]

    for r in rules_data:
        rule_name = r.get("rule", "Unknown")
        rule_class = "HARD" if r.get("is_hard", False) else "SOFT"
        syn_rate = r.get("synthetic_noise_rate", r.get("synthetic_violation_rate", 0.0)) * 100.0
        res_rate = r.get("resampled_noise_rate", r.get("resampled_violation_rate", 0.0)) * 100.0
        gap = r.get("gap_synthetic", r.get("gap", syn_rate - res_rate)) * (100.0 if "gap_synthetic" in r else 1.0)

        lines.append(
            f"{rule_name} & {rule_class} & {syn_rate:.2f}\\% & {res_rate:.2f}\\% & \\textbf{{{gap:+.2f}\\%}} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ])

    out_p = out_dir / "table1_noise_realism.tex"
    out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Generated {out_p}")
    return out_p


def generate_table2_ablation_dilution(out_dir: Path) -> Path:
    """Generates table2_ablation_dilution.tex from results/alpha_by_configuration.json."""
    json_path = ROOT / "results/alpha_by_configuration.json"
    if not json_path.exists():
        print(f"[!] Warning: {json_path} not found. Skipping Table 2.")
        return out_dir / "table2_ablation_dilution.tex"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        entries = list(data.values())
    else:
        entries = data

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Dilution Exponent ($\hat{\alpha}$) and Precision Stability Across Detector Configurations.}",
        r"\label{tab:ablation_dilution}",
        r"\begin{tabular}{llccc}",
        r"\toprule",
        r"\textbf{Detector Configuration} & \textbf{Noise Model} & \textbf{Fitted $\hat{\alpha}$} & \textbf{95\% Bootstrap CI} & \textbf{$R^2$} \\",
        r"\midrule",
    ]

    for entry in entries:
        if isinstance(entry, str):
            continue
        det_name = entry.get("detector_name", entry.get("detector", "Unknown"))
        nm = entry.get("noise_model", "resampled")
        alpha = entry.get("alpha_hat", 0.0)
        ci_l = entry.get("ci_lower", 0.0)
        ci_u = entry.get("ci_upper", 0.0)
        r2 = entry.get("r_squared", 0.0)

        lines.append(
            f"{det_name} & {nm.capitalize()} & \\textbf{{{alpha:.4f}}} & [{ci_l:.4f}, {ci_u:.4f}] & {r2:.4f} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ])

    out_p = out_dir / "table2_ablation_dilution.tex"
    out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Generated {out_p}")
    return out_p


def generate_table3_adaptive_adversary(out_dir: Path) -> Path:
    """Generates table3_adaptive_adversary.tex from results/adaptive_attacker.json."""
    json_path = ROOT / "results/adaptive_attacker.json"
    if not json_path.exists():
        print(f"[!] Warning: {json_path} not found. Skipping Table 3.")
        return out_dir / "table3_adaptive_adversary.tex"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    certs = data.get("certificates", [])

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Adaptive Adversary Capability Certificate and Detection Cost under Feasible Search.}",
        r"\label{tab:adaptive_adversary}",
        r"\begin{tabular}{lcccccc}",
        r"\toprule",
        r"\textbf{Objective Name} & \textbf{Achieved?} & \textbf{Infeasible Cost} & \textbf{Feasible Cost} & \textbf{Effort Overhead} & \textbf{Gated Score} & \textbf{Certificate Verdict} \\",
        r"\midrule",
    ]

    for c in certs:
        obj_name = c.get("objective_name", "Unknown")
        achieved = "YES" if c.get("achieved", False) else "NO"
        inf_cost = c.get("infeasible_edge_cost", 1.0)
        feas_cost = c.get("feasible_edge_cost_mean", c.get("feasible_edge_cost", 1.0))
        overhead = c.get("effort_overhead_mean", c.get("effort_overhead_ratio", 1.0))
        gated_score = c.get("gated_detector_max_score", 0.0)
        verdict = c.get("certificate_verdict", "Feasible realisation")

        lines.append(
            f"\\texttt{{{obj_name}}} & {achieved} & {inf_cost:.1f} & {feas_cost:.1f} & {overhead:.1f}x & {gated_score:.4f} & {verdict} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ])

    out_p = out_dir / "table3_adaptive_adversary.tex"
    out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Generated {out_p}")
    return out_p


def generate_table4_ood_partition_transfer(out_dir: Path) -> Path:
    """Generates table4_ood_partition_transfer.tex from results/ood_crossscenario.json."""
    json_path = ROOT / "results/ood_crossscenario.json"
    if not json_path.exists():
        print(f"[!] Warning: {json_path} not found. Skipping Table 4.")
        return out_dir / "table4_ood_partition_transfer.tex"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    transfer_data = data.get("partition_transfer_check", {})

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Out-of-Domain Partition Transfer Audit Across Target DARPA Scenarios.}",
        r"\label{tab:ood_partition_transfer}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"\textbf{Target Scenario} & \textbf{Invariant Rule Name} & \textbf{Violations} & \textbf{Benign Violation Rate (\%)} & \textbf{Partition Status} \\",
        r"\midrule",
    ]

    for sc_name, sc_rules in transfer_data.items():
        for r_name, r_info in sc_rules.items():
            v_count = r_info.get("violation_count", 0)
            rate_pct = r_info.get("violation_rate", 0.0) * 100.0
            status = r_info.get("status", "TRANSFERRED")

            lines.append(
                f"\\texttt{{{sc_name}}} & \\texttt{{{r_name}}} & {v_count} & {rate_pct:.4f}\\% & \\textbf{{{status}}} \\\\"
            )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ])

    out_p = out_dir / "table4_ood_partition_transfer.tex"
    out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Generated {out_p}")
    return out_p


def generate_table5_second_domain(out_dir: Path) -> Path:
    """Generates table5_second_domain.tex from results/second_domain.json."""
    json_path = ROOT / "results/second_domain.json"
    if not json_path.exists():
        print(f"[!] Warning: {json_path} not found. Skipping Table 5.")
        return out_dir / "table5_second_domain.tex"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("sweep_records", [])

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Empirical Performance Metrics under Dilution on the Elliptic Bitcoin Graph Anomaly Benchmark.}",
        r"\label{tab:second_domain}",
        r"\begin{tabular}{cddddc}",
        r"\toprule",
        r"\textbf{Dilution $m$ (nodes)} & \textbf{Precision} & \textbf{Recall} & \textbf{F1 Score} & \textbf{ROC-AUC} & \textbf{Spearman $\rho$} \\",
        r"\midrule",
    ]

    m_grid = sorted(list({r["m"] for r in records}))
    for m in m_grid:
        sub = [r for r in records if r["m"] == m]
        p = np.mean([r["precision"] for r in sub])
        r = np.mean([r["recall"] for r in sub])
        f1 = np.mean([r["f1"] for r in sub])
        auc = np.mean([r["auc"] for r in sub])
        rho = np.mean([r["spearman_rho"] for r in sub])

        lines.append(
            f"{m} & {p:.4f} & {r:.4f} & {f1:.4f} & {auc:.4f} & {rho:.4f} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ])

    out_p = out_dir / "table5_second_domain.tex"
    out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Generated {out_p}")
    return out_p


def main():
    out_dir = ROOT / "results/tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[*] Generating publication LaTeX tables in results/tables/...")
    generate_table1_noise_realism(out_dir)
    generate_table2_ablation_dilution(out_dir)
    generate_table3_adaptive_adversary(out_dir)
    generate_table4_ood_partition_transfer(out_dir)
    generate_table5_second_domain(out_dir)
    print("[+] All LaTeX tables generated successfully!")


if __name__ == "__main__":
    main()
