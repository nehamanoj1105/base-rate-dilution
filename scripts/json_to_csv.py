#!/usr/bin/env python3
"""
Convert a DARPA TC E3 THEIA JSON dump into the same CSV format that
parse_cdm_files_to_csv() produces from Avro .bin files.

The JSON lines are the Avro union-resolved records as serialized by the
TA3 Java consumer.  fastavro surfaces union branches as {branch: value};
the JSON dump does the same, so we unwrap each union before handing the
record to the existing parser logic.

Usage:
    python3 scripts/json_to_csv.py <input.json> <nodes_out.csv> <edges_out.csv>
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.graph_construction.cdm_parser import (
    _event_to_edge,
    _infer_record_type,
    _object_to_node,
    _subject_to_node,
)


_UNION_WRAPPER_KEYS = {
    "com.bbn.tc.schema.avro.cdm18.UUID",
    "com.bbn.tc.schema.avro.cdm18.Event",
    "com.bbn.tc.schema.avro.cdm18.Subject",
    "com.bbn.tc.schema.avro.cdm18.Object",
    "com.bbn.tc.schema.avro.cdm18.FileObject",
    "com.bbn.tc.schema.avro.cdm18.Principal",
    "com.bbn.tc.schema.avro.cdm18.Host",
    "com.bbn.tc.schema.avro.cdm18.NetFlowObject",
    "com.bbn.tc.schema.avro.cdm18.MemoryObject",
    "com.bbn.tc.schema.avro.cdm18.Edge",
    "com.bbn.tc.schema.avro.cdm18.Time",
    "com.bbn.tc.schema.avro.cdm18.MonotonicTime",
    "com.bbn.tc.schema.avro.cdm18.Thread",
    "com.bbn.tc.schema.avro.cdm18.Properties",
    "com.bbn.tc.schema.avro.cdm20.UUID",
}


def _unwrap(value):
    if isinstance(value, dict):
        keys = list(value.keys())
        if len(keys) == 1 and (
            keys[0] in _UNION_WRAPPER_KEYS
            or keys[0] in ("long", "int", "string", "boolean", "bytes", "double", "float")
        ):
            return _unwrap(value[keys[0]])
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def _iter_datum(path: Path):
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            datum = record.get("datum", record)
            if isinstance(datum, dict) and len(datum) == 1:
                inner_key = next(iter(datum))
                if inner_key.startswith("com.bbn.tc.schema.avro"):
                    datum = datum[inner_key]
            yield _unwrap(datum)


def convert(json_path: Path, nodes_out: Path, edges_out: Path):
    known_node_ids: set[str] = set()
    node_count = 0

    with open(nodes_out, "w", newline="") as nf:
        writer = csv.writer(nf)
        writer.writerow(["node_id", "node_type", "label", "cdm_type"])
        for datum in _iter_datum(json_path):
            record_type = _infer_record_type(datum)
            node = None
            if record_type == "subject":
                node = _subject_to_node(datum)
            elif record_type == "object":
                node = _object_to_node(datum)
            if node and node.node_id not in known_node_ids:
                known_node_ids.add(node.node_id)
                writer.writerow([
                    node.node_id,
                    node.node_type.value,
                    node.label,
                    node.attributes.get("cdm_type", ""),
                ])
                node_count += 1
    print(f"Pass 1 complete: {node_count} nodes written to {nodes_out}")

    edge_count = 0
    skipped = 0

    with open(edges_out, "w", newline="") as ef:
        writer = csv.writer(ef)
        writer.writerow(["edge_id", "source_id", "target_id", "edge_type", "timestamp", "sequence"])
        for datum in _iter_datum(json_path):
            if _infer_record_type(datum) != "event":
                continue
            edge = _event_to_edge(datum)
            if edge is None:
                continue
            if edge.source_id not in known_node_ids or edge.target_id not in known_node_ids:
                skipped += 1
                continue
            writer.writerow([
                edge.edge_id,
                edge.source_id,
                edge.target_id,
                edge.edge_type.value,
                edge.timestamp,
                edge.attributes.get("sequence", 0),
            ])
            edge_count += 1

    print(f"Pass 2 complete: {edge_count} edges written, {skipped} skipped")
    return node_count, edge_count, skipped


def main():
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <input.json> <nodes_out.csv> <edges_out.csv>")
        sys.exit(1)
    json_path = Path(sys.argv[1])
    nodes_out = Path(sys.argv[2])
    edges_out = Path(sys.argv[3])
    nodes_out.parent.mkdir(parents=True, exist_ok=True)
    edges_out.parent.mkdir(parents=True, exist_ok=True)
    convert(json_path, nodes_out, edges_out)


if __name__ == "__main__":
    main()
