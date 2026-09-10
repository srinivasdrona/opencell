"""Regression tests for `l21_active_window_audit`'s shared-Chromosome-stream
input-state ledger support (DNADamage).

Prior to this fix, the shared, multi-process `_honest_replay` harness
constructed a fresh, non-ledgered `KarrDNADamageProcess` for its own
bit-identity check, structurally unable to observe the ledger-driven
bit-identity result `tests/vivarium/test_karr_dna_damage_l2_replay.py`
already proved (see STATUS_L21_DNADAMAGE_ACTIVE_FIX.md Session 3) --
re-running the mechanical audit after the underlying RNG/algorithm fix
reproduced the identical `first_mismatch_tick=4` divergence, a harness
methodology gap, not an algorithm gap.

This fix extends `_ProcessSpec`/`_build_context`/`_honest_replay` (in
`l2_2_replay_common_v2.py` and `l21_active_window_audit.py` respectively)
to inject the SAME `chromosome_rand_stream_ledger.py` helper and
`KarrLedgerReplayStream` the process-specific replay test already uses --
reused, not duplicated -- so the shared audit harness can ALSO observe
genuine bit identity for the canonical seed2000 trace, while leaving
every other process (including the other two CHROMOSOME_ACTIVITY_TOKENS
processes, DNARepair and Replication, which have no
`chromosome_rand_stream_ledger_attr` and no ledger sidecar of their own)
completely unaffected.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import h5py
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(REPO_ROOT / "tests" / "vivarium") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tests" / "vivarium"))

import chromosome_rand_stream_ledger as ledger_mod  # noqa: E402
import l2_2_replay_common_v2 as replay_common  # noqa: E402
import l21_active_window_audit as active_windows  # noqa: E402

_CANONICAL_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s2000"
    / "DNADamage_20ticks.mat"
)
_CANONICAL_LEDGER = _CANONICAL_TRACE.with_suffix("").with_suffix(".chromosome_rand_stream_ledger.json")

# Applied per-test (NOT as a module-level `pytestmark`) -- a module-level
# marker would also skip the skip-detection/parsing unit tests below
# (`test_parse_pytest_summary_counts`,
# `test_rerun_manifest_replay_nodeid_detects_skip_not_pass`,
# `test_rerun_manifest_replay_nodeid_accepts_genuine_pass`) and the two
# pure `_ProcessSpec`/`_verify_manifest_ledger_binding` unit tests that
# need neither the canonical trace nor its ledger sidecar, silently
# hiding real regressions in those tests whenever this checkout's
# gitignored `.mat` trace tree happens to be absent (e.g. CI, a fresh
# clone). Only tests that genuinely read `_CANONICAL_TRACE`/
# `_CANONICAL_LEDGER` are decorated with this marker.
_requires_canonical_trace = pytest.mark.skipif(
    not (_CANONICAL_TRACE.exists() and _CANONICAL_LEDGER.exists()),
    reason=(
        "canonical seed2000 DNADamage trace/ledger not present in this checkout -- the .mat "
        "trace tree is gitignored/regenerated-on-demand, not committed"
    ),
)


def _copy_trace_and_ledger(dest_dir: Path) -> tuple[Path, Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_trace = dest_dir / _CANONICAL_TRACE.name
    dest_ledger = dest_dir / _CANONICAL_LEDGER.name
    shutil.copyfile(_CANONICAL_TRACE, dest_trace)
    shutil.copyfile(_CANONICAL_LEDGER, dest_ledger)
    return dest_trace, dest_ledger


def test_dnadamage_spec_declares_chromosome_rand_stream_ledger_attr() -> None:
    spec = replay_common._PROCESS_SPECS["DNADamage"]
    assert spec.chromosome_rand_stream_ledger_attr == "_site_sampling_rng"


def test_dnarepair_and_replication_specs_do_not_declare_a_ledger_attr() -> None:
    """The other two CHROMOSOME_ACTIVITY_TOKENS processes must be
    completely untouched by this feature -- no ledger attr, hence no
    ledger loading, hence no behavior change."""
    for name in ("DNARepair", "Replication"):
        spec = replay_common._PROCESS_SPECS[name]
        assert spec.chromosome_rand_stream_ledger_attr is None


@_requires_canonical_trace
def test_valid_ledger_seed2000_achieves_bit_identity_and_existing_window_pass() -> None:
    with h5py.File(_CANONICAL_TRACE, "r") as handle:
        ctx = replay_common._build_context(name="DNADamage", rng_seed=2000, handle=handle)
        assert ctx.chromosome_rand_stream_ledger is not None
        assert len(ctx.chromosome_rand_stream_ledger) == ctx.n_ticks

    bit_identity, honest = active_windows._honest_replay(
        process_name="DNADamage", trace_path=_CANONICAL_TRACE
    )
    assert bit_identity.pass_all_compared_ticks is True
    assert bit_identity.first_mismatch_tick is None
    assert honest.oc_active_on_karr_active_ticks == honest.karr_active_ticks

    candidate = active_windows._summarize_trace_candidate(
        "DNADamage", _CANONICAL_TRACE, known_sha=None, source_manifest=None
    )
    _, _, classification, _ = active_windows._classify_live_trace_candidate("DNADamage", candidate)
    assert classification == active_windows.CLASS_EXISTING_WINDOW_PASS


@_requires_canonical_trace
def test_missing_ledger_sidecar_falls_back_to_prior_stand_in_behavior(tmp_path: Path) -> None:
    """A DNADamage trace with NO companion ledger sidecar (e.g. seeds
    0-4, which never had one generated) must silently fall back to the
    pre-existing freshly-seeded stand-in stream -- never raise, never
    treat absence as a failure. This is the "no ledger available"
    baseline every other DNADamage trace already relies on."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_missing_ledger"
    dest_dir.mkdir(parents=True)
    dest_trace = dest_dir / _CANONICAL_TRACE.name
    shutil.copyfile(_CANONICAL_TRACE, dest_trace)
    # Deliberately do NOT copy the ledger sidecar.

    with h5py.File(dest_trace, "r") as handle:
        ctx = replay_common._build_context(name="DNADamage", rng_seed=2000, handle=handle)
        assert ctx.chromosome_rand_stream_ledger is None

    # The replay must still complete (using the stand-in stream), not raise.
    bit_identity, honest = active_windows._honest_replay(process_name="DNADamage", trace_path=dest_trace)
    assert bit_identity.compared_tick_count == 20
    assert honest.karr_active_ticks == 1


@_requires_canonical_trace
def test_tampered_ledger_hash_mismatch_fails_closed_not_silent_fallback(tmp_path: Path) -> None:
    """A ledger sidecar that no longer matches the trace it sits beside
    (e.g. the trace was re-extracted/edited after the ledger was built)
    must raise -- never silently fall back to the stand-in stream and
    never silently accept stale data."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_tampered"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    payload["trace_sha256"] = "0" * 64  # deliberately wrong
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with h5py.File(dest_trace, "r") as handle, pytest.raises(Exception, match="DIFFERENT trace file"):
        replay_common._build_context(name="DNADamage", rng_seed=2000, handle=handle)


@_requires_canonical_trace
def test_one_draw_short_ledger_fails_closed_not_silent_fallback(tmp_path: Path) -> None:
    """A ledger whose recorded n_draws/draws length disagree (a
    corrupted/truncated ledger, e.g. one manually edited to be one draw
    short) must raise at load time -- never silently truncate or pad."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_short"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    # Truncate tick 4's (0-indexed) draws by one, without updating n_draws,
    # so the internal n_draws/len(draws) consistency check fires.
    payload["per_tick"][4]["draws"] = payload["per_tick"][4]["draws"][:-1]
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with h5py.File(dest_trace, "r") as handle, pytest.raises(Exception, match="does not match len"):
        replay_common._build_context(name="DNADamage", rng_seed=2000, handle=handle)


@_requires_canonical_trace
def test_tampered_chromosome_source_hash_fails_closed(tmp_path: Path) -> None:
    """A ledger whose recorded `chromosome_source_sha256` no longer
    matches the CURRENT on-disk `Chromosome.m` (e.g. the ledger was
    reconstructed against a stale/edited source revision) must raise --
    never silently accept a mismatched source binding."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_chromosome_source_tamper"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    payload["chromosome_source_sha256"] = "0" * 64
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT.*Chromosome.m"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)


@_requires_canonical_trace
def test_tampered_randstream_util_source_hash_fails_closed(tmp_path: Path) -> None:
    """Same as above for `randstream_util_source_sha256` /
    `RandStream.m`."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_randstream_source_tamper"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    payload["randstream_util_source_sha256"] = "0" * 64
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT.*RandStream.m"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)


@_requires_canonical_trace
def test_tampered_dnadamage_source_hash_fails_closed(tmp_path: Path) -> None:
    """A ledger whose recorded `dnadamage_source_sha256` disagrees with
    the TRACE's own `dnadamage_source_resolved_sha256` metadata (i.e.
    the ledger was reconstructed against a different DNADamage.m
    revision than the one that actually produced this trace) must raise
    -- never silently accept a mismatched source-revision binding."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_dnadamage_source_tamper"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    payload["dnadamage_source_sha256"] = "0" * 64
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT DNADamage.m source revision"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)


@_requires_canonical_trace
def test_missing_required_source_hash_field_fails_closed(tmp_path: Path) -> None:
    """A ledger missing one of its three required source-hash provenance
    fields entirely (e.g. an older/hand-edited sidecar) must raise --
    never silently treat an absent field as "nothing to verify"."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_missing_source_field"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    del payload["chromosome_source_sha256"]
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="missing its required"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)


@_requires_canonical_trace
def test_unresolvable_wcm_source_fails_closed_not_silent_skip(tmp_path: Path) -> None:
    """If `resolve_wcm_source_path` cannot locate Chromosome.m/RandStream.m
    at all (e.g. `repo_root` sits outside any recognizable
    `opencell-worktrees` layout, and no worktree-local copy exists
    either), the loader must raise -- NOT silently skip the source-hash
    check the ledger records a hash for. This is the exact failure mode
    Opus flagged: the prior hardcoded-`E:\\opencell` fallback silently
    returned None under WSL, and the old loader's `if source_path is
    None: continue` treated that as "nothing to verify"."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_unresolvable_source"
    dest_trace, _dest_ledger = _copy_trace_and_ledger(dest_dir)

    # A repo_root with no "opencell-worktrees" segment and no local
    # data/m1_sources/WholeCell copy -- resolve_wcm_source_path must
    # return None for both Chromosome.m and RandStream.m from here.
    unresolvable_root = tmp_path / "some_other_checkout_layout"
    unresolvable_root.mkdir()
    assert (
        ledger_mod.resolve_wcm_source_path(
            "src", "+edu", "+stanford", "+covert", "+cell", "+sim", "+state", "Chromosome.m",
            repo_root=unresolvable_root,
        )
        is None
    )

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="could not be resolved on disk"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=unresolvable_root)


@_requires_canonical_trace
def test_one_draw_short_ledger_with_consistent_n_draws_fails_closed_during_replay(tmp_path: Path) -> None:
    """A ledger that is internally self-consistent (n_draws matches
    len(draws)) but genuinely one draw short of what OC's algorithm
    actually needs for that tick must still fail closed -- via
    `KarrLedgerReplayStream.assert_fully_consumed()` -- not silently
    proceed with a partially-consumed tick."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_short_consistent"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    tick4 = payload["per_tick"][4]
    tick4["draws"] = tick4["draws"][:-1]
    tick4["n_draws"] = len(tick4["draws"])
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="only consumed|exhausted after"):
        active_windows._honest_replay(process_name="DNADamage", trace_path=dest_trace)


@_requires_canonical_trace
def test_overflow_ledger_fails_closed_during_replay(tmp_path: Path) -> None:
    """A ledger padded with an extra draw OC's algorithm does not consume
    must fail closed via `KarrLedgerReplayStream.assert_fully_consumed()`
    detecting leftover draws -- never silently ignored."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_overflow"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    tick0 = payload["per_tick"][0]
    tick0["draws"] = [*tick0["draws"], 0.123456789]
    tick0["n_draws"] = len(tick0["draws"])
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="only consumed"):
        active_windows._honest_replay(process_name="DNADamage", trace_path=dest_trace)


def test_verify_manifest_ledger_binding_none_when_row_declares_nothing() -> None:
    """A manifest row with no `chromosome_rand_stream_ledger` object
    (every process/row other than DNADamage) must pass through
    unaffected -- `_verify_manifest_ledger_binding` returns None, not an
    error, for a row that never opted into this check."""
    assert active_windows._verify_manifest_ledger_binding({}, Path("does/not/exist.mat")) is None


@_requires_canonical_trace
def test_verify_manifest_ledger_binding_passes_for_matching_hash(tmp_path: Path) -> None:
    """The happy path: a row's declared `chromosome_rand_stream_ledger.sha256`
    matches the real sidecar sha256 living next to the resolved source
    trace -- no error."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_ledger_binding_ok"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)
    actual_sha256 = active_windows._sha256(dest_ledger)
    row = {"chromosome_rand_stream_ledger": {"sha256": actual_sha256}}
    assert active_windows._verify_manifest_ledger_binding(row, dest_trace) is None


@_requires_canonical_trace
def test_verify_manifest_ledger_binding_fails_closed_on_hash_mismatch(tmp_path: Path) -> None:
    """A row declaring a `chromosome_rand_stream_ledger.sha256` that does
    NOT match the real sidecar's actual hash (e.g. the sidecar was
    regenerated/tampered with fabricated draws since the manifest row was
    promoted) must fail closed with a clear reason -- this is the residual
    tamper vector the ledger loader's own internal source-hash checks
    cannot close on their own (see `_verify_manifest_ledger_binding`'s
    docstring): those checks bind the ledger to specific MATLAB source
    revisions and to this trace file, but not to any specific recorded
    draws."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_ledger_binding_mismatch"
    dest_trace, _dest_ledger = _copy_trace_and_ledger(dest_dir)
    row = {"chromosome_rand_stream_ledger": {"sha256": "0" * 64}}
    reason = active_windows._verify_manifest_ledger_binding(row, dest_trace)
    assert reason is not None
    assert "mismatch" in reason


@_requires_canonical_trace
def test_verify_manifest_ledger_binding_fails_closed_when_sidecar_missing(tmp_path: Path) -> None:
    """A row declaring a `chromosome_rand_stream_ledger.sha256` for a
    sidecar that is simply absent (e.g. deleted between promotion and a
    later re-verification) must fail closed -- never silently return None
    (which `verify_active_window_manifest_row` would otherwise be unable
    to distinguish from 'this row never declared a ledger binding')."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_ledger_binding_missing"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_trace = dest_dir / _CANONICAL_TRACE.name
    shutil.copyfile(_CANONICAL_TRACE, dest_trace)
    # Deliberately do NOT copy the ledger sidecar.
    row = {"chromosome_rand_stream_ledger": {"sha256": "0" * 64}}
    reason = active_windows._verify_manifest_ledger_binding(row, dest_trace)
    assert reason is not None
    assert "missing" in reason


@pytest.mark.parametrize(
    ("stdout", "expected_counts"),
    [
        ("1 passed in 47.56s", {"passed": 1}),
        ("1 skipped in 0.01s", {"skipped": 1}),
        ("1 failed in 0.12s", {"failed": 1}),
        ("1 failed, 1 passed in 3.00s", {"failed": 1, "passed": 1}),
    ],
)
def test_parse_pytest_summary_counts(stdout: str, expected_counts: dict[str, int]) -> None:
    assert active_windows._parse_pytest_summary_counts(stdout) == expected_counts


def test_rerun_manifest_replay_nodeid_detects_skip_not_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nested-audit skip detection: pytest exits 0 both when a nodeid
    genuinely PASSES and when it is entirely SKIPPED (zero failures) --
    `_rerun_manifest_replay_nodeid` must never accept a skip as
    re-verifying a manifest row's evidence. Mocks `subprocess.run` to
    return exactly the exit-code-0-but-skipped shape a real skipped
    pytest invocation produces, so this test does not depend on any
    gitignored trace/ledger data being present in this checkout."""

    class _FakeCompletedProcess:
        returncode = 0
        stdout = "s                                                                        [100%]\n1 skipped in 0.01s"
        stderr = ""

    monkeypatch.setattr(active_windows.subprocess, "run", lambda *a, **k: _FakeCompletedProcess())
    row = {"replay_evidence": {"nodeid": "tests/vivarium/test_karr_dna_damage_l2_replay.py::some_test"}}
    result = active_windows._rerun_manifest_replay_nodeid(row)
    assert result["passed"] is False
    assert result["returncode"] == 0
    assert "no PASSED outcome" in result["error"]


def test_rerun_manifest_replay_nodeid_accepts_genuine_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeCompletedProcess:
        returncode = 0
        stdout = ".                                                                        [100%]\n1 passed in 47.56s"
        stderr = ""

    monkeypatch.setattr(active_windows.subprocess, "run", lambda *a, **k: _FakeCompletedProcess())
    row = {"replay_evidence": {"nodeid": "tests/vivarium/test_karr_dna_damage_l2_replay.py::some_test"}}
    result = active_windows._rerun_manifest_replay_nodeid(row)
    assert result["passed"] is True
    assert result["error"] is None


# --- ReplicationInitiation cases (DEC-005/DEC-006: decisions/dec-005-full-
# simulation-source-hash-binding.md, decisions/dec-006-shared-chromosome-
# randstream-input-oracle.md) -- append-only extension of this module's
# existing DNADamage coverage above, mirroring the SAME shared
# infrastructure (`chromosome_rand_stream_ledger.py`,
# `_ProcessSpec.chromosome_rand_stream_ledger_attr`, `_build_context`,
# `_honest_replay`'s ledger injection block) for a second consuming
# process. See STATUS_L21_REPINIT_SEPT2.md for the full narrative.

_REPINIT_CANONICAL_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2"
    / "ReplicationInitiation_200ticks.mat"
)
_REPINIT_CANONICAL_LEDGER = _REPINIT_CANONICAL_TRACE.with_suffix("").with_suffix(".chromosome_rand_stream_ledger.json")

_requires_repinit_canonical_trace = pytest.mark.skipif(
    not (_REPINIT_CANONICAL_TRACE.exists() and _REPINIT_CANONICAL_LEDGER.exists()),
    reason=(
        "canonical seed0 ReplicationInitiation 200-tick trace/ledger not present in this "
        "checkout -- the .mat trace tree is gitignored/regenerated-on-demand, not committed"
    ),
)


def _copy_repinit_trace_and_ledger(dest_dir: Path) -> tuple[Path, Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_trace = dest_dir / _REPINIT_CANONICAL_TRACE.name
    dest_ledger = dest_dir / _REPINIT_CANONICAL_LEDGER.name
    shutil.copyfile(_REPINIT_CANONICAL_TRACE, dest_trace)
    shutil.copyfile(_REPINIT_CANONICAL_LEDGER, dest_ledger)
    return dest_trace, dest_ledger


def test_replication_initiation_spec_declares_chromosome_rand_stream_ledger_attr() -> None:
    spec = replay_common._PROCESS_SPECS["ReplicationInitiation"]
    assert spec.chromosome_rand_stream_ledger_attr == "_chromosome_rng"


@_requires_repinit_canonical_trace
def test_replication_initiation_ledger_loads_and_covers_every_tick() -> None:
    with h5py.File(_REPINIT_CANONICAL_TRACE, "r") as handle:
        ctx = replay_common._build_context(name="ReplicationInitiation", rng_seed=0, handle=handle)
        assert ctx.chromosome_rand_stream_ledger is not None
        assert len(ctx.chromosome_rand_stream_ledger) == ctx.n_ticks == 200


@_requires_repinit_canonical_trace
def test_replication_initiation_full_200_tick_chromosome_stream_ledger_bit_identity() -> None:
    """Session N+3 (`_second_copy_site_mask` source-fidelity fix, see
    STATUS_L21_REPINIT_SEPT2.md): `_honest_replay` no longer raises at
    all across the full 200-tick trace -- OC's own chromosome-owned
    site-selection algorithm now consumes EXACTLY the real recorded draw
    count on EVERY tick, verified here by asserting the actual
    `BitIdentityResult` fields directly (`pass_all_compared_ticks is
    True` and `first_mismatch_tick is None` over all 200 compared ticks),
    not merely that the replay ran to completion without raising.
    (An earlier revision of this docstring cited a one-off,
    never-committed `scripts/tmp_repinit_full_ledger_scan.py` scratch
    script as independent verification; no such file exists in this
    repository. The only genuine independent verification is this test
    itself asserting the real `BitIdentityResult`, plus the reproducible
    `scripts/diagnose_repinit_l21.py` diagnostic invoked directly --
    see STATUS_L21_REPINIT_SEPT2.md for the exact commands and output.)

    NOTE (Session N+5 correction, carried into this current-main
    integration -- see STATUS_L21_REPINIT_SEPT2.md "read this first"):
    the shared-Chromosome-RNG-stream mechanism being bit-exact does NOT
    by itself mean the process's full AGGREGATE observable replay is
    bit-identical WITHOUT the ledger -- the genuine non-ledger replay
    mismatches at a real, reproducible tick (see the explicit
    `--no-ledger` diagnostic in `scripts/diagnose_repinit_l21.py`), an
    accepted, documented, non-blocking gap under DEC-005/DEC-006's own
    input-oracle scope (the shared stream's real tick-to-tick position
    is not independently reconstructable from a single-process trace by
    architecture, not by omission). This test intentionally scopes ONLY
    the chromosome-stream-ledger mechanism (this replay call uses the
    ledger, restoring input state), exactly like every other assertion
    in this module."""
    bit_identity, honest = active_windows._honest_replay(
        process_name="ReplicationInitiation", trace_path=_REPINIT_CANONICAL_TRACE
    )
    assert bit_identity.compared_tick_count == 200
    assert bit_identity.pass_all_compared_ticks is True, (
        "ledger-restored ReplicationInitiation replay must be bit-identical across "
        f"all 200 ticks; first mismatch was {bit_identity.first_mismatch_tick!r} "
        f"({bit_identity.first_mismatch_observable!r}, index {bit_identity.first_mismatch_index!r}: "
        f"OC={bit_identity.first_mismatch_oc_val!r} vs Karr={bit_identity.first_mismatch_karr_val!r})"
    )
    assert bit_identity.first_mismatch_tick is None
    assert bit_identity.first_mismatch_observable is None
    assert bit_identity.first_mismatch_index is None
    assert honest is not None


@_requires_repinit_canonical_trace
def test_replication_initiation_missing_ledger_sidecar_falls_back_to_prior_stand_in_behavior(tmp_path: Path) -> None:
    """A ReplicationInitiation trace with NO companion ledger sidecar
    must silently fall back to the pre-existing freshly-seeded stand-in
    `_chromosome_rng` stream -- never raise, never treat absence as a
    failure. This is also this integration's own explicit, documented
    no-ledger diagnostic case: the real, non-ledger-restored replay is
    expected to diverge on OBSERVABLE grounds eventually but must never
    raise a ledger-related error while doing so."""
    dest_dir = tmp_path / "per_process_traces_v2_missing_ledger"
    dest_dir.mkdir(parents=True)
    dest_trace = dest_dir / _REPINIT_CANONICAL_TRACE.name
    shutil.copyfile(_REPINIT_CANONICAL_TRACE, dest_trace)
    # Deliberately do NOT copy the ledger sidecar.

    with h5py.File(dest_trace, "r") as handle:
        ctx = replay_common._build_context(name="ReplicationInitiation", rng_seed=0, handle=handle)
        assert ctx.chromosome_rand_stream_ledger is None

    # The replay must still run (using the stand-in stream), not raise --
    # it will still diverge eventually on OBSERVABLE grounds, but must
    # not raise a ledger-related error.
    bit_identity, honest = active_windows._honest_replay(
        process_name="ReplicationInitiation", trace_path=dest_trace
    )
    assert bit_identity.compared_tick_count == 200


@_requires_repinit_canonical_trace
def test_replication_initiation_tampered_ledger_hash_mismatch_fails_closed_not_silent_fallback(tmp_path: Path) -> None:
    """A ledger sidecar bound to a DIFFERENT trace than the one it sits
    beside must raise at load time -- never silently accept stale data."""
    dest_dir = tmp_path / "per_process_traces_v2_tampered"
    dest_trace, dest_ledger = _copy_repinit_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    payload["trace_sha256"] = "0" * 64  # deliberately wrong
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with h5py.File(dest_trace, "r") as handle, pytest.raises(Exception, match="DIFFERENT trace file"):
        replay_common._build_context(name="ReplicationInitiation", rng_seed=0, handle=handle)


@_requires_repinit_canonical_trace
def test_replication_initiation_truncated_ledger_n_draws_mismatch_fails_closed(tmp_path: Path) -> None:
    """A ledger whose recorded n_draws/draws length disagree (corrupted/
    manually-truncated) must raise at load time -- never silently
    truncate or pad."""
    dest_dir = tmp_path / "per_process_traces_v2_short"
    dest_trace, dest_ledger = _copy_repinit_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    # Tick 0 (0-indexed) is a real, nonzero-draw tick for this trace.
    payload["per_tick"][0]["draws"] = payload["per_tick"][0]["draws"][:-1]
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with h5py.File(dest_trace, "r") as handle, pytest.raises(Exception, match="does not match len"):
        replay_common._build_context(name="ReplicationInitiation", rng_seed=0, handle=handle)


@_requires_repinit_canonical_trace
def test_replication_initiation_overflow_ledger_fails_closed_during_replay(tmp_path: Path) -> None:
    """A ledger padded with an extra draw OC's algorithm does not consume
    must fail closed via the ledger replay stream's
    `assert_fully_consumed()` detecting leftover draws -- never silently
    ignored."""
    dest_dir = tmp_path / "per_process_traces_v2_overflow"
    dest_trace, dest_ledger = _copy_repinit_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    tick0 = payload["per_tick"][0]
    tick0["draws"] = [*tick0["draws"], 0.123456789]
    tick0["n_draws"] = len(tick0["draws"])
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="only consumed"):
        active_windows._honest_replay(process_name="ReplicationInitiation", trace_path=dest_trace)


@_requires_repinit_canonical_trace
def test_replication_initiation_overconsumption_ledger_fails_closed_immediately(tmp_path: Path) -> None:
    """A ledger tick whose recorded draws are too FEW for what OC's
    algorithm actually needs must raise immediately mid-call (exhausted),
    not just at the end-of-tick assert_fully_consumed check -- exercised
    here by truncating a tick known to need more than 1 draw down to
    exactly 1."""
    dest_dir = tmp_path / "per_process_traces_v2_underflow"
    dest_trace, dest_ledger = _copy_repinit_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    tick0 = payload["per_tick"][0]
    if tick0["n_draws"] > 1:
        tick0["draws"] = tick0["draws"][:1]
        tick0["n_draws"] = 1
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="exhausted after|only consumed"):
        active_windows._honest_replay(process_name="ReplicationInitiation", trace_path=dest_trace)


@_requires_repinit_canonical_trace
def test_replication_initiation_accepts_regenerated_ledger(tmp_path: Path) -> None:
    """Explicit proof (task requirement): main's UNCHANGED
    `chromosome_rand_stream_ledger.py` loader accepts a genuinely
    regenerated RepInit ledger sidecar -- i.e. the extractor's
    unconditional `dnadamage_source_resolved_sha256` fix (see
    `scripts/matlab/extract_per_process_traces_v2.m`'s metadata block
    and decisions/dec-006-shared-chromosome-randstream-input-oracle.md
    "Related Decisions") produced a trace/ledger pair that satisfies
    every one of main's stricter provenance checks (trace_sha256 binding,
    raw-byte Chromosome.m/RandStream.m hashes, and the
    dnadamage_source_sha256 cross-check against the trace's own
    metadata) -- not just that the DNADamage lane's own ledger passes."""
    ledger = ledger_mod.load_chromosome_rand_stream_ledger(_REPINIT_CANONICAL_TRACE, repo_root=REPO_ROOT)
    assert ledger is not None
    assert len(ledger) == 200


@_requires_repinit_canonical_trace
def test_replication_initiation_missing_dnadamage_binding_fails_closed(tmp_path: Path) -> None:
    """A RepInit ledger missing its `dnadamage_source_sha256` field
    entirely (an older/pre-portability-fix sidecar) must raise -- never
    silently treat an absent DNADamage source binding as
    "nothing to verify". Exercises the SAME shared loader code path as
    DNADamage's own `test_missing_required_source_hash_field_fails_closed`
    above, for RepInit's own trace/ledger pair."""
    dest_dir = tmp_path / "per_process_traces_v2_repinit_missing_dnadamage_field"
    dest_trace, dest_ledger = _copy_repinit_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    del payload["dnadamage_source_sha256"]
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="missing its required"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)


@_requires_repinit_canonical_trace
def test_replication_initiation_mismatched_dnadamage_binding_fails_closed(tmp_path: Path) -> None:
    """A RepInit ledger whose recorded `dnadamage_source_sha256`
    disagrees with the TRACE's own `dnadamage_source_resolved_sha256`
    metadata (the ledger was reconstructed against a different
    DNADamage.m revision than the one that actually produced this
    trace) must raise -- never silently accept a mismatched
    source-revision binding. Exercises the SAME shared loader code path
    as DNADamage's own `test_tampered_dnadamage_source_hash_fails_closed`
    above, for RepInit's own trace/ledger pair."""
    dest_dir = tmp_path / "per_process_traces_v2_repinit_mismatched_dnadamage_field"
    dest_trace, dest_ledger = _copy_repinit_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    payload["dnadamage_source_sha256"] = "0" * 64
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="DIFFERENT DNADamage.m source revision"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)


# --- Safe scalar-`draws` normalization (loader hardening, shared by every
# process using this ledger, not RepInit-specific): MATLAB's `jsonencode`
# collapses a length-1 numeric array to a bare scalar rather than a
# 1-element array (e.g. `jsonencode([1.5])` -> `1.5`, not `[1.5]`).
# Reproduced against the DNADamage canonical fixture (this normalization
# is a property of the shared loader, not of any one process's ledger).


@_requires_canonical_trace
def test_scalar_draws_with_matching_n_draws_one_normalizes_to_single_element_list(tmp_path: Path) -> None:
    """A tick whose `draws` field was written as a bare JSON scalar (not
    a 1-element list) by a MATLAB jsonencode call must be silently
    normalized to a 1-element list when -- and ONLY when -- the SAME
    entry's own `n_draws` field is exactly 1, never for any other
    `n_draws` value."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_scalar_draws_ok"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    tick0 = payload["per_tick"][0]
    tick0["n_draws"] = 1
    tick0["draws"] = 0.987654321  # bare scalar, not [0.987654321]
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    ledgers = ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)
    assert ledgers is not None
    assert ledgers[0] == [0.987654321]


@_requires_canonical_trace
def test_scalar_draws_with_mismatched_n_draws_still_fails_closed(tmp_path: Path) -> None:
    """A bare-scalar `draws` value whose `n_draws` is NOT 1 (e.g. a
    genuinely malformed/truncated ledger, not a jsonencode single-element
    collapse) must still raise -- the scalar-normalization convenience
    above must never mask an actual n_draws/draws-shape mismatch."""
    dest_dir = tmp_path / "per_process_traces_v2_event_s2000_scalar_draws_bad"
    dest_trace, dest_ledger = _copy_trace_and_ledger(dest_dir)

    payload = json.loads(dest_ledger.read_text(encoding="utf-8"))
    tick0 = payload["per_tick"][0]
    tick0["n_draws"] = 2
    tick0["draws"] = 0.5  # bare scalar, but n_draws claims 2 -- must not normalize
    dest_ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ledger_mod.ChromosomeRandStreamLedgerError, match="malformed/missing draws array"):
        ledger_mod.load_chromosome_rand_stream_ledger(dest_trace, repo_root=REPO_ROOT)
