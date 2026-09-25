#!/usr/bin/env python3
"""
Results Manifest Generator (Phase 13).

Generates results/MANIFEST.json, keying every result file and LaTeX table/figure
to its supporting experiment, git commit hash, seeds, config, and wall-clock times.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_git_commit_hash() -> str:
    """Gets current git commit hash, or fallback string if unavailable."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def generate_results_manifest(
    wall_clock_times: dict[str, float] | None = None,
    output_json: Path | str = "results/MANIFEST.json",
) -> Path:
    """Generates results/MANIFEST.json."""
    import torch
    import torch_geometric

    commit_hash = get_git_commit_hash()
    times = wall_clock_times or {}

    manifest = {
        "metadata": {
            "title": "Causal Provenance Tamper Detection - Experimental Artifact Manifest",
            "git_commit": commit_hash,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "environment": {
                "python_version": sys.version.split()[0],
                "pytorch_version": torch.__version__,
                "pyg_version": torch_geometric.__version__,
                "platform": sys.platform,
            },
        },
        "experiments": {
            "noise_realism_audit": {
                "description": "Quantifies OS-implausibility of synthetic mimicry vs resampled benign noise.",
                "script": "scripts/run_noise_audit.py",
                "result_file": "results/noise_audit_results.json",
                "table": "results/tables/table1_noise_realism.tex",
                "figure": "results/figs/noise_realism_gap.png",
                "doc": "docs/NOISE_REALISM.md",
                "wall_clock_seconds": round(times.get("noise_audit", 0.0), 2),
            },
            "gated_training": {
                "description": "Multi-seed training and split hygiene audit of GatedSAGE.",
                "script": "scripts/run_gated_training.py",
                "result_file": "results/training_metrics.json",
                "checkpoints": "results/checkpoints/",
                "splits_manifest": "config/splits.json",
                "wall_clock_seconds": round(times.get("gated_training", 0.0), 2),
            },
            "ablation_dilution": {
                "description": "5-detector dilution sweep across m=0..100k isolating the architectural gate.",
                "script": "scripts/run_ablation_experiments.py",
                "result_file": "results/ablation_dilution.csv",
                "alpha_fits": "results/alpha_by_configuration.json",
                "table": "results/tables/table2_ablation_dilution.tex",
                "figures": [
                    "results/figs/ablation_precision_vs_m.png",
                    "results/figs/tradeoff_frontier.png",
                ],
                "doc": "docs/ABLATION.md",
                "wall_clock_seconds": round(times.get("ablation", 0.0), 2),
            },
            "adaptive_attacker": {
                "description": "Experiment H: Feasible attacker search over 11 HARD rules across 7 objectives.",
                "script": "scripts/run_adaptive_attacker.py",
                "result_file": "results/adaptive_attacker.json",
                "table": "results/tables/table3_adaptive_adversary.tex",
                "doc": "docs/ADAPTIVE_ADVERSARY_V2.md",
                "wall_clock_seconds": round(times.get("adaptive_attacker", 0.0), 2),
            },
            "ood_crossscenario": {
                "description": "Experiment G: Cross-scenario generalization ({1r,3} <-> {5m,6r}) & partition transfer.",
                "script": "scripts/run_ood_experiments.py",
                "result_file": "results/ood_crossscenario.json",
                "table": "results/tables/table4_ood_partition_transfer.tex",
                "figure": "results/figs/ood_alpha.png",
                "doc": "docs/OOD.md",
                "wall_clock_seconds": round(times.get("ood", 0.0), 2),
            },
            "second_domain_elliptic": {
                "description": "Phase 12: Generality benchmark reproducing dilution on Elliptic Bitcoin graph.",
                "script": "scripts/run_second_domain.py",
                "result_file": "results/second_domain.json",
                "table": "results/tables/table5_second_domain.tex",
                "figure": "results/figs/second_domain_alpha.png",
                "doc": "docs/SECOND_DOMAIN.md",
                "wall_clock_seconds": round(times.get("second_domain", 0.0), 2),
            },
        },
    }

    out_p = ROOT / output_json
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[+] Results manifest saved to {output_json}")
    return out_p


def main():
    generate_results_manifest()


if __name__ == "__main__":
    main()
