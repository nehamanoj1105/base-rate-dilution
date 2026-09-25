"""
Unit tests for Phase 12: Second-Domain Generality Benchmark (Elliptic Graph Anomaly).
"""

from pathlib import Path
import pytest

from src.eval.second_domain_eval import evaluate_second_domain_dilution


def test_elliptic_small_scale_dilution(tmp_path):
    output_json = tmp_path / "second_domain_test.json"

    data = evaluate_second_domain_dilution(
        m_grid=[0, 100],
        seeds=[42],
        root_dir="data/elliptic",
        output_json_path=output_json,
    )

    assert output_json.exists()
    assert data["dataset"] == "EllipticBitcoinDataset"
    assert "alpha_fit" in data
    assert "sweep_records" in data
    assert len(data["sweep_records"]) == 2
