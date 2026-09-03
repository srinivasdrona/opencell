from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import chromcond_tick0_geometry_probe as base  # noqa: E402


def _coerce_rng_state(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _coerce_rng_state(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_coerce_rng_state(value) for value in node]
    if isinstance(node, (int, float)):
        return {
            "generator": "mcg16807",
            "seed": 0,
            "mcg_state": int(node),
        }
    return node


def _load_exact_matlab_ledger() -> dict[str, Any]:
    path = REPO / "tmp" / "chromcond_tick0_exact_geometry_probe.json"
    payload = json.loads(path.read_text())
    tick0 = payload["tick0"]
    samples = []
    for sample in tick0["samples"]:
        sample_copy = dict(sample)
        sample_copy["randStreamStateBefore"] = _coerce_rng_state(sample_copy["randStreamStateBefore"])
        sample_copy["randStreamStateAfter"] = _coerce_rng_state(sample_copy["randStreamStateAfter"])
        samples.append(sample_copy)
    return base._normalize_rng_states(  # noqa: SLF001
        {
            "outerPolymerized": tick0["outerPolymerized"],
            "existingSmcSites": tick0["existingSmcSites"],
            "shiftedSmcSpacingExclusions": tick0["shiftedSmcSpacingExclusions"],
            "outerAfterSmcExclusion": tick0["outerAfterSmcExclusion"],
            "accessibleRegions": tick0["accessibleRegions"],
            "bindingRegionsInitial": tick0["bindingRegionsInitial"],
            "samples": samples,
            "manualStoredPosStrnds": tick0["manualStoredPosStrnds"],
            "actualAddedSmcPosStrnds": tick0["actualAddedSmcPosStrnds"],
        }
    )


def main() -> int:
    matlab_ledger = _load_exact_matlab_ledger()
    python_ledger = base._normalize_rng_states(base._build_python_ledger())  # noqa: SLF001

    diff = base._compare("", matlab_ledger, python_ledger)  # noqa: SLF001
    if diff is None:
        print("FIRST_DIFFERING_DATUM none")
        return 0

    path, matlab_value, python_value = diff
    print("FIRST_DIFFERING_DATUM", path)
    print("MATLAB_VALUE", json.dumps(matlab_value, sort_keys=True))
    print("PYTHON_VALUE", json.dumps(python_value, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
