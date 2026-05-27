from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.run_chassis_v6_32400t import DiagnosticCollector


@dataclass
class _DummyEntity:
    update: dict[str, Any]
    schema: dict[str, Any]

    def __post_init__(self) -> None:
        self.parameters = {"rng_seed": 0}

    def ports_schema(self) -> dict[str, Any]:
        return self.schema

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        return self.update


@dataclass
class _DummyComposite:
    entity: _DummyEntity
    topology_entry: dict[str, Any]

    def __post_init__(self) -> None:
        self.processes = {"dummy": self.entity}
        self.steps = {}
        self.topology = {"dummy": self.topology_entry}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_diagnostic_collector_records_writes_from_multiple_ports(tmp_path: Path) -> None:
    entity = _DummyEntity(
        update={
            "substrates": {"ATP": 12.0},
            "rna": {"counts": {"RNA_1": 3.0}},
        },
        schema={
            "substrates": {"ATP": {"_default": 0.0, "_updater": "set"}},
            "rna": {"counts": {"RNA_1": {"_default": 0.0, "_updater": "accumulate"}}},
        },
    )
    composite = _DummyComposite(
        entity=entity,
        topology_entry={
            "substrates": ("substrates",),
            "rna": ("rna",),
        },
    )
    collector = DiagnosticCollector(
        composite=composite,
        process_traces_dir=tmp_path / "process_traces",
        process_trace_stride=1,
        seed=11,
    )

    collector.set_tick(10)
    entity.next_update(
        1.0,
        {
            "substrates": {"ATP": 10.0},
            "rna": {"counts": {"RNA_1": 5.0}},
        },
    )
    collector.close()

    rows = _read_rows(tmp_path / "process_traces" / "dummy.csv")
    by_key = {row["substrate"]: float(row["delta"]) for row in rows}
    assert by_key["ATP"] == 2.0
    assert by_key["RNA_1"] == 3.0
    assert collector.per_tick_process_sums["ATP"] == 2.0
    assert "RNA_1" not in collector.per_tick_process_sums


def test_diagnostic_collector_skips_non_shared_ports_without_crashing(tmp_path: Path) -> None:
    entity = _DummyEntity(
        update={
            "substrates": {"ATP": 1.0},
            "local": {"debug_value": 5.0},
        },
        schema={
            "substrates": {"ATP": {"_default": 0.0, "_updater": "accumulate"}},
            "local": {"debug_value": {"_default": 0.0, "_updater": "accumulate"}},
        },
    )
    composite = _DummyComposite(
        entity=entity,
        topology_entry={
            "substrates": ("substrates",),
            "local": (),
        },
    )
    collector = DiagnosticCollector(
        composite=composite,
        process_traces_dir=tmp_path / "process_traces",
        process_trace_stride=1,
        seed=17,
    )

    collector.set_tick(3)
    returned_update = entity.next_update(1.0, {"substrates": {"ATP": 0.0}})
    collector.close()

    rows = _read_rows(tmp_path / "process_traces" / "dummy.csv")
    assert returned_update == entity.update
    assert len(rows) == 1
    assert rows[0]["substrate"] == "ATP"


def test_diagnostic_collector_can_emit_noop_heartbeat_for_traceability(tmp_path: Path) -> None:
    entity = _DummyEntity(
        update={
            "rna": {"counts": {}},
        },
        schema={
            "rna": {"counts": {"RNA_1": {"_default": 0.0, "_updater": "accumulate"}}},
        },
    )
    entity.parameters["emit_trace_heartbeat_on_noop"] = True
    composite = _DummyComposite(
        entity=entity,
        topology_entry={
            "rna": ("rna",),
        },
    )
    collector = DiagnosticCollector(
        composite=composite,
        process_traces_dir=tmp_path / "process_traces",
        process_trace_stride=1,
        seed=23,
    )

    collector.set_tick(7)
    entity.next_update(1.0, {"rna": {"counts": {"RNA_1": 0.0}}})
    collector.close()

    rows = _read_rows(tmp_path / "process_traces" / "dummy.csv")
    assert len(rows) == 1
    assert rows[0]["substrate"] == "__noop__"
    assert float(rows[0]["delta"]) == 0.0
