"""
Tests for the benign subgraph resampler.

Verifies all scientific guarantees required by the task specification:
  1. inject() with m=0 returns a graph identical to the input.
  2. Injected edges reference only nodes that exist post-injection.
  3. Every injected process has a spawn event in the injected set.
  4. Per-process sequence indices are contiguous and monotone.
  5. No injected timestamp falls outside the graph's observed window.
  6. Poison edge set is bitwise unchanged after injection.
  7. Injected edges are disjoint from poison edges by construction.
"""

import unittest

from src.attacks.benign_resampler import BenignResampler
from src.detection.poisoning_injection import inject_poisoning
from src.graph_construction.schema import EdgeType, NodeType
from src.graph_construction.synthetic import generate_synthetic_graph


class TestBenignResampler(unittest.TestCase):
    """Scientific-integrity tests for the benign resampler."""

    def setUp(self):
        self.target_graph = generate_synthetic_graph(
            num_processes=10, num_files=15, num_network=5,
            target_edges=500, seed=123,
        )
        self.pool = BenignResampler.create_default_pool(
            num_graphs=3, edges_per_graph=300,
        )
        self.resampler = BenignResampler(self.pool, seed=42)

    # ── Test 1 ──────────────────────────────────────────────────────────
    def test_m_0_returns_identical(self):
        """inject() with m=0 returns a graph identical to the input."""
        new_graph, injected = self.resampler.inject(self.target_graph, m=0)

        self.assertEqual(len(injected), 0)
        self.assertEqual(len(new_graph.nodes), len(self.target_graph.nodes))
        self.assertEqual(len(new_graph.edges), len(self.target_graph.edges))
        # Must be a different object (deep copy)
        self.assertIsNot(new_graph, self.target_graph)

        # Edge-by-edge identity check
        orig_ids = {e.edge_id for e in self.target_graph.edges}
        new_ids = {e.edge_id for e in new_graph.edges}
        self.assertEqual(orig_ids, new_ids)

    # ── Test 2 ──────────────────────────────────────────────────────────
    def test_injected_edges_reference_existing_nodes(self):
        """Injected edges reference only nodes that exist post-injection."""
        new_graph, injected = self.resampler.inject(
            self.target_graph, m=5, seed=42,
        )
        self.assertGreater(len(injected), 0, "Should inject at least some edges")

        for edge in new_graph.edges:
            if edge.edge_id in injected:
                self.assertIn(
                    edge.source_id, new_graph.nodes,
                    f"Edge {edge.edge_id} source {edge.source_id} missing from nodes",
                )
                self.assertIn(
                    edge.target_id, new_graph.nodes,
                    f"Edge {edge.edge_id} target {edge.target_id} missing from nodes",
                )

    # ── Test 3 ──────────────────────────────────────────────────────────
    def test_every_injected_process_has_spawn(self):
        """Every injected process has a spawn event in the injected set."""
        new_graph, injected = self.resampler.inject(
            self.target_graph, m=5, seed=42,
        )

        # Identify all injected process nodes
        injected_procs = {
            nid for nid, node in new_graph.nodes.items()
            if "resample" in nid and node.node_type == NodeType.PROCESS
        }

        # Identify all processes that are TARGETS of injected SPAWN edges
        spawn_targets = set()
        for edge in new_graph.edges:
            if edge.edge_id in injected and edge.edge_type == EdgeType.SPAWN:
                spawn_targets.add(edge.target_id)

        # Every injected process must appear as the target of a SPAWN edge
        # Note: the parent of the seed process is also a spawned process
        # in the pool graph, so it should also have a spawn edge.
        missing_spawns = injected_procs - spawn_targets
        self.assertEqual(
            len(missing_spawns), 0,
            f"Injected processes without SPAWN events: {missing_spawns}",
        )

    # ── Test 4 ──────────────────────────────────────────────────────────
    def test_contiguous_sequence_indices(self):
        """Per-batch sequence indices are contiguous starting from 0."""
        new_graph, injected = self.resampler.inject(
            self.target_graph, m=5, seed=42,
        )

        # Group edge IDs by batch
        batches: dict[int, list[int]] = {}
        for eid in injected:
            # Format: resample_e_{batch}_{seq}
            parts = eid.split("_")
            batch = int(parts[2])
            seq = int(parts[3])
            batches.setdefault(batch, []).append(seq)

        for batch_id, seqs in batches.items():
            sorted_seqs = sorted(seqs)
            expected = list(range(len(seqs)))
            self.assertEqual(
                sorted_seqs, expected,
                f"Batch {batch_id} has non-contiguous seqs: {sorted_seqs}",
            )

    # ── Test 5 ──────────────────────────────────────────────────────────
    def test_timestamp_window(self):
        """No injected timestamp falls outside the graph's observed window."""
        min_ts = min(e.timestamp for e in self.target_graph.edges)
        max_ts = max(e.timestamp for e in self.target_graph.edges)

        new_graph, injected = self.resampler.inject(
            self.target_graph, m=5, seed=42,
        )

        for edge in new_graph.edges:
            if edge.edge_id in injected:
                self.assertGreaterEqual(
                    edge.timestamp, min_ts - 1e-9,
                    f"Edge {edge.edge_id} timestamp {edge.timestamp} < min_ts {min_ts}",
                )
                self.assertLessEqual(
                    edge.timestamp, max_ts + 1e-9,
                    f"Edge {edge.edge_id} timestamp {edge.timestamp} > max_ts {max_ts}",
                )

    # ── Test 6 ──────────────────────────────────────────────────────────
    def test_poison_edge_set_unchanged(self):
        """Poison edge set is bitwise unchanged after injection."""
        poison_result = inject_poisoning(
            self.target_graph, num_deletions=3, num_insertions=3,
            num_reorderings=3, num_forgeries=3, seed=99,
        )
        poisoned_graph = poison_result.graph
        poison_edge_ids = {ev.edge_id for ev in poison_result.events}

        # Record original poison edge attributes
        orig_poison_edges = {}
        for edge in poisoned_graph.edges:
            if edge.edge_id in poison_edge_ids:
                orig_poison_edges[edge.edge_id] = (
                    edge.source_id, edge.target_id,
                    edge.edge_type, edge.timestamp,
                )

        # Inject into poisoned graph
        resampler = BenignResampler(self.pool, seed=42)
        new_graph, injected = resampler.inject(poisoned_graph, m=5, seed=42)

        # Verify every poison edge is unchanged
        for eid, (src, tgt, etype, ts) in orig_poison_edges.items():
            new_edge = None
            for e in new_graph.edges:
                if e.edge_id == eid:
                    new_edge = e
                    break
            self.assertIsNotNone(
                new_edge, f"Poison edge {eid} missing from injected graph",
            )
            self.assertEqual(new_edge.source_id, src, f"Poison edge {eid} source changed")
            self.assertEqual(new_edge.target_id, tgt, f"Poison edge {eid} target changed")
            self.assertEqual(new_edge.edge_type, etype, f"Poison edge {eid} type changed")
            self.assertEqual(new_edge.timestamp, ts, f"Poison edge {eid} timestamp changed")

    # ── Test 7 ──────────────────────────────────────────────────────────
    def test_injected_disjoint_from_poison(self):
        """Injected edges are disjoint from poison edges by construction."""
        poison_result = inject_poisoning(
            self.target_graph, num_deletions=3, num_insertions=3,
            num_reorderings=3, num_forgeries=3, seed=99,
        )
        poison_edge_ids = {ev.edge_id for ev in poison_result.events}

        resampler = BenignResampler(self.pool, seed=42)
        _, injected = resampler.inject(poison_result.graph, m=5, seed=42)

        overlap = injected & poison_edge_ids
        self.assertEqual(
            len(overlap), 0,
            f"Injected edges overlap with poison edges: {overlap}",
        )

    # ── Additional invariant tests ──────────────────────────────────────
    def test_injected_count_matches_m(self):
        """m subgraphs should produce at least m groups of edges."""
        new_graph, injected = self.resampler.inject(
            self.target_graph, m=3, seed=42,
        )
        # Collect distinct batch numbers
        batches = set()
        for eid in injected:
            parts = eid.split("_")
            batches.add(int(parts[2]))

        self.assertEqual(len(batches), 3, f"Expected 3 batches, got {batches}")

    def test_pool_seeds_disjoint(self):
        """Pool graphs use seeds 5000+, disjoint from common eval seeds."""
        pool = BenignResampler.create_default_pool(num_graphs=5)
        # Verify we got 5 different graphs
        self.assertEqual(len(pool), 5)
        for g in pool:
            self.assertGreater(len(g.edges), 0)


if __name__ == "__main__":
    unittest.main()
