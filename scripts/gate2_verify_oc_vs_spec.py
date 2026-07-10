"""Gate 2 — report OC loaded input vocabularies vs the frozen Karr spec."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent

_DERIVE_SPEC = importlib.util.spec_from_file_location(
    "_gate2_derive_input_spec",
    SCRIPT_DIR / "derive_input_spec.py",
)
assert _DERIVE_SPEC is not None and _DERIVE_SPEC.loader is not None
derive_input_spec = importlib.util.module_from_spec(_DERIVE_SPEC)
_DERIVE_SPEC.loader.exec_module(derive_input_spec)

REPO_ROOT = derive_input_spec.REPO_ROOT
PROCESS_NAMES = derive_input_spec.PROCESS_NAMES
DEFAULT_SPEC_DIR = derive_input_spec.OUTPUT_ROOT
DEFAULT_FIXTURE_DIR = derive_input_spec.FIXTURE_ROOT
_REPLAY_COMMON_PATH = REPO_ROOT / "tests" / "vivarium" / "l2_2_replay_common_v2.py"
_ROLE_TO_SPEC_FIELD = {
    "substrates": "substrateWholeCellModelIDs",
    "enzymes": "enzymeWholeCellModelIDs",
}
_PREVIEW_LIMIT = 12


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_process_specs() -> Mapping[str, Any]:
    replay_spec = importlib.util.spec_from_file_location(
        "_gate2_replay_common_v2",
        _REPLAY_COMMON_PATH,
    )
    assert replay_spec is not None and replay_spec.loader is not None
    replay_common = importlib.util.module_from_spec(replay_spec)
    sys.modules[replay_spec.name] = replay_common
    replay_spec.loader.exec_module(replay_common)
    return replay_common._PROCESS_SPECS


def _normalize_vocab(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        return [value.decode("utf-8", errors="replace")]
    if isinstance(value, str):
        return [value]
    if isinstance(value, np.ndarray):
        return [str(item) for item in value.reshape(-1).tolist()]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _load_expected_vocab(spec_path: Path, *, role: str) -> list[str]:
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    vocabularies = payload.get("vocabularies") or {}
    field_name = _ROLE_TO_SPEC_FIELD[role]
    return [str(item) for item in vocabularies.get(field_name, [])]


def _compare_vocab_sets(*, expected: Iterable[str], actual: Iterable[str]) -> tuple[list[str], list[str]]:
    expected_set = set(expected)
    actual_set = set(actual)
    return sorted(expected_set - actual_set), sorted(actual_set - expected_set)


def _format_vocab_preview(wids: list[str]) -> str:
    if len(wids) <= _PREVIEW_LIMIT:
        preview = wids
    else:
        preview = [*wids[:_PREVIEW_LIMIT], f"+{len(wids) - _PREVIEW_LIMIT} more"]
    return f"[{', '.join(preview)}] (count={len(wids)})"


def _process_spec_items(
    process_specs: Mapping[str, Any] | None,
    *,
    process_names: tuple[str, ...],
) -> list[tuple[str, Any]]:
    specs = process_specs if process_specs is not None else _load_process_specs()
    return [(process_name, specs[process_name]) for process_name in process_names]


def _gate_result(
    *,
    spec_dir: Path = DEFAULT_SPEC_DIR,
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    process_specs: Mapping[str, Any] | None = None,
    process_names: tuple[str, ...] = PROCESS_NAMES,
) -> tuple[int, str]:
    expected = tuple(process_names)

    if not spec_dir.exists():
        return 0, (
            "GATE 2 (OC vs spec): SKIPPED — frozen spec dir absent at "
            f"{_display_path(spec_dir)}."
        )
    if not fixture_dir.exists():
        return 0, (
            "GATE 2 (OC vs spec): SKIPPED — fixtures absent at "
            f"{_display_path(fixture_dir)}."
        )

    missing_fixture_files = [
        process_name
        for process_name in expected
        if not (fixture_dir / f"{process_name}_flat.mat").exists()
    ]
    if missing_fixture_files:
        preview = ", ".join(missing_fixture_files[:4])
        if len(missing_fixture_files) > 4:
            preview += f", +{len(missing_fixture_files) - 4} more"
        return 0, (
            "GATE 2 (OC vs spec): SKIPPED — fixtures absent for "
            f"{len(missing_fixture_files)}/{len(expected)} expected process(es): {preview}."
        )

    findings: list[str] = []
    order_only_differences: list[str] = []
    divergent_processes = 0

    for process_name, spec in _process_spec_items(process_specs, process_names=expected):
        spec_path = spec_dir / f"{process_name}.yaml"
        if not spec_path.exists():
            findings.append(
                f"- {process_name}: missing frozen spec file {_display_path(spec_path)}"
            )
            divergent_processes += 1
            continue

        try:
            process = spec.process_cls({"rng_seed": 0})
        except Exception as exc:  # noqa: BLE001
            findings.append(
                f"- {process_name}: CONSTRUCT_ERROR {exc.__class__.__name__}: {exc}"
            )
            divergent_processes += 1
            continue

        role_findings: list[str] = []
        for role in ("substrates", "enzymes"):
            attr_name = spec.observable_to_wids_attr.get(role)
            oc_vocab = _normalize_vocab(getattr(process, attr_name, [])) if attr_name else []
            expected_vocab = _load_expected_vocab(spec_path, role=role)
            missing_in_oc, extra_in_oc = _compare_vocab_sets(
                expected=expected_vocab,
                actual=oc_vocab,
            )

            if missing_in_oc or extra_in_oc:
                role_findings.append(
                    f"{role} missing_in_oc={_format_vocab_preview(missing_in_oc)} "
                    f"extra_in_oc={_format_vocab_preview(extra_in_oc)}"
                )
                continue

            if expected_vocab != oc_vocab:
                order_only_differences.append(f"{process_name}.{role}")

        if role_findings:
            findings.append(f"- {process_name}: " + "; ".join(role_findings))
            divergent_processes += 1

    order_info = "INFO — order-only differences: [" + ", ".join(order_only_differences) + "]"

    if findings:
        return 1, "\n".join(
            [
                f"GATE 2 (OC vs spec): FAIL — {divergent_processes}/{len(expected)} processes diverge",
                *findings,
                order_info,
            ]
        )

    return 0, "\n".join(
        [
            f"GATE 2 (OC vs spec): PASS — {len(expected)}/{len(expected)} processes conform",
            order_info,
        ]
    )


def main() -> int:
    code, message = _gate_result()
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
