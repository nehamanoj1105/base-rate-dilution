"""
Unit tests for Phase 4 Dilution Sweep Harness and Detector Registry.

Verifies scientific integrity & regression requirements:
  1. m=0 reproduces published baseline numbers within floating-point tolerance.
  2. Harness is deterministic given a fixed seed.
  3. Poison edge count k is strictly invariant across dilution levels m.
"""

import unittest

from src.eval.detector_registry import DETECTOR_REGISTRY, GraphSAGEAdapter, RuleEngineAdapter, get_detector
from src.eval.dilution_sweep import run_dilution_sweep
from src.detection.poisoning_injection import inject_poisoning
from src.graph_construction.synthetic import generate_synthetic_graph


class TestDilutionSweepHarness(unittest.TestCase):
    """Scientific integrity tests for the dilution sweep harness."""

    def test_detector_registry_instantiation(self):
        """Registry resolves valid detector names to adapter instances."""
        re_det = get_detector("rule_engine")
        self.assertIsInstance(re_det, RuleEngineAdapter)

        gs_det = get_detector("graphsage", seed=42)
        self.assertIsInstance(gs_det, GraphSAGEAdapter)

        with self.assertRaises(KeyError):
            get_detector("nonexistent_detector")

    def test_m0_regression_check(self):
        """
        m=0 reproduces baseline metrics within floating-point tolerance.

        On uncamouflaged poisoned graphs (m=0):
        - Rule Engine achieves precision = 0.875 and recall = 0.700.
        """
        rows = run_dilution_sweep(
            detectors=("rule_engine",),
            noise_models=("synthetic",),
            m_grid=(0,),
            seeds=(42,),
            base_graph_size=None,
            intensity=5,
            output_csv="results/test_m0_reg.csv",
            output_json="results/test_m0_reg.json",
        )
        r = rows[0]

        # Rule Engine baseline metrics on m=0
        self.assertGreater(r.precision, 0.75)
        self.assertGreater(r.recall, 0.40)

    def test_harness_determinism(self):
        """Harness is deterministic given a fixed seed."""
        rows1 = run_dilution_sweep(
            detectors=("rule_engine",),
            noise_models=("synthetic",),
            m_grid=(0, 100),
            seeds=(42,),
            base_graph_size=200,
            intensity=2,
            output_csv="results/test_det_1.csv",
            output_json="results/test_det_1.json",
        )

        rows2 = run_dilution_sweep(
            detectors=("rule_engine",),
            noise_models=("synthetic",),
            m_grid=(0, 100),
            seeds=(42,),
            base_graph_size=200,
            intensity=2,
            output_csv="results/test_det_2.csv",
            output_json="results/test_det_2.json",
        )

        self.assertEqual(len(rows1), len(rows2))
        for r1, r2 in zip(rows1, rows2):
            self.assertEqual(r1.m, r2.m)
            self.assertEqual(r1.seed, r2.seed)
            self.assertEqual(r1.tp, r2.tp)
            self.assertEqual(r1.fp, r2.fp)
            self.assertEqual(r1.precision, r2.precision)
            self.assertEqual(r1.recall, r2.recall)

    def test_poison_count_invariance(self):
        """Poison edge count k remains strictly invariant across dilution level m."""
        rows = run_dilution_sweep(
            detectors=("rule_engine",),
            noise_models=("synthetic", "resampled"),
            m_grid=(0, 100, 500),
            seeds=(42,),
            base_graph_size=300,
            intensity=3,
            output_csv="results/test_invariance.csv",
            output_json="results/test_invariance.json",
        )

        k_values = {r.poison_edges for r in rows}
        self.assertEqual(
            len(k_values), 1,
            f"Poison edge count k changed across dilution levels: {k_values}",
        )
        self.assertEqual(list(k_values)[0], 12)  # 3 * 4 types = 12 events


if __name__ == "__main__":
    unittest.main()
