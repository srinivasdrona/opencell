"""Regression tests for scripts/derive_l25_pair_matrix.py's `_infer_l2_2_status`.

Covers the Opus round-3 finding: PROCESS_CATALOG.yaml's Cytokinesis row
originally added a `blocked_on` field to record that its N=50
event-window sweep is unauthorized pending a 50-seed onset-span survey
(see docs/phase_f/l2_event/CYTOKINESIS_ADAPTER_REPORT.md §11). `blocked_on`
turned out to be a pre-existing, reserved key already used by other
catalog entries (e.g. ChromosomeCondensation, ChromosomeSegregation:
`blocked_on: []`) and read directly by `_infer_l2_2_status()` as a
GENERIC L2.2 pass/fail signal -- any truthy value there flips the
inferred `l2_2_passed` to `False` for that process in the pairwise
matrix. Cytokinesis's non-empty string value collided with this,
incorrectly flipping its inferred status even though Cytokinesis's real
L2.2 in-scope status (`in_scope_L2_2: true`) is unrelated to the much
narrower N=50 event-sweep authorization gate. The field was renamed to
`event_sweep_blocked_on` to fix this; these tests pin both the fix and
the underlying collision behavior so neither regresses silently.

Run via `bin\\oc-pytest tests/scripts/test_derive_l25_pair_matrix.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import derive_l25_pair_matrix as m  # noqa: E402

CATALOG_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"


def _load_cytokinesis_entry() -> dict:
    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    entries = catalog["processes"] if isinstance(catalog, dict) else catalog
    for entry in entries:
        if entry.get("name") == "Cytokinesis":
            return entry
    raise AssertionError("Cytokinesis entry not found in PROCESS_CATALOG.yaml")


def test_cytokinesis_catalog_entry_has_no_generic_blocked_on_key():
    """The real, committed catalog must not carry the collision-prone
    generic `blocked_on` key for Cytokinesis -- only the renamed,
    event-sweep-specific field."""
    entry = _load_cytokinesis_entry()
    assert "blocked_on" not in entry
    assert "event_sweep_blocked_on" in entry
    assert entry["event_sweep_blocked_on"]


def test_cytokinesis_event_sweep_blocked_on_does_not_flip_l2_2_passed():
    """Reproduces the real catalog entry end-to-end: with the renamed
    field, `_infer_l2_2_status` must fall back to `in_scope_L2_2`
    (True), not the generic `blocked_on` fallback (False)."""
    entry = _load_cytokinesis_entry()
    passed, source = m._infer_l2_2_status(entry)
    assert passed is True
    assert source == "fallback:in_scope_L2_2"


def test_generic_blocked_on_key_still_flips_status_false():
    """Sanity check on the OTHER side of the collision: a synthetic
    entry using the real, reserved `blocked_on` key (as used by e.g.
    ChromosomeCondensation/ChromosomeSegregation in the catalog) is
    still correctly read as a generic L2.2 blocker. This pins the
    pre-existing behavior `_infer_l2_2_status` exists to provide, so a
    future edit can't accidentally weaken it while fixing the
    Cytokinesis-specific collision."""
    entry = {"name": "SyntheticProcess", "in_scope_L2_2": True, "blocked_on": "some reason"}
    passed, source = m._infer_l2_2_status(entry)
    assert passed is False
    assert source == "fallback:blocked_on"


def test_event_sweep_blocked_on_key_never_flips_status_on_a_synthetic_entry():
    """Isolates the fix from any other catalog quirks: a bare synthetic
    entry with ONLY `event_sweep_blocked_on` (no other status field)
    must fall back past it entirely, to `in_scope_L2_2` when present or
    `default_include` otherwise -- never treated as a status signal."""
    with_in_scope = {
        "name": "SyntheticProcess",
        "in_scope_L2_2": True,
        "event_sweep_blocked_on": "some reason",
    }
    passed, source = m._infer_l2_2_status(with_in_scope)
    assert passed is True
    assert source == "fallback:in_scope_L2_2"

    without_in_scope = {"name": "SyntheticProcess", "event_sweep_blocked_on": "some reason"}
    passed, source = m._infer_l2_2_status(without_in_scope)
    assert passed is True
    assert source == "fallback:default_include"


def test_pair_matrix_preexisting_staleness_is_unrelated_to_cytokinesis_catalog_edits():
    """`python scripts/derive_l25_pair_matrix.py --check` reports the
    committed docs/phase_f/L2_5_PAIR_MATRIX.md /
    data/schemas/l25_pair_list.toml as stale both with and without this
    branch's Cytokinesis catalog edits (last regenerated 2026-06-18,
    long before this branch existed) -- i.e. this branch did not cause
    new staleness and is not responsible for regenerating those
    artifacts. This test only pins that `_load_catalog` can still
    parse the real, current catalog file without raising; it
    deliberately does NOT assert freshness of the generated artifacts,
    which is an unrelated, pre-existing condition out of this branch's
    scope."""
    root = REPO_ROOT
    catalog_lookup, catalog_path, _fallback_mode = m._load_catalog(root)
    assert "Cytokinesis" in catalog_lookup
    assert catalog_path.exists()
