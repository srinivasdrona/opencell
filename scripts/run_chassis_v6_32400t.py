"""Run a full biological 32,400-second chassis_v6 trajectory with diagnostics.

This script is intentionally external to the ``opencell`` package so we can run
long ensemble members without modifying simulation core code.
"""

from __future__ import annotations

import argparse
import csv
import gc
import gzip
import json
import math
import random
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import importlib.metadata as importlib_metadata
import numpy as np
from vivarium.core.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opencell.analysis.cell_mass import AVOGADRO
from opencell.analysis.cell_mass import _load_protein_mw
from opencell.analysis.cell_mass import _load_rna_mw
from opencell.analysis.cell_mass import _load_substrate_mw
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from scripts.canary_csvs_to_e2_pkl import build_e2_payload
from scripts.canary_csvs_to_e2_pkl import write_payload

DEFAULT_OUT_DIR = ROOT / "artifacts" / "run_32400t_seed42"
DEFAULT_LOG_PATH = ROOT / ".codex_run_seed42.log"
DEFAULT_BIOLOGICAL_SECONDS = 32_400.0
DEFAULT_SEED = 42
DEFAULT_FULL_STRIDE = 10
DEFAULT_CONSERVATION_STRIDE = 10
DEFAULT_PROCESS_TRACE_STRIDE = 10

_DNTPS = ("DATP", "DGTP", "DCTP", "DTTP")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_sum_counts(counts: Any) -> float:
    if isinstance(counts, dict):
        return float(sum(float(v) for v in counts.values()))
    if isinstance(counts, (list, tuple)):
        return float(sum(float(v) for v in counts))
    if counts is None:
        return 0.0
    arr = np.asarray(counts, dtype=np.float64).reshape(-1)
    return float(np.sum(arr))


def _snapshot_substrates(engine: Engine) -> dict[str, float]:
    substrates_store = engine.state.get_path(("substrates",))
    substrates = substrates_store.get_value() if substrates_store is not None else {}
    out: dict[str, float] = {}
    if isinstance(substrates, dict):
        for wid, value in substrates.items():
            out[str(wid)] = _to_float(value, default=0.0)
    return out


def _get_store_dict(engine: Engine, path: tuple[str, ...]) -> dict[str, Any]:
    store = engine.state.get_path(path)
    value = store.get_value() if store is not None else {}
    return value if isinstance(value, dict) else {}


def _snapshot_runtime_state(engine: Engine) -> dict[str, Any]:
    return {
        "substrates": _get_store_dict(engine, ("substrates",)),
        "rna": _get_store_dict(engine, ("rna",)),
        "protein": _get_store_dict(engine, ("protein",)),
        "chromosome": _get_store_dict(engine, ("chromosome",)),
        "cell": _get_store_dict(engine, ("cell",)),
        "phenotype_observables": _get_store_dict(engine, ("phenotype_observables",)),
    }


def _collect_leaf_updaters(node: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(node, dict):
        return out
    for key, value in node.items():
        if not isinstance(value, dict):
            continue
        if "_updater" in value:
            out[str(key)] = str(value["_updater"])
        else:
            out.update(_collect_leaf_updaters(value))
    return out


def _division_detected(state: dict[str, Any]) -> bool:
    cell = state.get("cell", {})
    if bool(cell.get("division_complete", False)):
        return True
    if float(cell.get("division_event_count", 0.0)) > 0.0:
        return True
    phase = str(cell.get("cycle_phase", "")).strip().lower()
    return phase in {"division_complete", "divided"}


@dataclass
class MassEstimator:
    substrate_mw: dict[str, float]
    rna_mw: dict[str, float]
    protein_mw: dict[str, float]
    dry_fraction: float
    density_g_per_l: float

    @classmethod
    def build(cls, m1_model: km.KarrMetabolismModel, m2_model: tx.KarrTranscriptionModel, m3_model: tl.KarrTranslationModel) -> "MassEstimator":
        params_path = ROOT / "data" / "karr_fixtures" / "parameters.json"
        with params_path.open(encoding="utf-8") as f:
            raw = json.load(f)
        wet_fraction = float(raw["states"]["Mass"]["fractionWetWeight"])
        dry_fraction = max(1.0 - wet_fraction, 1e-12)
        density_g_per_l = float(raw["states"]["Geometry"]["density"])
        return cls(
            substrate_mw=_load_substrate_mw(m1_model),
            rna_mw=_load_rna_mw(m2_model),
            protein_mw=_load_protein_mw(m3_model),
            dry_fraction=dry_fraction,
            density_g_per_l=density_g_per_l,
        )

    def dry_mass_g(self, state: dict[str, Any]) -> float:
        substrates = state.get("substrates", {})
        rna = state.get("rna", {})
        protein = state.get("protein", {})
        rna_counts = rna.get("counts", {})
        protein_counts = protein.get("counts", {})

        sub_da = 0.0
        for sid, count in substrates.items():
            mw = self.substrate_mw.get(str(sid))
            if mw is None or mw <= 0.0:
                continue
            sub_da += float(count) * mw

        rna_da = 0.0
        for gid, count in rna_counts.items():
            mw = self.rna_mw.get(str(gid))
            if mw is None or mw <= 0.0:
                continue
            rna_da += float(count) * mw

        protein_da = 0.0
        for pid, count in protein_counts.items():
            mw = self.protein_mw.get(str(pid))
            if mw is None or mw <= 0.0:
                continue
            protein_da += float(count) * mw

        return float((sub_da + rna_da + protein_da) / AVOGADRO)

    def total_mass_g(self, dry_mass_g: float) -> float:
        return float(dry_mass_g / self.dry_fraction)

    def volume_l(self, total_mass_g: float) -> float:
        return float(total_mass_g / self.density_g_per_l)


class DiagnosticCollector:
    """Patch process/step next_update to mirror canary-level substrate tracing."""

    def __init__(
        self,
        *,
        composite: Any,
        process_traces_dir: Path,
        process_trace_stride: int,
        seed: int,
    ) -> None:
        self._composite = composite
        self._process_trace_stride = max(1, int(process_trace_stride))
        self._current_tick = {"tick": 0}
        self.per_tick_process_sums: dict[str, float] = defaultdict(float)
        self.exception_counts: dict[str, int] = defaultdict(int)
        self._entities: dict[str, Any] = {}
        self._entities.update(getattr(composite, "processes", {}))
        self._entities.update(getattr(composite, "steps", {}))
        self.process_trace_files: dict[str, Any] = {}
        self.process_trace_writers: dict[str, csv.writer] = {}
        process_traces_dir.mkdir(parents=True, exist_ok=True)
        for name in sorted(self._entities):
            path = process_traces_dir / f"{name}.csv"
            f = path.open("w", newline="", encoding="utf-8")
            w = csv.writer(f)
            w.writerow(["tick", "process_name", "substrate", "delta"])
            self.process_trace_files[name] = f
            self.process_trace_writers[name] = w
        self._seed_entities(seed=seed)
        self._patch_entities()

    def set_tick(self, tick: int) -> None:
        self._current_tick["tick"] = int(tick)
        self.per_tick_process_sums.clear()

    def close(self) -> None:
        for f in self.process_trace_files.values():
            f.close()

    def clear_pending_commands(self) -> None:
        for entity in self._entities.values():
            if hasattr(entity, "_pending_command"):
                entity._pending_command = None
            if hasattr(entity, "_command_result"):
                entity._command_result = None

    def _seed_entities(self, *, seed: int) -> None:
        names = sorted(self._entities.keys())
        children = np.random.SeedSequence(int(seed)).spawn(len(names))
        for idx, name in enumerate(names):
            entity = self._entities[name]
            child = children[idx]
            entity_seed = int(child.generate_state(1, dtype=np.uint32)[0])
            params = getattr(entity, "parameters", None)
            if isinstance(params, dict) and "rng_seed" in params:
                params["rng_seed"] = entity_seed
            if hasattr(entity, "_rng"):
                entity._rng = np.random.default_rng(entity_seed)

    def _patch_entities(self) -> None:
        for entity_name, entity_obj in self._entities.items():
            topology_entry = self._composite.topology.get(entity_name, {})
            shared_substrate_port = (
                isinstance(topology_entry, dict)
                and tuple(topology_entry.get("substrates", ())) == ("substrates",)
            )
            substrate_updaters: dict[str, str] = {}
            if shared_substrate_port:
                try:
                    schema = entity_obj.ports_schema()
                    substrate_updaters = _collect_leaf_updaters(schema.get("substrates", {}))
                except Exception:
                    substrate_updaters = {}
            original_next_update = entity_obj.next_update

            def wrapped_next_update(
                timestep: float,
                states: dict[str, Any],
                *,
                _entity_name: str = entity_name,
                _original: Any = original_next_update,
                _shared: bool = shared_substrate_port,
                _updaters: dict[str, str] = substrate_updaters,
            ) -> dict[str, Any]:
                tick = int(self._current_tick["tick"])
                try:
                    update = _original(timestep, states)
                except Exception:
                    self.exception_counts[_entity_name] += 1
                    raise

                if update is None:
                    update = {}
                if not (_shared and isinstance(update, dict)):
                    return update

                port_update = update.get("substrates", {})
                if not isinstance(port_update, dict):
                    return update
                current_substrates = states.get("substrates", {})
                writer = self.process_trace_writers[_entity_name]
                for wid, raw_value in port_update.items():
                    if not isinstance(raw_value, (int, float, np.number)):
                        continue
                    wid_str = str(wid)
                    raw = float(raw_value)
                    updater = _updaters.get(wid_str, "accumulate")
                    if updater == "set":
                        baseline = _to_float(current_substrates.get(wid_str, 0.0), default=0.0)
                        delta = raw - baseline
                    else:
                        delta = raw
                    if delta == 0.0:
                        continue
                    self.per_tick_process_sums[wid_str] += float(delta)
                    if tick % self._process_trace_stride == 0:
                        writer.writerow([tick, _entity_name, wid_str, f"{delta:.12g}"])
                return update

            entity_obj.next_update = wrapped_next_update


def _format_duration(seconds: float) -> str:
    s = int(max(0, round(float(seconds))))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _log_progress(log_file: Any, message: str) -> None:
    print(message, flush=True)
    log_file.write(message + "\n")
    log_file.flush()


def _open_progress_log(log_path: Path, out_dir: Path) -> tuple[Any, Path]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return log_path.open("a", encoding="utf-8"), log_path
    except PermissionError:
        fallback = out_dir / ".codex_run_seed42.log"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback.open("a", encoding="utf-8"), fallback


def _compress_if_large(path: Path, threshold_bytes: int = 500 * 1024 * 1024) -> Path:
    if not path.exists() or path.stat().st_size <= threshold_bytes:
        return path
    gz_path = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()
    return gz_path


def run_full_cycle(
    *,
    out_dir: Path,
    log_path: Path,
    seed: int,
    biological_seconds: float,
    full_stride: int,
    conservation_stride: int,
    process_trace_stride: int,
    memory_retry_attempts: int,
    memory_retry_sleep_s: float,
) -> dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed)

    m1_model = km.load_default()
    m2_model = tx.load_default()
    m3_model = tl.load_default()
    probe = build_karr_chassis_v6(m1_model=m1_model, m2_model=m2_model, m3_model=m3_model)
    timestep_s = float(
        getattr(probe.processes.get("karr_metabolism"), "parameters", {}).get("time_step", 1.0)
    )
    ticks = int(round(float(biological_seconds) / timestep_s))
    if not math.isclose(ticks * timestep_s, float(biological_seconds), rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError(
            f"biological_seconds ({biological_seconds}) is not divisible by timestep ({timestep_s})"
        )

    composite = build_karr_chassis_v6(
        m1_model=m1_model,
        m2_model=m2_model,
        m3_model=m3_model,
        time_step_s=timestep_s,
        emit_step_s=float(ticks),
    )
    diagnostics = DiagnosticCollector(
        composite=composite,
        process_traces_dir=out_dir / "process_traces",
        process_trace_stride=process_trace_stride,
        seed=seed,
    )
    engine = Engine(composite=composite, emit_step=float(ticks), display_info=False)

    out_dir.mkdir(parents=True, exist_ok=True)
    key_path = out_dir / "key_substrates.csv"
    full_path = out_dir / "substrates_full.csv"
    conservation_path = out_dir / "conservation.csv"
    replication_path = out_dir / "replication_events.csv"
    division_path = out_dir / "division_event.json"
    manifest_path = out_dir / "manifest.json"

    aa_ids = tuple(str(wid) for wid in composite.processes["karr_translation"].aa_ids)
    mass_estimator = MassEstimator.build(m1_model, m2_model, m3_model)
    progress_log_fh, progress_log_actual_path = _open_progress_log(log_path, out_dir)

    with (
        key_path.open("w", newline="", encoding="utf-8") as key_f,
        full_path.open("w", newline="", encoding="utf-8") as full_f,
        conservation_path.open("w", newline="", encoding="utf-8") as cons_f,
        replication_path.open("w", newline="", encoding="utf-8") as repl_f,
        progress_log_fh as log_f,
    ):
        key_w = csv.writer(key_f)
        full_w = csv.writer(full_f)
        cons_w = csv.writer(cons_f)
        repl_w = csv.writer(repl_f)

        key_header = [
            "tick",
            "time_s",
            "ATP",
            "GTP",
            "CTP",
            "UTP",
            "DATP",
            "DGTP",
            "DCTP",
            "DTTP",
            "dNTP_total",
        ]
        key_header.extend(f"AA_{wid}" for wid in aa_ids)
        key_header.extend(
            [
                "total_rna_count",
                "total_protein_count",
                "cell_dry_mass_g",
                "cell_total_mass_g",
                "cell_volume_L",
            ]
        )
        key_w.writerow(key_header)
        full_w.writerow(["tick", "time_s", "substrate", "count"])
        cons_w.writerow(
            ["tick", "time_s", "substrate", "store_delta", "sum_process_deltas", "unattributed_delta"]
        )
        repl_w.writerow(
            [
                "tick",
                "time_s",
                "replication_state",
                "fork_left_bp",
                "fork_right_bp",
                "fork_max_abs_bp",
                "replication_complete_flag",
                "event",
            ]
        )

        def write_key_row(tick: int, state: dict[str, Any]) -> tuple[float, float, float, float]:
            substrates = state.get("substrates", {})
            rna = state.get("rna", {})
            protein = state.get("protein", {})
            dntp_total = float(sum(_to_float(substrates.get(w, 0.0)) for w in _DNTPS))
            aa_values = [_to_float(substrates.get(w, 0.0)) for w in aa_ids]
            rna_counts_total = (
                _safe_sum_counts(rna.get("counts", {}))
                + _safe_sum_counts(rna.get("aminoacylated_counts", {}))
                + _safe_sum_counts(rna.get("modified_counts", {}))
            )
            protein_counts_total = _safe_sum_counts(protein.get("counts", {}))
            dry_mass = mass_estimator.dry_mass_g(state)
            total_mass = mass_estimator.total_mass_g(dry_mass)
            volume_l = mass_estimator.volume_l(total_mass)
            row = [
                tick,
                f"{tick * timestep_s:.12g}",
                f"{_to_float(substrates.get('ATP', 0.0)):.12g}",
                f"{_to_float(substrates.get('GTP', 0.0)):.12g}",
                f"{_to_float(substrates.get('CTP', 0.0)):.12g}",
                f"{_to_float(substrates.get('UTP', 0.0)):.12g}",
                f"{_to_float(substrates.get('DATP', 0.0)):.12g}",
                f"{_to_float(substrates.get('DGTP', 0.0)):.12g}",
                f"{_to_float(substrates.get('DCTP', 0.0)):.12g}",
                f"{_to_float(substrates.get('DTTP', 0.0)):.12g}",
                f"{dntp_total:.12g}",
            ]
            row.extend(f"{v:.12g}" for v in aa_values)
            row.extend(
                [
                    f"{rna_counts_total:.12g}",
                    f"{protein_counts_total:.12g}",
                    f"{dry_mass:.12g}",
                    f"{total_mass:.12g}",
                    f"{volume_l:.12g}",
                ]
            )
            key_w.writerow(row)
            return (
                _to_float(substrates.get("ATP", 0.0)),
                total_mass,
                rna_counts_total,
                protein_counts_total,
            )

        def write_full_rows(tick: int, substrates: dict[str, float]) -> None:
            if tick % max(1, int(full_stride)) != 0:
                return
            time_s = tick * timestep_s
            for wid in sorted(substrates):
                full_w.writerow([tick, f"{time_s:.12g}", wid, f"{_to_float(substrates[wid]):.12g}"])

        def write_replication_row(tick: int, state: dict[str, Any], event: str) -> None:
            chromosome = state.get("chromosome", {})
            fork = chromosome.get("fork_position_bp", {})
            left = _to_float(fork.get("left", 0.0)) if isinstance(fork, dict) else 0.0
            right = _to_float(fork.get("right", 0.0)) if isinstance(fork, dict) else 0.0
            repl_state = str(chromosome.get("replication_state", "idle"))
            events = chromosome.get("events", {})
            complete_flag = _to_float(events.get("replication_complete", 0.0)) if isinstance(events, dict) else 0.0
            repl_w.writerow(
                [
                    tick,
                    f"{tick * timestep_s:.12g}",
                    repl_state,
                    f"{left:.12g}",
                    f"{right:.12g}",
                    f"{max(abs(left), abs(right)):.12g}",
                    f"{complete_flag:.12g}",
                    event,
                ]
            )

        t_start = time.time()
        state = _snapshot_runtime_state(engine)
        write_key_row(0, state)
        initial_substrates = {str(k): _to_float(v) for k, v in state.get("substrates", {}).items()}
        write_full_rows(0, initial_substrates)
        write_replication_row(0, state, "none")

        replication_initiation_tick: int | None = None
        replication_completion_tick: int | None = None
        division_tick: int | None = None
        division_state: dict[str, Any] | None = None
        max_abs_unattributed = 0.0

        for tick in range(1, ticks + 1):
            do_conservation = tick % max(1, int(conservation_stride)) == 0
            before = _snapshot_substrates(engine) if do_conservation else {}
            diagnostics.set_tick(tick)
            update_attempt = 0
            while True:
                try:
                    engine.update(timestep_s)
                    break
                except Exception as exc:
                    is_memory_error = isinstance(exc, MemoryError) or exc.__class__.__name__ == "ArrayMemoryError"
                    if (not is_memory_error) or update_attempt >= max(0, int(memory_retry_attempts)):
                        raise
                    update_attempt += 1
                    diagnostics.clear_pending_commands()
                    gc.collect()
                    msg = (
                        f"[seed={seed}] memory-retry tick={tick}/{ticks} "
                        f"attempt={update_attempt}/{memory_retry_attempts} "
                        f"sleep_s={memory_retry_sleep_s:.1f} err={exc.__class__.__name__}"
                    )
                    _log_progress(log_f, msg)
                    time.sleep(float(memory_retry_sleep_s))
            state = _snapshot_runtime_state(engine)
            after = {str(k): _to_float(v) for k, v in state.get("substrates", {}).items()}

            atp, total_mass, final_rna_total, final_protein_total = write_key_row(tick, state)
            write_full_rows(tick, after)

            chromosome = state.get("chromosome", {})
            repl_state = str(chromosome.get("replication_state", "idle")).strip().lower()
            repl_event = "none"
            if replication_initiation_tick is None and repl_state in {"initiating", "elongating", "complete"}:
                replication_initiation_tick = tick
                repl_event = "initiation"
            events = chromosome.get("events", {})
            complete_flag = _to_float(events.get("replication_complete", 0.0)) if isinstance(events, dict) else 0.0
            if replication_completion_tick is None and (
                repl_state == "complete" or complete_flag > 0.0
            ):
                replication_completion_tick = tick
                repl_event = "completion" if repl_event == "none" else "initiation+completion"
            write_replication_row(tick, state, repl_event)

            if do_conservation:
                all_substrates = set(before) | set(after) | set(diagnostics.per_tick_process_sums)
                time_s = tick * timestep_s
                for wid in sorted(all_substrates):
                    store_delta = _to_float(after.get(wid, 0.0)) - _to_float(before.get(wid, 0.0))
                    proc_delta = _to_float(diagnostics.per_tick_process_sums.get(wid, 0.0))
                    unattributed = store_delta - proc_delta
                    max_abs_unattributed = max(max_abs_unattributed, abs(unattributed))
                    cons_w.writerow(
                        [
                            tick,
                            f"{time_s:.12g}",
                            wid,
                            f"{store_delta:.12g}",
                            f"{proc_delta:.12g}",
                            f"{unattributed:.12g}",
                        ]
                    )

            if division_tick is None and _division_detected(state):
                division_tick = tick
                division_state = {
                    "cell": state.get("cell", {}),
                    "chromosome": state.get("chromosome", {}),
                    "phenotype_observables": state.get("phenotype_observables", {}),
                }

            if tick % 1000 == 0 or tick == ticks:
                elapsed = time.time() - t_start
                rate = tick / elapsed if elapsed > 0.0 else 0.0
                remaining_ticks = max(0, ticks - tick)
                eta_s = (remaining_ticks / rate) if rate > 0 else float("inf")
                msg = (
                    f"[seed={seed}] tick={tick}/{ticks} "
                    f"ATP={atp:.6g} total_mass_g={total_mass:.6g} "
                    f"elapsed={_format_duration(elapsed)} "
                    f"eta={_format_duration(eta_s) if math.isfinite(eta_s) else 'inf'}"
                )
                _log_progress(log_f, msg)
                gc.collect()

        wall_time_s = float(time.time() - t_start)
        division_payload = {
            "division_reached": division_tick is not None,
            "division_tick": division_tick,
            "division_time_s": (division_tick * timestep_s) if division_tick is not None else None,
            "final_state_at_division": division_state,
        }
        with division_path.open("w", encoding="utf-8") as f:
            json.dump(division_payload, f, indent=2, sort_keys=True)
            f.write("\n")

    trajectory_pkl_path = out_dir / "trajectory.pkl"
    trajectory_payload = build_e2_payload(
        out_dir,
        reference_fixture=ROOT / "data" / "phase_e" / "v6_trajectory_32400s.pkl",
    )
    write_payload(trajectory_payload, trajectory_pkl_path)

    diagnostics.close()

    full_path = _compress_if_large(full_path)

    versions = {}
    for pkg in ("numpy", "vivarium-core", "pandas", "pytest"):
        try:
            versions[pkg] = importlib_metadata.version(pkg)
        except importlib_metadata.PackageNotFoundError:
            continue

    manifest = {
        "head_sha": _run_git_rev_parse(),
        "seed": int(seed),
        "timestep_s": float(timestep_s),
        "ticks": int(ticks),
        "biological_seconds": float(ticks * timestep_s),
        "wall_time_s": float(wall_time_s),
        "python_version": sys.version,
        "library_versions": versions,
        "outputs": {
            "key_substrates_csv": str(key_path),
            "substrates_full_csv_or_gz": str(full_path),
            "replication_events_csv": str(replication_path),
            "division_event_json": str(division_path),
            "conservation_csv": str(conservation_path),
            "process_traces_dir": str(out_dir / "process_traces"),
            "trajectory_pkl": str(trajectory_pkl_path),
            "progress_log_path": str(progress_log_actual_path),
        },
        "sampling": {
            "substrates_full_every_n_ticks": int(full_stride),
            "conservation_every_n_ticks": int(conservation_stride),
            "process_trace_every_n_ticks": int(process_trace_stride),
            "key_substrates_every_n_ticks": 1,
        },
        "replication": {
            "initiation_tick": replication_initiation_tick,
            "completion_tick": replication_completion_tick,
        },
        "division": {
            "division_tick": division_tick,
        },
        "conservation": {
            "max_abs_unattributed_delta": float(max_abs_unattributed),
        },
        "process_exception_counts": {
            k: int(v) for k, v in sorted(diagnostics.exception_counts.items())
        },
        "run_completed": True,
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return manifest


def _run_git_rev_parse() -> str:
    import subprocess

    out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
    return out.strip()


def _gather_file_sizes(out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file():
            rows.append(
                {
                    "path": str(path),
                    "size_bytes": int(path.stat().st_size),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--biological-seconds", type=float, default=DEFAULT_BIOLOGICAL_SECONDS)
    parser.add_argument("--full-stride", type=int, default=DEFAULT_FULL_STRIDE)
    parser.add_argument("--conservation-stride", type=int, default=DEFAULT_CONSERVATION_STRIDE)
    parser.add_argument("--process-trace-stride", type=int, default=DEFAULT_PROCESS_TRACE_STRIDE)
    parser.add_argument("--memory-retry-attempts", type=int, default=120)
    parser.add_argument("--memory-retry-sleep-s", type=float, default=30.0)
    parser.add_argument("--fresh", action="store_true", help="delete out-dir before run")
    args = parser.parse_args()

    if args.fresh and args.out_dir.exists():
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.log_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = run_full_cycle(
        out_dir=args.out_dir,
        log_path=args.log_path,
        seed=int(args.seed),
        biological_seconds=float(args.biological_seconds),
        full_stride=int(args.full_stride),
        conservation_stride=int(args.conservation_stride),
        process_trace_stride=int(args.process_trace_stride),
        memory_retry_attempts=int(args.memory_retry_attempts),
        memory_retry_sleep_s=float(args.memory_retry_sleep_s),
    )
    manifest["files"] = _gather_file_sizes(args.out_dir)
    with (args.out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    print(
        "run_chassis_v6_32400t:"
        f" completed seed={manifest['seed']}"
        f" ticks={manifest['ticks']}"
        f" timestep_s={manifest['timestep_s']}"
        f" biological_seconds={manifest['biological_seconds']}"
        f" out_dir={args.out_dir}"
    )


if __name__ == "__main__":
    main()
