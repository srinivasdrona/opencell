"""Drift test binding each isolated Octave harness `.m` file used by
scripts/l22_evidence/h12_perturbation.py to a normalized, defined
transformation of the vendored Karr source it claims to transcribe.

Per Opus5 perturbation-review BLOCKER 7: the harness files are hand-written
"verbatim transcription" claims in their own docstrings/README, but nothing
previously enforced that claim mechanically. This test extracts the exact
cited vendored-source line range for each harness file, normalizes both
sides (drop blank lines and comments, collapse internal whitespace), applies
an explicit, minimal ALLOWED_SUBSTITUTIONS allow-list, and asserts the
result is identical. Any other difference is drift and fails the test.

The allow-list is intentionally small and documented per entry -- this is
NOT a general MATLAB-to-Octave transpiler/AST equivalence checker (out of
scope per the same review round), just a normalized-diff guard against the
specific, already-understood substitutions this harness relies on.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_ROOT = REPO_ROOT / "data" / "karr_vendored_source"
HARNESS_ROOT = REPO_ROOT / "scripts" / "octave_h12_perturbation"
# Genuine-MATLAB (not Octave) Scenario B harness files live in a separate
# directory specifically so the two execution engines (Octave stub-based
# Scenario A/macromol vs. real-MATLAB Scenario B) are never confused by
# file location alone -- see scripts/matlab_h12_perturbation/README.md.
MATLAB_HARNESS_ROOT = REPO_ROOT / "scripts" / "matlab_h12_perturbation"

# The ONLY substitutions allowed between the vendored Karr .m source and the
# isolated Octave harness transcription. Applied to the VENDORED side before
# comparison (i.e. these describe what the harness is allowed to have done
# to the original text). Any other divergence is drift.
ALLOWED_SUBSTITUTIONS = [
    # WholeCell's this.randStream.stochasticRound/.mnrnd are RandStream
    # instance methods; this harness has no RandStream object, so calls are
    # replaced by free-function scaffold stubs of the same name minus the
    # `this.randStream.` prefix (stochasticRoundStub.m / mnrndStub.m).
    (re.compile(r"this\.randStream\.stochasticRound\("), "stochasticRoundStub("),
    (re.compile(r"this\.randStream\.mnrnd\("), "mnrndStub("),
    # MATLAB's throw(MException(id, msg)) has no direct Octave equivalent;
    # error(id, msg) raises an identically-identified/worded error and is
    # the standard MATLAB/Octave-portable substitution for this pattern.
    (re.compile(r"throw\(MException\('([^']*)',\s*'([^']*)'\)\);"), r"error('\1', '\2');"),
]

# (harness_filename, vendored_filename, vendored_body_start_line, vendored_body_end_line)
# Body bounds are 1-based, inclusive, and exclude the function signature
# line(s) and the closing `end` -- i.e. exactly the statements inside the
# function. These line numbers are the same ones cited in
# docs/phase_f/l2_2_design_a/h12/perturbation/PERTURBATION_SPEC.json and the
# generated evidence artifacts' karr_source_citation.line_ranges.
BINDINGS = [
    ("evolveState_ppii.m", "ProteinProcessingII.m", 349, 445),
    ("buildProteinComplexs_montecarlokinetic.m", "MacromolecularComplexation.m", 336, 357),
    ("buildProteinComplexs_rates_collisionTheory.m", "MacromolecularComplexation.m", 362, 387),
    ("buildProteinComplexs_bounds.m", "MacromolecularComplexation.m", 391, 391),
]

# Genuine-MATLAB Scenario B harness bindings. Unlike BINDINGS above, these
# are TRUE VERBATIM transcriptions: ZERO allowed substitutions, because the
# real-MATLAB driver supplies a real edu.stanford.covert.util.RandStream
# instance as `this.randStream` (see run_ppii_scenario_b_matlab.m), so
# `this.randStream.stochasticRound(...)`/`.mnrnd(...)` calls do not need to
# be (and must not be) rewritten to stub free functions. Same
# (harness_filename, vendored_filename, start_line, end_line) shape, but
# resolved against MATLAB_HARNESS_ROOT instead of HARNESS_ROOT.
MATLAB_BINDINGS = [
    ("evolveState_ppii_matlab.m", "ProteinProcessingII.m", 349, 445),
]


def _read_lines(path: Path) -> list[str]:
    # Vendored WholeCell source is copy-pasted from an original MATLAB
    # authoring environment and contains stray non-UTF-8 bytes (e.g. Windows
    # CP-1252 en/em-dash punctuation, 0x96/0x97) inside comments. cp1252
    # round-trips every byte value without raising, and these bytes never
    # appear in the executable statements this test actually compares (they
    # get discarded by _normalize's comment-stripping regardless).
    return path.read_text(encoding="cp1252").splitlines()


def _extract_vendored_body(filename: str, start_line: int, end_line: int) -> list[str]:
    lines = _read_lines(VENDORED_ROOT / filename)
    return lines[start_line - 1 : end_line]


def _extract_harness_body(filename: str, root: Path = HARNESS_ROOT) -> list[str]:
    lines = _read_lines(root / filename)
    assert lines and lines[0].strip().startswith("function "), (
        f"{filename}: expected first line to be a function signature, got {lines[:1]!r}"
    )
    assert lines[-1].strip() == "end", f"{filename}: expected last line to be a bare 'end', got {lines[-1:]!r}"
    return lines[1:-1]


def _join_continuations(lines: list[str]) -> list[str]:
    # MATLAB/Octave `...` line-continuation is a pure source-formatting
    # device -- code split across multiple physical lines via a trailing
    # `...` is one logical statement. The harness transcription sometimes
    # reflows a vendored multi-line continuation onto a single physical
    # line (or vice versa); that is not a logic change, so join continued
    # lines into one logical line (dropping the `...` marker) before the
    # line-by-line comparison, on BOTH sides.
    out = []
    pending = None
    for ln in lines:
        if pending is not None:
            ln = f"{pending} {ln}"
            pending = None
        if ln.endswith("..."):
            pending = ln[: -len("...")].rstrip()
        else:
            out.append(ln)
    if pending is not None:
        out.append(pending)
    return out


def _normalize(lines: list[str]) -> list[str]:
    out = []
    for ln in lines:
        # MATLAB/Octave comments start with '%' and none of the bound
        # function bodies contain a literal '%' inside a string/expression,
        # so truncating at the first '%' safely drops both whole-line and
        # trailing inline comments.
        s = ln.split("%", 1)[0].strip()
        if not s:
            continue
        s = re.sub(r"\s+", " ", s)
        out.append(s)
    out = _join_continuations(out)
    return [re.sub(r"\s+", " ", s).strip() for s in out]


def _normalize_vendored(lines: list[str]) -> list[str]:
    subbed = []
    for ln in lines:
        for pattern, repl in ALLOWED_SUBSTITUTIONS:
            ln = pattern.sub(repl, ln)
        subbed.append(ln)
    return _normalize(subbed)


@pytest.mark.parametrize("harness_file,vendored_file,start,end", BINDINGS, ids=[b[0] for b in BINDINGS])
def test_harness_matches_vendored_source_modulo_allowed_substitutions(harness_file, vendored_file, start, end):
    vendored_norm = _normalize_vendored(_extract_vendored_body(vendored_file, start, end))
    harness_norm = _normalize(_extract_harness_body(harness_file))
    assert harness_norm == vendored_norm, (
        f"{harness_file} has drifted from {vendored_file} lines {start}-{end} beyond the allowed "
        "substitutions (this.randStream.stochasticRound->stochasticRoundStub, "
        "this.randStream.mnrnd->mnrndStub, throw(MException(...))->error(...)).\n"
        f"vendored(normalized)={vendored_norm!r}\nharness (normalized)={harness_norm!r}"
    )


def test_allowed_substitutions_are_each_actually_exercised():
    # Guards against the allow-list silently becoming dead code (e.g. a
    # future re-citation of line ranges that no longer contains the pattern
    # it's meant to permit) -- each substitution must match at least one
    # line across the bound vendored bodies.
    combined = "\n".join(
        line for _, vendored_file, start, end in BINDINGS for line in _extract_vendored_body(vendored_file, start, end)
    )
    for pattern, _ in ALLOWED_SUBSTITUTIONS:
        assert pattern.search(combined), (
            f"allowed substitution pattern {pattern.pattern!r} never matched any bound vendored line -- "
            "update BINDINGS or ALLOWED_SUBSTITUTIONS, this guard has drifted"
        )


def test_harness_files_contain_no_unsubstituted_randstream_reference():
    # Cheap net: if a harness file's actual CODE still references
    # this.randStream.* raw, it should have been caught by the exact-match
    # test above, but this gives a more specific failure message for that
    # specific class of bug. Checked against the normalized (comment-
    # stripped) body so the harness files' own documentation comments
    # (which legitimately quote `this.randStream.` as prose) don't trigger
    # a false positive.
    forbidden = re.compile(r"\bthis\.randStream\.")
    for harness_file, _, _, _ in BINDINGS:
        body = "\n".join(_normalize(_extract_harness_body(harness_file)))
        assert not forbidden.search(body), (
            f"{harness_file} still references this.randStream.* directly -- should have been substituted "
            "with a harness stub (stochasticRoundStub/mnrndStub)"
        )


@pytest.mark.parametrize("harness_file,vendored_file,start,end", MATLAB_BINDINGS, ids=[b[0] for b in MATLAB_BINDINGS])
def test_matlab_harness_matches_vendored_source_exactly(harness_file, vendored_file, start, end):
    # True verbatim: no ALLOWED_SUBSTITUTIONS applied to either side. If this
    # ever fails because a substitution *would* make it pass, that is a
    # signal the file has silently become a stub-based transcription again
    # and must be re-reviewed, not patched via the Octave allow-list.
    vendored_norm = _normalize(_extract_vendored_body(vendored_file, start, end))
    harness_norm = _normalize(_extract_harness_body(harness_file, root=MATLAB_HARNESS_ROOT))
    assert harness_norm == vendored_norm, (
        f"{harness_file} (true-verbatim MATLAB harness) has drifted from {vendored_file} lines {start}-{end}. "
        "This binding permits ZERO substitutions -- any difference is drift, not an allowed transcription "
        "choice.\n"
        f"vendored(normalized)={vendored_norm!r}\nharness (normalized)={harness_norm!r}"
    )


def test_matlab_harness_files_contain_real_randstream_reference():
    # Inverse of test_harness_files_contain_no_unsubstituted_randstream_reference:
    # the whole point of the MATLAB_BINDINGS harnesses is that they call the
    # REAL this.randStream.stochasticRound/.mnrnd (a genuine RandStream
    # instance method), not a stub free function. If a MATLAB harness file
    # ever loses these references (e.g. someone "fixes" it by copying the
    # Octave stub version), this test fails loudly rather than silently
    # degrading Scenario B back into stub-based evidence.
    required = re.compile(r"\bthis\.randStream\.(stochasticRound|mnrnd)\(")
    for harness_file, _, _, _ in MATLAB_BINDINGS:
        body = "\n".join(_normalize(_extract_harness_body(harness_file, root=MATLAB_HARNESS_ROOT)))
        assert required.search(body), (
            f"{harness_file} does not call this.randStream.stochasticRound/.mnrnd -- this is supposed to be "
            "a true-verbatim real-MATLAB RandStream harness, not a stub-based one"
        )
        forbidden_stub = re.compile(r"\b(stochasticRoundStub|mnrndStub)\(")
        assert not forbidden_stub.search(body), (
            f"{harness_file} references a stub function ({forbidden_stub.pattern}) -- MATLAB Scenario B "
            "harnesses must not use the Octave stub scaffolds"
        )
