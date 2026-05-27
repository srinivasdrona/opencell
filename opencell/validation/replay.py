"""Per-process Karr replay harness utilities.

Notes
-----
- The primary fixture artifact is ``data/karr_fixtures/per_process/<Process>_flat.mat``.
- Companion ``.json``/``.npz`` files are consumed when present because they provide
  a flattened, Python-friendly view of many fields.
- Input/output key splitting is heuristic and intentionally conservative. If no clear
  split is found, callers should provide explicit key subsets in process-specific tests.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.io import loadmat

_DEFAULT_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process"
_REPLAY_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process_replay"

_INPUT_HINTS = (
    "state_before",
    "states_before",
    "_before",
    "/before",
    "input",
    "inputs",
    "requires",
)
_OUTPUT_HINTS = (
    "state_after",
    "states_after",
    "_after",
    "/after",
    "output",
    "outputs",
    "update",
    "delta",
)
_TICK_HINTS = ("tick", "time", "state_before", "states_before", "state_after", "states_after")
_REPLAY_INPUT_PREFIXES = ("state_before__", "states_before__")
_REPLAY_OUTPUT_PREFIXES = ("state_after__", "states_after__")


@dataclass
class KarrReplayFixture:
    """One Karr process fixture with replay-ready arrays."""

    process_name: str
    fixture_path: Path
    n_ticks: int
    inputs: dict[str, np.ndarray]
    outputs: dict[str, np.ndarray]
    metadata: dict[str, Any]


def _normalize_process_name(process_name: str) -> str:
    base = process_name.strip()
    if not base:
        raise ValueError("process_name must be non-empty")

    if base.endswith("_flat"):
        stem = base[:-5]
    elif base.endswith("_flat.mat"):
        stem = base[:-9]
    elif base.endswith(".mat"):
        stem = base[:-4]
    else:
        stem = base
    return stem


def _resolve_fixture_path(process_name: str, root: Path) -> Path:
    stem = _normalize_process_name(process_name)
    path = root / f"{stem}_flat.mat"
    if not path.exists():
        raise FileNotFoundError(f"Per-process fixture not found: {path}")
    return path


def _normalize_array_key(key: str) -> str:
    # Flattened companion npz keys often encode "/" as "__".
    return key.replace("__", "/")


def _load_companion_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _load_companion_npz(path: Path, *, normalize_keys: bool = True) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    out: dict[str, np.ndarray] = {}
    with np.load(path, allow_pickle=False) as payload:
        for key in payload.files:
            normalized = _normalize_array_key(key) if normalize_keys else key
            out[normalized] = np.asarray(payload[key])
    return out


def _try_extract_fixture_field_names(fixture_path: Path) -> list[str]:
    try:
        mat = loadmat(str(fixture_path), squeeze_me=False, struct_as_record=False)
    except Exception:
        return []

    try:
        root = mat["data"][0, 0]
        fixture = getattr(root, "fixture", None)
        if isinstance(fixture, np.ndarray) and fixture.size > 0:
            fixture_struct = fixture[0, 0]
            fields = list(getattr(fixture_struct, "_fieldnames", []))
            return [str(field) for field in fields]
    except Exception:
        return []
    return []


def _infer_n_ticks(arrays: dict[str, np.ndarray], companion_json: dict[str, Any]) -> int:
    for key in ("n_ticks", "nticks", "num_ticks"):
        value = companion_json.get(key)
        if isinstance(value, (int, float)) and int(value) > 0:
            return int(value)

    manifest = companion_json.get("manifest", {})
    if isinstance(manifest, dict):
        for key in ("n_ticks", "nticks", "num_ticks"):
            value = manifest.get(key)
            if isinstance(value, (int, float)) and int(value) > 0:
                return int(value)

    candidates: list[int] = []
    for key, arr in arrays.items():
        if arr.ndim < 1 or arr.shape[0] <= 1:
            continue
        low = key.lower()
        if any(hint in low for hint in _TICK_HINTS):
            candidates.append(int(arr.shape[0]))
            if arr.ndim > 1 and arr.shape[-1] > 1:
                candidates.append(int(arr.shape[-1]))

    if candidates:
        return Counter(candidates).most_common(1)[0][0]
    return 1


def _looks_tick_series(arr: np.ndarray, n_ticks: int) -> bool:
    if n_ticks <= 1:
        return arr.ndim > 0 and arr.shape[0] == 1
    if arr.ndim > 0 and arr.shape[0] == n_ticks:
        return True
    return arr.ndim > 1 and arr.shape[-1] == n_ticks


def _ensure_tick_major(arr: np.ndarray, n_ticks: int) -> np.ndarray:
    if arr.ndim == 0:
        return arr.reshape(1)

    if n_ticks <= 1:
        if arr.shape[0] == 1:
            return arr
        return arr.reshape((1, *arr.shape))

    if arr.shape[0] == n_ticks:
        return arr
    if arr.ndim > 1 and arr.shape[-1] == n_ticks:
        return np.moveaxis(arr, -1, 0)
    raise ValueError(f"Array cannot be interpreted as tick-series with n_ticks={n_ticks}: {arr.shape}")


def _split_inputs_outputs(
    arrays: dict[str, np.ndarray],
    *,
    n_ticks: int,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], list[str]]:
    inputs: dict[str, np.ndarray] = {}
    outputs: dict[str, np.ndarray] = {}
    unclassified_series: list[str] = []

    for key, raw in arrays.items():
        arr = np.asarray(raw)
        low = key.lower()
        is_input = any(hint in low for hint in _INPUT_HINTS)
        is_output = any(hint in low for hint in _OUTPUT_HINTS)

        if not _looks_tick_series(arr, n_ticks):
            continue

        series = _ensure_tick_major(arr, n_ticks)
        if is_input and not is_output:
            inputs[key] = series
        elif is_output and not is_input:
            outputs[key] = series
        elif is_input and is_output:
            # Ambiguous keys are available to both sides; process tests can pin keys.
            inputs[key] = series
            outputs[key] = series
        else:
            unclassified_series.append(key)

    # If we detected a multi-tick series but no explicit output keys, default to output side.
    if n_ticks > 1 and not outputs:
        for key in unclassified_series:
            outputs[key] = _ensure_tick_major(np.asarray(arrays[key]), n_ticks)

    return inputs, outputs, unclassified_series


def _strip_replay_channel_prefix(key: str, *, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if key.startswith(prefix):
            return _normalize_array_key(key[len(prefix) :])
    return _normalize_array_key(key)


def _rewrite_replay_io_keys(
    inputs: dict[str, np.ndarray],
    outputs: dict[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    rewritten_inputs: dict[str, np.ndarray] = {}
    rewritten_outputs: dict[str, np.ndarray] = {}

    for raw_key, series in inputs.items():
        key = _strip_replay_channel_prefix(raw_key, prefixes=_REPLAY_INPUT_PREFIXES)
        if key in rewritten_inputs and raw_key != key:
            raise ValueError(
                f"Replay fixture input key collision after prefix stripping: {raw_key!r} -> {key!r}"
            )
        rewritten_inputs[key] = series

    for raw_key, series in outputs.items():
        key = _strip_replay_channel_prefix(raw_key, prefixes=_REPLAY_OUTPUT_PREFIXES)
        if key in rewritten_outputs and raw_key != key:
            raise ValueError(
                f"Replay fixture output key collision after prefix stripping: {raw_key!r} -> {key!r}"
            )
        rewritten_outputs[key] = series

    return rewritten_inputs, rewritten_outputs


def _select_default_fixture_root(process_name: str) -> Path:
    stem = _normalize_process_name(process_name)
    replay_npz = _REPLAY_FIXTURE_ROOT / f"{stem}.npz"
    replay_json = _REPLAY_FIXTURE_ROOT / f"{stem}.json"
    if replay_npz.exists() and replay_json.exists():
        return _REPLAY_FIXTURE_ROOT
    return _DEFAULT_FIXTURE_ROOT


def load_per_process_fixture(process_name: str, root: Path | None = None) -> KarrReplayFixture:
    """Load one per-process fixture from ``data/karr_fixtures/per_process``.

    Input/output split heuristic:
    - Input keys: names containing markers such as ``states_before``/``_before``/``input``.
    - Output keys: names containing markers such as ``states_after``/``_after``/``output``/``delta``.
    - If no clear split is available (common in current flattened fixtures), inputs/outputs
      may be empty and process-specific tests should provide explicit key mappings.
    """
    fixture_root = Path(root) if root is not None else _select_default_fixture_root(process_name)
    base = _normalize_process_name(process_name)
    replay_json_path = fixture_root / f"{base}.json"
    replay_npz_path = fixture_root / f"{base}.npz"
    replay_has_artifacts = replay_json_path.exists() and replay_npz_path.exists()
    legacy_mat_path = fixture_root / f"{base}_flat.mat"

    using_replay_npz = replay_has_artifacts and not legacy_mat_path.exists()
    if using_replay_npz:
        fixture_path = replay_npz_path
        companion_json = _load_companion_json(replay_json_path)
        arrays = _load_companion_npz(replay_npz_path, normalize_keys=False)
        companion_json_path = replay_json_path
        companion_npz_path = replay_npz_path
    else:
        fixture_path = _resolve_fixture_path(process_name, fixture_root)
        stem = fixture_path.stem
        if stem.endswith("_flat"):
            base = stem[:-5]
        companion_json_path = fixture_path.with_name(f"{base}.json")
        companion_npz_path = fixture_path.with_name(f"{base}.npz")
        companion_json = _load_companion_json(companion_json_path)
        arrays = _load_companion_npz(companion_npz_path)

    n_ticks = _infer_n_ticks(arrays, companion_json)
    inputs, outputs, unclassified = _split_inputs_outputs(arrays, n_ticks=n_ticks)
    if using_replay_npz:
        inputs, outputs = _rewrite_replay_io_keys(inputs, outputs)

    metadata: dict[str, Any] = {
        "root": str(fixture_root),
        "companion_json_path": str(companion_json_path) if companion_json_path.exists() else None,
        "companion_npz_path": str(companion_npz_path) if companion_npz_path.exists() else None,
        "manifest": companion_json.get("manifest", {}),
        "json_scalars": companion_json.get("scalars", {}),
        "array_keys": sorted(arrays.keys()),
        "fixture_field_names": _try_extract_fixture_field_names(fixture_path),
        "io_split_rule": {
            "input_hints": list(_INPUT_HINTS),
            "output_hints": list(_OUTPUT_HINTS),
            "fallback": (
                "If no clear keys are present, inputs/outputs remain partial or empty; "
                "process-specific replay tests should define explicit mappings."
            ),
        },
        "unclassified_tick_series_keys": sorted(unclassified),
    }

    return KarrReplayFixture(
        process_name=base,
        fixture_path=fixture_path,
        n_ticks=int(max(1, n_ticks)),
        inputs=inputs,
        outputs=outputs,
        metadata=metadata,
    )


def _slice_tick_value(series: np.ndarray, tick_index: int, n_ticks: int) -> np.ndarray:
    arr = np.asarray(series)
    if n_ticks <= 1:
        if arr.ndim == 0:
            return arr
        return np.asarray(arr[0])

    if arr.ndim > 0 and arr.shape[0] == n_ticks:
        return np.asarray(arr[tick_index])
    if arr.ndim > 1 and arr.shape[-1] == n_ticks:
        return np.asarray(np.take(arr, tick_index, axis=-1))
    raise ValueError(f"Value is not tick-indexed with n_ticks={n_ticks}: shape={arr.shape}")


def _to_python_value(value: np.ndarray) -> Any:
    arr = np.asarray(value)
    if arr.ndim == 0:
        return arr.item()
    return arr


def _unflatten_state(flat_state: dict[str, np.ndarray]) -> dict[str, Any]:
    nested: dict[str, Any] = {}
    for key, value in flat_state.items():
        parts = [part for part in key.split("/") if part]
        if not parts:
            continue
        cursor = nested
        for part in parts[:-1]:
            if part not in cursor or not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = _to_python_value(value)
    return nested


def _flatten_mapping(payload: Any, *, prefix: str = "") -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}

    if isinstance(payload, dict):
        for key, value in payload.items():
            next_prefix = f"{prefix}/{key}" if prefix else str(key)
            out.update(_flatten_mapping(value, prefix=next_prefix))
        return out

    if prefix:
        out[prefix] = np.asarray(payload)
    return out


def _resolve_timestep(process: Any) -> float:
    parameters = getattr(process, "parameters", {})
    if isinstance(parameters, dict):
        raw = parameters.get("time_step", 1.0)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 1.0
    return 1.0


def replay_one_tick(
    process: Any,
    fixture: KarrReplayFixture,
    tick_index: int,
) -> dict[str, np.ndarray]:
    """Replay one recorded tick against a Vivarium process instance."""

    if tick_index < 0 or tick_index >= fixture.n_ticks:
        raise IndexError(f"tick_index {tick_index} out of range [0, {fixture.n_ticks})")

    tick_inputs = {
        key: _slice_tick_value(series, tick_index, fixture.n_ticks)
        for key, series in fixture.inputs.items()
    }
    nested_state = _unflatten_state(tick_inputs)
    timestep = _resolve_timestep(process)
    update = process.next_update(timestep, nested_state)
    return _flatten_mapping(update)


def _format_diff(actual: np.ndarray, expected: np.ndarray, *, atol: float) -> tuple[float, float]:
    delta = np.abs(actual - expected)
    max_abs = float(np.nanmax(delta)) if delta.size else 0.0
    denom = np.maximum(np.abs(expected), atol)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(denom > 0, delta / denom, np.where(delta > 0, np.inf, 0.0))
    max_rel = float(np.nanmax(rel)) if rel.size else 0.0
    return max_abs, max_rel


def assert_replay_match(
    actual: dict[str, np.ndarray],
    expected: dict[str, np.ndarray],
    *,
    rtol: float = 1e-5,
    atol: float = 0.0,
    keys: Iterable[str] | None = None,
) -> None:
    """Assert replay output matches expected values, accumulating all mismatches."""

    if keys is None:
        keys_to_check = sorted(set(actual.keys()) | set(expected.keys()))
    else:
        keys_to_check = [str(key) for key in keys]

    failures: list[str] = []
    for key in keys_to_check:
        if key not in actual:
            failures.append(f"{key}: missing in actual")
            continue
        if key not in expected:
            failures.append(f"{key}: missing in expected")
            continue

        a = np.asarray(actual[key])
        e = np.asarray(expected[key])

        if a.shape != e.shape:
            failures.append(f"{key}: shape mismatch actual={a.shape} expected={e.shape}")
            continue

        numeric = np.issubdtype(a.dtype, np.number) and np.issubdtype(e.dtype, np.number)
        if numeric:
            if not np.allclose(a, e, rtol=rtol, atol=atol, equal_nan=True):
                max_abs, max_rel = _format_diff(a.astype(np.float64), e.astype(np.float64), atol=atol)
                failures.append(
                    f"{key}: value mismatch max_abs={max_abs:.6g} max_rel={max_rel:.6g}"
                )
        else:
            if not np.array_equal(a, e):
                failures.append(f"{key}: non-numeric mismatch")

    if failures:
        details = "\n".join(f"- {item}" for item in failures)
        raise AssertionError(f"Replay mismatch summary ({len(failures)} issue(s)):\n{details}")


__all__ = [
    "KarrReplayFixture",
    "assert_replay_match",
    "load_per_process_fixture",
    "replay_one_tick",
]
