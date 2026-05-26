"""Full per-tick diagnostic probe.

Runs the v6 chassis for a short window. At every tick, captures:
  1. EVERY port returned by EVERY process's next_update (not just `substrates`)
  2. Selected substrate / mRNA / protein counts (the biology indicators)

Outputs per-tick CSVs — NO summary files. Every emit, every component.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opencell.vivarium.karr_composite import build_karr_chassis_v6  # noqa: E402
from vivarium.core.engine import Engine  # noqa: E402


def _flatten(d: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dict into dotted keys, keeping leaf scalars only."""
    out: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(_flatten(v, key))
    elif isinstance(d, (list, tuple)):
        for i, v in enumerate(d):
            key = f"{prefix}[{i}]"
            out.update(_flatten(v, key))
    else:
        out[prefix] = d
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    process_dir = out_dir / "process_updates"
    process_dir.mkdir(exist_ok=True)
    state_dir = out_dir / "state_snapshots"
    state_dir.mkdir(exist_ok=True)

    print(f"[probe] building chassis (seed={args.seed}) ...", flush=True)
    t0 = time.time()
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    print(f"[probe] composite built in {time.time()-t0:.1f}s", flush=True)

    entities: dict[str, Any] = {}
    entities.update(getattr(composite, "processes", {}))
    entities.update(getattr(composite, "steps", {}))

    # One CSV per entity. Every tick, every port, every leaf write — appended.
    writers: dict[str, csv.writer] = {}
    files: dict[str, Any] = {}
    for name in sorted(entities):
        f = (process_dir / f"{name}.csv").open("w", newline="", encoding="utf-8")
        w = csv.writer(f)
        w.writerow(["tick", "port", "key", "value"])
        writers[name] = w
        files[name] = f

    # Per-tick counters
    call_counts: dict[str, int] = defaultdict(int)
    nonempty_counts: dict[str, int] = defaultdict(int)
    exception_counts: dict[str, int] = defaultdict(int)
    current = {"tick": 0}

    # Patch every entity's next_update to dump ALL returned ports.
    for name, entity in entities.items():
        orig = entity.next_update

        def wrapped(timestep, states, *, _name=name, _orig=orig):
            tick = current["tick"]
            call_counts[_name] += 1
            try:
                upd = _orig(timestep, states)
            except Exception:  # noqa: BLE001
                exception_counts[_name] += 1
                raise
            if upd is None:
                upd = {}
            if isinstance(upd, dict) and upd:
                nonempty_counts[_name] += 1
                w = writers[_name]
                for port, port_payload in upd.items():
                    flat = _flatten(port_payload)
                    for key, value in flat.items():
                        if isinstance(value, (int, float, np.number)):
                            v = float(value)
                            if v == 0.0:
                                continue
                            w.writerow([tick, port, key, f"{v:.12g}"])
                        elif isinstance(value, (str, bool)):
                            w.writerow([tick, port, key, str(value)])
            return upd

        entity.next_update = wrapped

    # Seed rngs deterministically per entity
    children = np.random.SeedSequence(int(args.seed)).spawn(len(entities))
    for idx, name in enumerate(sorted(entities)):
        ent = entities[name]
        seed = int(children[idx].generate_state(1, dtype=np.uint32)[0])
        params = getattr(ent, "parameters", None)
        if isinstance(params, dict) and "rng_seed" in params:
            params["rng_seed"] = seed
        if hasattr(ent, "_rng"):
            ent._rng = np.random.default_rng(seed)

    engine = Engine(composite=composite, emit_step=1.0, display_info=False)

    # Indicator substrates (initial state snapshot)
    init_state = engine.state.get_value() if hasattr(engine.state, "get_value") else {}
    substrates_init = init_state.get("substrates", {}) if isinstance(init_state, dict) else {}
    mrna_init = init_state.get("rna", {}) if isinstance(init_state, dict) else {}
    protein_init = init_state.get("protein", {}) if isinstance(init_state, dict) else {}
    chrom_init = init_state.get("chromosome", {}) if isinstance(init_state, dict) else {}
    print(f"[probe] init: substrates={len(substrates_init)} keys, "
          f"rna={len(mrna_init) if isinstance(mrna_init, dict) else type(mrna_init).__name__}, "
          f"protein={len(protein_init) if isinstance(protein_init, dict) else type(protein_init).__name__}, "
          f"chromosome={type(chrom_init).__name__}", flush=True)

    # Per-tick state CSV — biology indicators + ATP + DnaA
    indicators_path = out_dir / "indicators_per_tick.csv"
    ind_f = indicators_path.open("w", newline="", encoding="utf-8")
    ind_w = csv.writer(ind_f)
    ind_w.writerow([
        "tick", "ATP", "ADP", "GTP", "CTP", "UTP",
        "MG_469", "MG_469_MONOMER",
        "rna_total_keys", "rna_total_count",
        "protein_total_keys", "protein_total_count",
        "complex_total_keys",
    ])

    def snap_indicators(tick: int) -> None:
        st = engine.state.get_value()
        sub = st.get("substrates", {}) if isinstance(st, dict) else {}
        rna = st.get("rna", {}) if isinstance(st, dict) else {}
        prot = st.get("protein", {}) if isinstance(st, dict) else {}
        comp = st.get("complex", {}) if isinstance(st, dict) else {}

        def _g(d, k):
            v = d.get(k) if isinstance(d, dict) else None
            return v if isinstance(v, (int, float)) else 0

        def _sum_leaves(d):
            total = 0.0
            keys = 0
            if isinstance(d, dict):
                for v in d.values():
                    if isinstance(v, (int, float)):
                        total += float(v); keys += 1
                    elif isinstance(v, dict):
                        for vv in v.values():
                            if isinstance(vv, (int, float)):
                                total += float(vv); keys += 1
            return keys, total

        rna_k, rna_t = _sum_leaves(rna)
        prot_k, prot_t = _sum_leaves(prot)
        comp_k, _ = _sum_leaves(comp)
        ind_w.writerow([
            tick,
            _g(sub, "ATP"), _g(sub, "ADP"), _g(sub, "GTP"), _g(sub, "CTP"), _g(sub, "UTP"),
            _g(sub, "MG_469"), _g(sub, "MG_469_MONOMER"),
            rna_k, f"{rna_t:.6g}",
            prot_k, f"{prot_t:.6g}",
            comp_k,
        ])

    snap_indicators(0)

    print(f"[probe] running {args.ticks} ticks (per-tick emit, per-component) ...", flush=True)
    t1 = time.time()
    for tick in range(1, args.ticks + 1):
        current["tick"] = tick
        engine.update(1.0)
        snap_indicators(tick)
        if tick % 20 == 0:
            print(f"[probe]   t={tick}  elapsed={time.time()-t1:.1f}s", flush=True)

    ind_f.close()
    for f in files.values():
        f.close()

    # Per-entity stats
    stats_path = out_dir / "entity_call_stats.csv"
    with stats_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity", "calls", "nonempty_returns", "exceptions"])
        for name in sorted(entities):
            w.writerow([name, call_counts[name], nonempty_counts[name], exception_counts[name]])

    print(f"\n[probe] done in {time.time()-t0:.1f}s", flush=True)
    print(f"[probe] outputs in {out_dir}", flush=True)
    print(f"[probe]   process_updates/  — per-tick port-level writes for every entity", flush=True)
    print(f"[probe]   indicators_per_tick.csv  — ATP/DnaA/rna_total/protein_total per tick", flush=True)
    print(f"[probe]   entity_call_stats.csv  — call/nonempty/exception counts per entity", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
