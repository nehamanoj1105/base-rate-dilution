#!/usr/bin/env python3
"""
CLI entry point for Phase 4: Reusable Dilution Sweep Harness & Visualization.

Executes dilution volume m sweep across registered detectors (Rule Engine, GraphSAGE)
under synthetic mimicry noise and resampled benign noise models.

Outputs:
- results/dilution_sweep.csv
- results/dilution_sweep_metadata.json
- results/figs/precision_vs_m_raw.png

Usage:
    python3 scripts/run_dilution_sweep.py
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.eval.dilution_sweep import run_dilution_sweep


def plot_precision_vs_m(csv_rows: list[dict], output_fig: str = "results/figs/precision_vs_m_raw.png") -> str:
    """
    Plots Precision vs dilution volume m for Rule Engine and GraphSAGE under
    synthetic vs resampled noise models on log-log / log-linear axes.
    """
    fig_path = Path(output_fig)
    fig_path.parent.mkdir(parents=True, exist_ok=True)

    # Group data by (detector, noise_model, m) -> list[precision]
    grouped = defaultdict(list)
    for row in csv_rows:
        key = (row["detector"], row["noise_model"], int(row["m"]))
        grouped[key].append(float(row["precision"]))

    # Identify unique series
    detectors = sorted(list({r["detector"] for r in csv_rows}))
    noise_models = sorted(list({r["noise_model"] for r in csv_rows}))

    plt.figure(figsize=(10, 6), dpi=300)

    styles = {
        ("Rule Engine", "synthetic"): ("#D9534F", "s", "--", "Rule Engine (Synthetic Noise)"),
        ("Rule Engine", "resampled"): ("#5CB85C", "o", "-", "Rule Engine (Resampled Benign)"),
        ("GraphSAGE", "synthetic"): ("#F0AD4E", "^", "--", "GraphSAGE (Synthetic Noise)"),
        ("GraphSAGE", "resampled"): ("#0275D8", "D", "-", "GraphSAGE (Resampled Benign)"),
    }

    for det in detectors:
        for nm in noise_models:
            # Extract m values sorted
            m_vals = sorted(list({int(r["m"]) for r in csv_rows if r["detector"] == det and r["noise_model"] == nm}))
            if not m_vals:
                continue

            means = []
            stds = []
            for m in m_vals:
                vals = grouped[(det, nm, m)]
                means.append(np.mean(vals) if vals else 0.0)
                stds.append(np.std(vals) if vals else 0.0)

            means = np.array(means)
            stds = np.array(stds)

            # Map x for 0 to 1 for log plot rendering
            x_plot = np.array([max(1, m) for m in m_vals])

            color, marker, linestyle, label = styles.get(
                (det, nm), ("#333333", "o", "-", f"{det} ({nm})")
            )

            plt.plot(
                x_plot, means,
                label=label,
                color=color,
                marker=marker,
                linestyle=linestyle,
                linewidth=2,
                markersize=7,
            )
            plt.fill_between(
                x_plot,
                np.clip(means - stds, 0, 1),
                np.clip(means + stds, 0, 1),
                color=color,
                alpha=0.15,
            )

    plt.xscale("log")
    plt.yscale("linear")
    plt.ylim(-0.05, 1.05)
    plt.xlabel("Dilution Volume $m$ (Injected Noise Edges, log scale)", fontsize=12, fontweight="bold")
    plt.ylabel("Precision", fontsize=12, fontweight="bold")
    plt.title("EXPERIMENT A & B: Precision vs. Dilution Volume $m$", fontsize=14, fontweight="bold", pad=12)
    plt.grid(True, which="both", linestyle=":", alpha=0.6)
    plt.legend(loc="best", fontsize=10, framealpha=0.9)
    plt.tight_layout()

    plt.savefig(fig_path)
    plt.close()
    return str(fig_path)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 4 Dilution Sweep Harness: Precision vs m Benchmark"
    )
    parser.add_argument(
        "--base-graph-size", type=int, default=1000,
        help="Target base graph size in edges",
    )
    parser.add_argument(
        "--intensity", type=int, default=5,
        help="Poisoning intensity per type (k = intensity * 4)",
    )
    parser.add_argument(
        "--output-csv", type=str, default="results/dilution_sweep.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--output-json", type=str, default="results/dilution_sweep_metadata.json",
        help="Output sidecar JSON path",
    )
    parser.add_argument(
        "--output-fig", type=str, default="results/figs/precision_vs_m_raw.png",
        help="Output figure path",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick run mode",
    )
    args = parser.parse_args()

    quick_mode = args.quick or os.environ.get("QUICK_MODE") == "1"
    seeds = (0, 1) if quick_mode else (0, 1, 2, 3, 4)
    m_grid = (0, 500, 2000) if quick_mode else (0, 1000, 2500, 5000, 10000, 25000, 50000, 100000)

    print("=" * 80)
    print("PHASE 4: Reusable Dilution Sweep Harness & Benchmark")
    print("=" * 80)
    print()

    # Execute sweep
    rows = run_dilution_sweep(
        detectors=("rule_engine", "graphsage"),
        noise_models=("synthetic", "resampled"),
        m_grid=m_grid,
        seeds=seeds,
        base_graph_size=args.base_graph_size,
        intensity=args.intensity,
        output_csv=args.output_csv,
        output_json=args.output_json,
    )

    # Convert dataclass rows to dict list for plotting
    dict_rows = [r.to_dict() for r in rows]

    print("\n[*] Generating Precision vs m Benchmark Plot...")
    fig_path = plot_precision_vs_m(dict_rows, args.output_fig)
    print(f"[+] Plot saved to {fig_path}")

    print("\n" + "=" * 80)
    print("PHASE 4 DILUTION SWEEP COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
