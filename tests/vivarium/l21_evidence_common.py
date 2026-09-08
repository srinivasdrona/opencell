from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_L21_ACTIVE_WINDOWS_MANIFEST_PATH = (
    _REPO_ROOT / "docs" / "phase_f" / "l2_1" / "L21_ACTIVE_WINDOWS_MANIFEST.json"
)


def _l21_manifest_classification(process_name: str) -> str | None:
    try:
        payload = json.loads(_L21_ACTIVE_WINDOWS_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for row in payload.get("rows", []):
        if row.get("process") == process_name:
            return row.get("classification")
    return None


def skip_or_fail_missing_artifact(path: Path, process_name: str, description: str) -> None:
    """Fail for missing evidence claimed by the manifest; otherwise skip."""
    classification = _l21_manifest_classification(process_name)
    message = f"{description}: {path}"
    if classification == "EXISTING_WINDOW_PASS":
        pytest.fail(
            f"{message} -- FAILING (not skipping): "
            f"{_L21_ACTIVE_WINDOWS_MANIFEST_PATH.as_posix()} records "
            f"classification=EXISTING_WINDOW_PASS for {process_name!r}, so this artifact "
            "MUST exist. Regenerate the trace or correct the stale manifest row."
        )
    pytest.skip(message)
