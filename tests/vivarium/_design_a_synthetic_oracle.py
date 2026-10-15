"""File-backed inputs for existing arithmetic-only runner unit tests."""

from pathlib import Path
from typing import Any

import _l2_2_design_a_runner_helpers as helpers
import numpy as np


def bind_synthetic_oracle(oracle: dict[str, Any], root: Path) -> dict[str, Any]:
    path = root / "synthetic_inputs" / f"{oracle['process']}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {key: value for key, value in oracle.items() if isinstance(value, np.ndarray)}
    np.savez(path, **arrays)
    source = helpers.capture_input_source(path)
    with np.load(path, allow_pickle=False) as data:
        loaded = {key: data[key] for key in data.files}
    helpers.verify_input_sources([source])
    return {**oracle, **loaded, "oracle_path": path, "input_sources": [source]}
