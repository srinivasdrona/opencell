from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

# Ensure imports resolve to this worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    ChannelSpec,
    build_state_template,
    load_fitted_init_from_mat,
    load_fixture_channel_wids,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
)
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess  # noqa: E402


OBSERVABLES: tuple[str, ...] = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "RNAs",
)
FITTED_CHANNELS: tuple[str, ...] = ("substrates", "enzymes", "boundEnzymes")


@dataclass(frozen=True)
class TranscriptionRunConfig:
    seed_list: tuple[int, ...]
    n_ticks: int = 100
    output_root: Path = _REPO_ROOT / "data" / "opencell_ensembles" / "transcription"
    karr_root: Path = _REPO_ROOT / "data" / "m1_sources" / "karr_native" / "ensembles" / "transcription"
    force_overwrite: bool = False


def _observable_wids(process: KarrTranscriptionProcess) -> dict[str, list[str]]:
    return {
        "substrates": [str(x) for x in process.substrate_wids],
        "enzymes": [str(x) for x in process.enzyme_wids],
        "boundEnzymes": [str(x) for x in process.enzyme_wids],
        "RNAs": [str(x) for x in process.gene_ids],
    }


def _accumulate_leaf(state: dict[str, Any], channel: str, deltas: dict[str, Any]) -> None:
    channel_state = state.setdefault(channel, {})
    if not isinstance(channel_state, dict):
        channel_state = {}
        state[channel] = channel_state
    for wid, delta in deltas.items():
        wid_s = str(wid)
        channel_state[wid_s] = float(channel_state.get(wid_s, 0.0)) + float(delta)


def _apply_transcription_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    rna_update = update.get("rna", {})
    if isinstance(rna_update, dict):
        counts_update = rna_update.get("counts")
        if isinstance(counts_update, dict):
            rna_state = state.setdefault("rna", {})
            if not isinstance(rna_state, dict):
                rna_state = {}
                state["rna"] = rna_state
            counts_state = rna_state.setdefault("counts", {})
            if not isinstance(counts_state, dict):
                counts_state = {}
                rna_state["counts"] = counts_state
            for wid, val in counts_update.items():
                counts_state[str(wid)] = float(val)

    for channel in ("substrates", "enzymes", "boundEnzymes"):
        channel_update = update.get(channel)
        if isinstance(channel_update, dict):
            _accumulate_leaf(state, channel, channel_update)


def _project_rnas_from_state(state: dict[str, Any], wids: list[str]) -> np.ndarray:
    rna_state = state.get("rna", {})
    if not isinstance(rna_state, dict):
        return np.zeros(len(wids), dtype=np.float64)
    counts = rna_state.get("counts", {})
    if not isinstance(counts, dict):
        return np.zeros(len(wids), dtype=np.float64)
    return np.asarray([float(counts.get(wid, 0.0)) for wid in wids], dtype=np.float64).reshape(-1)


def _channel_map_for_fitted_init(
    *,
    process: KarrTranscriptionProcess,
    wids_by_observable: dict[str, list[str]],
) -> dict[str, ChannelSpec]:
    channel_map: dict[str, ChannelSpec] = {}
    for channel in FITTED_CHANNELS:
        oc_wids = tuple(wids_by_observable.get(channel, ()))
        if not oc_wids:
            continue
        karr_wids = load_fixture_channel_wids("Transcription", channel)
        if not karr_wids:
            karr_wids = oc_wids
        channel_map[channel] = ChannelSpec(
            karr_field=channel,
            karr_wids=tuple(karr_wids),
            oc_wids=tuple(oc_wids),
        )
    return channel_map


def _run_transcription_seed(
    *,
    seed: int,
    n_ticks: int,
    karr_root: Path,
) -> tuple[dict[str, np.ndarray], dict[str, list[str]], dict[str, ChannelSpec]]:
    process = KarrTranscriptionProcess({"rng_seed": int(seed)})
    state = build_state_template(process)
    wids_by_observable = _observable_wids(process)
    channel_map = _channel_map_for_fitted_init(process=process, wids_by_observable=wids_by_observable)

    fitted_path = karr_root / f"seed_{seed:03d}" / f"Transcription_{n_ticks}ticks.mat"
    fitted_init = load_fitted_init_from_mat(fitted_path, channel_map)
    for channel, vec in fitted_init.items():
        overlay_observable_into_state(
            process=process,
            state=state,
            observable=channel,
            vector=np.asarray(vec, dtype=np.float64).reshape(-1),
            wids=wids_by_observable[channel],
        )

    vectors = {
        obs: np.zeros((n_ticks, len(wids_by_observable[obs])), dtype=np.float64) for obs in OBSERVABLES
    }

    for tick in range(n_ticks):
        refresh_allocator_views(process, state)
        update = process.next_update(1.0, state)
        _apply_transcription_update(state, update)

        for obs in OBSERVABLES:
            if obs == "RNAs":
                vec = _project_rnas_from_state(state, wids_by_observable[obs])
            else:
                vec = project_observable_from_state(
                    process=process,
                    state=state,
                    observable=obs,
                    wids=wids_by_observable[obs],
                    bound_enzymes_before=None,
                )
            vectors[obs][tick, :] = np.asarray(vec, dtype=np.float64).reshape(-1)

    return vectors, wids_by_observable, channel_map


def _source_git_sha(path: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "log", "-n", "1", "--format=%H", "--", str(path)],
            cwd=_REPO_ROOT,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
        if out.startswith("fatal:"):
            return "unknown"
        return out
    except Exception:
        return "unknown"


def _save_seed_output(
    *,
    seed: int,
    n_ticks: int,
    output_root: Path,
    vectors: dict[str, np.ndarray],
    wids_by_observable: dict[str, list[str]],
    channel_map: dict[str, ChannelSpec],
) -> Path:
    seed_dir = output_root / f"seed_{seed:03d}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    npz_path = seed_dir / f"Transcription_{n_ticks}ticks.npz"
    metadata_path = seed_dir / "metadata.json"

    npz_payload: dict[str, np.ndarray] = {}
    for obs, arr in vectors.items():
        npz_payload[f"obs__{obs}"] = arr
    np.savez_compressed(npz_path, **npz_payload)

    metadata = {
        "process_name": "Transcription",
        "process_class": "KarrTranscriptionProcess",
        "process_module": "opencell.vivarium.karr_transcription",
        "process_source_git_sha": _source_git_sha(_REPO_ROOT / "opencell" / "vivarium" / "karr_transcription.py"),
        "rng_seed": int(seed),
        "n_ticks": int(n_ticks),
        "observables": list(OBSERVABLES),
        "wids_by_observable": wids_by_observable,
        "fitted_channels": list(FITTED_CHANNELS),
        "fitted_channel_map": {
            channel: {
                "karr_field": spec.karr_field,
                "karr_wids": list(spec.karr_wids),
                "oc_wids": list(spec.oc_wids),
            }
            for channel, spec in channel_map.items()
        },
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "npz_file": npz_path.name,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return npz_path


def run_transcription_ensemble(config: TranscriptionRunConfig) -> dict[str, Any]:
    output_root = config.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for seed in config.seed_list:
        seed_dir = output_root / f"seed_{seed:03d}"
        npz_path = seed_dir / f"Transcription_{config.n_ticks}ticks.npz"
        if npz_path.exists() and not config.force_overwrite:
            entries.append(
                {
                    "seed": int(seed),
                    "npz_path": npz_path.as_posix(),
                    "size_bytes": int(npz_path.stat().st_size),
                    "status": "reused",
                }
            )
            continue

        vectors, wids_by_observable, channel_map = _run_transcription_seed(
            seed=seed,
            n_ticks=config.n_ticks,
            karr_root=config.karr_root,
        )
        out_path = _save_seed_output(
            seed=seed,
            n_ticks=config.n_ticks,
            output_root=output_root,
            vectors=vectors,
            wids_by_observable=wids_by_observable,
            channel_map=channel_map,
        )
        entries.append(
            {
                "seed": int(seed),
                "npz_path": out_path.as_posix(),
                "size_bytes": int(out_path.stat().st_size),
                "status": "generated",
            }
        )

    manifest = {
        "process_name": "Transcription",
        "process_class": "KarrTranscriptionProcess",
        "process_module": "opencell.vivarium.karr_transcription",
        "process_source_git_sha": _source_git_sha(_REPO_ROOT / "opencell" / "vivarium" / "karr_transcription.py"),
        "seed_range": [int(min(config.seed_list)), int(max(config.seed_list))],
        "seed_count": len(config.seed_list),
        "n_ticks": int(config.n_ticks),
        "observables": list(OBSERVABLES),
        "fitted_channels": list(FITTED_CHANNELS),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "entries": entries,
    }
    manifest_path = output_root / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _parse_seed_spec(spec: str) -> tuple[int, ...]:
    text = spec.strip()
    if ":" in text:
        start_text, end_text = text.split(":", maxsplit=1)
        start = int(start_text)
        end = int(end_text)
        if end < start:
            raise ValueError(f"seed range end < start: {spec}")
        return tuple(range(start, end + 1))
    return (int(text),)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenCell Transcription ensemble for L2.2.")
    parser.add_argument("--seeds", default="0:49", help="Seed range (e.g., 0:49) or single seed.")
    parser.add_argument("--n-ticks", type=int, default=100, help="Ticks per seed run.")
    parser.add_argument(
        "--output-root",
        default=str((_REPO_ROOT / "data" / "opencell_ensembles" / "transcription").as_posix()),
        help="Output directory root.",
    )
    parser.add_argument(
        "--karr-root",
        default=str(
            (_REPO_ROOT / "data" / "m1_sources" / "karr_native" / "ensembles" / "transcription").as_posix()
        ),
        help="Karr ensemble root (contains seed_<NNN>/Transcription_100ticks.mat).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing per-seed outputs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    seed_list = _parse_seed_spec(args.seeds)
    config = TranscriptionRunConfig(
        seed_list=seed_list,
        n_ticks=int(args.n_ticks),
        output_root=Path(args.output_root),
        karr_root=Path(args.karr_root),
        force_overwrite=bool(args.force),
    )
    manifest = run_transcription_ensemble(config)
    print(
        json.dumps(
            {
                "process_name": manifest["process_name"],
                "seed_count": manifest["seed_count"],
                "n_ticks": manifest["n_ticks"],
                "output_root": str(config.output_root),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
