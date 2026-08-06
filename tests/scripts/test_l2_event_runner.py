"""Unit tests for `scripts/l2_event/runner.py` (requirement 4: refusal
gauntlet -- missing/incomplete window, single-seed-vs-ensemble, empty
support, wrong adapter, mid-cycle traces; requirement 6: adapter mismatch,
seed cluster bootstrap wiring, input completeness; plus CLI-level
smoke/gate-mode dispatch)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.adapters.fakes import SyntheticFireCountAdapter, WrongProcessAdapter
from scripts.l2_event.registry import EventRegistryEntry
from scripts.l2_event.runner import (
    EXIT_OK,
    EXIT_REFUSED,
    RunnerRefusal,
    check_adapter,
    check_empty_support,
    check_ensemble_size,
    evaluate_gate,
    load_and_check_window,
    main,
)
from scripts.l2_event.schema import EventObservation, EventTimeline

_RA_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s000"
    / "RibosomeAssembly_100ticks.mat"
)
_STANDARD_TRACE = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s001" / "Translation_100ticks.mat"


def _timeline(seed: int, fire_ticks: list[int], n_ticks: int = 20) -> EventTimeline:
    fire_set = set(fire_ticks)
    obs = tuple(
        EventObservation(tick=t, fired=t in fire_set, fire_count=1 if t in fire_set else 0, timing_tick=t if t in fire_set else None)
        for t in range(n_ticks)
    )
    return EventTimeline(process="P", seed=seed, observations=obs)


def _entry(**overrides) -> EventRegistryEntry:
    base = dict(
        process="P",
        in_scope_v4=True,
        adapter_id="test.synthetic_fire_count.v1",
        adapter_status="structural_smoke_only",
        event_timing_model="repeated_firing",
        magnitude_gateable=False,
        required_n_seeds=1,
        deferred_reason=None,
    )
    base.update(overrides)
    return EventRegistryEntry(**base)


# ---------------------------------------------------------------------------
# check_ensemble_size
# ---------------------------------------------------------------------------


def test_check_ensemble_size_passes_when_single_seed_required():
    check_ensemble_size(1, 1)  # must not raise


def test_check_ensemble_size_refuses_single_seed_when_ensemble_required():
    with pytest.raises(RunnerRefusal) as exc_info:
        check_ensemble_size(1, 50)
    assert exc_info.value.reason == "SINGLE_SEED_ENSEMBLE_REQUIRED"


def test_check_ensemble_size_passes_when_full_ensemble_provided():
    check_ensemble_size(50, 50)  # must not raise


# ---------------------------------------------------------------------------
# check_adapter
# ---------------------------------------------------------------------------


def test_check_adapter_refuses_process_mismatch():
    adapter = WrongProcessAdapter()
    entry = _entry(adapter_id=adapter.adapter_id)
    with pytest.raises(RunnerRefusal) as exc_info:
        check_adapter(adapter, "SyntheticTestProcess", entry)
    assert exc_info.value.reason == "ADAPTER_PROCESS_MISMATCH"


def test_check_adapter_refuses_unregistered_adapter_id():
    adapter = SyntheticFireCountAdapter()
    entry = _entry(adapter_id="some.other.adapter.v1", adapter_status="gating_ready")
    with pytest.raises(RunnerRefusal) as exc_info:
        check_adapter(adapter, "SyntheticTestProcess", entry)
    assert exc_info.value.reason == "ADAPTER_NOT_REGISTERED"


def test_check_adapter_refuses_when_not_gating_ready():
    adapter = SyntheticFireCountAdapter()
    entry = _entry(adapter_id=adapter.adapter_id, adapter_status="structural_smoke_only")
    with pytest.raises(RunnerRefusal) as exc_info:
        check_adapter(adapter, "SyntheticTestProcess", entry)
    assert exc_info.value.reason == "ADAPTER_NOT_GATING_READY"


def test_check_adapter_passes_for_matching_gating_ready_adapter():
    adapter = SyntheticFireCountAdapter()
    entry = _entry(adapter_id=adapter.adapter_id, adapter_status="gating_ready")
    check_adapter(adapter, "SyntheticTestProcess", entry)  # must not raise


# ---------------------------------------------------------------------------
# load_and_check_window (thin wrapper over window_loader)
# ---------------------------------------------------------------------------


def test_load_and_check_window_refuses_missing_file(tmp_path):
    with pytest.raises(RunnerRefusal) as exc_info:
        load_and_check_window(tmp_path / "nope.mat", ("obsA",))
    assert exc_info.value.reason == "MISSING_WINDOW"


@pytest.mark.skipif(not _STANDARD_TRACE.exists(), reason="Real standard mid-cycle Translation MAT not present locally")
def test_load_and_check_window_refuses_standard_mid_cycle_trace():
    with pytest.raises(RunnerRefusal) as exc_info:
        load_and_check_window(_STANDARD_TRACE, ("substrates",))
    assert exc_info.value.reason == "NOT_EVENT_WINDOW_TRACE"


# ---------------------------------------------------------------------------
# check_empty_support
# ---------------------------------------------------------------------------


def test_check_empty_support_refuses_vacuous_zero_zero_cohort():
    karr = [_timeline(s, []) for s in range(5)]
    oc = [_timeline(s, []) for s in range(5)]
    with pytest.raises(RunnerRefusal) as exc_info:
        check_empty_support(karr, oc)
    assert exc_info.value.reason == "EMPTY_EVENT_SUPPORT"


def test_check_empty_support_does_not_refuse_when_oc_fires_despite_karr_silence():
    """This is a hard FAIL case for the gate, not a refusal -- the runner
    must let it through to evaluate_gate so it can be reported as FAIL,
    not silently swallowed as a precondition refusal."""
    karr = [_timeline(s, []) for s in range(5)]
    oc = [_timeline(s, [3]) for s in range(5)]
    check_empty_support(karr, oc)  # must not raise


def test_check_empty_support_passes_when_karr_has_support():
    karr = [_timeline(s, [2]) for s in range(5)]
    oc = [_timeline(s, [2]) for s in range(5)]
    check_empty_support(karr, oc)  # must not raise


# ---------------------------------------------------------------------------
# evaluate_gate -- pure orchestration over synthetic timelines
# ---------------------------------------------------------------------------


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def _adapter_and_entry(**entry_overrides) -> tuple[SyntheticFireCountAdapter, EventRegistryEntry]:
    """Build a matching (adapter, registry_entry) pair for `evaluate_gate`'s
    new M2 signature: a `SyntheticFireCountAdapter` whose `process_name`
    matches the entry's `process`, with `adapter_status='gating_ready'` so
    `check_adapter`'s internal gauntlet (now run BY `evaluate_gate` itself,
    not just by a caller that remembers to run it first) passes."""
    process = entry_overrides.pop("process", "P")
    adapter = SyntheticFireCountAdapter(process_name=process)
    entry_overrides.setdefault("required_n_seeds", 1)
    entry = _entry(
        process=process,
        adapter_id=adapter.adapter_id,
        adapter_status="gating_ready",
        **entry_overrides,
    )
    return adapter, entry


def _repeated_firing_cohort(n_seeds: int = 24, n_ticks: int = 20) -> list[list[int]]:
    """Fire-tick lists with real inter-seed variance in both per-seed
    counts and tick positions (2/3/4 fires per seed, cycling), so pooled
    Karr support clears the M1 floor (>=50) and the null bootstrap is
    never degenerate -- unlike a naive constant-count/constant-tick
    fixture, which would spuriously hit DEGENERATE_NULL."""
    fires = []
    for s in range(n_seeds):
        k = 2 + (s % 3)
        base = 3 + (s % 5)
        fires.append([base + i * 2 for i in range(k)])
    return fires


def test_evaluate_gate_passes_for_matching_repeated_firing_cohorts():
    fire_ticks = _repeated_firing_cohort()
    karr = [_timeline(s, fire_ticks[s], n_ticks=20) for s in range(len(fire_ticks))]
    oc = [_timeline(s, fire_ticks[s], n_ticks=20) for s in range(len(fire_ticks))]
    adapter, entry = _adapter_and_entry(event_timing_model="repeated_firing", magnitude_gateable=False)
    result = evaluate_gate(
        process="P",
        registry_entry=entry,
        adapter=adapter,
        karr_timelines=karr,
        oc_timelines=oc,
        rng=_rng(),
    )
    assert result.verdict == "PASS"
    payload_channel = next(c for c in result.channels if c.channel == "payload")
    assert payload_channel.verdict == "NOT_GATEABLE_REDUNDANT"


def test_evaluate_gate_fails_on_spurious_oc_only_firings_between_events():
    """C6: OC firing on ticks Karr never fired must fail the whole gate,
    even if aggregate counts might otherwise look plausible. Checked
    before any support-floor consideration, so a small cohort still
    exercises this path cleanly."""
    karr = [_timeline(s, [3], n_ticks=20) for s in range(20)]
    oc = [_timeline(s, [3, 4, 5], n_ticks=20) for s in range(20)]
    adapter, entry = _adapter_and_entry(event_timing_model="repeated_firing", magnitude_gateable=False)
    result = evaluate_gate(
        process="P",
        registry_entry=entry,
        adapter=adapter,
        karr_timelines=karr,
        oc_timelines=oc,
        rng=_rng(),
    )
    assert result.verdict == "FAIL"
    assert result.oc_only_fire_ticks
    assert any("spurious OC-only" in r for r in result.reasons)


def test_evaluate_gate_refuses_empty_support_vacuous_cohort():
    karr = [_timeline(s, []) for s in range(5)]
    oc = [_timeline(s, []) for s in range(5)]
    adapter, entry = _adapter_and_entry(event_timing_model="repeated_firing", magnitude_gateable=False)
    with pytest.raises(RunnerRefusal) as exc_info:
        evaluate_gate(
            process="P",
            registry_entry=entry,
            adapter=adapter,
            karr_timelines=karr,
            oc_timelines=oc,
            rng=_rng(),
        )
    assert exc_info.value.reason == "EMPTY_EVENT_SUPPORT"


def test_evaluate_gate_fails_hard_when_karr_silent_but_oc_fires():
    """No zero==zero PASS, and no silent laundering when only OC fires."""
    karr = [_timeline(s, []) for s in range(5)]
    oc = [_timeline(s, [4]) for s in range(5)]
    adapter, entry = _adapter_and_entry(event_timing_model="repeated_firing", magnitude_gateable=False)
    result = evaluate_gate(
        process="P",
        registry_entry=entry,
        adapter=adapter,
        karr_timelines=karr,
        oc_timelines=oc,
        rng=_rng(),
    )
    assert result.verdict == "FAIL"


def test_evaluate_gate_requires_matched_timeline_lengths():
    karr = [_timeline(0, [1])]
    oc = [_timeline(0, [1]), _timeline(1, [1])]
    adapter, entry = _adapter_and_entry(event_timing_model="repeated_firing", magnitude_gateable=False)
    with pytest.raises(ValueError):
        evaluate_gate(
            process="P",
            registry_entry=entry,
            adapter=adapter,
            karr_timelines=karr,
            oc_timelines=oc,
            rng=_rng(),
        )


def test_evaluate_gate_single_firing_requires_offsets():
    karr = [_timeline(s, [3]) for s in range(5)]
    oc = [_timeline(s, [3]) for s in range(5)]
    adapter, entry = _adapter_and_entry(event_timing_model="single_firing", magnitude_gateable=False)
    with pytest.raises(ValueError):
        evaluate_gate(
            process="P",
            registry_entry=entry,
            adapter=adapter,
            karr_timelines=karr,
            oc_timelines=oc,
            rng=_rng(),
        )


def test_evaluate_gate_payload_gate_wired_when_magnitude_gateable():
    karr = [_timeline(s, [3], n_ticks=20) for s in range(20)]
    oc = [_timeline(s, [3], n_ticks=20) for s in range(20)]
    # Payload values vary across seeds (non-degenerate null) but Karr and
    # OC are shifted by two orders of magnitude.
    karr_payloads = [{"a": 5.0 + (i % 5) * 0.5} for i in range(20)]
    oc_payloads = [{"a": 500.0 + (i % 5) * 0.5} for i in range(20)]
    adapter, entry = _adapter_and_entry(event_timing_model="repeated_firing", magnitude_gateable=True)
    result = evaluate_gate(
        process="P",
        registry_entry=entry,
        adapter=adapter,
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=[[p] for p in karr_payloads],
        oc_payloads_by_seed=[[p] for p in oc_payloads],
        rng=_rng(),
    )
    payload_channel = next(c for c in result.channels if c.channel == "payload")
    assert payload_channel.verdict == "FAIL"
    assert result.verdict == "FAIL"


def test_evaluate_gate_insufficient_karr_support_refuses_whole_process_verdict():
    """M1/M2 reproduction of an Opus-reported false green: only 3 fires
    total (well below the pooled-fire-tick floor of 50) must REFUSE the
    whole process verdict, never silently compute PASS/FAIL from an
    under-powered cohort. This is also the direct-`evaluate_gate`-API
    bypass check: even calling this function directly (never through the
    CLI) cannot skip the M1 support floor, because the floor is enforced
    inside `metrics.count_gate`/`timing_gate_repeated_firing`, which
    `evaluate_gate` always calls."""
    karr = [_timeline(0, [3, 9, 12], n_ticks=20)]
    oc = [_timeline(0, [3, 9, 12], n_ticks=20)]
    adapter, entry = _adapter_and_entry(event_timing_model="repeated_firing", magnitude_gateable=False)
    result = evaluate_gate(
        process="P",
        registry_entry=entry,
        adapter=adapter,
        karr_timelines=karr,
        oc_timelines=oc,
        rng=_rng(),
    )
    assert result.verdict == "REFUSED"
    count_channel = next(c for c in result.channels if c.channel == "count")
    assert count_channel.verdict == "INSUFFICIENT_KARR_SUPPORT"


def test_evaluate_gate_direct_call_cannot_bypass_gauntlet_with_n_seeds_one():
    """M2: n_seeds=1 fed straight into `evaluate_gate` (bypassing the CLI
    entirely) must still be refused if the registry declares an ensemble
    requirement -- `evaluate_gate` runs `check_ensemble_size` itself, so
    there is no direct-API path around it."""
    karr = [_timeline(0, [3, 9])]
    oc = [_timeline(0, [3, 9])]
    adapter, entry = _adapter_and_entry(
        event_timing_model="repeated_firing", magnitude_gateable=False, required_n_seeds=50
    )
    with pytest.raises(RunnerRefusal) as exc_info:
        evaluate_gate(
            process="P",
            registry_entry=entry,
            adapter=adapter,
            karr_timelines=karr,
            oc_timelines=oc,
            rng=_rng(),
        )
    assert exc_info.value.reason == "SINGLE_SEED_ENSEMBLE_REQUIRED"


# ---------------------------------------------------------------------------
# CLI-level dispatch (main())
# ---------------------------------------------------------------------------


def test_main_refuses_unknown_process():
    assert main(["--process", "NotARealProcess", "--mode", "smoke", "--seeds", "0"]) == EXIT_REFUSED


def test_main_refuses_out_of_scope_process_dna_damage():
    assert main(["--process", "DNADamage", "--mode", "smoke", "--seeds", "0"]) == EXIT_REFUSED


def test_main_refuses_out_of_scope_process_ftsz():
    assert main(["--process", "FtsZPolymerization", "--mode", "gate", "--seeds", "0"]) == EXIT_REFUSED


def test_main_refuses_cytokinesis_smoke_no_adapter():
    assert main(["--process", "Cytokinesis", "--mode", "smoke", "--seeds", "0"]) == EXIT_REFUSED


def test_main_gate_mode_always_refuses_for_ribosome_assembly_single_seed():
    assert main(["--process", "RibosomeAssembly", "--mode", "gate", "--seeds", "0"]) == EXIT_REFUSED


def test_main_gate_mode_refuses_for_ribosome_assembly_full_ensemble_no_cli_wiring():
    """As of the 2026-08-05 promotion, RibosomeAssembly IS
    ``adapter_status: gating_ready`` in the live registry, so
    ``check_ensemble_size``/``check_adapter`` no longer raise for this
    call. This still refuses because `main`'s own ``--mode gate`` CLI
    dispatch has no per-process wiring to actually build timelines and
    call `evaluate_gate` for ANY process in this foundation build -- real
    N=50 gate evidence for RibosomeAssembly is produced by the dedicated
    ``scripts/l2_event/ribosome_assembly_n50_gate.py`` driver instead (see
    ``docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/``), not via
    this CLI's ``--mode gate`` path."""
    seeds = ",".join(str(i) for i in range(50))
    assert main(["--process", "RibosomeAssembly", "--mode", "gate", "--seeds", seeds]) == EXIT_REFUSED


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_main_smoke_mode_refuses_for_ribosome_assembly_now_that_it_is_gating_ready(tmp_path, monkeypatch):
    """Historical note: before the 2026-08-05 promotion (see
    ``docs/phase_f/l2_event/event_registry.yaml`` and
    ``tests/scripts/test_l2_event_ribosome_assembly_n50.py`` for the real
    50-seed gate this promotion is based on), this exact CLI invocation
    (``--process RibosomeAssembly --mode smoke``) was the only way to get
    ANY evidence for this process, and succeeded with a
    ``structural_smoke`` / ``NOT_APPLICABLE`` verdict. Now that the
    registry declares ``ribosome_assembly.gate.v1`` / ``gating_ready`` for
    this process, `main`'s smoke-mode dispatch (which only ever recognizes
    ``adapter_status == 'structural_smoke_only'``) correctly refuses
    instead -- this CLI has no path left to the RETIRED smoke adapter for
    an already-promoted process, and must never silently fall back to it.
    Real gate evidence for this process is produced by
    ``scripts/l2_event/ribosome_assembly_n50_gate.py`` instead (see
    ``docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/``)."""
    from scripts.l2_event import evidence as evidence_mod

    live_root = tmp_path / "artifacts"
    bundle_root = tmp_path / "bundle"
    index_path = tmp_path / "index.json"
    monkeypatch.setattr(evidence_mod, "LIVE_EVIDENCE_ROOT", live_root)
    monkeypatch.setattr(evidence_mod, "TRACKED_BUNDLE_ROOT", bundle_root)
    monkeypatch.setattr(evidence_mod, "TRACKED_INDEX_PATH", index_path)

    rc = main(["--process", "RibosomeAssembly", "--mode", "smoke", "--seeds", "0"])
    assert rc == EXIT_REFUSED
    assert not bundle_root.exists()


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_main_smoke_mode_succeeds_against_a_stale_pre_promotion_registry_copy(tmp_path, monkeypatch):
    """Regression coverage for the CLI's smoke-mode success path itself
    (exit 0, full evidence artifact set written+bundled+indexed,
    verdict=NOT_APPLICABLE) now that the live registry has no process left
    with ``adapter_status: structural_smoke_only`` (RibosomeAssembly was
    the only one, and it has graduated -- see
    ``test_main_smoke_mode_refuses_for_ribosome_assembly_now_that_it_is_gating_ready``
    above). We exercise this path against an explicit, in-memory-authored
    stale registry copy (only ``adapter_status`` reverted back to
    ``structural_smoke_only``, matching the exact pre-promotion state) via
    ``--registry-path``, never against the live registry file."""
    import yaml

    from scripts.l2_event import evidence as evidence_mod
    from scripts.l2_event.registry import REGISTRY_PATH

    stale_registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    for row in stale_registry["processes"]:
        if row["process"] == "RibosomeAssembly":
            row["adapter_status"] = "structural_smoke_only"
            row["adapter_id"] = "ribosome_assembly.smoke.v1"
    stale_registry_path = tmp_path / "stale_event_registry.yaml"
    stale_registry_path.write_text(yaml.safe_dump(stale_registry), encoding="utf-8")

    live_root = tmp_path / "artifacts"
    bundle_root = tmp_path / "bundle"
    index_path = tmp_path / "index.json"
    monkeypatch.setattr(evidence_mod, "LIVE_EVIDENCE_ROOT", live_root)
    monkeypatch.setattr(evidence_mod, "TRACKED_BUNDLE_ROOT", bundle_root)
    monkeypatch.setattr(evidence_mod, "TRACKED_INDEX_PATH", index_path)

    rc = main(
        [
            "--process",
            "RibosomeAssembly",
            "--mode",
            "smoke",
            "--seeds",
            "0",
            "--registry-path",
            str(stale_registry_path),
        ]
    )
    assert rc == EXIT_OK

    bundled_result = evidence_mod.read_json(bundle_root / "RibosomeAssembly" / "result.json")
    assert bundled_result["verdict"] == "NOT_APPLICABLE"
    assert bundled_result["mode"] == "structural_smoke"

    # Note: unlike the (now-retired) live-registry version of this test, we
    # deliberately do NOT assert `audit_index(...) == []` here.
    # `audit_index`'s registry_sha256 check always recomputes against the
    # real, LIVE `event_registry.yaml` (there is no override hook for it),
    # so provenance recorded against our intentionally-stale
    # `--registry-path` copy will always disagree with the live file's
    # current hash -- that is the correct, expected consequence of using a
    # non-live registry snapshot here, not a genuine evidence-integrity bug.
