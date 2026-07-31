"""Targeted tests for scripts/l22_dnas_power/diagnostic_runner.py.

`seed_count_override` is unit-tested against a lightweight fake helpers
module (no real MAT files, no real OC simulation) to prove: (a) it only
intercepts the targeted process, (b) it passes through the override's
`max_seeds` value to `_load_v2_ensemble`, (c) it restores the original
`load_karr_oracle` attribute afterwards even if the wrapped code raises.

`run_seed_config`'s own argument-validation (max_seeds_override must exceed
max(seeds)) is tested directly; the real `run_design_a` call path itself is
exercised only by the (separately committed, non-unit-test) diagnostic
report run against real seed data -- reproducing it here would require the
full real oracle + OC simulation stack.

Run via `bin\\oc-pytest tests/scripts/test_l22_dnas_power_diagnostic_runner.py -v`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l22_dnas_power import diagnostic_runner  # noqa: E402


def _fake_helpers_module(*, v2_ensemble_seed_counts: dict[int, int]):
    """A fake helpers module whose `load_karr_oracle` always returns a
    sentinel distinguishable "legacy" payload, and whose `_load_v2_ensemble`
    returns a sentinel payload keyed by the `max_seeds` it was called with
    (or `None` if that `max_seeds` isn't in `v2_ensemble_seed_counts`, to
    simulate "no ensemble found at this seed count")."""
    module = types.SimpleNamespace()

    def _load_karr_oracle(process: str):
        return {"process": process, "canonical_seed_count": 1, "source": "legacy"}

    def _load_v2_ensemble(process: str, max_seeds: int = 50):
        if max_seeds not in v2_ensemble_seed_counts:
            return None
        return {"process": process, "canonical_seed_count": v2_ensemble_seed_counts[max_seeds], "source": "v2"}

    module.load_karr_oracle = _load_karr_oracle
    module._load_v2_ensemble = _load_v2_ensemble
    return module


def test_seed_count_override_widens_seed_search_for_target_process():
    helpers = _fake_helpers_module(v2_ensemble_seed_counts={100: 100})
    with diagnostic_runner.seed_count_override(helpers, "DNASupercoiling", 100):
        result = helpers.load_karr_oracle("DNASupercoiling")
    assert result == {"process": "DNASupercoiling", "canonical_seed_count": 100, "source": "v2"}


def test_seed_count_override_does_not_affect_other_processes():
    helpers = _fake_helpers_module(v2_ensemble_seed_counts={100: 100})
    with diagnostic_runner.seed_count_override(helpers, "DNASupercoiling", 100):
        result = helpers.load_karr_oracle("RNADecay")
    assert result == {"process": "RNADecay", "canonical_seed_count": 1, "source": "legacy"}


def test_seed_count_override_restores_original_after_exit():
    helpers = _fake_helpers_module(v2_ensemble_seed_counts={100: 100})
    original = helpers.load_karr_oracle
    with diagnostic_runner.seed_count_override(helpers, "DNASupercoiling", 100):
        pass
    assert helpers.load_karr_oracle is original


def test_seed_count_override_restores_original_even_on_exception():
    helpers = _fake_helpers_module(v2_ensemble_seed_counts={100: 100})
    original = helpers.load_karr_oracle
    with pytest.raises(RuntimeError):
        with diagnostic_runner.seed_count_override(helpers, "DNASupercoiling", 100):
            raise RuntimeError("boom")
    assert helpers.load_karr_oracle is original


def test_seed_count_override_falls_back_to_original_when_widened_returns_none():
    """If `_load_v2_ensemble(process, max_seeds=N)` returns None (e.g. fewer
    than N seed files actually exist on disk), the patched loader must fall
    back to the original (unpatched) `load_karr_oracle` rather than
    returning None itself."""
    helpers = _fake_helpers_module(v2_ensemble_seed_counts={})  # no max_seeds value resolves
    with diagnostic_runner.seed_count_override(helpers, "DNASupercoiling", 100):
        result = helpers.load_karr_oracle("DNASupercoiling")
    assert result == {"process": "DNASupercoiling", "canonical_seed_count": 1, "source": "legacy"}


def test_run_seed_config_rejects_max_seeds_override_not_exceeding_seeds(tmp_path):
    with pytest.raises(ValueError, match="max_seeds_override"):
        diagnostic_runner.run_seed_config(seeds=[0, 1, 99], out_dir=tmp_path, max_seeds_override=99)


def test_extract_primary_components_reads_chromosome_channel():
    payload = {
        "result": {
            "channels": {
                "chromosome": {
                    "per_component": {"component_n_nonzero_oc": {"linkingNumbers.delta_nnz": 17}},
                }
            }
        }
    }
    assert diagnostic_runner.extract_primary_components(payload) == {
        "component_n_nonzero_oc": {"linkingNumbers.delta_nnz": 17}
    }
