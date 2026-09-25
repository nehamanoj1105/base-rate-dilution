"""
Unit tests for Full-Scale Rerun & Frozen Threshold Architecture (Task 13 follow-up).
"""

import json
from pathlib import Path
import pytest

from src.eval.detector_registry import get_detector, get_frozen_threshold, load_frozen_thresholds
from src.eval.alpha_estimator import fit_alpha_exponent


def test_frozen_threshold_constancy():
    """Asserts operating thresholds are identical across seeds and m values for all detectors."""
    frozen_cfg = load_frozen_thresholds()
    assert "graphsage_baseline" in frozen_cfg
    assert "gated_sage" in frozen_cfg

    expected_gs_thresh = frozen_cfg["graphsage_baseline"]
    expected_gated_thresh = frozen_cfg["gated_sage"]

    # Verify detector adapters instantiate with exact frozen thresholds across multiple seeds
    for seed in [0, 1, 2, 3, 4]:
        det_gs = get_detector("graphsage_baseline", seed=seed)
        assert det_gs.operating_threshold == expected_gs_thresh, (
            f"GraphSAGE threshold varied for seed {seed}! Expected {expected_gs_thresh}, got {det_gs.operating_threshold}"
        )

        det_gated = get_detector("gated_sage", seed=seed)
        assert det_gated.operating_threshold == expected_gated_thresh, (
            f"GatedSAGE threshold varied for seed {seed}! Expected {expected_gated_thresh}, got {det_gated.operating_threshold}"
        )


def test_non_degenerate_bootstrap_cis():
    """Asserts cluster bootstrap yields non-degenerate CIs (ci_upper > ci_lower) when n_seeds >= 5."""
    m_vals = [1000, 2500, 5000, 10000] * 5
    # Simulate realistic seed variance in precision across 5 seeds
    seeds = [0]*4 + [1]*4 + [2]*4 + [3]*4 + [4]*4
    precisions = [
        0.50, 0.30, 0.15, 0.08,  # seed 0
        0.55, 0.33, 0.18, 0.10,  # seed 1
        0.45, 0.28, 0.13, 0.06,  # seed 2
        0.52, 0.31, 0.16, 0.09,  # seed 3
        0.48, 0.29, 0.14, 0.07,  # seed 4
    ]

    fit_res = fit_alpha_exponent(m_vals, precisions, seeds=seeds, n_bootstrap=500)

    assert fit_res.ci_upper > fit_res.ci_lower, (
        f"CI collapsed to point! ci_lower={fit_res.ci_lower}, ci_upper={fit_res.ci_upper}"
    )
    assert (fit_res.ci_upper - fit_res.ci_lower) > 0.01
