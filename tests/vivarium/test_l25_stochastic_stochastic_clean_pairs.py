"""L2.5 honest-mode stochastic-stochastic clean-vs-clean pair sweep.

Mirrors `test_l25_deterministic_stochastic_pairs.py` but parametrizes over the
56 SS pairs from `docs/phase_f/L2_5_CLEAN_CLEAN_PAIRS.md` where BOTH processes
are classified CLEAN by `scripts/probe_hint_shortcircuit_audit.py` (i.e., the
process module contains no `trace_hint` usage).

Why clean-only: per `docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md` (Day-35), 13 of
28 L2.5 processes have hint-driven short-circuits that bypass biology when
`trace_hint` is present. L2.1 and L2.2 verdicts on those 13 processes are
oracle-leaked; L2.5 honest mode is the first gate to expose the biology
samplers.

This file deliberately excludes any pair involving one of the 13 short-
circuited processes. The expectation is that most clean-vs-clean SS pairs
should PASS honest mode (today's 11 DS clean-vs-clean run got 5/7 testable =
71% honest-green). Pairs that FAIL here are either:
  - Hidden short-circuits the audit missed (e.g., hint read via a different
    variable name); or
  - Real composition-time biology drift independent of trace_hint.

Both are valuable to surface.
"""

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

# The 56 SS clean-vs-clean pairs, sourced from
# `scripts/probe_clean_clean_pairs.py` against the Day-35 short-circuit audit.
# If the audit's classification changes, regenerate this list:
#   python scripts/probe_clean_clean_wiring.py | grep stochastic_stochastic
_CLEAN_SS_PAIRS: list[tuple[str, str]] = [
    ("ProteinFolding", "ProteinTranslocation"),
    ("ProteinFolding", "ProteinProcessingI"),
    ("ProteinFolding", "ProteinProcessingII"),
    ("ProteinProcessingI", "ProteinProcessingII"),
    ("ProteinProcessingI", "ProteinTranslocation"),
    ("ProteinProcessingII", "ProteinTranslocation"),
    ("RNAModification", "RNAProcessing"),
    ("MacromolecularComplexation", "ProteinFolding"),
    ("ProteinFolding", "RibosomeAssembly"),
    ("ProteinTranslocation", "RibosomeAssembly"),
    ("ProteinProcessingI", "RibosomeAssembly"),
    ("ProteinProcessingII", "RibosomeAssembly"),
    ("RNAModification", "tRNAAminoacylation"),
    ("RNAProcessing", "tRNAAminoacylation"),
    ("DNADamage", "DNARepair"),
    ("RNAProcessing", "RibosomeAssembly"),
    ("DNARepair", "RNAModification"),
    ("DNARepair", "tRNAAminoacylation"),
    ("ProteinTranslocation", "RNAProcessing"),
    ("DNARepair", "ProteinFolding"),
    ("DNARepair", "ProteinTranslocation"),
    ("DNARepair", "RNAProcessing"),
    ("ProteinFolding", "RNAProcessing"),
    ("ProteinFolding", "tRNAAminoacylation"),
    ("ProteinTranslocation", "tRNAAminoacylation"),
    ("RNAModification", "RibosomeAssembly"),
    ("Cytokinesis", "DNARepair"),
    ("Cytokinesis", "ProteinFolding"),
    ("Cytokinesis", "ProteinTranslocation"),
    ("Cytokinesis", "RNAProcessing"),
    ("Cytokinesis", "RibosomeAssembly"),
    ("Cytokinesis", "tRNAAminoacylation"),
    ("DNARepair", "RibosomeAssembly"),
    ("ProteinFolding", "RNAModification"),
    ("ProteinProcessingI", "tRNAAminoacylation"),
    ("ProteinTranslocation", "RNAModification"),
    ("RibosomeAssembly", "tRNAAminoacylation"),
    ("Cytokinesis", "DNADamage"),
    ("Cytokinesis", "ProteinProcessingI"),
    ("Cytokinesis", "ProteinProcessingII"),
    ("Cytokinesis", "RNAModification"),
    ("DNADamage", "ProteinFolding"),
    ("DNADamage", "ProteinProcessingI"),
    ("DNADamage", "ProteinProcessingII"),
    ("DNADamage", "ProteinTranslocation"),
    ("DNADamage", "RNAModification"),
    ("DNADamage", "RNAProcessing"),
    ("DNADamage", "RibosomeAssembly"),
    ("DNADamage", "tRNAAminoacylation"),
    ("DNARepair", "ProteinProcessingI"),
    ("DNARepair", "ProteinProcessingII"),
    ("ProteinProcessingI", "RNAModification"),
    ("ProteinProcessingI", "RNAProcessing"),
    ("ProteinProcessingII", "RNAModification"),
    ("ProteinProcessingII", "RNAProcessing"),
    ("ProteinProcessingII", "tRNAAminoacylation"),
]


def _validate_pairs_in_catalog() -> None:
    """Sanity check: every hardcoded pair must exist in l25_pair_list.toml
    with l25_honest_required=true. Fails fast if the catalog drifted."""
    with _PAIR_LIST_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    catalog_index: dict[frozenset[str], dict] = {
        frozenset({p["process_a"], p["process_b"]}): p for p in data["pairs"]
    }
    missing: list[str] = []
    not_honest_required: list[str] = []
    for a, b in _CLEAN_SS_PAIRS:
        key = frozenset({a, b})
        meta = catalog_index.get(key)
        if meta is None:
            missing.append(f"{a}+{b}")
        elif not meta.get("l25_honest_required"):
            not_honest_required.append(f"{a}+{b}")
    if missing or not_honest_required:
        raise AssertionError(
            "Clean SS pair list drifted from l25_pair_list.toml:\n"
            f"  missing: {missing}\n"
            f"  not honest-required: {not_honest_required}"
        )


_validate_pairs_in_catalog()

assert len(_CLEAN_SS_PAIRS) == 56, (
    f"Expected 56 clean SS pairs (per Day-35 audit), found {len(_CLEAN_SS_PAIRS)}"
)

_SS_PAIR_CASES = [
    pytest.param(a, b, id=f"{a}+{b}") for a, b in _CLEAN_SS_PAIRS
]


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
@pytest.mark.parametrize(("process_a", "process_b"), _SS_PAIR_CASES)
def test_l25_stochastic_stochastic_clean_pair_no_hints(
    process_a: str,
    process_b: str,
    rng_seed: int,
) -> None:
    """L2.5 honest-mode SS pair replay where neither side has a trace_hint
    short-circuit (per Day-35 audit). Predicted attack surface: ~63%
    honest-green by extrapolation from the DS clean-vs-clean run.
    """
    run_integrated_replay_v2(
        under_test_processes=[process_a, process_b],
        rng_seed=rng_seed,
        disable_trace_hints=True,
    )
