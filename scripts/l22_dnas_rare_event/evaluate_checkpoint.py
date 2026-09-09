"""Evaluate a frozen DNASupercoiling tensor checkpoint with the prereg gate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_dnas_rare_event.sparse_gate import (  # noqa: E402
    evaluate_process,
    guarantee_examples,
    sensitivity_evaluations,
)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _coerce_component_scales(raw: Any) -> dict[str, float]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): float(value) for key, value in raw.items()}
    if hasattr(raw, "item"):
        try:
            item = raw.item()
        except ValueError:
            item = None
        if isinstance(item, dict):
            return {str(key): float(value) for key, value in item.items()}
    if isinstance(raw, np.ndarray) and raw.dtype.kind in {"U", "S"} and raw.size == 1:
        try:
            payload = json.loads(str(raw.reshape(-1)[0]))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return {str(key): float(value) for key, value in payload.items()}
    raise ValueError("Could not decode component scales from checkpoint.")


def _load_tensor_checkpoint(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=True) as payload:
        keys = set(payload.files)
        oc_key = next((name for name in ("oc_tensor", "oc", "oc_projection_tensor") if name in keys), None)
        karr_key = next((name for name in ("karr_tensor", "karr", "karr_projection_tensor") if name in keys), None)
        if oc_key is None or karr_key is None:
            raise KeyError(f"Checkpoint {path} is missing OC/Karr tensor arrays; keys={sorted(keys)}")
        scales_key = next(
            (name for name in ("component_scales", "component_scales_json", "component_scale_map") if name in keys),
            None,
        )
        return {
            "keys": sorted(keys),
            "oc_tensor": np.array(payload[oc_key], dtype=np.float64, copy=True),
            "karr_tensor": np.array(payload[karr_key], dtype=np.float64, copy=True),
            "component_scales": _coerce_component_scales(payload[scales_key]) if scales_key is not None else {},
        }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, help="Path to the frozen tensor checkpoint .npz file.")
    parser.add_argument("--out", required=True, help="Output JSON path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    checkpoint_path = Path(args.checkpoint).resolve()
    out_path = Path(args.out).resolve()
    loaded = _load_tensor_checkpoint(checkpoint_path)
    primary = evaluate_process(
        loaded["oc_tensor"],
        loaded["karr_tensor"],
        loaded["component_scales"],
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_keys": loaded["keys"],
        "shape": list(loaded["oc_tensor"].shape),
        "component_scales": loaded["component_scales"],
        "guarantee_examples": guarantee_examples(),
        "primary_evaluation": primary,
        "sensitivity": sensitivity_evaluations(
            loaded["oc_tensor"],
            loaded["karr_tensor"],
            loaded["component_scales"],
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
