from __future__ import annotations

import argparse
import json
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
    apply_count_update,
    build_state_template,
    project_observable_from_state,
    refresh_allocator_views,
)
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process  # noqa: E402


OBSERVABLES: tuple[str, ...] = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "monomers",
)

SUMMARY_FIELDS: tuple[str, ...] = (
    "ribosome_state_active_count",
    "ribosome_bound_mrnas_nonzero_count",
    "ribosome_mrna_positions_sum",
)


@dataclass(frozen=True)
class TranslationRunConfig:
    seed_list: tuple[int, ...]
    n_ticks: int = 100
    output_root: Path = _REPO_ROOT / "data" / "opencell_ensembles" / "translation"
    force_overwrite: bool = False


def _observable_wids(process: KarrTranslationV3Process) -> dict[str, list[str]]:
    substrate_wids = list(getattr(process, "allocation_substrate_wids", ()))
    if not substrate_wids:
        substrate_wids = list(getattr(process, "aa_ids", ()))
    return {
        "substrates": substrate_wids[:20],
        "enzymes": list(process.enzyme_wids),
        "boundEnzymes": list(process.enzyme_wids),
        "monomers": list(process.protein_ids),
    }


def _translation_summary_from_process(process: KarrTranslationV3Process) -> dict[str, float]:
    out = {k: 0.0 for k in SUMMARY_FIELDS}

    rib_active = getattr(process, "_ribosome_state_active", None)
    if rib_active is not None:
        rib_active_arr = np.asarray(rib_active, dtype=np.bool_)
        out["ribosome_state_active_count"] = float(np.sum(rib_active_arr))

    rib_bound = getattr(process, "_ribosome_bound_mrnas", None)
    if rib_bound is not None:
        rib_bound_arr = np.asarray(rib_bound, dtype=np.float64).reshape(-1)
        out["ribosome_bound_mrnas_nonzero_count"] = float(np.sum(rib_bound_arr > 0))

    rib_pos = getattr(process, "_ribosome_mrna_positions", None)
    if rib_pos is not None:
        rib_pos_arr = np.asarray(rib_pos, dtype=np.float64).reshape(-1)
        out["ribosome_mrna_positions_sum"] = float(np.sum(rib_pos_arr))

    return out


def _run_translation_seed(seed: int, n_ticks: int) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, list[str]]]:
    process = KarrTranslationV3Process({"rng_seed": int(seed)})
    state = build_state_template(process)
    wids_by_observable = _observable_wids(process)

    vectors = {
        obs: np.zeros((n_ticks, len(wids_by_observable[obs])), dtype=np.float64) for obs in OBSERVABLES
    }
    summaries = {name: np.zeros(n_ticks, dtype=np.float64) for name in SUMMARY_FIELDS}

    for tick in range(n_ticks):
        refresh_allocator_views(process, state)
        update = process.next_update(1.0, state)
        apply_count_update(state, update)

        for obs in OBSERVABLES:
            vec = project_observable_from_state(
                process=process,
                state=state,
                observable=obs,
                wids=wids_by_observable[obs],
                bound_enzymes_before=None,
            )
            vectors[obs][tick, :] = vec

        summary = _translation_summary_from_process(process)
        for name in SUMMARY_FIELDS:
            summaries[name][tick] = float(summary[name])

    return vectors, summaries, wids_by_observable


def _save_seed_output(
    *,
    seed: int,
    n_ticks: int,
    output_root: Path,
    vectors: dict[str, np.ndarray],
    summaries: dict[str, np.ndarray],
    wids_by_observable: dict[str, list[str]],
) -> Path:
    seed_dir = output_root / f"seed_{seed:03d}"
    seed_dir.mkdir(parents=True, exist_ok=True)
    npz_path = seed_dir / f"Translation_{n_ticks}ticks.npz"
    metadata_path = seed_dir / "metadata.json"

    npz_payload: dict[str, np.ndarray] = {}
    for obs, arr in vectors.items():
        npz_payload[f"obs__{obs}"] = arr
    for name, arr in summaries.items():
        npz_payload[f"summary__{name}"] = arr
    np.savez_compressed(npz_path, **npz_payload)

    metadata = {
        "process_name": "Translation",
        "process_class": "KarrTranslationV3Process",
        "rng_seed": int(seed),
        "n_ticks": int(n_ticks),
        "observables": list(OBSERVABLES),
        "summary_fields": list(SUMMARY_FIELDS),
        "wids_by_observable": wids_by_observable,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "npz_file": npz_path.name,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return npz_path


def run_translation_ensemble(config: TranslationRunConfig) -> dict[str, Any]:
    output_root = config.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for seed in config.seed_list:
        seed_dir = output_root / f"seed_{seed:03d}"
        npz_path = seed_dir / f"Translation_{config.n_ticks}ticks.npz"
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

        vectors, summaries, wids_by_observable = _run_translation_seed(seed, config.n_ticks)
        out_path = _save_seed_output(
            seed=seed,
            n_ticks=config.n_ticks,
            output_root=output_root,
            vectors=vectors,
            summaries=summaries,
            wids_by_observable=wids_by_observable,
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
        "process_name": "Translation",
        "process_class": "KarrTranslationV3Process",
        "seed_range": [int(min(config.seed_list)), int(max(config.seed_list))],
        "seed_count": len(config.seed_list),
        "n_ticks": int(config.n_ticks),
        "observables": list(OBSERVABLES),
        "summary_fields": list(SUMMARY_FIELDS),
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
    parser = argparse.ArgumentParser(description="Run OpenCell Translation ensemble for L2.2.")
    parser.add_argument("--seeds", default="0:49", help="Seed range (e.g., 0:49) or single seed.")
    parser.add_argument("--n-ticks", type=int, default=100, help="Ticks per seed run.")
    parser.add_argument(
        "--output-root",
        default=str((_REPO_ROOT / "data" / "opencell_ensembles" / "translation").as_posix()),
        help="Output directory root.",
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
    config = TranslationRunConfig(
        seed_list=seed_list,
        n_ticks=int(args.n_ticks),
        output_root=Path(args.output_root),
        force_overwrite=bool(args.force),
    )
    manifest = run_translation_ensemble(config)
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
