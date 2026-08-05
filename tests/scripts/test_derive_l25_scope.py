"""Regenerability and correctness tests for scripts/derive_l25_scope.py.

Run via `bin\\oc-pytest tests/scripts/test_derive_l25_scope.py -v`.

Two families of test here:
  1. Isolated unit tests of the selection algorithm and gap-grep heuristic
     against synthetic fixtures (no dependency on real oracle traces / L2.2
     evidence -- these must pass in any environment).
  2. Real-data regenerability tests against the actual repo tree (denominator
     facts, byte-stable double-run, and the current honest eligible set) --
     these require the same local oracle-trace / evidence-sweep data the
     rest of the L2.1/L2.2 test suite already depends on.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import derive_l25_pair_matrix as pairmat  # noqa: E402
import derive_l25_scope as scope  # noqa: E402


def _make_pair(
    a: str,
    b: str,
    *,
    tier: int = 1,
    complexity: str = "stochastic_stochastic",
    substrates: int = 0,
    enzymes: int = 0,
    monomers: int = 0,
    complexs: int = 0,
    rnas: int = 0,
) -> pairmat.PairRecord:
    return pairmat.PairRecord(
        process_a=a,
        process_b=b,
        substrates_shared=[],
        enzymes_shared=[],
        monomers_shared=[],
        complexs_shared=[],
        rnas_shared=[],
        substrates_overlap=substrates,
        enzymes_overlap=enzymes,
        monomers_overlap=monomers,
        complexs_overlap=complexs,
        rnas_overlap=rnas,
        total_overlap=substrates + enzymes + monomers + complexs + rnas,
        classification="shared_pool",
        tier=tier,
        l2_2_passed_a=True,
        l2_2_passed_b=True,
        oracle_type_a="distributional",
        oracle_type_b="distributional",
        pair_oracle_complexity=complexity,
        l25_honest_required=True,
    )


def _make_verdict(name: str, *, eligible: bool, gap: bool = False) -> scope.ProcessVerdict:
    return scope.ProcessVerdict(
        name=name,
        bucket="ALGORITHMIC_SHALLOW",
        oracle_type="distributional",
        oc_module=None,
        gate_verdict="PASS" if eligible else "FAIL",
        gate_detail={},
        eligible=eligible,
        known_short_circuit_gap=gap,
        gap_reason="synthetic gap" if gap else None,
    )


# ---------------------------------------------------------------------------
# 1. Synthetic, environment-independent unit tests
# ---------------------------------------------------------------------------


def test_process_verdict_eligible_gap_free_requires_both():
    assert _make_verdict("A", eligible=True, gap=False).eligible_gap_free is True
    assert _make_verdict("A", eligible=True, gap=True).eligible_gap_free is False
    assert _make_verdict("A", eligible=False, gap=False).eligible_gap_free is False


def test_required_coverage_classes_are_derived_from_structural_pairs_only():
    pairs = [
        _make_pair("A", "B", tier=1, complexity="stochastic_stochastic", substrates=2),
        _make_pair("C", "D", tier=2, complexity="deterministic_stochastic", enzymes=1),
    ]
    classes = scope._required_coverage_classes(pairs)
    # Only classes structurally present among the given pairs are required --
    # no "monomers"/"complexs"/"rnas" channel class since no synthetic pair
    # touches those groups, and no deterministic_deterministic complexity.
    assert ("oracle_complexity", "stochastic_stochastic") in classes
    assert ("oracle_complexity", "deterministic_stochastic") in classes
    assert ("oracle_complexity", "deterministic_deterministic") not in classes
    assert ("contention_tier", "1") in classes
    assert ("contention_tier", "2") in classes
    assert ("shared_wid_channel", "substrates") in classes
    assert ("shared_wid_channel", "enzymes") in classes
    assert ("shared_wid_channel", "monomers") not in classes


def test_selection_never_uses_a_known_gap_process_even_if_it_would_cover_a_class():
    # A is eligible but gap-flagged; B and C are both clean-eligible but their
    # pair does not cover the same class combination as (A, B). The selector
    # must NOT select (A, B) to satisfy that class -- it must report the
    # class UNCOVERED_ONLY_VIA_KNOWN_GAP instead of silently waiving the gap.
    pair_gap = _make_pair("A", "B", tier=1, complexity="stochastic_stochastic", substrates=3)
    pair_clean = _make_pair("B", "C", tier=2, complexity="deterministic_stochastic", enzymes=1)
    eligibility = {
        "A": _make_verdict("A", eligible=True, gap=True),
        "B": _make_verdict("B", eligible=True, gap=False),
        "C": _make_verdict("C", eligible=True, gap=False),
    }
    result = scope.select_minimal_covering_set([pair_gap, pair_clean], eligibility)

    selected_keys = {(p.process_a, p.process_b) for p in result["selected_pairs"]}
    assert ("A", "B") not in selected_keys, "known-gap process must never be selected"

    uncovered_reasons = {
        (row["class"]["kind"], row["class"]["value"]): row["reason"] for row in result["uncovered"]
    }
    assert uncovered_reasons[("oracle_complexity", "stochastic_stochastic")] == (
        "UNCOVERED_ONLY_VIA_KNOWN_GAP"
    )
    # blocking_pair must be reported for operator transparency
    blocking = next(
        row
        for row in result["coverage_report"]
        if row["class"] == {"kind": "oracle_complexity", "value": "stochastic_stochastic"}
    )
    assert blocking["blocking_pair"] == ["A", "B"]


def test_selection_covers_a_class_with_a_gap_free_eligible_pair():
    pair_clean = _make_pair("B", "C", tier=2, complexity="deterministic_stochastic", enzymes=1)
    eligibility = {
        "B": _make_verdict("B", eligible=True, gap=False),
        "C": _make_verdict("C", eligible=True, gap=False),
    }
    result = scope.select_minimal_covering_set([pair_clean], eligibility)
    assert len(result["uncovered"]) == 0
    selected_keys = {(p.process_a, p.process_b) for p in result["selected_pairs"]}
    assert ("B", "C") in selected_keys


def test_selection_reports_no_eligible_pair_when_neither_process_qualifies():
    pair = _make_pair("X", "Y", tier=1, complexity="stochastic_stochastic", substrates=1)
    eligibility = {
        "X": _make_verdict("X", eligible=False),
        "Y": _make_verdict("Y", eligible=False),
    }
    result = scope.select_minimal_covering_set([pair], eligibility)
    assert result["selected_pairs"] == []
    reasons = {row["reason"] for row in result["uncovered"]}
    assert reasons == {"UNCOVERED_NO_ELIGIBLE_PAIR"}


def test_grep_known_short_circuit_gap_repo_relative_contract(tmp_path, monkeypatch):
    fake_repo = tmp_path
    module_rel = "opencell/vivarium/fake_proc.py"
    module_abs = fake_repo / module_rel
    module_abs.parent.mkdir(parents=True)
    module_abs.write_text("hint = states.get('trace_hint', {})\n")

    monkeypatch.setattr(scope, "_REPO", fake_repo)
    gap, reason = scope._grep_known_short_circuit_gap(module_rel)
    assert gap is True
    assert "trace_hint" in reason

    module_abs.write_text("no short circuit token here\n")
    gap2, reason2 = scope._grep_known_short_circuit_gap(module_rel)
    assert gap2 is False
    assert reason2 is None


def test_grep_known_short_circuit_gap_missing_module_fails_closed():
    gap, reason = scope._grep_known_short_circuit_gap("opencell/vivarium/does_not_exist_xyz.py")
    assert gap is True
    assert reason is not None and "does not exist" in reason and "failing closed" in reason


def test_grep_known_short_circuit_gap_none_module_fails_closed():
    gap, reason = scope._grep_known_short_circuit_gap(None)
    assert gap is True
    assert reason is not None and "failing closed" in reason


# ---------------------------------------------------------------------------
# 2. Real-data regenerability tests (require local oracle traces + evidence)
# ---------------------------------------------------------------------------


def test_denominator_is_28_canonical_processes_with_378_total_pairs():
    payload, _ok = scope.build_payload()
    assert payload["denominator"]["canonical_karr_process_count"] == 28
    assert len(payload["processes"]) == 28
    assert payload["denominator"]["total_pairs_c_28_2"] == 378
    assert (
        payload["denominator"]["structural_shared_pool_pairs"]
        + payload["denominator"]["structural_disjoint_pairs"]
        == 378
    )


def test_two_independent_builds_are_byte_stable():
    first, _ = scope.build_payload()
    second, _ = scope.build_payload()
    rendered_first = scope.render_yaml(first)
    rendered_second = scope.render_yaml(second)
    assert rendered_first == rendered_second
    assert first["content_hash"] == second["content_hash"]


def test_terminal_organelle_assembly_is_eligible_but_gap_flagged_today():
    # Ground-truth fact established by direct investigation (see
    # docs/phase_f/L2_5_SCOPE_RATIFICATION.md): TerminalOrganelleAssembly is
    # L2.1-GENUINE (bit-identity honest-mode) but still carries a live
    # `trace_hint` short-circuit reference per L2_5_SHORTCIRCUIT_AUDIT.md, so
    # it must be eligible=True but eligible_gap_free=False -- i.e. it may
    # never be silently selected into a pair, even though its gate is green.
    payload, _ok = scope.build_payload()
    row = next(p for p in payload["processes"] if p["name"] == "TerminalOrganelleAssembly")
    assert row["eligible"] is True
    assert row["known_short_circuit_gap"] is True
    assert row["eligible_gap_free"] is False


def test_no_selected_pair_ever_includes_an_ineligible_or_gapped_process():
    payload, _ok = scope.build_payload()
    eligible_gap_free_names = {p["name"] for p in payload["processes"] if p["eligible_gap_free"]}
    for pair in payload["selected_pairs"]:
        assert pair["process_a"] in eligible_gap_free_names
        assert pair["process_b"] in eligible_gap_free_names


def test_summary_ok_matches_uncovered_classes_emptiness():
    payload, ok = scope.build_payload()
    expected = (
        len(payload["uncovered_classes"]) == 0
        and len(payload["processes"]) == 28
        and payload["registry_integrity"]["ok"]
    )
    assert ok == expected
    assert payload["summary"]["ok"] == ok
    assert payload["registry_integrity"]["ok"] is True
    assert payload["registry_integrity"]["violations"] == []


def test_check_mode_matches_tracked_artifact(tmp_path):
    """The tracked docs/phase_f/l2_5/L2_5_SCOPE_CATALOG.yaml must always be
    exactly what a fresh run produces -- this is the regenerability
    obligation from the task contract (no hand-edited catalog fields)."""
    tracked = REPO_ROOT / "docs" / "phase_f" / "l2_5" / "L2_5_SCOPE_CATALOG.yaml"
    assert tracked.exists(), "run scripts/derive_l25_scope.py to (re)generate the tracked catalog"
    payload, _ok = scope.build_payload()
    fresh_rendered = scope.render_yaml(payload)
    assert fresh_rendered == tracked.read_text(encoding="utf-8"), (
        "tracked L2_5_SCOPE_CATALOG.yaml is stale vs. a fresh derivation -- "
        "regenerate with `bin\\oc-py scripts/derive_l25_scope.py`"
    )


# ---------------------------------------------------------------------------
# 3. Registry/pair-universe drift mutation tests
# ---------------------------------------------------------------------------
#
# These prove the fail-closed contract requested after Opus review: missing
# per-process TOMLs or catalog rows must never be able to shrink the
# structural pair universe (and therefore the required coverage classes)
# far enough to spuriously flip `ok` to True. All three monkeypatch the real
# repo-loading functions so they still exercise the real 28-process data,
# just with one function's return value truncated.


def test_registry_integrity_flags_missing_schema_and_forces_ok_false(monkeypatch):
    real_load = pairmat._load_process_schemas

    def _drop_metabolism(root, catalog_lookup):
        return [s for s in real_load(root, catalog_lookup) if s.name != "Metabolism"]

    monkeypatch.setattr(pairmat, "_load_process_schemas", _drop_metabolism)
    payload, ok = scope.build_payload()

    assert ok is False
    assert payload["registry_integrity"]["ok"] is False
    violations = " ".join(payload["registry_integrity"]["violations"])
    assert "Metabolism" in violations
    assert "name-set mismatch" in violations
    assert "378" in violations  # total pair count drift is also reported


def test_registry_integrity_catches_drastic_schema_shrink_that_would_otherwise_look_covered(
    monkeypatch,
):
    """Without the registry-integrity gate, shrinking the live schema set to
    just the two structurally-disjoint eligible processes would make
    ``shared_pool_pairs`` empty, ``_required_coverage_classes`` return an
    empty list (nothing left to require coverage for), and the pre-fix
    ``ok = len(uncovered) == 0 and len(verdicts) == 28`` formula would
    therefore have spuriously reported ``ok=True`` -- even though 26 of 28
    processes' per-process TOMLs had silently vanished from the pair
    universe (``verdicts`` is derived from the catalog, not from
    ``schemas``, so it stays at 28 regardless). This is exactly the
    "hollow green" failure mode the registry-integrity check exists to
    close."""
    real_load = pairmat._load_process_schemas
    keep = {"ProteinActivation", "TerminalOrganelleAssembly"}

    def _shrink(root, catalog_lookup):
        return [s for s in real_load(root, catalog_lookup) if s.name in keep]

    monkeypatch.setattr(pairmat, "_load_process_schemas", _shrink)
    payload, ok = scope.build_payload()

    # Confirm the premise: the shrunk pair universe has zero shared-pool
    # pairs (ProteinActivation x TerminalOrganelleAssembly is structurally
    # disjoint), so there is nothing left that requires coverage.
    assert payload["denominator"]["structural_shared_pool_pairs"] == 0
    assert payload["summary"]["n_uncovered_classes"] == 0

    # And yet ok must be False: registry_integrity catches the schema-count
    # and pair-universe drift even though coverage looks trivially satisfied.
    assert payload["registry_integrity"]["ok"] is False
    assert ok is False
    violations = " ".join(payload["registry_integrity"]["violations"])
    assert "name-set mismatch" in violations
    assert "378" in violations


def test_registry_integrity_catches_catalog_side_drift(monkeypatch):
    """Symmetric check for catalog-side (rather than schema-side) drift.
    This direction is already caught by the pre-existing
    ``len(verdicts) == 28`` guard, but registry_integrity must independently
    flag and explain it too, since it is the single gate a reviewer is told
    to check."""
    real_load_rows = scope._load_raw_catalog_rows

    def _drop_row(path):
        rows = dict(real_load_rows(path))
        rows.pop("Metabolism", None)
        return rows

    monkeypatch.setattr(scope, "_load_raw_catalog_rows", _drop_row)
    payload, ok = scope.build_payload()

    assert len(payload["processes"]) == 27
    assert ok is False
    assert payload["registry_integrity"]["ok"] is False
    violations = " ".join(payload["registry_integrity"]["violations"])
    assert "Metabolism" in violations
    assert "name-set mismatch" in violations
    assert "catalog process count is 27" in violations


def test_no_independently_hardcoded_catalog_path_constant():
    """derive_l25_scope.py must not define its own second PROCESS_CATALOG.yaml
    path constant alongside derive_l25_pair_matrix's candidate-list
    resolution -- exactly one function (`pairmat._load_catalog`) may decide
    which file "the catalog" is, or a future
    docs/phase_f/PROCESS_CATALOG.yaml could silently split the two
    derivations onto different files."""
    assert not hasattr(scope, "CATALOG_PATH"), (
        "found a standalone CATALOG_PATH constant in derive_l25_scope.py -- "
        "the catalog path must be resolved exactly once, via "
        "derive_l25_pair_matrix._load_catalog(_REPO), and reused from there"
    )


def test_build_payload_records_the_same_catalog_path_pairmat_resolves():
    """The `denominator.source` field recorded in the payload must name the
    same file `derive_l25_pair_matrix._load_catalog` resolves to -- i.e.
    build_payload's own raw-row parse and its schema/pair machinery agree on
    one authoritative catalog path, not two independently-derived ones."""
    _catalog_lookup, expected_path, _fallback_mode = pairmat._load_catalog(scope._REPO)
    expected_rel = expected_path.relative_to(scope._REPO).as_posix()
    payload, _ok = scope.build_payload()
    assert payload["denominator"]["source"].startswith(expected_rel)


def test_catalog_path_resolution_is_shared_not_independently_hardcoded(monkeypatch, tmp_path):
    """Simulates the future scenario the operator flagged: a new
    docs/phase_f/PROCESS_CATALOG.yaml starts taking precedence over
    docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml. Patching
    `pairmat._load_catalog`'s resolved path -- the single authoritative
    resolution point -- must be sufficient to redirect BOTH the schema
    loader and build_payload's own raw-row parse. If derive_l25_scope.py
    still had a second, independently hardcoded path constant, this
    monkeypatch would have no effect on the raw-row parse and this test
    would fail."""
    real_catalog_path = scope._REPO / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
    fake_catalog = tmp_path / "PROCESS_CATALOG.yaml"
    fake_catalog.write_text(real_catalog_path.read_text(encoding="utf-8"), encoding="utf-8")

    real_load_catalog = pairmat._load_catalog

    def _fake_load_catalog(root):
        lookup, _old_path, fallback_mode = real_load_catalog(root)
        return lookup, fake_catalog, fallback_mode

    monkeypatch.setattr(pairmat, "_load_catalog", _fake_load_catalog)

    seen_paths: list[Path] = []
    real_load_rows = scope._load_raw_catalog_rows

    def _spy_load_rows(path):
        seen_paths.append(path)
        return real_load_rows(path)

    monkeypatch.setattr(scope, "_load_raw_catalog_rows", _spy_load_rows)

    scope.build_payload()

    assert seen_paths == [fake_catalog], (
        "build_payload must resolve the catalog path exactly once via "
        "derive_l25_pair_matrix._load_catalog and reuse it for its own "
        "raw-row parse -- a second, independently hardcoded path would "
        "silently ignore this monkeypatch and keep reading the real file"
    )
