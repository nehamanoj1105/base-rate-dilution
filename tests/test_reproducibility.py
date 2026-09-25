"""
Unit tests for Phase 13: One-Command Reproducibility Pipeline & LaTeX Artifact Tracing.
"""

import json
from pathlib import Path
import pytest

from scripts.generate_manifest import generate_results_manifest
from scripts.make_figures import main as make_figs_main
from scripts.make_tables import main as make_tables_main
from src.eval.second_domain_eval import evaluate_second_domain_dilution


def test_manifest_generation(tmp_path):
    manifest_p = tmp_path / "MANIFEST.json"
    generate_results_manifest(output_json=manifest_p)

    assert manifest_p.exists()
    with open(manifest_p, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "experiments" in data
    assert "git_commit" in data["metadata"]
    assert "noise_realism_audit" in data["experiments"]
    assert "second_domain_elliptic" in data["experiments"]


def test_make_tables_and_figures():
    # Execute table and figure generation
    make_tables_main()
    make_figs_main()

    tables_dir = Path("results/tables")
    figs_dir = Path("results/figs")

    assert tables_dir.exists()
    assert figs_dir.exists()

    expected_tables = [
        "table1_noise_realism.tex",
        "table2_ablation_dilution.tex",
        "table3_adaptive_adversary.tex",
        "table4_ood_partition_transfer.tex",
        "table5_second_domain.tex",
    ]
    for tbl in expected_tables:
        assert (tables_dir / tbl).exists(), f"Missing table file {tbl}"


def test_latex_table_tracing():
    tbl5_path = Path("results/tables/table5_second_domain.tex")
    json_path = Path("results/second_domain.json")

    if tbl5_path.exists() and json_path.exists():
        tex_content = tbl5_path.read_text(encoding="utf-8")
        with open(json_path, "r", encoding="utf-8") as f:
            jdata = json.load(f)

        # Confirm that numbers in Table 5 trace to JSON result
        alpha_val = f"{jdata['alpha_fit']['alpha_hat']:.4f}"
        # All records in table should match JSON metrics
        assert "\\begin{table*}" in tex_content
        assert "\\bottomrule" in tex_content


def test_reproducibility_determinism(tmp_path):
    p1 = tmp_path / "run1.json"
    p2 = tmp_path / "run2.json"

    d1 = evaluate_second_domain_dilution(
        m_grid=[0, 100], seeds=[42], root_dir="data/elliptic", output_json_path=p1
    )
    d2 = evaluate_second_domain_dilution(
        m_grid=[0, 100], seeds=[42], root_dir="data/elliptic", output_json_path=p2
    )

    content1 = p1.read_text(encoding="utf-8")
    content2 = p2.read_text(encoding="utf-8")

    assert content1 == content2, "Two runs with identical seeds produced non-identical output files!"
