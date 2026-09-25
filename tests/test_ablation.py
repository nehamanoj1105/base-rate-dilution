"""
Unit tests for Phase 9 Ablation Experiments (Experiment E & F).
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import pytest

from src.eval.detector_registry import get_detector, DETECTOR_REGISTRY


def test_all_five_detectors_registered():
    """Asserts that all 5 required detector configurations are registered and instantiable."""
    required_keys = ["rule_hard", "rule_all", "graphsage_baseline", "graphsage_inv_features", "gated_sage"]
    for key in required_keys:
        assert key in DETECTOR_REGISTRY
        detector = get_detector(key, seed=42)
        assert detector.name is not None


def test_ablation_artifacts_exist():
    """Asserts that all Phase 9 ablation output files and figures exist."""
    assert os.path.exists("results/ablation_dilution.csv")
    assert os.path.exists("results/alpha_by_configuration.json")
    assert os.path.exists("results/figs/ablation_precision_vs_m.png")
    assert os.path.exists("results/figs/tradeoff_frontier.png")
    assert os.path.exists("docs/ABLATION.md")


def test_ablation_csv_schema():
    """Asserts that results/ablation_dilution.csv has required columns."""
    csv_path = Path("results/ablation_dilution.csv")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        assert header is not None
        required_cols = ["detector", "detector_key", "m", "seed", "precision", "recall", "f1", "roc_auc", "pr_auc"]
        for col in required_cols:
            assert col in header
