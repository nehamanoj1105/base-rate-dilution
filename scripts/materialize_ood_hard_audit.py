"""Materialize the OOD per-rule HARD violation audit."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/ood_crossscenario.json"
CSV_PATH = ROOT / "results/ood_hard_violation_audit.csv"
JSON_PATH = ROOT / "results/ood_hard_violation_audit.json"


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = payload.get("hard_violation_audit", [])
    grouped: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"violations": 0, "opportunities": 0}
    )
    for row in rows:
        key = (row["direction"], row["noise_model"], row["rule_name"])
        grouped[key]["violations"] += int(row["violations"])
        grouped[key]["opportunities"] += int(row["opportunities"])

    output = []
    for (direction, noise_model, rule_name), totals in sorted(grouped.items()):
        opportunities = totals["opportunities"]
        output.append({
            "direction": direction,
            "noise_model": noise_model,
            "rule_name": rule_name,
            "violations": totals["violations"],
            "opportunities": opportunities,
            "violation_rate": totals["violations"] / opportunities if opportunities else 0.0,
        })

    fields = ["direction", "noise_model", "rule_name", "violations", "opportunities", "violation_rate"]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    JSON_PATH.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(output)} aggregate HARD-rule rows.")


if __name__ == "__main__":
    main()
