from __future__ import annotations

from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
_METABOLISM_ORACLE_PATH = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay" / "Metabolism.npz"


def load_karr_oracle(process: str) -> dict[str, Any]:
    """Load the canonical Karr replay fixture for a Design-A process."""
    raise NotImplementedError(f"Design-A oracle loading is not implemented yet for {process!r}.")


def run_oc_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell tick from a prepared state snapshot."""
    raise NotImplementedError("Design-A OC replay is not implemented yet.")


def compute_w1(oc: Any, karr: Any) -> float:
    """Compute the channel Wasserstein distance between OC and Karr samples."""
    raise NotImplementedError("Design-A W1 computation is not implemented yet.")


def compute_null_q95(*args: Any, **kwargs: Any) -> float:
    """Compute the 95th percentile of the Karr-only null calibration."""
    raise NotImplementedError("Design-A null calibration is not implemented yet.")


__all__ = [
    "_METABOLISM_ORACLE_PATH",
    "compute_null_q95",
    "compute_w1",
    "load_karr_oracle",
    "run_oc_tick",
]
