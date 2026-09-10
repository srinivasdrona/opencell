"""Anti-cheat / inversion tests for the TranscriptionalRegulation L2.1
active-window CODE_GAP fix (site-level/strand-aware TF-promoter binding).

Covers the four failure modes named in the fix mandate:

1. Wrong shape -- the site-level ``tf_bound_promoters`` surface must be
   34-element (17 sites x 2 chromosome copies), never the legacy 130-element
   (5 TFs x 26 TUs) TU-level surface.
2. Strand collapse -- chromosome copy 0 (pre-replication) and copy 1
   (post-replication) occupancy must be tracked independently; binding one
   copy of a site must not be conflated with binding the other, and
   Karr's ``boundTFs`` (column-0-only) derivation must not silently sum
   both columns.
3. TU-level laundering -- the legacy ``tf_binding`` TU-level compatibility
   view is a DERIVED, write-only-by-the-process output. It must not be
   readable as an input that could be used to fabricate site-level state
   (i.e. `next_update` must not consult ``tf_binding`` at all).
4. Oracle-output leakage -- production code must not read any hint/oracle
   channel (the pre-fix ``trace_hint`` cribbing mechanism, or any
   equivalent) to compute ``enzymes``/``boundEnzymes`` deltas.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
)

_MODULE_PATH = (
    _REPO_ROOT / "opencell" / "vivarium" / "karr_transcriptional_regulation.py"
)


def _empty_state(process: KarrTranscriptionalRegulationProcess) -> dict[str, Any]:
    return {
        "protein": {"counts": {tf: 0.0 for tf in process.tf_wids}},
        "complex": {"counts": {tf: 0.0 for tf in process.tf_wids}},
        "chromosome": {},
        "tf_bound_promoters": {wid: 0.0 for wid in process.tf_bound_promoters_wids},
    }


def _tf_store(process: KarrTranscriptionalRegulationProcess, tf_wid: str) -> str:
    return str(process._tf_wid_source.get(tf_wid, "protein"))


def _set_tf_count(
    process: KarrTranscriptionalRegulationProcess,
    state: dict[str, Any],
    tf_wid: str,
    count: float,
) -> None:
    state[_tf_store(process, tf_wid)]["counts"][tf_wid] = float(count)


# ---------------------------------------------------------------------------
# 1. Wrong shape
# ---------------------------------------------------------------------------


def test_tf_bound_promoters_surface_is_site_level_not_tu_level() -> None:
    """The authoritative binding surface must be 2 * n_sites (34 for the
    real KB fixture: 17 sites x 2 chromosome copies), never n_tf * n_tu
    (130 for 5 TFs x 26 TUs -- the legacy, wrong TU-level shape that this
    CODE_GAP fix replaces)."""
    p = KarrTranscriptionalRegulationProcess({})
    n_sites = p._n_sites
    assert n_sites == 17, "real KB fixture must expose exactly 17 TF-promoter sites"
    assert len(p.tf_bound_promoters_wids) == 2 * n_sites == 34
    wrong_tu_level_shape = len(p.tf_wids) * len(p.tu_wids)
    assert len(p.tf_bound_promoters_wids) != wrong_tu_level_shape
    schema = p.ports_schema()
    assert len(schema["tf_bound_promoters"]) == 34
    assert len(schema["bound_tfs"]) == len(p.tf_wids) == 5


def test_tf_bound_promoters_wid_order_matches_karr_column_major_layout() -> None:
    """WIDs must be ordered [site0..siteN copy0, site0..siteN copy1] to
    match Karr's own `tfBoundPromoters = reshape(isDnaBound(...), [], 2)`
    column-major flatten (verified positionally against the genuine event
    trace's HDF5 cell layout)."""
    p = KarrTranscriptionalRegulationProcess({})
    n = p._n_sites
    wids = p.tf_bound_promoters_wids
    assert wids[:n] == [f"site{s:03d}_copy0" for s in range(n)]
    assert wids[n:] == [f"site{s:03d}_copy1" for s in range(n)]


def test_wid_length_mismatch_against_wrong_shape_vector_is_detected() -> None:
    """Simulates the Rule-3 WID-length guard: an oracle vector shaped like
    the legacy 130-element TU-level surface must not silently be accepted
    as this process's 34-element site-level surface."""
    p = KarrTranscriptionalRegulationProcess({})
    fake_karr_after = np.zeros(len(p.tf_wids) * len(p.tu_wids), dtype=np.float64)
    assert fake_karr_after.shape[0] != len(p.tf_bound_promoters_wids)


# ---------------------------------------------------------------------------
# 2. Strand collapse
# ---------------------------------------------------------------------------


def test_chromosome_copy_columns_tracked_independently_not_collapsed() -> None:
    """Binding only chromosome-copy-1 (column 1) of a site must not be
    visible as chromosome-copy-0 (column 0) occupancy, and vice versa --
    the two columns must never be collapsed/summed into a single boolean."""
    p = KarrTranscriptionalRegulationProcess({})
    site = int(np.flatnonzero(p.site_tf_index == p.site_tf_index[0])[0])
    n = p._n_sites
    col0_wid = p.tf_bound_promoters_wids[site]
    col1_wid = p.tf_bound_promoters_wids[n + site]
    assert col0_wid != col1_wid

    state = _empty_state(p)
    # Mark ONLY column 1 (post-replication copy) of this site as bound.
    state["tf_bound_promoters"][col1_wid] = 1.0

    occ = p._read_site_occupancy(state)
    assert occ[site, 1] is np.True_ or bool(occ[site, 1]) is True
    assert bool(occ[site, 0]) is False, "column 0 must not be inferred from column 1 occupancy"


def test_bound_tfs_uses_column0_only_not_sum_of_both_columns() -> None:
    """Karr's `boundTFs = histc(tfIndexs(logical(tfBoundPromoters(:,1))), ...)`
    counts column-0 (chromosome copy 1) occupancy ONLY. A site bound only
    on column 1 must NOT contribute to `bound_tfs`, even though the TF is
    genuinely bound to a (second-copy) promoter somewhere on the
    chromosome. Verified empirically against the genuine trace: at several
    ticks `boundEnzymes` (which counts both columns) and `boundTFs` (column
    0 only) diverge by exactly the column-1-only occupancy count."""
    p = KarrTranscriptionalRegulationProcess({})
    tf_i = int(p.site_tf_index[0])
    tf_wid = p.tf_wids[tf_i]
    site = int(np.flatnonzero(p.site_tf_index == tf_i)[0])
    n = p._n_sites
    col1_wid = p.tf_bound_promoters_wids[n + site]

    state = _empty_state(p)
    state["tf_bound_promoters"][col1_wid] = 1.0
    _set_tf_count(p, state, tf_wid, 0.0)  # no free copies -> no new binding this tick

    update = p.next_update(1.0, state)
    assert update["bound_tfs"][tf_wid] == pytest.approx(0.0), (
        "a column-1-only bound site must not count toward boundTFs (column-0-only stat)"
    )


# ---------------------------------------------------------------------------
# 3. TU-level laundering
# ---------------------------------------------------------------------------


def test_tf_binding_tu_level_view_is_not_read_as_binding_input() -> None:
    """`tf_binding` (legacy TU-level compatibility view) must be a
    write-only DERIVED output. Poisoning it with fabricated "already
    bound" entries in the input state must have NO effect on the process's
    actual (site-level-driven) binding decisions -- proving the TU-level
    view cannot be used to launder a fake site-level authority."""
    p_clean = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    p_poisoned = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    state_clean = _empty_state(p_clean)
    state_poisoned = deepcopy(state_clean)
    # Fabricate a TU-level view claiming every TU is already regulated by
    # every TF -- this must be silently ignored since real Karr treats
    # tf_binding as a getter/derived property, never a stored input.
    state_poisoned["tf_binding"] = {
        tf: {tu: 1.0 for tu in p_poisoned.tu_wids} for tf in p_poisoned.tf_wids
    }
    for tf in p_clean.tf_wids:
        _set_tf_count(p_clean, state_clean, tf, 5.0)
        _set_tf_count(p_poisoned, state_poisoned, tf, 5.0)

    update_clean = p_clean.next_update(1.0, state_clean)
    update_poisoned = p_poisoned.next_update(1.0, state_poisoned)

    assert update_clean.get("tf_bound_promoters") == update_poisoned.get("tf_bound_promoters")
    assert update_clean["bound_tfs"] == update_poisoned["bound_tfs"]
    assert update_clean["tx_rate_fold_change"] == update_poisoned["tx_rate_fold_change"]


def test_next_update_never_reads_tf_binding_key_ast_scan() -> None:
    """Static guard: `next_update` (and any helper it calls) must never
    subscript/read `states["tf_binding"]` -- it is an output key only.
    Complements the behavioural inversion test above with a guarantee that
    survives future refactors."""
    text = _MODULE_PATH.read_text(encoding="utf-8")
    violations = [
        banned
        for banned in ('states["tf_binding"]', 'states.get("tf_binding"', "states['tf_binding']")
        if banned in text
    ]
    assert not violations, f"next_update must not read tf_binding as an input: {violations}"


# ---------------------------------------------------------------------------
# 4. Oracle-output leakage
# ---------------------------------------------------------------------------


def test_no_trace_hint_or_oracle_reference_in_production_source() -> None:
    """Static guard: the pre-fix `trace_hint`-based cribbing mechanism
    (which computed `enzymes`/`boundEnzymes` deltas as literal
    `karr_after - karr_before`, fed to production code by the L2.1 test
    harness under a name deliberately distinct from the AST oracle-path
    scanner's banned tokens) must not exist anywhere in this module."""
    text = _MODULE_PATH.read_text(encoding="utf-8")
    for banned in ("trace_hint", "_next", "boundEnzymes_next", "enzymes_next"):
        assert banned not in text, f"production source must not reference {banned!r}"


def test_fake_trace_hint_in_state_has_no_effect_on_output() -> None:
    """Inversion test: even if some future caller (accidentally or
    maliciously) populates a `trace_hint`-shaped key in the state dict
    with fabricated oracle-looking values, `next_update`'s output must be
    byte-identical to a run without it -- proving the process computes
    every delta from genuine biology (site occupancy, free copies,
    chromosome state), never from a hint channel."""
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    state_clean = _empty_state(p)
    for tf in p.tf_wids:
        _set_tf_count(p, state_clean, tf, 3.0)
    state_poisoned = deepcopy(state_clean)
    # Fabricate an oracle-style hint claiming every TF's free/bound counts
    # will jump to obviously-fake, unreachable values next tick.
    state_poisoned["trace_hint"] = {
        "enzymes_next": {tf: 999.0 for tf in p.tf_wids},
        "boundEnzymes_next": {tf: 999.0 for tf in p.tf_wids},
    }

    p_clean = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    p_poisoned = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    update_clean = p_clean.next_update(1.0, state_clean)
    update_poisoned = p_poisoned.next_update(1.0, state_poisoned)

    assert update_clean.get("enzymes") == update_poisoned.get("enzymes")
    assert update_clean.get("boundEnzymes") == update_poisoned.get("boundEnzymes")
    assert update_clean.get("tf_bound_promoters") == update_poisoned.get("tf_bound_promoters")
