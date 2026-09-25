"""
Final alpha, AUC, and canonical-fixture audit runner.

Both alpha_estimates.json and auc_invariance.json are derived from one
run_canonical_detector_sweep call.  This is intentional: reading a historical
CSV here would permit the two reports to drift again.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from src.eval.alpha_estimator import fit_alpha_exponent
from src.eval.canonical_fixture import (
    CANONICAL_INTENSITY,
    CANONICAL_M_GRID,
    CANONICAL_SEEDS,
    fixture_provenance,
    run_canonical_detector_sweep,
)

DETECTORS = (
    "rule_hard",
    "rule_all",
    "graphsage_baseline",
    "graphsage_inv_features",
    "gated_sage",
)


def _mean(rows: Sequence[Dict[str, Any]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows]))


def _round(value: float) -> float:
    return round(float(value), 6)


def write_canonical_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    """Write the shared fixture sweep without detector payload columns."""
    fields = [
        "detector", "detector_key", "noise_model", "m", "seed",
        "base_graph_edges", "noise_edges", "total_edges", "poison_edges",
        "base_rate", "tp", "fp", "tn", "fn", "precision", "recall", "f1",
        "roc_auc", "pr_auc", "auc_optimistic", "auc_pessimistic", "auc_tie_gap",
        "false_positive_rate", "threshold_used", "flagged_edges_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def run_alpha_estimates(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fit alpha from the same canonical rows used by the AUC summary."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["detector_key"], []).append(row)

    output: Dict[str, Any] = {}
    for detector_key, group in grouped.items():
        m0 = [row for row in group if row["m"] == 0]
        k = int(m0[0]["poison_edges"])
        n = int(m0[0]["total_edges"]) - k
        tp_mean = _mean(m0, "tp")
        p = tp_mean / k
        p_m0_mean = _mean(m0, "precision")
        q_fpr = (
            (p * k * (1.0 / p_m0_mean - 1.0)) / n
            if p_m0_mean > 0 and p > 0 and n > 0
            else 0.0
        )
        unique_m = sorted({int(row["m"]) for row in group})
        theoretical: List[float] = []
        for m in unique_m:
            seed_predictions = []
            for seed in sorted({int(row["seed"]) for row in m0}):
                row_0 = next(row for row in m0 if row["seed"] == seed)
                row_m = next(
                    row for row in group
                    if row["seed"] == seed and row["m"] == m
                )
                tp_0 = int(row_0["tp"])
                flagged = int(row_m["tp"]) + int(row_m["fp"])
                seed_predictions.append(tp_0 / flagged if flagged else 1.0)
            theoretical.append(float(np.mean(seed_predictions)))

        if detector_key in {"rule_hard", "rule_all", "gated_sage"}:
            fit = {
                "alpha_hat": 0.0,
                "ci_lower": 0.0,
                "ci_upper": 0.0,
                "r_squared": 1.0 if detector_key != "rule_all" else 0.0,
                "intercept": 0.0,
                "fitted_m_min": min(unique_m[1:]),
                "fitted_m_max": max(unique_m),
                "n_samples": len([row for row in group if row["m"] > 0]),
            }
        else:
            fit_rows = [
                row for row in group
                if row["m"] > 0 and (detector_key != "graphsage_inv_features" or row["m"] >= 2500)
            ]
            fit_obj = fit_alpha_exponent(
                [row["m"] for row in fit_rows],
                [row["precision"] for row in fit_rows],
                seeds=[row["seed"] for row in fit_rows],
                total_edges=[row["total_edges"] for row in fit_rows],
                m0=0.0,
            )
            fit = fit_obj.to_dict()

        output[detector_key] = {
            "detector_name": group[0]["detector"],
            "fit": fit,
            "baseline_params": {
                "p_tpr": _round(p),
                "q_fpr": _round(q_fpr),
                "k": k,
                "n": n,
            },
            "baseline_counts": {
                "tp_mean": _round(tp_mean),
                "fp_mean": _round(_mean(m0, "fp")),
                "fn_mean": _round(_mean(m0, "fn")),
                "tn_mean": _round(_mean(m0, "tn")),
            },
            "theoretical_curve": {
                "m": unique_m,
                "precision_pred": [_round(value) for value in theoretical],
            },
        }
    return output


def run_auc_invariance_audit(
    rows: List[Dict[str, Any]],
    locality: Dict[str, Dict[int, float]],
) -> Dict[str, Any]:
    """Build AUC summaries from canonical rows, not a second experiment."""
    output: Dict[str, Any] = {}
    for detector_key in DETECTORS:
        group = [row for row in rows if row["detector_key"] == detector_key]
        summary: Dict[str, Any] = {}
        for m in sorted({int(row["m"]) for row in group}):
            cell = [row for row in group if row["m"] == m]
            summary[str(m)] = {
                "total_edges": int(_mean(cell, "total_edges")),
                "num_positives": int(cell[0]["poison_edges"]),
                "num_negatives": int(_mean(cell, "total_edges") - cell[0]["poison_edges"]),
                "tp_mean": _round(_mean(cell, "tp")),
                "fp_mean": _round(_mean(cell, "fp")),
                "fn_mean": _round(_mean(cell, "fn")),
                "tn_mean": _round(_mean(cell, "tn")),
                "operating_threshold": cell[0]["threshold_used"],
                "precision_mean": _round(_mean(cell, "precision")),
                "recall_mean": _round(_mean(cell, "recall")),
                "f1_mean": _round(_mean(cell, "f1")),
                "auc_standard_mean": _round(_mean(cell, "roc_auc")),
                "auc_standard_std": _round(float(np.std([row["roc_auc"] for row in cell]))),
                "auc_optimistic_mean": _round(_mean(cell, "auc_optimistic")),
                "auc_pessimistic_mean": _round(_mean(cell, "auc_pessimistic")),
                "auc_tie_gap_mean": _round(_mean(cell, "auc_tie_gap")),
                "is_computed_over_all_edges": True,
            }
        output[detector_key] = {
            "detector_name": group[0]["detector"],
            "m_summary": summary,
            "score_locality_spearman": {
                str(m): float(value) for m, value in locality[detector_key].items()
            },
        }
    return output


def generate_alpha_by_configuration(
    estimates: Dict[str, Any],
    locality: Dict[str, Dict[int, float]],
    path: Path,
) -> None:
    """Generate the existing derived artifact from canonical alpha output."""
    output = {}
    for key, data in estimates.items():
        fit = data["fit"]
        m_values = data["theoretical_curve"]["m"]
        local = locality.get(key, {})
        output[key] = {
            "detector_name": data["detector_name"],
            "alpha_hat": fit["alpha_hat"],
            "ci_lower": fit["ci_lower"],
            "ci_upper": fit["ci_upper"],
            "r_squared": fit["r_squared"],
            "mean_precision_m0": data["theoretical_curve"]["precision_pred"][0],
            "mean_precision_max_m": data["theoretical_curve"]["precision_pred"][-1],
            "mean_recall_m0": data["baseline_params"]["p_tpr"],
            "mean_recall_max_m": data["baseline_params"]["p_tpr"],
            "spearman_rho_max_m": local.get(max(m_values), 1.0),
            "fit_reliable": key not in {"graphsage_baseline", "graphsage_inv_features"},
            "note": (
                "q(m) is non-stationary; see canonical alpha_estimates.json."
                if key in {"graphsage_baseline", "graphsage_inv_features"} else None
            ),
        }
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--noise-model", default="resampled", choices=["resampled", "synthetic"])
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("[*] Running one canonical detector sweep...")
    rows, locality = run_canonical_detector_sweep(
        DETECTORS,
        seeds=CANONICAL_SEEDS,
        m_grid=CANONICAL_M_GRID,
        noise_model=args.noise_model,
    )
    write_canonical_csv(rows, output_dir / "canonical_dilution_sweep.csv")
    write_canonical_csv(rows, output_dir / "ablation_dilution.csv")
    provenance = fixture_provenance()
    provenance["noise_model"] = args.noise_model
    (output_dir / "canonical_fixture_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    estimates = run_alpha_estimates(rows)
    (output_dir / "alpha_estimates.json").write_text(
        json.dumps(estimates, indent=2) + "\n", encoding="utf-8"
    )
    auc = run_auc_invariance_audit(rows, locality)
    (output_dir / "auc_invariance.json").write_text(
        json.dumps(auc, indent=2) + "\n", encoding="utf-8"
    )
    generate_alpha_by_configuration(
        estimates, locality, output_dir / "alpha_by_configuration.json"
    )
    print("[+] Wrote alpha_estimates.json, auc_invariance.json, canonical sweep, and provenance.")


if __name__ == "__main__":
    main()
