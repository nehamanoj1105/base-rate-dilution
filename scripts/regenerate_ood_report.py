"""Regenerate docs/OOD.md from the final OOD artifacts (no experiment rerun)."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "results/ood_crossscenario.json"
CSV_PATH = ROOT / "results/ood_hard_violation_audit.csv"
MD_PATH = ROOT / "docs/OOD.md"


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    sweep = data["sweep_results"]
    alpha_fits = data["alpha_fits"]
    partition = data["partition_transfer_check"]
    provenance = data["noise_provenance"]

    csv_rows = list(csv.DictReader(CSV_PATH.open())) if CSV_PATH.exists() else []
    agg: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: {"v": 0, "o": 0})
    for row in csv_rows:
        key = (row["direction"], row["noise_model"], row["rule_name"])
        agg[key]["v"] += int(row["violations"])
        agg[key]["o"] += int(row["opportunities"])

    per_rule_rows = []
    for (direction, noise_model, rule_name), totals in sorted(agg.items()):
        opp = totals["o"]
        per_rule_rows.append((direction, noise_model, rule_name, totals["v"], opp,
                              totals["v"] / opp if opp else 0.0))

    lines = [
        "# Out-of-Domain (OOD) Generalization & Partition Transfer (Phase 11 — Experiment G)",
        "",
        "## Executive Summary",
        "",
        "This evaluation establishes **Experiment G**: testing whether the feasibility-gated detector's "
        "precision-under-dilution behavior transfers across unseen DARPA scenario shifts "
        "({1r, 3} ↔ {5m, 6r}). All numbers below are post-fix and derived from the canonical "
        "evaluation path used by Issue K (`src/eval/canonical_fixture.py` / `src/eval/ood_evaluation.py`).",
        "",
        "> [!IMPORTANT]",
        "> **Leading result (fitted $\\hat{\\alpha}$, not $m=0$ snapshot):**",
        "> - `gated_sage` + **resampled** OOD noise: $\\hat{\\alpha} = 0.9650$, $R^2=0.7228$ (Dir1), "
        "$\\hat{\\alpha} = 1.0463$, $R^2=0.5494$ (Dir2).",
        "> - `gated_sage` + **synthetic** OOD noise: $\\hat{\\alpha} \\approx 0$ (precision saturates near "
        "0 at the first dilution step), $R^2 \\approx 0$.",
        "> - `graphsage_baseline` collapses to $\\mathrm{TP}=0$ and cannot sustain a dilution exponent.",
        "",
        "> [!NOTE]",
        "> **Scope of the invariance claim.** The 11 HARD invariants are empirically benign-null on the "
        "synthetic/realistic pool used for the original HARD-invariant *soundness validation* "
        "(`BenignResampler.create_default_pool(num_graphs=10, edges_per_graph=500)`). They are **not** "
        "benign-null on every distribution: when the dilution noise is drawn from the **source (train) "
        "scenario graphs** (`load_combined_scenario_graph(train_scenarios)`, a different distribution), "
        "HARD rules are violated at a non-zero rate. The gated-detector invariance guarantee therefore "
        "holds **on the supported noise distribution of the threat model**, not universally. This is a "
        "distributional boundary condition, not a universal invariance.",
        "",
        "---",
        "",
        "## 1. Partition Transfer Audit Table",
        "",
        "Benign violation rates of the 11 HARD rules on unpoisoned test-scenario traffic "
        "(partition transfer check is over the *target* scenario, not the noise population):",
        "",
        "| Scenario | Rule Name | Violation Count | Total Edges | Benign Violation Rate (%) | Status |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
    ]
    for sc_name, sc_rules in sorted(partition.items()):
        for r_name, r_info in sc_rules.items():
            rate_pct = r_info["violation_rate"] * 100.0
            status = r_info["status"]
            lines.append(
                f"| `{sc_name}` | `{r_name}` | {r_info['violation_count']} | "
                f"{r_info['total_edges']} | {rate_pct:.4f}% | **{status}** |"
            )

    lines += [
        "",
        "---",
        "",
        "## 2. Dilution Exponent ($\\hat{\\alpha}$) — Post-Fix (fitted, reported first)",
        "",
        "| Direction | Detector | Noise Model | $\\hat{\\alpha}$ | 95% CI | $R^2$ | Asymptotic Regime |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :--- |",
    ]
    regime_map = {
        "gated_sage": {
            "resampled": "Dilution Decay ($\\alpha\\sim 1$)",
            "synthetic": "Saturated (precision collapse at $m=1000$, $\\alpha\\sim 0$)",
        },
        "graphsage_baseline": {
            "resampled": "Baseline Failure ($\\mathrm{TP}=0$)",
            "synthetic": "Baseline Failure ($\\mathrm{TP}=0$)",
        },
    }
    for a in alpha_fits:
        regime = regime_map.get(a["detector"], {}).get(a["noise_model"], "Dilution Decay")
        lines.append(
            f"| `{a['direction']}` | `{a['detector']}` | `{a['noise_model']}` | "
            f"**{a['alpha_hat']:.4f}** | [{a['ci_lower']:.4f}, {a['ci_upper']:.4f}] | "
            f"{a['r_squared']:.4f} | {regime} |"
        )

    lines += [
        "",
        "### Exact post-fix gated_sage / resampled headline",
        "",
        "| Direction | $\\hat{\\alpha}$ | $R^2$ |",
        "| :--- | :---: | :---: |",
        "| `Dir1_1r3_to_5m6r` | **0.9650** | 0.7228 |",
        "| `Dir2_5m6r_to_1r3` | **1.0463** | 0.5494 |",
        "",
        "---",
        "",
        "## 3. Per-Rule HARD Violation Audit (noise edges only)",
        "",
        "Reuses `src/eval/noise_realism_audit.measure_noise_violations` on the **actual injected noise "
        "edge set** per (direction, noise_model, m, seed), then aggregated over all m and seeds.",
        "",
        "### 3.1 Aggregate violation rates per noise model",
        "",
        "| Direction | Noise Model | Total Violations | Total Noise Edges | Aggregate Rate |",
        "| :--- | :--- | :---: | :---: | :---: |",
    ]
    agg_model: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"v": 0, "o": 0})
    for row in csv_rows:
        key = (row["direction"], row["noise_model"])
        agg_model[key]["v"] += int(row["violations"])
        agg_model[key]["o"] += int(row["opportunities"])
    for (direction, noise_model), totals in sorted(agg_model.items()):
        opp = totals["o"]
        lines.append(
            f"| `{direction}` | `{noise_model}` | {totals['v']} | {opp} | "
            f"{totals['v']/opp if opp else 0.0:.6f} |"
        )

    lines += [
        "",
        "### 3.2 Per-rule HARD violation table (top contributors)",
        "",
        "| Direction | Noise Model | Rule Name | Violations | Opportunities | Rate |",
        "| :--- | :--- | :--- | :---: | :---: | :---: |",
    ]
    top = sorted(per_rule_rows, key=lambda r: -r[3])[:12]
    for direction, noise_model, rule_name, v, o, rate in top:
        lines.append(
            f"| `{direction}` | `{noise_model}` | `{rule_name}` | {v} | {o} | {rate:.6f} |"
        )

    lines += [
        "",
        "### 3.3 Full per-rule table",
        "",
        "| Direction | Noise Model | Rule Name | Violations | Opportunities | Rate |",
        "| :--- | :--- | :--- | :---: | :---: | :---: |",
    ]
    for direction, noise_model, rule_name, v, o, rate in per_rule_rows:
        lines.append(
            f"| `{direction}` | `{noise_model}` | `{rule_name}` | {v} | {o} | {rate:.6f} |"
        )

    lines += [
        "",
        "### 3.4 Explanation of the $\\hat{\\alpha}$ gap",
        "",
        "- **Synthetic OOD noise** massively activates HARD invariants (Dir2 aggregate rate ≈ 5.5%, "
        "driven by `ProcessActivityTemporalRule` ≈ 31% and `ParentChildTemporalRule` ≈ 13%) and "
        "saturates `gated_sage` precision to ~0.003 at the first dilution step ($m=1000$). Because "
        "precision is already at its asymptote, the log-precision decay has no dynamic range and the "
        "fitted $\\hat{\\alpha} \\approx 0$.",
        "- **Resampled OOD noise** (source-scenario donor pool) produces few HARD violations (Dir1 "
        "aggregate rate ≈ 2.7e-5; Dir2 ≈ 2.4e-4), so the gated mask does not saturate; precision "
        "decays gradually with $m$, yielding $\\hat{\\alpha} \\approx 0.97$–$1.05$.",
        "- Therefore the $\\hat{\\alpha}$ gap is **NOT** explained by synthetic noise *failing* to "
        "activate HARD invariants — synthetic noise over-activates them. It is explained by synthetic "
        "noise driving precision to saturation instantly (no decay to fit), whereas resampled noise "
        "preserves a decaying precision curve.",
        "",
        "---",
        "",
        "## 4. Precision & Recall Across Dilution (selected $m$)",
        "",
        "| Direction | Detector | Noise | $m$ | Precision | Recall | TP | FP |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    m_sample = [0, 1000, 10000, 50000, 100000]
    directions = sorted({r["direction"] for r in sweep})
    detectors = sorted({r["detector"] for r in sweep})
    noise_models = sorted({r["noise_model"] for r in sweep})
    for dir_name in directions:
        for det in detectors:
            for nm in noise_models:
                for m_target in m_sample:
                    sub = [
                        r for r in sweep
                        if r["direction"] == dir_name
                        and r["detector"] == det
                        and r["noise_model"] == nm
                        and r["m"] == m_target
                    ]
                    if not sub:
                        continue
                    import numpy as _np
                    prec = _np.mean([r["precision"] for r in sub])
                    rec = _np.mean([r["recall"] for r in sub])
                    tp = _np.mean([r["tp"] for r in sub])
                    fp = _np.mean([r["fp"] for r in sub])
                    lines.append(
                        f"| `{dir_name}` | `{det}` | `{nm}` | {m_target} | "
                        f"{prec:.4f} | {rec:.4f} | {tp:.1f} | {fp:.1f} |"
                    )

    lines += [
        "",
        "---",
        "",
        "## 5. Noise Provenance",
        "",
        f"- **Resampled OOD noise donor**: `{provenance['resampled_donor']['benign_pool_generator']}` "
        f"(train scenarios: {provenance['resampled_donor']['train_scenarios_by_direction']}).",
        f"- **Same distribution as soundness validation?** "
        f"{provenance['resampled_donor']['same_distribution_as_soundness_validation']}.",
        f"- **Soundness-validation distribution**: "
        f"{provenance['resampled_donor']['soundness_validation_distribution']}.",
        f"- **Conclusion**: the OOD resampled noise population is drawn from the **source scenario graphs**, "
        "a distributional shift relative to the synthetic/realistic pool used to certify the HARD "
        "invariants. The observed HARD violations are therefore the expected boundary condition, "
        "not a failure of the threat-model (base-rate dilution) guarantee.",
        "",
        "---",
        "",
        "## Conclusion",
        "Experiment G confirms that, on the **supported noise distribution** (base-rate dilution), "
        "`gated_sage` shows a single fitted $\\hat{\\alpha}$ per direction driven by gradual precision "
        "decay under resampled noise, while the ungated baseline collapses. The invariance claim is "
        "scoped to the base-rate dilution threat model: the HARD invariants are benign-null on the "
        "certification pool but are violated by the source-scenario donor distribution used for OOD "
        "resampling — a distributional boundary condition rather than a universal invariance.",
    ]

    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {MD_PATH} ({len(lines)} lines).")


if __name__ == "__main__":
    main()
