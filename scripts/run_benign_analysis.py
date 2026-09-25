#!/usr/bin/env python3
"""
CLI entry point for Phase 2: Benign Violation Rate Measurement.

Runs the full two-tier benign evaluation:
  Tier 1 — Synthetic clean baseline (zero-violation validation)
  Tier 2 — Realistic benign corpus (violation measurement)

Outputs per-rule violation rates, the HARD/SOFT partition, and saves
results to results/benign_violation_rates.json.

Usage:
    python scripts/run_benign_analysis.py
    python scripts/run_benign_analysis.py --sizes 500 2000 --trials 3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.benign_violation_analysis import (
    format_results_table,
    partition_invariants,
    run_benign_evaluation,
    save_results_json,
)


def main():
    parser = argparse.ArgumentParser(
        description="Measure benign violation rates for all 15 invariants"
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[500, 2000, 10000, 50000],
        help="Graph sizes (target_edges) to evaluate",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=5,
        help="Number of trials per size",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/benign_violation_rates.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("PHASE 2: Benign Violation Rate Measurement")
    print("=" * 72)
    print(f"Graph sizes: {args.sizes}")
    print(f"Trials per size: {args.trials}")
    print()

    # -------------------------------------------------------------------
    # Tier 1: Synthetic Clean Baseline
    # -------------------------------------------------------------------
    print("─" * 72)
    print("TIER 1: Synthetic Clean Baseline")
    print("─" * 72)

    t0 = time.time()
    rows_clean = run_benign_evaluation(
        num_trials_per_size=args.trials,
        graph_sizes=args.sizes,
        tiers=["synthetic_clean"],
    )
    t1 = time.time()

    print(f"Completed in {t1 - t0:.1f}s")
    print()
    table_clean = format_results_table(rows_clean, tier_filter="synthetic_clean")
    print(table_clean)
    print()

    hard_clean, soft_clean = partition_invariants(rows_clean, tier_filter="synthetic_clean")
    print(f"HARD rules (synthetic): {len(hard_clean)}")
    for r in hard_clean:
        print(f"  ✅ {r}")
    if soft_clean:
        print(f"SOFT rules (synthetic): {len(soft_clean)}")
        for r in soft_clean:
            print(f"  ⚠️  {r}")
    print()

    # -------------------------------------------------------------------
    # Tier 2: Realistic Benign Corpus
    # -------------------------------------------------------------------
    print("─" * 72)
    print("TIER 2: Realistic Benign Corpus")
    print("─" * 72)

    t2 = time.time()
    rows_realistic = run_benign_evaluation(
        num_trials_per_size=args.trials,
        graph_sizes=args.sizes,
        tiers=["realistic_benign"],
    )
    t3 = time.time()

    print(f"Completed in {t3 - t2:.1f}s")
    print()
    table_realistic = format_results_table(rows_realistic, tier_filter="realistic_benign")
    print(table_realistic)
    print()

    hard_real, soft_real = partition_invariants(rows_realistic, tier_filter="realistic_benign")
    print(f"HARD rules (realistic): {len(hard_real)}")
    for r in hard_real:
        print(f"  ✅ {r}")
    print(f"SOFT rules (realistic): {len(soft_real)}")
    for r in soft_real:
        print(f"  ⚠️  {r}")
    print()

    # -------------------------------------------------------------------
    # Combined partition
    # -------------------------------------------------------------------
    all_rows = rows_clean + rows_realistic
    hard_all, soft_all = partition_invariants(all_rows)

    print("=" * 72)
    print("FINAL HARD/SOFT PARTITION (across both tiers)")
    print("=" * 72)
    print(f"\nHARD ({len(hard_all)} rules — zero benign violations):")
    for r in hard_all:
        print(f"  ✅ {r}")
    print(f"\nSOFT ({len(soft_all)} rules — non-zero benign violations):")
    for r in soft_all:
        print(f"  ⚠️  {r}")
    print()

    # -------------------------------------------------------------------
    # Save results
    # -------------------------------------------------------------------
    save_results_json(all_rows, args.output)
    print(f"Results saved to {args.output}")

    # -------------------------------------------------------------------
    # Summary statistics
    # -------------------------------------------------------------------
    print()
    print("=" * 72)
    print("FEASIBILITY ASSESSMENT")
    print("=" * 72)

    if len(hard_all) >= 10:
        print(f"✅ {len(hard_all)}/15 invariants are HARD (zero benign FP rate).")
        print("   The base-rate dilution detector is FEASIBLE using the HARD set.")
    elif len(hard_all) >= 5:
        print(f"⚠️  {len(hard_all)}/15 invariants are HARD.")
        print("   Detector is feasible but with reduced detection surface.")
    else:
        print(f"❌ Only {len(hard_all)}/15 invariants are HARD.")
        print("   The invariant-based approach may not be viable.")

    print(f"\nTotal evaluation time: {t3 - t0:.1f}s")


if __name__ == "__main__":
    main()
