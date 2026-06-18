from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
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

from l2_2_replay_common_v2 import run_integrated_replay_v2

_PAIR_LIST_PATH = _REPO_ROOT / "data/schemas/l25_pair_list.toml"
_EXPECTED_DS_PAIR_COUNT = 43


def _load_deterministic_stochastic_pairs() -> list[tuple[str, str]]:
    with _PAIR_LIST_PATH.open("rb") as handle:
        data = tomllib.load(handle)

    pairs: list[tuple[str, str]] = []
    for pair in data["pairs"]:
        if not pair.get("l25_honest_required"):
            continue
        if pair.get("pair_oracle_complexity") != "deterministic_stochastic":
            continue
        pairs.append((str(pair["process_a"]), str(pair["process_b"])))

    return pairs


DS_PAIRS = _load_deterministic_stochastic_pairs()
if len(DS_PAIRS) != _EXPECTED_DS_PAIR_COUNT:
    raise AssertionError(
        "L2.5 DS pair inventory mismatch: "
        f"expected {_EXPECTED_DS_PAIR_COUNT}, found {len(DS_PAIRS)}"
    )
DS_PAIR_CASES = [
    pytest.param(process_a, process_b, id=f"{process_a}+{process_b}")
    for process_a, process_b in DS_PAIRS
]


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
@pytest.mark.parametrize(("process_a", "process_b"), DS_PAIR_CASES)
def test_l25_deterministic_stochastic_pair_no_hints(
    process_a: str,
    process_b: str,
    rng_seed: int,
) -> None:
    """L2.5 honest-mode DS pair replay with catalog-driven per-side oracles."""
    run_integrated_replay_v2(
        under_test_processes=[process_a, process_b],
        rng_seed=rng_seed,
        disable_trace_hints=True,
    )
