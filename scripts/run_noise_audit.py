#!/usr/bin/env python3
"""
CLI entry point for Phase 3: Noise Realism Audit.

Runs the 15 invariant rules over synthetic mimicry noise edges, resampled
benign noise edges, and real benign activity. Produces a three-column
comparison table to establish whether the existing noise generator's output
is OS-plausible.

Usage:
    python3 scripts/run_noise_audit.py
    python3 scripts/run_noise_audit.py --skip-resampled
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.noise_realism_audit import (
    audit_synthetic_noise,
    audit_resampled_noise,
    build_comparison_table,
    format_comparison_table_md,
    get_benign_baseline_rates,
    save_audit_json,
)


def main():
    parser = argparse.ArgumentParser(
        description="Noise Realism Audit: compare violation rates across noise sources"
    )
    parser.add_argument(
        "--graph-size", type=int, default=2000,
        help="Target graph size for evaluation",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed",
    )
    parser.add_argument(
        "--skip-resampled", action="store_true",
        help="Skip resampled noise evaluation (if benign_resampler not yet available)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick run mode",
    )
    parser.add_argument(
        "--output", type=str, default="results/noise_realism_audit.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    if args.quick or os.environ.get("QUICK_MODE") == "1":
        args.graph_size = 500

    print("=" * 72)
    print("PHASE 3: Noise Realism Audit")
    print("=" * 72)
    print()

    # -------------------------------------------------------------------
    # Step 1: Get real-benign baseline rates
    # -------------------------------------------------------------------
    print("─" * 72)
    print("Step 1: Computing real-benign baseline violation rates...")
    print("─" * 72)
    t0 = time.time()
    benign_rates = get_benign_baseline_rates()
    print(f"  Completed in {time.time() - t0:.1f}s")
    for rule, rate in sorted(benign_rates.items()):
        emoji = "✅" if rate == 0.0 else "⚠️"
        print(f"  {emoji} {rule}: {rate:.6f}")
    print()

    # -------------------------------------------------------------------
    # Step 2: Audit synthetic noise
    # -------------------------------------------------------------------
    print("─" * 72)
    print("Step 2: Auditing synthetic mimicry noise...")
    print("─" * 72)
    t1 = time.time()
    synth_rows = audit_synthetic_noise(
        graph_size=args.graph_size,
        seed=args.seed,
        strengths=["light", "medium", "heavy"],
    )
    print(f"  Completed in {time.time() - t1:.1f}s")
    print(f"  {len(synth_rows)} measurements across 3 strengths × 15 rules")
    print()

    # -------------------------------------------------------------------
    # Step 3: Audit resampled noise (if available)
    # -------------------------------------------------------------------
    resamp_rows = None
    if not args.skip_resampled:
        print("─" * 72)
        print("Step 3: Auditing resampled benign noise...")
        print("─" * 72)
        try:
            t2 = time.time()
            resamp_rows = audit_resampled_noise(
                graph_size=args.graph_size,
                seed=args.seed,
                m_values=[100, 500, 1000],
            )
            print(f"  Completed in {time.time() - t2:.1f}s")
            print(f"  {len(resamp_rows)} measurements across 3 m-values × 15 rules")
        except ImportError as e:
            print(f"  ⚠️  Skipping resampled noise: {e}")
            resamp_rows = None
    else:
        print("─" * 72)
        print("Step 3: Skipping resampled noise (--skip-resampled)")
        print("─" * 72)
    print()

    # -------------------------------------------------------------------
    # Step 4: Build comparison table
    # -------------------------------------------------------------------
    print("=" * 72)
    print("COMPARISON TABLE")
    print("=" * 72)
    print()

    table = build_comparison_table(benign_rates, synth_rows, resamp_rows)
    md_table = format_comparison_table_md(table)
    print(md_table)
    print()

    # -------------------------------------------------------------------
    # Step 5: Diagnosis
    # -------------------------------------------------------------------
    print("=" * 72)
    print("DIAGNOSIS")
    print("=" * 72)

    # Count rules where synthetic noise has significantly higher violation rate
    implausible_rules = [
        r for r in table
        if r["gap_synthetic"] > 0.01
    ]
    plausible_rules = [
        r for r in table
        if r["gap_synthetic"] <= 0.01
    ]

    print(f"\n🔴 IMPLAUSIBLE synthetic noise ({len(implausible_rules)} rules with gap > 1%):")
    for r in implausible_rules:
        print(f"   {r['rule']}: benign={r['benign_rate']:.4f} → synth={r['synthetic_noise_rate']:.4f} (gap={r['gap_synthetic']:+.4f})")

    print(f"\n✅ PLAUSIBLE synthetic noise ({len(plausible_rules)} rules with gap ≤ 1%):")
    for r in plausible_rules:
        print(f"   {r['rule']}: benign={r['benign_rate']:.4f} → synth={r['synthetic_noise_rate']:.4f}")

    if resamp_rows:
        resamp_implausible = [r for r in table if r.get("gap_resampled", 0) > 0.01]
        resamp_plausible = [r for r in table if abs(r.get("gap_resampled", 0)) <= 0.01]
        print(f"\nResampled noise: {len(resamp_plausible)} plausible, {len(resamp_implausible)} implausible")

        if len(resamp_implausible) == 0:
            print("✅ Resampled noise closely matches real benign — resampler is CORRECT.")
        else:
            print("🔴 Resampled noise diverges from real benign — resampler may be BROKEN.")

    total_gap = sum(r["gap_synthetic"] for r in table)
    if len(implausible_rules) >= 5:
        print(f"\n🔴 CONCLUSION: Synthetic mimicry noise is OS-IMPLAUSIBLE.")
        print(f"   {len(implausible_rules)}/15 rules show elevated violation rates.")
        print(f"   The precision collapse under mimicry is a GENERATOR ARTIFACT.")
    elif len(implausible_rules) >= 2:
        print(f"\n⚠️  CONCLUSION: Synthetic mimicry noise is PARTIALLY implausible.")
    else:
        print(f"\n✅ CONCLUSION: Synthetic mimicry noise appears plausible.")

    # -------------------------------------------------------------------
    # Step 6: Save results
    # -------------------------------------------------------------------
    save_audit_json(table, synth_rows, resamp_rows, args.output)
    print(f"\nResults saved to {args.output}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
