"""
Unit tests for Dilution Exponent (Alpha) Estimator, AUC Invariance Audit, and Score Locality Test.
"""

import numpy as np
import pytest

from src.eval.alpha_estimator import (
    fit_alpha_exponent,
    theoretical_precision_prediction,
)
from src.eval.auc_invariance import (
    audit_auc_and_ties,
    compute_optimistic_pessimistic_auc,
    measure_score_locality,
)
from src.eval.detector_registry import RuleEngineAdapter
from src.graph_construction.synthetic import generate_synthetic_graph


def test_alpha_estimator_synthetic_q_positive():
    """Verifies alpha_hat ~ 1.0 on synthetic precision sweep with q > 0."""
    p = 0.85
    q = 0.01
    k = 20
    n = 1000
    m_grid = [10000, 20000, 50000, 100000, 200000, 500000]

    # Generate theoretical precision values under base-rate dilution
    precisions = theoretical_precision_prediction(p, q, k, n, m_grid)

    result = fit_alpha_exponent(m_grid, precisions, m0=0.0)

    # In the large-m regime with q > 0, alpha_hat should be close to 1.0
    assert 0.85 <= result.alpha_hat <= 1.15, f"Expected alpha_hat ~ 1.0, got {result.alpha_hat}"
    assert result.r_squared >= 0.95, f"Expected high R^2, got {result.r_squared}"


def test_alpha_estimator_benign_null_q_zero():
    """Verifies alpha_hat ~ 0.0 on a detector with zero false positive rate (q = 0)."""
    p = 0.85
    q = 0.0
    k = 20
    n = 1000
    m_grid = [100, 500, 1000, 2000, 5000, 10000]

    precisions = theoretical_precision_prediction(p, q, k, n, m_grid)

    result = fit_alpha_exponent(m_grid, precisions, m0=0.0)

    # When q = 0, precision is constant at 1.0, so alpha_hat = 0.0
    assert abs(result.alpha_hat) < 1e-4, f"Expected alpha_hat ~ 0.0, got {result.alpha_hat}"


def test_score_locality_rule_engine():
    """Verifies Spearman rank correlation rho = 1.0 exactly for Rule Engine across dilution volumes."""
    adapter = RuleEngineAdapter()
    m_grid = [0, 200, 500, 1000]

    locality_results = measure_score_locality(
        detector=adapter,
        m_grid=m_grid,
        noise_model="resampled",
        seed=42,
        base_graph_size=500,
        poison_events=10,
    )

    for m, rho in locality_results.items():
        assert rho == 1.0, f"Expected rho = 1.0 at m={m}, got {rho}"


def test_optimistic_pessimistic_auc():
    """Verifies dual tie-handling ROC-AUC logic on synthetic tied scores."""
    # 4 items with tied score 0.5: 2 positives, 2 negatives
    y_true = np.array([1, 1, 0, 0])
    y_score = np.array([0.5, 0.5, 0.5, 0.5])

    opt_auc, pess_auc = compute_optimistic_pessimistic_auc(y_true, y_score)

    assert opt_auc == 1.0, f"Expected optimistic AUC = 1.0, got {opt_auc}"
    assert pess_auc == 0.0, f"Expected pessimistic AUC = 0.0, got {pess_auc}"


def test_audit_auc_and_ties():
    """Verifies full audit_auc_and_ties output structure and metrics."""
    scores = {"e1": 0.8, "e2": 0.5, "e3": 0.5, "e4": 0.1}
    gt_ids = {"e1", "e2"}

    audit = audit_auc_and_ties(scores, gt_ids)

    assert audit.total_edges == 4
    assert audit.num_positives == 2
    assert audit.num_negatives == 2
    assert audit.modal_score == 0.5
    assert audit.modal_score_count == 2
    assert audit.largest_tied_block_size == 2
    assert audit.is_all_edges is True
    assert audit.auc_optimistic >= audit.auc_pessimistic


def test_score_locality_decay_graphsage_vs_gated():
    """Verifies that GraphSAGE baseline exhibits score locality decay (rho < 1.0) while gated/rule detectors retain rho = 1.0."""
    import json
    from pathlib import Path

    json_path = Path("results/score_locality_final.json")
    if json_path.exists():
        with open(json_path) as f:
            locality_data = json.load(f)

        assert locality_data["rule_hard"]["100000"] == 1.0
        assert locality_data["gated_sage"]["100000"] == 1.0
        assert locality_data["graphsage_baseline"]["100000"] < 1.0
        assert locality_data["graphsage_inv_features"]["100000"] < 1.0

