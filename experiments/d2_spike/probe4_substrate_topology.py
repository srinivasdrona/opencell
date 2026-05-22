"""Probe 4: Substrate topology migration surface and mixed-topology behavior."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from vivarium.core.engine import Engine
from vivarium.core.process import Process


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)
OUT = ARTIFACT_DIR / "d2_probe4_results.json"

ROOT = Path(__file__).resolve().parents[2]


def count_surface() -> dict[str, Any]:
    py_files = list((ROOT / "opencell").rglob("*.py")) + list((ROOT / "tests").rglob("*.py"))
    files_with_substrates = 0
    occurrences_substrates_key = 0
    occurrences_dotted = 0
    dotted_re = re.compile(r"substrates\.")
    key_re = re.compile(r"[\"']substrates[\"']")
    for p in py_files:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        k = len(key_re.findall(txt))
        d = len(dotted_re.findall(txt))
        if k > 0 or d > 0:
            files_with_substrates += 1
        occurrences_substrates_key += k
        occurrences_dotted += d
    return {
        "files_scanned": len(py_files),
        "files_with_substrates_refs": files_with_substrates,
        "occurrences_substrates_key": occurrences_substrates_key,
        "occurrences_dotted_substrates": occurrences_dotted,
    }


class FlatWriter(Process):
    name = "flat_writer"

    def ports_schema(self):
        return {"substrates": {"ATP": {"_default": 0, "_updater": "accumulate", "_emit": True}}}

    def next_update(self, timestep, states):
        return {"substrates": {"ATP": 1}}


class NestedWriter(Process):
    name = "nested_writer"

    def ports_schema(self):
        return {
            "substrates": {
                "counts": {"ATP": {"_default": 0, "_updater": "accumulate", "_emit": True}}
            }
        }

    def next_update(self, timestep, states):
        return {"substrates": {"counts": {"ATP": 1}}}


def mixed_topology_test() -> dict[str, Any]:
    try:
        engine = Engine(
            processes={"flat": FlatWriter(), "nested": NestedWriter()},
            topology={
                "flat": {"substrates": ("substrates",)},
                "nested": {"substrates": ("substrates",)},
            },
            initial_state={"substrates": {"ATP": 0}},
            emit_step=1.0,
            display_info=False,
        )
        engine.update(2.0)
        ts = engine.emitter.get_timeseries()
        out: dict[str, Any] = {"ok": True, "error": ""}
        # Best-effort capture; key may differ depending on merge behavior.
        out["timeseries_keys"] = list(ts.get("substrates", {}).keys())
        return out
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)}


def main() -> None:
    result = {
        "probe": "probe4_substrate_topology",
        "migration_surface": count_surface(),
        "mixed_topology_result": mixed_topology_test(),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
