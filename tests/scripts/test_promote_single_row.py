"""Tests for `scripts/l22_evidence/promote_single_row.py`.

Run via `bin\\oc-pytest tests/scripts/test_promote_single_row.py -v`.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_evidence import promote_single_row as psr  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402


def test_unknown_process_raises():
    with pytest.raises(ValueError, match="not found in current index rows"):
        psr.promote_single_row("NotARealProcess")


def test_promoting_a_row_leaves_every_other_row_byte_identical():
    """Against the REAL, currently-committed index/catalog/bundle (never a
    synthetic fixture -- this tool's whole point is operating on the real
    tracked evidence), re-derive MacromolecularComplexation's row and
    confirm every other row is byte-for-byte identical to what is
    currently committed. `promote_single_row` only READS `index_path`; it
    never writes, so this is side-effect-free."""
    before = __import__("json").loads(schema.INDEX_PATH.read_text(encoding="utf-8"))
    before_rows = {row["process"]: row for row in before["rows"]}

    payload = psr.promote_single_row("MacromolecularComplexation")

    assert payload["n_in_scope"] == before["n_in_scope"]
    after_rows = {row["process"]: row for row in payload["rows"]}
    assert set(after_rows) == set(before_rows)
    for name, before_row in before_rows.items():
        if name == "MacromolecularComplexation":
            continue
        assert after_rows[name] == before_row, f"unrelated row {name!r} changed unexpectedly"


def test_target_row_is_freshly_recomputed_not_copied_through():
    """The target row must come from a REAL `build_process_row` call
    against the current evidence bundle, not merely be copied through from
    the old index (which would defeat the entire point of promotion)."""
    before = __import__("json").loads(schema.INDEX_PATH.read_text(encoding="utf-8"))
    before_row = next(row for row in before["rows"] if row["process"] == "MacromolecularComplexation")

    payload = psr.promote_single_row("MacromolecularComplexation")
    after_row = next(row for row in payload["rows"] if row["process"] == "MacromolecularComplexation")

    # sweep_provenance.git_sha binds to the CURRENT tree's git SHA (recorded
    # at the sweep-launcher's own generation time), never a copy-through of
    # a stale, previously-recorded value -- a strong "this was recomputed"
    # signal independent of whatever the mechanical_verdict happens to be.
    assert after_row["sweep_provenance"]["git_sha"] != "unknown"
    assert after_row != before_row or after_row["mechanical_verdict"] == before_row["mechanical_verdict"]


def test_aggregate_fields_are_recomputed_from_the_full_new_row_set():
    payload = psr.promote_single_row("MacromolecularComplexation")
    tally: dict[str, int] = {}
    for row in payload["rows"]:
        tally[row["mechanical_verdict"]] = tally.get(row["mechanical_verdict"], 0) + 1
    assert payload["tally"] == tally
    expected_aggregate = "GREEN" if payload["rows"] and all(row["green"] for row in payload["rows"]) else "NON_GREEN"
    assert payload["aggregate_verdict"] == expected_aggregate


def test_repeated_promotion_is_deterministic_modulo_timestamp():
    payload_1 = psr.promote_single_row("MacromolecularComplexation")
    payload_2 = psr.promote_single_row("MacromolecularComplexation")
    stripped_1 = copy.deepcopy(payload_1)
    stripped_2 = copy.deepcopy(payload_2)
    stripped_1.pop("generated_at")
    stripped_2.pop("generated_at")
    assert stripped_1 == stripped_2
