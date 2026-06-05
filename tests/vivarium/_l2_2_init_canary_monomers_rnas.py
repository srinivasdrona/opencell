from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

from opencell.vivarium.karr_transcription import KarrTranscriptionProcess
from opencell.vivarium.karr_translation import KarrTranslationProcess

_REPO_ROOT = Path(__file__).resolve().parents[2]

_TRANSLATION_MAT = (
    _REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "ensembles"
    / "translation"
    / "seed_000"
    / "Translation_100ticks.mat"
)
_TRANSCRIPTION_MAT = (
    _REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "ensembles"
    / "transcription"
    / "seed_000"
    / "Transcription_100ticks.mat"
)
_TRANSLATION_FIXTURE = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Translation_flat.mat"
_TRANSCRIPTION_FIXTURE = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Transcription_flat.mat"


def _mat_cell_vector(handle: h5py.File, group: str, name: str, tick: int) -> np.ndarray:
    ds = handle[f"{group}/{name}"]
    rows, cols = int(ds.shape[0]), int(ds.shape[1])
    if rows == 1 and cols >= (tick + 1):
        ref = ds[0, tick]
    elif cols == 1 and rows >= (tick + 1):
        ref = ds[tick, 0]
    elif rows >= (tick + 1):
        ref = ds[tick, 0]
    elif cols >= (tick + 1):
        ref = ds[0, tick]
    else:
        raise IndexError(f"Tick {tick} out of range for {group}/{name} with shape={ds.shape}")
    return np.asarray(handle[ref][()], dtype=np.float64).reshape(-1)


def _parse_object_ids(values: object) -> list[str]:
    arr = np.asarray(values, dtype=object).reshape(-1)
    out: list[str] = []
    for raw in arr:
        item: object = raw
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


def _load_state_ids_from_fixture(fixture_path: Path, attr_name: str) -> list[str]:
    fixture_mat = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)
    data = fixture_mat.get("data")
    fixture = getattr(data, "fixture", None)
    if fixture is None:
        raise RuntimeError(f"Fixture missing data.fixture: {fixture_path}")

    states = np.asarray(getattr(fixture, "states", []), dtype=object).reshape(-1)
    for idx, state in enumerate(states):
        if hasattr(state, attr_name):
            raw = getattr(state, attr_name)
            ids = _parse_object_ids(raw)
            if ids:
                return ids
            raise RuntimeError(
                f"Found {attr_name} on fixture state[{idx}] but parsed empty IDs: {fixture_path}"
            )
    raise RuntimeError(f"Could not find {attr_name} in fixture states: {fixture_path}")


def _print_set_summary(*, label: str, karr_wids: list[str], oc_wids: list[str]) -> None:
    karr_set = set(karr_wids)
    oc_set = set(oc_wids)
    inter = sorted(karr_set.intersection(oc_set))
    dropped_karr = sorted(karr_set.difference(oc_set))
    dropped_oc = sorted(oc_set.difference(karr_set))

    print(f"{label}:")
    print(f"  karr_wid_count={len(karr_wids)}")
    print(f"  oc_wid_count={len(oc_wids)}")
    print(f"  same_order={karr_wids == oc_wids}")
    print(f"  karr_subset_of_oc={karr_set.issubset(oc_set)}")
    print(f"  oc_subset_of_karr={oc_set.issubset(karr_set)}")
    print(f"  intersection_count={len(inter)}")
    print(f"  dropped_karr_count={len(dropped_karr)}")
    print(f"  dropped_oc_count={len(dropped_oc)}")
    print(f"  karr_first10={karr_wids[:10]}")
    print(f"  oc_first10={oc_wids[:10]}")
    print(f"  intersection_first10={inter[:10]}")
    print(f"  dropped_karr_first10={dropped_karr[:10]}")
    print(f"  dropped_oc_first10={dropped_oc[:10]}")


def _translation_canary() -> None:
    with h5py.File(_TRANSLATION_MAT, "r") as handle:
        before = _mat_cell_vector(handle, "states_before", "monomers", 0)
        after = _mat_cell_vector(handle, "states_after", "monomers", 0)
    print("Translation::monomers")
    print(f"  mat_path={_TRANSLATION_MAT}")
    print(f"  tick0_states_before_len={before.shape[0]}")
    print(f"  tick0_states_after_len={after.shape[0]}")

    karr_wids = _load_state_ids_from_fixture(_TRANSLATION_FIXTURE, "monomerWholeCellModelIDs")
    process = KarrTranslationProcess({"rng_seed": 0})
    oc_wids = [str(x) for x in process.protein_ids]
    _print_set_summary(label="  WID_surface", karr_wids=karr_wids, oc_wids=oc_wids)


def _transcription_canary() -> None:
    with h5py.File(_TRANSCRIPTION_MAT, "r") as handle:
        before = _mat_cell_vector(handle, "states_before", "RNAs", 0)
        after = _mat_cell_vector(handle, "states_after", "RNAs", 0)
    print("Transcription::RNAs")
    print(f"  mat_path={_TRANSCRIPTION_MAT}")
    print(f"  tick0_states_before_len={before.shape[0]}")
    print(f"  tick0_states_after_len={after.shape[0]}")

    karr_wids = _load_state_ids_from_fixture(_TRANSCRIPTION_FIXTURE, "transcriptionUnitWholeCellModelIDs")
    process = KarrTranscriptionProcess({"rng_seed": 0})
    oc_gene_wids = [str(x) for x in process.gene_ids]
    _print_set_summary(label="  RNAs_vs_oc_gene_ids", karr_wids=karr_wids, oc_wids=oc_gene_wids)

    schema = process.ports_schema()
    rna_schema = ((schema.get("rna") or {}).get("counts") or {})
    rna_store_wids = [str(x) for x in rna_schema.keys()] if isinstance(rna_schema, dict) else []
    print("  OC_rna_store_surface:")
    print(f"    rna.counts_wid_count={len(rna_store_wids)}")
    print(f"    rna.counts_first10={rna_store_wids[:10]}")

    tu_like_attrs: list[tuple[str, int, list[str]]] = []
    for attr in dir(process):
        if attr.startswith("_"):
            continue
        if "tu" not in attr.lower() and "transcriptionunit" not in attr.lower():
            continue
        value: Any
        try:
            value = getattr(process, attr)
        except Exception:
            continue
        if isinstance(value, (list, tuple)) and value and all(isinstance(x, str) for x in value):
            tu_like_attrs.append((attr, len(value), [str(x) for x in value[:10]]))
    print("  OC_tu_like_string_attrs:")
    if not tu_like_attrs:
        print("    none")
    else:
        for name, count, preview in tu_like_attrs:
            print(f"    {name}: count={count}, first10={preview}")


def main() -> int:
    _translation_canary()
    print("-" * 100)
    _transcription_canary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
