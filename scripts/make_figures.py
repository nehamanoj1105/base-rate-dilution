#!/usr/bin/env python3
"""
Paper Figure Generator (Phase 13).

Consolidates and generates all publication-quality paper figures directly from results/ files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np


def plot_noise_realism_gap(json_path: Path, output_png: Path):
    """Plots synthetic vs resampled violation gaps from noise_realism_audit.json."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    table = data.get("comparison_table", [])
    if not table:
        return

    rules = [r["rule"].replace("Rule", "") for r in table]
    syn_gaps = [r.get("gap_synthetic", 0.0) * 100.0 for r in table]
    res_gaps = [r.get("gap_resampled", 0.0) * 100.0 for r in table]

    x = np.arange(len(rules))
    width = 0.35

    plt.figure(figsize=(12, 5))
    plt.bar(x - width/2, syn_gaps, width, label="Synthetic Mimicry Gap (%)", color="#d95f02", alpha=0.85)
    plt.bar(x + width/2, res_gaps, width, label="Resampled Benign Gap (%)", color="#7570b3", alpha=0.85)

    plt.axhline(0, color="black", linewidth=0.8, linestyle="--")
    plt.axhline(1.0, color="red", linewidth=0.8, linestyle=":", label="Plausibility Threshold (1%)")

    plt.ylabel("Violation Rate Gap (%)")
    plt.title("Empirical Invariant Violation Rate Gap Relative to Real Benign Traffic")
    plt.xticks(x, rules, rotation=45, ha="right")
    plt.legend()
    plt.grid(True, linestyle=":", alpha=0.5)
    plt.tight_layout()

    plt.savefig(output_png, dpi=300)
    plt.close()
    print(f"[+] Saved {output_png}")


def main():
    figs_dir = ROOT / "results/figs"
    figs_dir.mkdir(parents=True, exist_ok=True)

    print("[*] Generating all publication figures in results/figs/...")

    # 1. Noise Realism Audit Figure
    try:
        json_p = ROOT / "results/noise_realism_audit.json"
        if not json_p.exists():
            json_p = ROOT / "results/noise_audit_results.json"
        if json_p.exists():
            plot_noise_realism_gap(json_p, output_png=figs_dir / "noise_realism_gap.png")
    except Exception as e:
        print(f"[!] Error generating noise_realism_gap.png: {e}")

    # 2. OOD Cross-Scenario Alpha Figure
    try:
        from scripts.run_ood_experiments import plot_ood_alpha_curves
        json_p = ROOT / "results/ood_crossscenario.json"
        if json_p.exists():
            with open(json_p, "r", encoding="utf-8") as f:
                data = json.load(f)
            plot_ood_alpha_curves(data, output_png=figs_dir / "ood_alpha.png")
    except Exception as e:
        print(f"[!] Error generating ood_alpha.png: {e}")

    # 3. Second-Domain Elliptic Figure
    try:
        from scripts.run_second_domain import plot_second_domain_results
        json_p = ROOT / "results/second_domain.json"
        if json_p.exists():
            with open(json_p, "r", encoding="utf-8") as f:
                data = json.load(f)
            plot_second_domain_results(data, output_png=figs_dir / "second_domain_alpha.png")
    except Exception as e:
        print(f"[!] Error generating second_domain_alpha.png: {e}")

    print("[+] All publication figures generated successfully!")


if __name__ == "__main__":
    main()
