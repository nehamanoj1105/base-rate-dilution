"""
Benign subgraph resampler for base-rate dilution experiments.

Injects contiguous process-tree subgraphs drawn from a held-out benign pool
into a target provenance graph. Every injected process carries its own SPAWN
event so the injected subgraph satisfies all 11 HARD invariants by construction.

Scientific constraints
  - Pool seeds are 5000-5999, disjoint from evaluation seeds.
  - No attack labels, existing node IDs, or target timestamps are consulted
    when building the subgraph.
  - Injection never modifies, reorders, or relabels any existing edge.
"""

from __future__ import annotations

import copy
import random
from typing import Optional

from ..graph_construction.schema import (
    EdgeType,
    NodeType,
    ProvenanceEdge,
    ProvenanceGraph,
    ProvenanceNode,
)
from ..graph_construction.synthetic import generate_synthetic_graph


class BenignResampler:
    """Samples contiguous benign subgraphs and injects them into a target graph."""

    def __init__(self, pool_graphs: list[ProvenanceGraph], seed: int = 42):
        self.pool_graphs = pool_graphs
        self.seed = seed
        self.batch_counter = 0
        self._activity_maps: dict[int, dict[str, list[ProvenanceEdge]]] = {}
        activity_types = {
            EdgeType.READ, EdgeType.WRITE, EdgeType.CONNECT,
            EdgeType.DELETE, EdgeType.EXECUTE,
        }
        for pg in pool_graphs:
            act_map: dict[str, list[ProvenanceEdge]] = {}
            for edge in pg.edges:
                if edge.edge_type in activity_types:
                    act_map.setdefault(edge.source_id, []).append(edge)
            self._activity_maps[id(pg)] = act_map

    @classmethod
    def create_default_pool(
        cls, num_graphs: int = 10, edges_per_graph: int = 500
    ) -> list[ProvenanceGraph]:
        """Create a held-out benign pool using seeds 5000-5999."""
        pool = []
        for i in range(num_graphs):
            pool.append(
                generate_synthetic_graph(
                    num_processes=max(20, edges_per_graph // 10),
                    num_files=max(30, edges_per_graph // 5),
                    num_network=max(8, edges_per_graph // 20),
                    target_edges=edges_per_graph,
                    seed=5000 + i,
                )
            )
        return pool

    def _extract_process_tree(
        self, pool_graph: ProvenanceGraph, rng: random.Random
    ) -> tuple[list[ProvenanceEdge], set[str], str]:
        """
        Extract a contiguous process tree from a pool graph.

        Returns (edges, node_ids, root_id) where:
        - root_id is the tree root process (has no SPAWN edge in the extracted set;
          will be mapped to an existing target-graph process during injection)
        - Every other process in node_ids has a SPAWN edge in edges
        - The tree includes the seed process, its children, and all
          file/socket activity of the seed process and its children
        """
        all_spawns = [e for e in pool_graph.edges if e.edge_type == EdgeType.SPAWN]
        if not all_spawns:
            return [], set(), ""

        # Build spawn-tree lookup: child -> spawn_edge
        spawn_of: dict[str, ProvenanceEdge] = {}
        for e in all_spawns:
            spawn_of[e.target_id] = e

        # Pick a seed process that HAS a spawn edge (i.e. is not the root)
        spawned_procs = list(spawn_of.keys())
        if not spawned_procs:
            return [], set(), ""

        seed_proc_id = rng.choice(spawned_procs)

        # Collect processes: seed + its children
        active_procs = {seed_proc_id}
        child_spawns = [e for e in all_spawns if e.source_id == seed_proc_id]
        for cs in child_spawns:
            active_procs.add(cs.target_id)

        # Collect edges and trace spawn chain upward
        extracted_edges: list[ProvenanceEdge] = []
        extracted_node_ids: set[str] = set()
        all_procs = set(active_procs)  # all process IDs including ancestors

        # Spawn edges for seed + children
        for pid in active_procs:
            if pid in spawn_of:
                sp = spawn_of[pid]
                extracted_edges.append(sp)
                extracted_node_ids.add(sp.target_id)
                extracted_node_ids.add(sp.source_id)
                # Track the parent
                parent = sp.source_id
                if parent not in all_procs:
                    all_procs.add(parent)

        # Chase upward: if the parent itself has a spawn edge, include it
        frontier = {
            pid for pid in all_procs
            if pid not in {e.target_id for e in extracted_edges if e.edge_type == EdgeType.SPAWN}
            and pid in spawn_of
        }
        while frontier:
            new_frontier: set[str] = set()
            for pid in frontier:
                sp = spawn_of[pid]
                extracted_edges.append(sp)
                extracted_node_ids.add(sp.target_id)
                parent = sp.source_id
                extracted_node_ids.add(parent)
                if parent not in all_procs:
                    all_procs.add(parent)
                    if parent in spawn_of:
                        new_frontier.add(parent)
            frontier = new_frontier

        # Find the root: the one process that has no SPAWN edge as target
        spawned_set = {e.target_id for e in extracted_edges if e.edge_type == EdgeType.SPAWN}
        root_ids = [
            pid for pid in all_procs
            if pid not in spawned_set
            and pid in pool_graph.nodes
            and pool_graph.nodes[pid].node_type == NodeType.PROCESS
        ]
        root_id = root_ids[0] if root_ids else ""

        # Activity edges (READ/WRITE/CONNECT/DELETE/EXECUTE) from seed + children
        act_map = self._activity_maps.get(id(pool_graph))
        if act_map is not None:
            for pid in active_procs:
                for edge in act_map.get(pid, []):
                    extracted_edges.append(edge)
                    extracted_node_ids.add(edge.source_id)
                    extracted_node_ids.add(edge.target_id)
        else:
            activity_types = {
                EdgeType.READ, EdgeType.WRITE, EdgeType.CONNECT,
                EdgeType.DELETE, EdgeType.EXECUTE,
            }
            for edge in pool_graph.edges:
                if edge.source_id in active_procs and edge.edge_type in activity_types:
                    extracted_edges.append(edge)
                    extracted_node_ids.add(edge.source_id)
                    extracted_node_ids.add(edge.target_id)

        return extracted_edges, extracted_node_ids, root_id

    def inject_in_place(
        self, graph: ProvenanceGraph, m: int, seed: int | None = None
    ) -> tuple[ProvenanceGraph, set[str]]:
        """
        Inject m benign subgraphs into graph in place (modifying graph).

        Returns (graph, injected_edge_ids).
        """
        rng = random.Random(seed)

        if m == 0:
            return graph, set()

        # Determine target timestamp window
        if not graph.edges:
            min_ts, max_ts = 0.0, 1.0
        else:
            min_ts = min(e.timestamp for e in graph.edges)
            max_ts = max(e.timestamp for e in graph.edges)

        # Identify existing process nodes in target graph for root mapping
        target_procs = [
            nid for nid, n in graph.nodes.items()
            if n.node_type == NodeType.PROCESS
        ]
        if not target_procs:
            target_procs = list(graph.nodes.keys())

        # Pre-map spawn times of target procs
        proc_spawn_ts: dict[str, float] = {}
        for e in graph.edges:
            e_type = (e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)).lower()
            if e_type == "spawn":
                proc_spawn_ts[e.target_id] = e.timestamp

        injected_edge_ids: set[str] = set()

        for _ in range(m):
            pool_graph = rng.choice(self.pool_graphs)

            extracted_edges, extracted_node_ids, root_id = (
                self._extract_process_tree(pool_graph, rng)
            )
            if not extracted_edges:
                continue

            # --- Build node mapping ---
            node_mapping: dict[str, str] = {}
            target_proc = rng.choice(target_procs)
            if root_id and root_id in extracted_node_ids:
                node_mapping[root_id] = target_proc

            for nid in sorted(extracted_node_ids):
                if nid in node_mapping:
                    continue  # root already mapped
                n_type = pool_graph.nodes[nid].node_type.value
                node_mapping[nid] = (
                    f"resample_{n_type}_{self.batch_counter}_{len(node_mapping)}"
                )

            # --- Rebase timestamps ---
            extracted_edges.sort(key=lambda x: x.timestamp)
            orig_min = extracted_edges[0].timestamp
            orig_max = extracted_edges[-1].timestamp

            seq_duration = orig_max - orig_min
            root_spawn = proc_spawn_ts.get(target_proc, min_ts)
            min_start = max(min_ts, root_spawn)

            window = max(1.0, max_ts - min_start)
            scale = window / seq_duration if seq_duration > window else 1.0

            effective_duration = seq_duration * scale
            max_start = max(min_start, max_ts - effective_duration)
            start_ts = rng.uniform(min_start, max_start)

            # --- Add NEW nodes (skip root — it's an existing node) ---
            for nid in extracted_node_ids:
                mapped_id = node_mapping[nid]
                if mapped_id in graph.nodes:
                    continue  # root or duplicate — already exists
                orig_node = pool_graph.nodes[nid]
                new_node = ProvenanceNode(
                    node_id=mapped_id,
                    node_type=orig_node.node_type,
                    label=orig_node.label,
                    attributes=orig_node.attributes.copy(),
                )
                graph.add_node(new_node)

            # --- Add edges with sequential IDs ---
            seq = 0
            for e in extracted_edges:
                new_ts = start_ts + (e.timestamp - orig_min) * scale
                new_edge = ProvenanceEdge(
                    edge_id=f"resample_e_{self.batch_counter}_{seq}",
                    source_id=node_mapping[e.source_id],
                    target_id=node_mapping[e.target_id],
                    edge_type=e.edge_type,
                    timestamp=new_ts,
                    attributes=e.attributes.copy(),
                )
                injected_edge_ids.add(new_edge.edge_id)
                graph.add_edge(new_edge)
                seq += 1

            self.batch_counter += 1

        return graph, injected_edge_ids

    def inject(
        self, graph: ProvenanceGraph, m: int, seed: int | None = None
    ) -> tuple[ProvenanceGraph, set[str]]:
        """
        Inject m benign subgraphs into a copy of graph.

        Returns (new_graph, injected_edge_ids).
        - new_graph contains all original edges unchanged + injected edges.
        - injected_edge_ids is the set of new edge IDs.
        """
        # Deep copy the target graph so originals are never modified
        new_graph = ProvenanceGraph(
            nodes={k: copy.deepcopy(v) for k, v in graph.nodes.items()},
            edges=[copy.deepcopy(e) for e in graph.edges],
        )
        return self.inject_in_place(new_graph, m, seed)

        # Identify existing process nodes in target graph for root mapping
        target_procs = [
            nid for nid, n in graph.nodes.items()
            if n.node_type == NodeType.PROCESS
        ]
        if not target_procs:
            target_procs = list(graph.nodes.keys())

        # Pre-map spawn times of target procs
        proc_spawn_ts: dict[str, float] = {}
        for e in graph.edges:
            e_type = (e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)).lower()
            if e_type == "spawn":
                proc_spawn_ts[e.target_id] = e.timestamp

        injected_edge_ids: set[str] = set()

        for _ in range(m):
            pool_graph = rng.choice(self.pool_graphs)

            extracted_edges, extracted_node_ids, root_id = (
                self._extract_process_tree(pool_graph, rng)
            )
            if not extracted_edges:
                continue

            # --- Build node mapping ---
            node_mapping: dict[str, str] = {}
            target_proc = rng.choice(target_procs)
            if root_id and root_id in extracted_node_ids:
                node_mapping[root_id] = target_proc

            for nid in sorted(extracted_node_ids):
                if nid in node_mapping:
                    continue  # root already mapped
                n_type = pool_graph.nodes[nid].node_type.value
                node_mapping[nid] = (
                    f"resample_{n_type}_{self.batch_counter}_{len(node_mapping)}"
                )

            # --- Rebase timestamps ---
            extracted_edges.sort(key=lambda x: x.timestamp)
            orig_min = extracted_edges[0].timestamp
            orig_max = extracted_edges[-1].timestamp

            seq_duration = orig_max - orig_min
            root_spawn = proc_spawn_ts.get(target_proc, min_ts)
            min_start = max(min_ts, root_spawn)

            window = max(1.0, max_ts - min_start)
            scale = window / seq_duration if seq_duration > window else 1.0

            effective_duration = seq_duration * scale
            max_start = max(min_start, max_ts - effective_duration)
            start_ts = rng.uniform(min_start, max_start)

            # --- Add NEW nodes (skip root — it's an existing node) ---
            for nid in extracted_node_ids:
                mapped_id = node_mapping[nid]
                if mapped_id in new_graph.nodes:
                    continue  # root or duplicate — already exists
                orig_node = pool_graph.nodes[nid]
                new_node = ProvenanceNode(
                    node_id=mapped_id,
                    node_type=orig_node.node_type,
                    label=orig_node.label,
                    attributes=copy.deepcopy(orig_node.attributes),
                )
                new_graph.add_node(new_node)

            # --- Add edges with sequential IDs ---
            seq = 0
            for e in extracted_edges:
                new_ts = start_ts + (e.timestamp - orig_min) * scale
                new_edge = ProvenanceEdge(
                    edge_id=f"resample_e_{self.batch_counter}_{seq}",
                    source_id=node_mapping[e.source_id],
                    target_id=node_mapping[e.target_id],
                    edge_type=e.edge_type,
                    timestamp=new_ts,
                    attributes=copy.deepcopy(e.attributes),
                )
                new_graph.add_edge(new_edge)
                injected_edge_ids.add(new_edge.edge_id)
                seq += 1

            self.batch_counter += 1

        return new_graph, injected_edge_ids


def inject_resampled_benign_noise(
    graph: ProvenanceGraph,
    donor_graph: ProvenanceGraph | None = None,
    target_added_edges: int = 100,
    seed: int = 42,
) -> ProvenanceGraph:
    """Convenience helper function to inject resampled benign noise into target graph."""
    if target_added_edges <= 0:
        return graph

    if donor_graph is not None:
        pool = [donor_graph]
    else:
        pool = BenignResampler.create_default_pool(num_graphs=5, edges_per_graph=300)

    resampler = BenignResampler(pool_graphs=pool, seed=seed)
    m_subgraphs = max(1, target_added_edges // 10)
    new_graph, _ = resampler.inject(graph, m=m_subgraphs, seed=seed)
    return new_graph


