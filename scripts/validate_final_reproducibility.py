"""Post-run integrity checks for the final reproducibility artifacts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    alpha = load(ROOT / "results/alpha_estimates.json")
    auc = load(ROOT / "results/auc_invariance.json")
    provenance = load(ROOT / "results/canonical_fixture_provenance.json")
    ood = load(ROOT / "results/ood_crossscenario.json")
    detectors = [
        "rule_hard",
        "rule_all",
        "graphsage_baseline",
        "graphsage_inv_features",
        "gated_sage",
    ]
    assert provenance["fixture_module"] == "src.eval.canonical_fixture"
    assert provenance["builder"] == "build_canonical_fixture"
    assert set(alpha) == set(detectors)
    assert set(auc) == set(detectors)
    for detector in detectors:
        alpha_counts = alpha[detector]["baseline_counts"]
        auc_counts = auc[detector]["m_summary"]["0"]
        assert alpha_counts["tp_mean"] == auc_counts["tp_mean"], detector
        assert alpha[detector]["baseline_params"]["p_tpr"] == auc_counts["recall_mean"], detector
        assert alpha_counts["fp_mean"] == auc_counts["fp_mean"], detector
        assert alpha_counts["fn_mean"] == auc_counts["fn_mean"], detector

    directions = {row["name"] for row in ood["directions"]}
    assert directions == {"Dir1_1r3_to_5m6r", "Dir2_5m6r_to_1r3"}
    gated = [
        row for row in ood["alpha_fits"]
        if row["detector"] == "gated_sage" and row["noise_model"] == "resampled"
    ]
    assert {row["direction"] for row in gated} == directions
    assert "hard_violation_audit" in ood
    hard = ood["hard_violation_audit"]
    assert hard
    assert {"synthetic", "resampled"} <= {row["noise_model"] for row in hard}
    assert {"rule_name", "violations", "opportunities", "violation_rate"} <= set(hard[0])
    assert (ROOT / "results/ood_hard_violation_audit.csv").exists()
    assert (ROOT / "results/ood_hard_violation_audit.json").exists()
    print("FINAL VALIDATION: PASS")
    for detector in detectors:
        print(
            detector,
            f"tp={alpha[detector]['baseline_counts']['tp_mean']}",
            f"recall={alpha[detector]['baseline_params']['p_tpr']}",
            f"fp={alpha[detector]['baseline_counts']['fp_mean']}",
        )
    for row in gated:
        print(
            "OOD",
            row["direction"],
            f"alpha_hat={row['alpha_hat']}",
            f"R2={row['r_squared']}",
        )


if __name__ == "__main__":
    main()
