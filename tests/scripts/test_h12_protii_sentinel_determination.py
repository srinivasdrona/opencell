"""Regression tests pinning the ProteinProcessingII H12 SENTINEL_FAIL
determination (see
docs/phase_f/l2_2_design_a/h12/perturbation/
PROTEINPROCESSINGII_MNRND_SHIM_DETERMINATION_2026-08-05.md).

This file does NOT attempt to flip the verdict green. It mechanically
pins two things:

  1. The current `H12_OBSERVED_REGIME` sentinel for ProteinProcessingII is
     reproducible from on-disk artifacts (fresh hashes, `decide_verdict`
     re-derivation, `validate_h12_support` rejection reason) -- so a
     future reader can trust the SENTINEL_FAIL in `evidence_index.json` is
     mechanically justified, not stale or hand-edited.
  2. The repaired manual `mnrnd` compatibility shim
     (`scripts/matlab/mnrnd.m`, fixed for the Canary D duplicate-bin-edge
     crash) is never wired into the genuine-MATLAB H12 Scenario B pathway
     (`scripts/matlab_h12_perturbation/`, `scripts/l22_evidence/
     h12_perturbation.py`) as a substitute for the missing Statistics
     Toolbox `mnrnd` -- doing so would silently swap Karr's real
     conditional-binomial `mnrnd` algorithm for this shim's different
     per-trial categorical-sampling algorithm under the same seed, which is
     exactly the "distributionally different RNG" bypass this
     determination rules out.

Run via `bin\\oc-pytest tests/scripts/test_h12_protii_sentinel_determination.py -v`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import (
    h12,  # noqa: E402
    schema,  # noqa: E402
)

PROCESS = "ProteinProcessingII"
ARTIFACT_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / f"{PROCESS}_h12.json"
EVIDENCE_INDEX_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "evidence_index.json"
SCENARIO_B_DRIVER = REPO_ROOT / "scripts" / "matlab_h12_perturbation" / "run_ppii_scenario_b_matlab.m"
SCENARIO_B_PROBE = REPO_ROOT / "scripts" / "matlab_h12_perturbation" / "probe_matlab_environment.m"
H12_PERTURBATION_SOURCE = REPO_ROOT / "scripts" / "l22_evidence" / "h12_perturbation.py"
MANUAL_MNRND_SHIM = REPO_ROOT / "scripts" / "matlab" / "mnrnd.m"


def _load_artifact() -> dict:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Structural (paren/quote-aware) MATLAB call-argument parsing helpers.
#
# These exist because a plain substring search (e.g. `"scripts/matlab'" not
# in source`) misses semantically-equivalent ways of spelling the same
# addpath target: `addpath('../matlab')`, `addpath(fullfile(this_dir, '..',
# 'matlab'))`, `addpath(fullfile(repo_root, 'scripts', 'matlab'))`, or a
# variable built up in several steps. Parsing the actual call arguments (via
# balanced paren/quote scanning, not a single regex over the whole line)
# lets the test assert the POSITIVE contract -- the only addpath(...) call
# is `addpath(wholecell_src)` with `wholecell_src` bound to exactly
# `getenv('PPII_WHOLECELL_SRC_ROOT')` -- rather than an open-ended list of
# banned spellings that can never be exhaustive.
# ---------------------------------------------------------------------------


def _extract_call_arg_texts(source: str, func_name: str) -> list[str]:
    """Return the raw (unsplit) argument-list text of every top-level
    `func_name(...)` call in `source`, located by balanced paren/quote
    scanning rather than a single regex, so parens/quotes nested inside an
    argument (e.g. another function call) do not truncate the match."""
    calls = []
    for m in re.finditer(rf"(?<![.\w]){re.escape(func_name)}\s*\(", source):
        i = m.end()
        depth = 1
        in_squote = False
        in_dquote = False
        start = i
        while i < len(source) and depth > 0:
            ch = source[i]
            if in_squote:
                if ch == "'":
                    if i + 1 < len(source) and source[i + 1] == "'":
                        i += 1  # MATLAB '' escaped-quote inside a literal
                    else:
                        in_squote = False
            elif in_dquote:
                if ch == '"':
                    in_dquote = False
            elif ch == "'":
                in_squote = True
            elif ch == '"':
                in_dquote = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        calls.append(source[start : i - 1])
    return calls


def _split_top_level_args(args_text: str) -> list[str]:
    """Split a call's raw argument text on top-level commas only (commas
    inside nested parens/brackets/quotes do not split)."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_squote = False
    in_dquote = False
    i = 0
    while i < len(args_text):
        ch = args_text[i]
        if in_squote:
            current.append(ch)
            if ch == "'":
                if i + 1 < len(args_text) and args_text[i + 1] == "'":
                    current.append(args_text[i + 1])
                    i += 1
                else:
                    in_squote = False
        elif in_dquote:
            current.append(ch)
            if ch == '"':
                in_dquote = False
        elif ch == "'":
            in_squote = True
            current.append(ch)
        elif ch == '"':
            in_dquote = True
            current.append(ch)
        elif ch in "([{":
            depth += 1
            current.append(ch)
        elif ch in ")]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append("".join(current).strip())
    return [p for p in parts if p != ""]


def _as_matlab_literal(arg: str) -> str | None:
    """If `arg` (already trimmed) is a single quoted MATLAB/Octave string
    literal, return its unquoted value; otherwise `None` (it is an
    identifier, expression, or call)."""
    arg = arg.strip()
    if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "'\"":
        return arg[1:-1].replace("''", "'")
    return None


def _assert_addpath_only_resolves_to_wholecell_src(path: Path) -> None:
    """Structurally enforce the intended Scenario B addpath contract for a
    single `.m` file:

      1. Every `fullfile(...)` call's literal arguments are scanned for a
         contiguous ('scripts','matlab') or ('..','matlab') subsequence
         (case-insensitive) -- either would resolve to the manual mnrnd
         shim's directory (`scripts/matlab`), the second being the
         relative sibling-dir spelling from
         `scripts/matlab_h12_perturbation/`.
      2. A defense-in-depth literal-text scan (both path separators,
         case-insensitive) catches any single-literal spelling of
         `scripts/matlab` or a relative `../matlab` that isn't inside a
         `fullfile(...)` call.
      3. There is EXACTLY ONE `addpath(...)` call in the file, and its
         sole argument is the bare identifier `wholecell_src` -- not a
         literal, not `fullfile(...)`, not any other expression.
      4. Every assignment to the bare name `wholecell_src` (not a
         qualified/field name like `report.wholecell_src_root_used`) has a
         right-hand side that is exactly `getenv('PPII_WHOLECELL_SRC_ROOT')`
         -- so the identifier addpath'd in (3) cannot itself have been
         quietly redefined to point at the shim directory.

    Together (3)+(4) mean the ONLY thing this file can ever addpath is
    whatever `PPII_WHOLECELL_SRC_ROOT` resolves to at runtime, and (1)+(2)
    mean nothing anywhere in the file can construct a path that resolves
    to the manual shim's directory in the first place.
    """
    source = path.read_text(encoding="utf-8")

    for args_text in _extract_call_arg_texts(source, "fullfile"):
        literals = [_as_matlab_literal(a) for a in _split_top_level_args(args_text)]
        lowered = [lit.lower() if lit is not None else None for lit in literals]
        for i in range(len(lowered) - 1):
            pair = (lowered[i], lowered[i + 1])
            assert pair != ("scripts", "matlab"), (
                f"{path.name}: fullfile(...) constructs a ('scripts','matlab') path "
                "-- would resolve to the manual mnrnd shim's directory"
            )
            assert pair != ("..", "matlab"), (
                f"{path.name}: fullfile(...) constructs a relative ('..','matlab') "
                "path -- would resolve to the manual mnrnd shim's directory from "
                "scripts/matlab_h12_perturbation/"
            )

    normalized_single_quoted = source.replace("\\", "/").replace('"', "'").lower()
    assert "'scripts/matlab'" not in normalized_single_quoted, (
        f"{path.name}: literal 'scripts/matlab' path fragment found"
    )
    assert "'../matlab'" not in normalized_single_quoted, f"{path.name}: literal '../matlab' path fragment found"

    addpath_args = _extract_call_arg_texts(source, "addpath")
    assert len(addpath_args) == 1, (
        f"{path.name}: expected exactly one addpath(...) call, found {len(addpath_args)}: {addpath_args!r}"
    )
    sole_arg = addpath_args[0].strip()
    assert sole_arg == "wholecell_src", (
        f"{path.name}: addpath(...) must take the bare identifier 'wholecell_src' as "
        f"its ONLY argument, got {sole_arg!r} -- a literal, fullfile(...), or any "
        "other expression here would bypass this structural check"
    )

    assignments = re.findall(r"(?<![.\w])wholecell_src\s*=\s*([^;]+);", source)
    assert assignments, f"{path.name}: no assignment to the bare identifier wholecell_src found"
    for rhs in assignments:
        assert rhs.strip() == "getenv('PPII_WHOLECELL_SRC_ROOT')", (
            f"{path.name}: wholecell_src must be assigned exactly from "
            f"getenv('PPII_WHOLECELL_SRC_ROOT'), got {rhs.strip()!r}"
        )


_EQUIVALENCE_WORD = re.compile(r"\bbit[- ]identical\b|\bequivalent\b|\bidentical\b", re.IGNORECASE)
_STATS_TOOLBOX_OR_REAL_MNRND_MENTION = re.compile(r"statistics toolbox|real\s+mnrnd", re.IGNORECASE)
_NEGATION_WORD = re.compile(r"\b(not|never|n't|no|isn't|doesn't|cannot|can't)\b", re.IGNORECASE)


def _assert_no_unsupported_equivalence_claim(source: str, label: str) -> None:
    """Semantic guard (not a blind substring ban): permits truthful
    disclaimers such as "NOT bit-identical to the Statistics Toolbox's
    mnrnd" or "never claims bit-identity with the real mnrnd" (both true
    and desirable to state), but fails on any UNNEGATED claim that the
    manual shim IS bit-identical/equivalent/identical to the real
    Statistics Toolbox mnrnd -- a false claim this determination
    explicitly rules out, since the two algorithms consume the RNG
    stream's uniforms in structurally different amounts/orders.

    Scoped to matches near a "Statistics Toolbox"/"real mnrnd" mention so
    unrelated, true statements (e.g. mnrnd.m's own "pure language core,
    identical in MATLAB and Octave") are not flagged.
    """
    for m in _EQUIVALENCE_WORD.finditer(source):
        context = source[max(0, m.start() - 20) : m.end() + 80]
        if not _STATS_TOOLBOX_OR_REAL_MNRND_MENTION.search(context):
            continue
        preceding = source[max(0, m.start() - 45) : m.start()]
        assert _NEGATION_WORD.search(preceding), (
            f"{label}: found an unnegated claim ({m.group(0)!r} near offset {m.start()}) "
            "that the manual mnrnd shim is bit-identical/equivalent/identical to the "
            "real Statistics Toolbox mnrnd -- this determination requires the opposite "
            "(the algorithms are NOT equivalent); any text making this comparison must "
            "say so explicitly, e.g. 'NOT bit-identical'"
        )


# ---------------------------------------------------------------------------
# 1. Reproduce the current sentinel derivation mechanically.
# ---------------------------------------------------------------------------


def test_artifact_file_exists_and_is_the_primary_gating_artifact():
    assert ARTIFACT_PATH.is_file()
    payload = _load_artifact()
    assert payload["process"] == PROCESS


def test_predictor_source_hash_is_fresh_not_stale():
    """The artifact's recorded predictor hash must match a fresh re-hash of
    the on-disk `scripts/l22_evidence/h12.py` -- if this ever fails, the
    artifact is stale and must be regenerated before its verdict can be
    trusted at all (see h12.py's v4 evaluator-schema note)."""
    payload = _load_artifact()
    module_path = REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH
    assert payload["predictor_source_sha256_lf_normalized"] == h12._sha256_lf_normalized(module_path)


def test_vendored_karr_source_hash_is_fresh_not_stale():
    payload = _load_artifact()
    citation = payload["karr_source_citation"]
    vendored_path = REPO_ROOT / citation["vendored_path"]
    assert citation["vendored_sha256_lf_normalized"] == h12._sha256_lf_normalized(vendored_path)


def test_fixture_hash_is_fresh_not_stale():
    payload = _load_artifact()
    fixture_path = REPO_ROOT / payload["fixture_path"]
    assert payload["fixture_sha256"] == h12._sha256_file(fixture_path)


def test_decide_verdict_recomputation_from_stored_metrics_matches_artifact_exactly():
    """Feed the artifact's OWN recorded nontrivial/exact-match/branch
    metrics back through the pure, independently-testable `decide_verdict`
    function and require an exact (verdict, verdict_reason) match -- this
    is the mechanical reproduction of the sentinel's derivation without
    needing the (locally unavailable) full 50-seed oracle trace."""
    payload = _load_artifact()
    verdict, reason = h12.decide_verdict(
        payload["nontrivial_sample_count"],
        payload["exact_match_count"],
        payload["exact_match_rate"],
        payload["trivial_mismatch_count"],
        set(payload["branches_confirmed"]),
        h12.REQUIRED_BRANCHES[PROCESS],
    )
    assert verdict == payload["verdict"] == "H12_OBSERVED_REGIME"
    assert reason == payload["verdict_reason"]


def test_missing_required_branch_is_exactly_transferase_fires():
    payload = _load_artifact()
    assert payload["missing_required_branches"] == ["transferase_fires"]
    assert set(payload["branches_confirmed"]) == {"passthrough_fires", "peptidase_fires"}
    assert h12.REQUIRED_BRANCHES[PROCESS] == frozenset(
        {"passthrough_fires", "peptidase_fires", "transferase_fires"}
    )


def test_validate_h12_support_rejects_real_artifact_today():
    """The central acceptance gate must mechanically reject this artifact
    right now, with a reason naming the actual stored (non-CONFIRMED)
    verdict -- this is the exact mechanism producing evidence_index.json's
    SENTINEL_FAIL for the ProteinProcessingII row."""
    payload = _load_artifact()
    reason = h12.validate_h12_support(payload, expected_process=PROCESS)
    assert reason is not None
    assert "H12_CONFIRMED" in reason
    assert "H12_OBSERVED_REGIME" in reason


def test_evidence_index_ppii_row_records_matching_sentinel_fail():
    """Read-only check of the shared evidence_index.json (never edited by
    this task): the ProteinProcessingII row's reasons must currently
    contain the exact SENTINEL_FAIL string this determination explains."""
    payload = json.loads(EVIDENCE_INDEX_PATH.read_text(encoding="utf-8"))
    rows = [row for row in payload["rows"] if row["process"] == PROCESS]
    assert len(rows) == 1
    row = rows[0]
    assert row["green"] is False
    assert row["mechanical_verdict"] == schema.STATUS_FAIL
    assert any(
        reason.startswith(schema.STATUS_SENTINEL_FAIL) and "H12_OBSERVED_REGIME" in reason
        for reason in row["reasons"]
    )


# ---------------------------------------------------------------------------
# 2. The repaired manual mnrnd shim must never be wired into Scenario B.
# ---------------------------------------------------------------------------


def test_manual_mnrnd_shim_file_exists_and_is_unrelated_subsystem():
    """Sanity: the shim this task investigated is a real, tracked file, so
    the "never wired in" checks below are checking against a real
    artifact, not a typo'd path that would vacuously pass."""
    assert MANUAL_MNRND_SHIM.is_file()
    source = MANUAL_MNRND_SHIM.read_text(encoding="utf-8")
    assert "Minimal multinomial RNG fallback" in source
    assert "Deliberately does NOT call histcounts" in source
    # Semantic (not blind-substring) guard: the shim's docstring may
    # truthfully disclose it is NOT bit-identical/equivalent to the real
    # Statistics Toolbox mnrnd, but must never claim that it IS.
    _assert_no_unsupported_equivalence_claim(source, label=str(MANUAL_MNRND_SHIM))


@pytest.mark.parametrize("path", [SCENARIO_B_DRIVER, SCENARIO_B_PROBE])
def test_scenario_b_matlab_scripts_addpath_only_ever_resolves_to_wholecell_src(path):
    """Structural guard: parses the actual `addpath(...)`/`fullfile(...)`
    call arguments in each genuine-MATLAB Scenario B script (via
    paren/quote-aware scanning, NOT a substring match over the raw text),
    and requires that the file's ONLY `addpath(...)` call is
    `addpath(wholecell_src)` with `wholecell_src` bound to exactly
    `getenv('PPII_WHOLECELL_SRC_ROOT')`. This structurally rules out
    `addpath('../matlab')`, `addpath(fullfile(this_dir, '..', 'matlab'))`,
    `addpath(fullfile(repo_root, 'scripts', 'matlab'))`, and any
    variable-indirected path that resolves to the manual mnrnd shim's
    directory (`scripts/matlab`) -- not just the specific literal
    spellings a substring check would need to enumerate."""
    _assert_addpath_only_resolves_to_wholecell_src(path)


@pytest.mark.parametrize(
    ("source", "should_pass"),
    [
        pytest.param("addpath(wholecell_src);\nwholecell_src = getenv('PPII_WHOLECELL_SRC_ROOT');\n", True, id="authorized"),
        pytest.param("addpath('../matlab');\n", False, id="relative-literal"),
        pytest.param("addpath(fullfile(repo_root, 'scripts', 'matlab'));\n", False, id="fullfile-scripts-matlab"),
        pytest.param("addpath(fullfile(this_dir, '..', 'matlab'));\n", False, id="fullfile-dotdot-matlab"),
        pytest.param(
            "addpath(wholecell_src);\nwholecell_src = fullfile(repo_root, 'scripts', 'matlab');\n",
            False,
            id="wholecell-src-redefined-to-shim-dir",
        ),
    ],
)
def test_addpath_structural_guard_rejects_every_named_bypass_shape(source, should_pass, tmp_path):
    """Adversarial probe for the guard itself (per FIX_TEMPLATE_L2_REPLAY's
    no-trace-cribbing / adversarial-probe discipline): proves
    `_assert_addpath_only_resolves_to_wholecell_src` actually rejects every
    bypass shape named in the task (relative literal, fullfile-split
    literal, fullfile-relative, and a redefined `wholecell_src` variable),
    not just the two real on-disk files, which could otherwise pass this
    guard vacuously if the checker itself were too permissive."""
    probe_path = tmp_path / "probe.m"
    probe_path.write_text(source, encoding="utf-8")
    if should_pass:
        _assert_addpath_only_resolves_to_wholecell_src(probe_path)
    else:
        with pytest.raises(AssertionError):
            _assert_addpath_only_resolves_to_wholecell_src(probe_path)


@pytest.mark.parametrize(
    ("source", "should_pass"),
    [
        pytest.param(
            "This shim is NOT bit-identical to the real Statistics Toolbox mnrnd.",
            True,
            id="truthful-negated-disclaimer",
        ),
        pytest.param(
            "This shim never claims to be equivalent to the Statistics Toolbox mnrnd.",
            True,
            id="truthful-never-claims",
        ),
        pytest.param(
            "the bin-counting loop is identical in MATLAB and Octave",
            True,
            id="unrelated-identical-claim-ignored",
        ),
        pytest.param(
            "This shim is bit-identical to the real Statistics Toolbox mnrnd.",
            False,
            id="false-unnegated-bit-identical-claim",
        ),
        pytest.param(
            "This shim is equivalent to the Statistics Toolbox mnrnd.",
            False,
            id="false-unnegated-equivalent-claim",
        ),
    ],
)
def test_equivalence_claim_guard_permits_truthful_disclaimers_but_rejects_false_claims(source, should_pass):
    """Adversarial probe for the semantic equivalence-claim guard itself:
    proves it passes truthful negated disclaimers and unrelated uses of
    "identical", but fails an unnegated claim that the shim IS
    bit-identical/equivalent to the real Statistics Toolbox mnrnd."""
    if should_pass:
        _assert_no_unsupported_equivalence_claim(source, label="probe")
    else:
        with pytest.raises(AssertionError):
            _assert_no_unsupported_equivalence_claim(source, label="probe")


def test_h12_perturbation_module_never_references_manual_mnrnd_shim():
    """The Python-side H12 perturbation module must never import, shell
    out to, or otherwise reference the manual mnrnd shim or its directory
    -- the Scenario B evidence pipeline is genuine-MATLAB-only end to
    end."""
    source = H12_PERTURBATION_SOURCE.read_text(encoding="utf-8")
    assert "scripts/matlab/mnrnd" not in source
    assert "scripts.matlab.mnrnd" not in source
    assert "scripts\\matlab\\mnrnd" not in source


def test_scenario_b_canary_artifact_honestly_records_missing_statistics_toolbox():
    """The already-executed canary artifact must keep recording the real,
    honest toolbox-availability gap -- not a laundered/assumed-available
    value."""
    canary_path = (
        REPO_ROOT
        / "docs"
        / "phase_f"
        / "l2_2_design_a"
        / "h12"
        / "perturbation"
        / f"{PROCESS}_h12_scenario_b_perturbation_canary.json"
    )
    payload = json.loads(canary_path.read_text(encoding="utf-8"))
    manifest = payload["states"]["transferase_capacity_scarce"]["run_manifest"]
    assert manifest["statistics_toolbox_installed"] is False
    assert payload["states"]["transferase_capacity_scarce"]["n_seeds"] == 20
    # This canary is stochasticRound-only evidence and must never be
    # relabeled/counted as N=50 catalog-domain evidence.
    assert payload["states"]["transferase_capacity_scarce"]["n_seeds"] != h12.CATALOG_N_M[PROCESS][0]
    assert payload["gating"].startswith("NON_GATING")


def test_scenario_a_perturbation_artifact_stays_non_gating_pending_reviewer_decision():
    """Scenario A (the RNG-invariant, already-`H12_PERTURBATION_CONFIRMED`
    evidence that actually targets the missing `transferase_fires` branch
    tag) must remain explicitly NON_GATING -- folding it into the primary
    artifact requires the separately-authorized CONDITION_GATED taxonomy
    decision, not a routine fix."""
    scenario_a_path = (
        REPO_ROOT
        / "docs"
        / "phase_f"
        / "l2_2_design_a"
        / "h12"
        / "perturbation"
        / f"{PROCESS}_h12_perturbation.json"
    )
    payload = json.loads(scenario_a_path.read_text(encoding="utf-8"))
    assert payload["gating"].startswith("NON_GATING")
    assert payload["verdict"] == "H12_PERTURBATION_CONFIRMED"
    assert payload["target_branch"] == "transferase_fires"


def test_condition_gated_taxonomy_proposal_still_not_implemented():
    """Guards against silent enactment: the CONDITION_GATED taxonomy
    remains PROPOSAL ONLY until a separately-authorized commit says
    otherwise. If this ever flips, `verdict.py`'s gate and this
    determination must be revisited together."""
    proposal_path = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "CONDITION_GATED_TAXONOMY_PROPOSAL.md"
    source = proposal_path.read_text(encoding="utf-8")
    assert "PROPOSAL ONLY" in source
    assert "NOT IMPLEMENTED ON THIS BRANCH" in source


def test_verdict_module_still_only_accepts_literal_h12_confirmed():
    """`_has_valid_h12_support`'s acceptance gate must still hard-require
    the literal string 'H12_CONFIRMED' -- no CONDITION_GATED/OBSERVED_REGIME
    synonym has been silently added to the accepted set."""
    verdict_path = REPO_ROOT / "scripts" / "l22_evidence" / "verdict.py"
    source = verdict_path.read_text(encoding="utf-8")
    assert '"H12_CONFIRMED"' in source
    h12_source = H12_PERTURBATION_SOURCE.parent / "h12.py"
    assert 'return "H12_CONFIRMED"' in h12_source.read_text(encoding="utf-8")
