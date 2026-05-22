"""Probe 5: Cost/surprises of adding a 4th process to chassis composer."""

from __future__ import annotations

import json
import importlib.util
import time
from pathlib import Path
from typing import Any


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)
OUT = ARTIFACT_DIR / "d2_probe5_results.json"
ROOT = Path(__file__).resolve().parents[2]


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def token_count(path: Path, token: str) -> int:
    return path.read_text(encoding="utf-8", errors="ignore").count(token)


def load_builder():
    mod_path = ROOT / "experiments" / "d2_spike" / "karr_composite_4process.py"
    spec = importlib.util.spec_from_file_location("karr_composite_4process", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {mod_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_karr_m1_m2_m3_decay_engine


def main() -> None:
    base_file = ROOT / "opencell" / "vivarium" / "karr_composite.py"
    probe_file = ROOT / "experiments" / "d2_spike" / "karr_composite_4process.py"
    base_loc = line_count(base_file)
    probe_loc = line_count(probe_file)
    token_hits = token_count(probe_file, "protein_decay_stub")
    t0 = time.perf_counter()
    ok = True
    err = ""
    final_time_points = 0
    try:
        build_karr_m1_m2_m3_decay_engine = load_builder()
        engine = build_karr_m1_m2_m3_decay_engine(time_step_s=1.0, emit_step_s=1.0)
        engine.update(5.0)
        ts = engine.emitter.get_timeseries()
        final_time_points = len(ts["time"])
    except Exception as e:  # noqa: BLE001
        ok = False
        err = repr(e)
    wall_s = time.perf_counter() - t0
    result: dict[str, Any] = {
        "probe": "probe5_third_process",
        "base_composer_file": str(base_file.relative_to(ROOT)),
        "probe_composer_file": str(probe_file.relative_to(ROOT)),
        "base_loc": base_loc,
        "probe_loc": probe_loc,
        "added_loc": probe_loc - base_loc,
        "protein_decay_stub_token_hits": token_hits,
        "engine_run_ok": ok,
        "engine_run_error": err,
        "wall_seconds": wall_s,
        "timeseries_time_points": final_time_points,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
