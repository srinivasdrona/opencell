"""Static/parse-only regression tests for
`scripts/matlab/extract_per_process_traces_v2.m` (M4 fixed/anchor
event-window extractor).

This file never invokes MATLAB, Octave, or any simulation/bootstrap code
against the real extractor's normal entry point (calling
`extract_per_process_traces_v2()` with zero/default arguments falls
straight into `karr_bootstrap()`, a real WholeCell simulation bootstrap --
forbidden by the "no simulation/bootstrap/extraction" constraint this
branch operates under).

Two independent static checks are used:

* A lightweight, dependency-free block-keyword-balance heuristic (always
  runs, no MATLAB/Octave required).
* An OPTIONAL, environment-gated real parse-only probe using Octave
  (skipped cleanly if Octave/MATLAB is unavailable, e.g. in cloud CI).
  The technique -- prepending a `1;` statement before the real source so
  every `function ... end` in it becomes a *local function* inside a
  script -- was verified empirically in a disposable scratch directory
  (never against this repository's real file) before being relied on
  here: Octave's `source()` parses the whole file, including every nested
  local function body (raising a genuine syntax error for a malformed
  one), WITHOUT ever calling any of those functions. This was confirmed
  both for a single-function file and for a multi-function file where one
  local function calls another -- the same shape as this extractor
  (`extract_per_process_traces_v2` calling several helper functions).

Earlier revisions of this file additionally asserted that MATLAB/Octave
cannot parse chained dynamic-field access (e.g. `a.(b).(c)`) as a single
expression. That premise was incorrect -- chained dynamic-field access IS
valid MATLAB/Octave syntax -- and the regression test built on it has been
removed; see docs/phase_f/l2_event/EVENT_WINDOW_EXTRACTOR_CONTRACT.md's
"Static parse checking" section for the corrected account.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = REPO_ROOT / "scripts" / "matlab" / "extract_per_process_traces_v2.m"

_BLOCK_OPENERS = re.compile(r"\b(function|if|for|while|switch|try)\b")
_STANDALONE_END_LINE_RE = re.compile(r"^\s*end\s*;?\s*$")


def _read_source() -> str:
    assert EXTRACTOR_PATH.is_file(), f"missing {EXTRACTOR_PATH}"
    return EXTRACTOR_PATH.read_text(encoding="utf-8")


def _function_body(source: str, signature_line: str) -> str:
    """Return the body of the top-level function whose exact signature
    line is `signature_line`, delimited by the START of the NEXT
    top-level `function ` declaration (or end of file) -- NOT by the
    first bare `end` line, which would false-match on the function's own
    internal `for`/`if`/`while` block terminators (this file nests those
    freely inside every function)."""
    start = source.index(signature_line)
    body_start = start + len(signature_line)
    next_fn = re.search(r"\nfunction ", source[body_start:])
    body_end = body_start + next_fn.start() if next_fn else len(source)
    return source[body_start:body_end]


def _strip_comments_and_strings(source: str) -> str:
    """Best-effort removal of `%`-comments and single-quoted string
    literals so keyword/pattern counts below aren't confused by the word
    "end" (or a keyword like "for"/"if") appearing inside a comment or a
    string literal.

    Scans each line character-by-character tracking whether a `'` has
    opened a string literal (honoring MATLAB's `''` escaped-quote
    convention): a `%` encountered *inside* an open string is just a
    character, never a comment start. A naive `line.split('%', 1)[0]`
    (this function's earlier, incorrect implementation) truncated any
    line containing a single-quoted string with a `%d`/`%s`-style format
    specifier at the first such `%`, silently discarding the rest of the
    line -- including any real keyword/`end` token after it. That defect
    was undetectable with this file's OLD content (no format-specifier
    string on the same physical line as a bare keyword like "for") but
    surfaced as a false block-imbalance failure once Turn 3's
    `error('...', 'extraction failed for %d of %d ...', ...)` message put
    the word "for" before a `%d` on one line -- proving the truncation bug
    (not the real extractor source) was the actual defect.
    """
    out_lines = []
    for line in source.splitlines():
        result = []
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if ch == "'":
                # Consume the whole single-quoted string literal (honoring
                # the '' escaped-quote convention) and replace it with a
                # placeholder -- its content (any %, for/if/end, etc.)
                # can never leak into the keyword/pattern counts below.
                j = i + 1
                while j < n:
                    if line[j] == "'":
                        if j + 1 < n and line[j + 1] == "'":
                            j += 2
                            continue
                        j += 1
                        break
                    j += 1
                result.append("''")
                i = j
                continue
            if ch == "%":
                # A real comment start (only reached when NOT inside an
                # open string, per the branch above) -- the rest of the
                # physical line is dropped.
                break
            result.append(ch)
            i += 1
        out_lines.append("".join(result))
    return "\n".join(out_lines)


def test_extractor_file_exists_and_is_nonempty():
    source = _read_source()
    assert len(source) > 0


def test_block_keyword_balance():
    """Lightweight static parse sanity check: every block-opening keyword
    (`function`/`if`/`for`/`while`/`switch`/`try`) must be matched by a
    standalone `end` statement (MATLAB's `case`/`otherwise`/`catch`/
    `else`/`elseif` do not open a new `end`-terminated block of their
    own; and an `end` used as an array/cell index shorthand, e.g.
    `tokens{end + 1}` or `wid(k:end)`, is never a block closer -- it is
    only counted here when it is the sole token on its line). This does
    not replace a real MATLAB parser, but it is a real static check that
    would fail loudly if an edit dropped or added an unbalanced block --
    the same class of defect underlying the original syntax error."""
    code = _strip_comments_and_strings(_read_source())
    openers = len(_BLOCK_OPENERS.findall(code))
    closers = sum(1 for line in code.splitlines() if _STANDALONE_END_LINE_RE.match(line))
    assert openers == closers, (
        f"block-keyword balance mismatch: {openers} opener(s) "
        f"(function/if/for/while/switch/try) vs {closers} standalone "
        "'end' statement(s) -- static evidence of an unbalanced/malformed "
        "block."
    )


def test_merge_event_observables_uses_two_step_dereference():
    """Positive-form static check: `merge_event_observables` dereferences
    the signal container into a named temporary
    (`container = mod.(container_name);`) before reading any field off of
    it. This is a readability/validation choice (it lets the container be
    checked/validated once by name before any field access), not a parse
    requirement -- chained dynamic-field access such as
    `mod.(container_name).(field_name)` is valid MATLAB/Octave syntax."""
    source = _read_source()
    assert "container = mod.(container_name);" in source
    # And the two real per-observable dereferences must be against that
    # temporary, never re-chained through `mod.(...)` a second time.
    assert "container.pinchedDiameter" in source
    assert "container.(field_name)" in source


def test_chromosome_object_excluded_only_for_diameter_decrease_anchor():
    """Performance/sufficiency patch static proof: the full sparse
    `chromosome` snapshot property must be excluded ONLY for
    `window_contract='anchor'` + `signal_kind='diameter_decrease'`
    (Cytokinesis) -- never for a fixed window, and never for a generic
    `signal_kind='boolean_transition'` anchor (requirement: "do not remove
    chromosome snapshots for other processes/profiles")."""
    source = _read_source()

    # The exclusion helper exists and is invoked exactly once, immediately
    # after the generic pick_snapshot_properties() call -- never inlined
    # elsewhere, so there is exactly one place that can ever drop
    # 'chromosome' from the captured set.
    assert source.count("function props = exclude_chromosome_object_for_diameter_anchor(") == 1
    assert (
        "snapshot_props = exclude_chromosome_object_for_diameter_anchor(snapshot_props, window_contract, anchor_opts);"
        in source
    )

    # Extract the helper's body and prove its guard checks BOTH
    # window_contract=='anchor' AND signal_kind=='diameter_decrease' (a
    # conjunction, not just one of the two) before ever calling setdiff to
    # remove 'chromosome'.
    body_match = re.search(
        r"function props = exclude_chromosome_object_for_diameter_anchor\(.*?\n(.*?)\nend\n",
        source,
        re.DOTALL,
    )
    assert body_match is not None, "could not locate exclude_chromosome_object_for_diameter_anchor's body"
    body = body_match.group(1)
    assert "strcmp(window_contract, 'anchor')" in body
    assert "strcmp(anchor_opts.signal_kind, 'diameter_decrease')" in body
    assert "&&" in body
    assert "setdiff(props, {'chromosome'})" in body

    # merge_event_observables' 'diameter_decrease' case must flatten the
    # replacement chromosome_segregated scalar via the same validated-
    # temporary two-step dereference pattern as pinchedDiameter/FtsZRing.
    assert "chrom = mod.chromosome;" in source
    assert "snapshot.chromosome_segregated = logical(chrom.segregated);" in source

    # The 'boolean_transition' case (generic EVENT_CLASS processes) must
    # never reference the chromosome-exclusion/chromosome_segregated
    # machinery at all -- it is Cytokinesis-diameter-decrease-specific.
    boolean_case_match = re.search(
        r"case 'boolean_transition'\n(.*?)\n\s*otherwise\n",
        source,
        re.DOTALL,
    )
    assert boolean_case_match is not None, "could not locate the 'boolean_transition' case body"
    boolean_case_body = boolean_case_match.group(1)
    assert "chromosome" not in boolean_case_body


def test_boolean_transition_host_witnesses_are_flattened_from_real_host_state():
    """Static proof for HostInteraction anchor extraction: when the
    generic boolean-transition path is pointed at the real `host`
    container, it must flatten the source-written host booleans into the
    trace snapshot rather than exposing the raw host object."""
    source = _read_source()
    boolean_case_match = re.search(
        r"case 'boolean_transition'\n(.*?)\n\s*otherwise\n",
        source,
        re.DOTALL,
    )
    assert boolean_case_match is not None, "could not locate the 'boolean_transition' case body"
    boolean_case_body = boolean_case_match.group(1)
    assert "if strcmp(container_name, 'host')" in boolean_case_body
    assert "isBacteriumAdherent" in boolean_case_body
    assert "isNFkBActivated" in boolean_case_body
    assert "isInflammatoryResponseActivated" in boolean_case_body
    assert "isTLRActivated" in boolean_case_body
    assert "sprintf('isTLRActivated_%d', k)" in boolean_case_body


def test_genuine_mnrnd_provider_metadata_written_for_fixed_and_anchor_not_legacy():
    """Static proof of the provider-migration contract: the extractor
    must persist the genuine-provider metadata for BOTH 'fixed' and
    'anchor' windows, and must still leave the '' (no window_contract)
    legacy path untouched."""
    source = _read_source()

    assert source.count("metadata.mnrnd_provider_kind = mnrnd_provider.kind;") == 1
    assert source.count("metadata.mnrnd_provider_matlab_release = mnrnd_provider.matlab_release;") == 1
    assert source.count("metadata.mnrnd_provider_toolbox_version = mnrnd_provider.toolbox_version;") == 1
    assert (
        source.count(
            "metadata.mnrnd_provider_path_relative_to_matlabroot = mnrnd_provider.provider_path_relative_to_matlabroot;"
        )
        == 1
    )
    assert source.count("metadata.mnrnd_provider_sha256 = mnrnd_provider.sha256_lf_normalized;") == 1
    assert source.count(
        "metadata.statistics_rng_provider_identity_json = mnrnd_provider.identity_json;"
    ) == 1
    assert "mnrnd_shim" not in source

    # The single assignment site must be guarded by
    # strcmp(window_contract, 'fixed') || strcmp(window_contract, 'anchor')
    # -- not nested separately inside each branch (which could drift out
    # of sync) and not unconditional (which would corrupt the legacy ''
    # metadata shape).
    guard_match = re.search(
        r"if strcmp\(window_contract, 'fixed'\) \|\| strcmp\(window_contract, 'anchor'\)\n"
        r"(.*?)\n\s*end\n",
        source,
        re.DOTALL,
    )
    assert guard_match is not None, "could not locate the genuine-provider metadata guard block"
    guard_body = guard_match.group(1)
    assert "metadata.mnrnd_provider_kind" in guard_body
    assert "metadata.mnrnd_provider_sha256" in guard_body
    assert "[sim, mnrnd_provider, dnadamage_overlay] = karr_bootstrap();" in source


def test_dnadamage_overlay_provenance_is_written_into_trace_metadata():
    """dec-005 (source-hash binding), ported process-local into this
    worktree pending the catalog-provenance migration landing on main
    (see decisions/dec-005-full-simulation-source-hash-binding.md in
    E:\\opencell-worktrees\\fix-dual-cyt-window). DNADamage is one of the
    28 processes in Karr's shared per-tick scheduler, so its resolved
    source identity must be bound into EVERY fixed/anchor trace -- not
    gated on `canonical_name == 'DNADamage'` (that narrower gate was the
    dec-005-named blind spot for this single-process extractor; this
    proves it is now closed for any target process, Cytokinesis
    included)."""
    source = _read_source()

    assert source.count("metadata.dnadamage_source_original_sha256 = dnadamage_overlay.source_sha256_lf_normalized;") == 1
    assert source.count("metadata.dnadamage_source_patched_sha256 = dnadamage_overlay.patched_sha256_lf_normalized;") == 1
    assert source.count("metadata.dnadamage_source_resolved_sha256 = dnadamage_overlay.resolved_sha256_lf_normalized;") == 1
    assert source.count("metadata.dnadamage_source_resolved_path = dnadamage_overlay.resolved_path;") == 1
    assert source.count("metadata.dnadamage_overlay_required = logical(dnadamage_overlay.overlay_required);") == 1
    # The narrower single-process gate must be gone -- these assignments
    # must no longer be nested inside `if strcmp(canonical_name, 'DNADamage')`.
    assert "if strcmp(canonical_name, 'DNADamage')" not in source

    # All five assignments must live inside the SAME fixed/anchor guard as
    # the genuine-mnrnd-provider metadata (no separate/duplicated guard).
    guard_match = re.search(
        r"if strcmp\(window_contract, 'fixed'\) \|\| strcmp\(window_contract, 'anchor'\)\n"
        r"(.*?)\n\s*end\n",
        source,
        re.DOTALL,
    )
    assert guard_match is not None, "could not locate the fixed/anchor metadata guard block"
    guard_body = guard_match.group(1)
    assert "metadata.dnadamage_source_resolved_sha256" in guard_body
    assert "metadata.dnadamage_overlay_required" in guard_body


def test_rand_stream_state_captured_at_both_tap_points():
    """Task requirement: capture the target process's own randStream
    state in states_before (and states_after, for audit) per tick, so a
    fresh source-bound event-window trace carries a hash-bound,
    per-tick RNG-state ledger sufficient to restore/verify an isolated OC
    replay's stream state exactly (never inferred)."""
    source = _read_source()

    assert source.count("function state_vec = capture_rand_stream_state(mod)") == 1
    assert "state_vec = double(mod.randStream.state(:));" in source
    assert source.count("before_tick.randStreamState = capture_rand_stream_state(mod);") == 1
    assert source.count("after_tick.randStreamState = capture_rand_stream_state(mod);") == 1

    # Both capture call sites must sit inside evolve_state_with_tap's
    # `if proc_idx == target_idx` taps, immediately alongside the existing
    # snapshot_from_process/merge_event_observables calls -- never
    # elsewhere, and never gated on anchor_opts (so both the fixed and
    # anchor window paths get the same per-tick RNG-state witness). Uses
    # plain substring position ordering (never gets confused by nested
    # `if ~isempty(anchor_opts) ... end` blocks the way a naive "first
    # standalone end" regex would).
    idx_before_snapshot = source.index("before_tick = snapshot_from_process(mod, snapshot_props);")
    idx_before_capture = source.index("before_tick.randStreamState = capture_rand_stream_state(mod);")
    idx_evolve_state = source.index("mod.evolveState();")
    idx_after_snapshot = source.index("after_tick = snapshot_from_process(mod, snapshot_props);")
    idx_after_capture = source.index("after_tick.randStreamState = capture_rand_stream_state(mod);")

    assert idx_before_snapshot < idx_before_capture < idx_evolve_state < idx_after_snapshot < idx_after_capture, (
        "randStreamState capture call sites are not correctly ordered around "
        "evolveState() relative to the existing before/after snapshot calls"
    )


def test_pick_snapshot_properties_includes_transcriptional_regulation_binding_surfaces():
    """Static proof that the generic snapshot-property whitelist exposes
    the real TranscriptionalRegulation binding witnesses needed for long
    active-window traces."""
    source = _read_source()
    assert "'boundTFs'" in source
    assert "'tfBoundPromoters'" in source


def test_extraction_opts_override_surface_is_wired_into_real_scheduler_path():
    """DNADamage stimulus cohorts rely on a real extractor-side override
    surface, not a filename-only relabel. Statically prove that
    `extract_per_process_traces_v2` now accepts `extraction_opts`,
    persists the identity metadata, patches the REAL metabolite/setCounts
    state for DNADamage, and still reapplies the process-local substrate
    override inside the scheduler."""
    source = _read_source()

    assert (
        "function extract_per_process_traces_v2(process_names, output_subdir, n_ticks, seed, tick_offset, window_contract, anchor_opts, extraction_opts)"
        in source
    )
    assert "extraction_opts = default_extraction_opts(extraction_opts);" in source
    assert "metadata.condition_label = extraction_opts.condition_label;" in source
    assert "metadata.extraction_identity_json = extraction_opts.metadata_identity_json;" in source
    assert "function opts = default_extraction_opts(opts)" in source
    assert "function [sim, applied] = apply_condition_overrides(sim, proc, canonical_name, extraction_opts)" in source
    assert "function mod = apply_process_substrate_overrides(mod, extraction_opts)" in source

    assert "if ~strcmp(canonical_name, 'DNADamage')" in source
    assert "mets = sim.state_metabolite;" in source
    assert "proc.substrateMetaboliteGlobalCompartmentIndexs(local_idx)" in source
    assert "Condition.objectCompartmentIndexs" in source
    assert "mets.setCounts = mets.setCounts(keep, :);" in source
    assert "mets.counts(object_compartment_idx) = double(value);" in source
    assert "metadata.condition_override_metabolite_wids" in source
    assert "metadata.condition_override_values" in source
    assert "metadata.condition_override_object_compartment_indexs" in source

    # The scheduler still reapplies the local process substrate override
    # before both calcResourceRequirements_Current() and evolveState() so
    # the conditioned value survives allocation injection inside the same
    # tick.
    assert source.count("mod = apply_process_substrate_overrides(mod, extraction_opts);") == 2
    assert "r = mod.calcResourceRequirements_Current();" in source
    assert "mod.substrates(lidx, :) = allocation;" in source
    # The fixed/'' capture loop passes `fixed_tap_anchor_opts` (empty
    # unless the caller opted into anchor_opts.capture_signal_container --
    # see default_anchor_opts), never an unconditional `[]`, so a fixed
    # window can also carry the real per-tick signal-container projection
    # without ever performing an anchor SEARCH (capture_anchor_window is
    # only invoked for window_contract='anchor').
    assert "fixed_tap_anchor_opts = [];" in source
    assert "anchor_opts.capture_signal_container" in source
    assert (
        "[sim, ~, ~] = evolve_state_with_tap(sim, target_idx, snapshot_props, fixed_tap_anchor_opts, extraction_opts);"
        in source
    )
    assert (
        "[sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, fixed_tap_anchor_opts, extraction_opts);"
        in source
    )
    assert (
        "[sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, anchor_opts, extraction_opts);"
        in source
    )


def test_per_process_enzyme_overrides_wired_at_both_copyfromstate_sites():
    """Static proof for the enzyme-knockout override surface (used to
    extract HostInteraction's discriminating condition windows -- see
    docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md): a
    process-local `this.enzymes` override, applied fresh every tick right
    after copyFromState() repopulates it from the global protein pool, at
    BOTH copyFromState() call sites (the resource-requirements loop and
    the real evolveState() loop) -- same shape and same non-restriction as
    apply_process_substrate_overrides."""
    source = _read_source()

    assert "function [mod, override_snapshot] = apply_process_enzyme_overrides(mod, extraction_opts)" in source
    assert "function mod = restore_process_enzyme_overrides(mod, override_snapshot)" in source
    assert "function override_values = select_process_enzyme_overrides(per_process_overrides, mod)" in source
    assert "per_process_enzyme_overrides" in source
    assert "opts.per_process_enzyme_overrides = struct();" in source

    # Called immediately after copyFromState() at both call sites, mirroring
    # apply_process_substrate_overrides's own two call sites exactly.
    assert source.count("[mod, enzyme_override_snapshot] = apply_process_enzyme_overrides(mod, extraction_opts);") == 2

    first_site_match = re.search(
        r"mod\.copyFromState\(\);\n\s*mod = apply_process_substrate_overrides\(mod, extraction_opts\);\n"
        r"\s*\[mod, enzyme_override_snapshot\] = apply_process_enzyme_overrides\(mod, extraction_opts\);\n"
        r"\s*r = mod\.calcResourceRequirements_Current\(\);",
        source,
    )
    assert first_site_match is not None, "enzyme override not wired into the resource-requirements loop"
    # And the loop-1 restore call must follow calcResourceRequirements_Current()
    # (hygiene restore; no copyToState() in this loop, see loop body comment).
    assert re.search(
        r"r = mod\.calcResourceRequirements_Current\(\);\n"
        r"(?:.*\n)*?"
        r"\s*mod = restore_process_enzyme_overrides\(mod, enzyme_override_snapshot\);",
        source,
    ), "loop-1 restore call must follow calcResourceRequirements_Current()"

    second_site_match = re.search(
        r"mod\.substrates\(lidx, :\) = allocation;\n"
        r"\s*mod = apply_process_substrate_overrides\(mod, extraction_opts\);\n"
        r"\s*\[mod, enzyme_override_snapshot\] = apply_process_enzyme_overrides\(mod, extraction_opts\);\n",
        source,
    )
    assert second_site_match is not None, "enzyme override not wired into the real evolveState() scheduler loop"

    # Never restricted to a single process (unlike apply_condition_overrides,
    # whose DNADamage-only guard is `if ~strcmp(canonical_name, 'DNADamage')`).
    enzyme_fn_body = _function_body(
        source, "function [mod, override_snapshot] = apply_process_enzyme_overrides(mod, extraction_opts)"
    )
    assert "canonical_name" not in enzyme_fn_body
    assert "DNADamage" not in enzyme_fn_body

    # The pre-override genuine values must be captured BEFORE the override
    # loop mutates mod.enzymes, so restore can undo it exactly.
    snapshot_idx = enzyme_fn_body.index(
        "override_snapshot = struct('enzymes', mod.enzymes, 'boundEnzymes', mod.boundEnzymes);"
    )
    mutation_idx = enzyme_fn_body.index("mod.enzymes(idx, :) = double(value);")
    assert snapshot_idx < mutation_idx, "pre-override snapshot must be captured before the override mutates mod.enzymes"


def test_per_process_enzyme_overrides_are_contained_before_copytostate():
    """CONTAINMENT (2026-09-08, Opus review fix): Process.m's copyToState()
    unconditionally writes this.enzymes/this.boundEnzymes back into the
    SHARED global metabolite/rna/monomer/complex state whenever
    this.enzymes is non-empty (verified directly against
    data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/
    Process.m's copyToState method). A prior revision of this codepath
    incorrectly assumed enzyme overrides were "never written back by
    copyToState()" and left the override in place across the copyToState()
    call -- this would have corrupted the shared global protein pool for
    every other process and every later tick, not just the target
    process's own evolveState() read.

    This test REQUIRES (not merely describes) that:
      1. restore_process_enzyme_overrides() is called after evolveState()
         and strictly BEFORE copyToState() in the real evolveState loop.
      2. A runtime containment assertion (comparing the shared global
         monomer/complex counts for the overridden WIDs before and after
         copyToState(), raising a MATLAB error on any mismatch) is present
         and gated on an override actually being active this tick.
    A regression that removes either of these must FAIL this test."""
    source = _read_source()

    body = _function_body(
        source,
        "function [sim, before_tick, after_tick] = evolve_state_with_tap(sim, target_idx, snapshot_props, anchor_opts, extraction_opts)",
    )

    evolve_idx = body.index("mod.evolveState();")
    # evolve_state_with_tap's SECOND (real, per-tick) loop is the one with
    # the copyToState() containment obligation; its own restore call is
    # necessarily the LAST occurrence in this function body (the first
    # loop's restore call, over calcResourceRequirements_Current(), comes
    # textually earlier and has no copyToState() call at all).
    assert body.count("mod = restore_process_enzyme_overrides(mod, enzyme_override_snapshot);") == 2, (
        "expected exactly 2 restore call sites: the resource-requirements loop "
        "(hygiene only, no copyToState()) and the real evolveState() loop (containment-critical)"
    )
    restore_idx = body.rindex("mod = restore_process_enzyme_overrides(mod, enzyme_override_snapshot);")
    copy_to_state_idx = body.index("mod.copyToState();")
    assert evolve_idx < restore_idx < copy_to_state_idx, (
        "restore_process_enzyme_overrides must run after evolveState() and strictly "
        "before copyToState() -- this ordering is the entire containment guarantee"
    )

    # The runtime containment assertion itself: gated on an override being
    # active, comparing genuine global monomer/complex counts captured
    # before evolveState()/restore/copyToState() against the same after
    # copyToState(), raising a MATLAB error (fail-closed, not a warning or
    # log line) on any mismatch.
    assert "enzyme_containment_check = ~isempty(enzyme_override_snapshot);" in body
    assert "global_monomer_before = mod.monomer.counts(monomer_gidx);" in body
    assert "global_complex_before = mod.complex.counts(complex_gidx);" in body
    assert "global_monomer_after = mod.monomer.counts(monomer_gidx);" in body
    assert "global_complex_after = mod.complex.counts(complex_gidx);" in body
    assert "extract_per_process_traces_v2:enzyme_override_leaked_to_global_state" in body

    before_capture_idx = body.index("global_monomer_before = mod.monomer.counts(monomer_gidx);")
    after_capture_idx = body.index("global_monomer_after = mod.monomer.counts(monomer_gidx);")
    assert evolve_idx > before_capture_idx, "global 'before' snapshot must be captured before evolveState()"
    assert after_capture_idx > copy_to_state_idx, "global 'after' snapshot must be captured after copyToState()"

    # restore_process_enzyme_overrides itself must actually write both
    # vectors back from the captured snapshot (not a no-op stub).
    restore_fn_body = _function_body(source, "function mod = restore_process_enzyme_overrides(mod, override_snapshot)")
    assert "mod.enzymes = override_snapshot.enzymes;" in restore_fn_body
    assert "mod.boundEnzymes = override_snapshot.boundEnzymes;" in restore_fn_body


def _octave_executable() -> str | None:
    """Locate an Octave CLI binary on PATH, or return None if unavailable.

    This project's canonical execution environment is WSL (see the
    project's copilot-instructions "Execution Environment" rule), so this
    looks for the binary names Octave installs there. No MATLAB/Octave
    installation is required for this test suite to pass -- absence is a
    clean skip, never a failure, so cloud CI without Octave/MATLAB is
    unaffected."""
    for name in ("octave-cli", "octave"):
        path = shutil.which(name)
        if path:
            return path
    return None


@pytest.mark.skipif(
    _octave_executable() is None,
    reason="octave-cli not available on PATH; parse-only probe skipped",
)
def test_real_parse_only_probe_via_octave(tmp_path: Path):
    """Real (not heuristic) parse-only regression check, run only when
    Octave is available.

    Technique (verified empirically in a disposable scratch directory
    before being relied on here, and never run against this repository's
    real file until this exact probe): prepend a bare `1;` statement
    before the extractor source. That statement makes the file a
    *script*, so every subsequent `function ... end` in it becomes a
    *local function* defined within the script rather than the file's
    single top-level function. Octave's `source()` then parses the
    *entire* file -- including every nested local function body, so a
    genuine syntax error anywhere in the file is raised -- but it never
    *calls* `extract_per_process_traces_v2` or any of its helpers, so no
    simulation/bootstrap code ever runs. A sentinel string is printed
    only after `source()` returns successfully, and the real function
    bodies never execute, so the sentinel's presence/absence combined
    with the process exit code distinguishes "parses cleanly" from "parse
    error" without ever exercising `karr_bootstrap()` or any other
    simulation/extraction side effect.
    """
    octave = _octave_executable()
    assert octave is not None  # narrowed by skipif above

    source = _read_source()
    probe_path = tmp_path / "extract_per_process_traces_v2_parse_probe.m"
    probe_path.write_text("1;\n" + source, encoding="utf-8")

    sentinel = "PARSE_OK_NO_EXEC"
    result = subprocess.run(
        [
            octave,
            "--no-gui",
            "--eval",
            f"source('{probe_path.as_posix()}'); disp('{sentinel}');",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, (
        "octave failed to parse extract_per_process_traces_v2.m "
        f"(exit {result.returncode}); stderr:\n{result.stderr}"
    )
    assert sentinel in result.stdout, (
        "expected parse-success sentinel missing from octave stdout "
        f"(stdout: {result.stdout!r})"
    )
    # The real function bodies must never execute. `karr_bootstrap` (the
    # simulation entry point reachable from this file's default-argument
    # path) is never invoked by `source()`, so its distinctive log banner
    # must never appear here -- this is a load-bearing assertion that the
    # probe truly never runs simulation/extraction code.
    assert "karr_bootstrap" not in result.stdout
    assert "karr_bootstrap" not in result.stderr
