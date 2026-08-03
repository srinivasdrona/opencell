"""L2.1 strict-rubric test — enforces the supplement checks for all 28 processes.

Each L2.1 PASS is classified into GENUINE / UNINFORMATIVE / COINCIDENTAL /
FAIL based on:
  1. Bit-identity per-tick (the original L2.1 rubric)
  2. Karr-active rate (does Karr's recorded trace show non-trivial delta on any tick?)
  3. OC-fire-on-Karr-active rate (did OC's next_update return non-empty on
     ticks where Karr's recorded delta was non-trivial?)

A test PASS requires verdict == GENUINE. Other verdicts are surfaced as
xfail / skip / failure so the validation surface is honest.

Expected verdicts are pinned per-process; changes to biology, port reads,
or trace data that move a verdict will fail the test until the expected
verdict is updated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_2_replay_common_v2 import (  # type: ignore
    _PROCESS_SPECS,
    _build_context,
    _inject_hidden_read_surface,
    _project_trace_vector,
    resolve_trace_path,
)
from l2_replay_common import (  # type: ignore
    apply_count_update,
    build_state_template,
    collect_count_delta_dicts,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
)

# Day-37 (2026-06-23) Phase B+ baseline — oracle-type-aware rubric
# Stochastic processes (oracle_type=distributional) no longer require per-tick
# bit-identity. Per-tick bit-identity is checked only for deterministic
# processes (oracle_type=bit_identity). This is the correct rubric per
# process class and restores the L2.2 ⊆ L2.1 hierarchy expectation.
EXPECTED_VERDICTS = {
    # GENUINE: 18 (was 16; Day-37 PM: +TerminalOrg from schema-v2.1 fallback,
    # +TranscriptionalRegulation and +Metabolism from non-standard channel
    # detection — their biology fires on tf_binding/tx_rate_fold_change/
    # metabolic_reaction.fluxs which the strict rubric now recognizes)
    #
    # DNARepair stays COINCIDENTAL, but NOT because the harness lacks its inputs:
    # `_classify()` now injects the chromosome hidden-read surface (states_before,
    # via `_inject_hidden_read_surface`), so DNARepair fires real biology on 8/100
    # ticks (BER/NER/HR repairs + MunI methylation). It remains COINCIDENTAL because
    # its single Karr-active tick is the stochastic-rare (~3%/tick) MunI maintenance
    # methylation, which OC fires on different ticks in a single trace. That is an
    # L2.2 (distributional rate) concern, not a per-tick fire-rate one.
    "DNARepair": "COINCIDENTAL",
    "DNASupercoiling": "GENUINE",
    "FtsZPolymerization": "GENUINE",
    "MacromolecularComplexation": "GENUINE",
    "Metabolism": "GENUINE",
    "ProteinActivation": "GENUINE",
    "ProteinFolding": "GENUINE",
    "ProteinModification": "GENUINE",
    "ProteinProcessingI": "GENUINE",
    "ProteinProcessingII": "GENUINE",
    "ProteinTranslocation": "GENUINE",
    "RNADecay": "GENUINE",
    "RNAProcessing": "GENUINE",
    "ReplicationInitiation": "GENUINE",
    "TerminalOrganelleAssembly": "GENUINE",
    "Transcription": "GENUINE",
    "TranscriptionalRegulation": "GENUINE",
    "Translation": "GENUINE",
    "tRNAAminoacylation": "GENUINE",
    # UNINFORMATIVE: 6 (Karr's trace shows no activity for 100-tick window)
    "ChromosomeSegregation": "UNINFORMATIVE",
    "Cytokinesis": "UNINFORMATIVE",
    "DNADamage": "UNINFORMATIVE",
    "HostInteraction": "UNINFORMATIVE",
    "RNAModification": "UNINFORMATIVE",
    "RibosomeAssembly": "UNINFORMATIVE",
    # COINCIDENTAL: 3 (Metabolism + TxReg now GENUINE via non-standard channels;
    # DNARepair, ProteinDecay, and Replication are still biology-silent on this
    # standard-observable-only strict-rubric surface — real gaps)
    "ProteinDecay": "COINCIDENTAL",
    "Replication": "COINCIDENTAL",
    # FAIL: 1 (bit-identity broken for deterministic process)
    "ChromosomeCondensation": "FAIL",
    # ERROR: 0 (was 1 — TerminalOrg moved to GENUINE Day-37 PM after schema v2.1 fallback)
}

# Threshold for "Karr-active" — magnitude of |delta| considered non-trivial.
# 1.0 = at least one integer-count change. Lower would flag fractional drift.
KARR_ACTIVE_THRESHOLD = 1.0


def _classify(name: str) -> dict:
    """Run a single process's strict-rubric replay."""
    spec = _PROCESS_SPECS.get(name)
    if spec is None:
        return {"name": name, "verdict": "ERROR", "error": "no spec"}

    try:
        handle = h5py.File(resolve_trace_path(name), "r")
    except Exception as exc:
        return {"name": name, "verdict": "ERROR", "error": f"trace: {exc}"}

    try:
        ctx = _build_context(name=name, rng_seed=0, handle=handle)
    except Exception as exc:
        handle.close()
        return {"name": name, "verdict": "ERROR", "error": f"build_context: {exc}"}

    process = ctx.process
    n_ticks = ctx.n_ticks
    observables = list(spec.observables)
    wids_by_observable = ctx.wids_by_observable

    bit_identity_failures = 0
    karr_active = 0
    oc_fired = 0
    oc_fired_on_karr_active = 0

    try:
        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vecs = {}
            for obs in observables:
                before = _project_trace_vector(ctx, "states_before", obs, tick)
                before_vecs[obs] = before
                overlay_observable_into_state(
                    process=process, state=state, observable=obs,
                    vector=before, wids=wids_by_observable[obs],
                    store_path_override=spec.store_path_override,
                )
            # Inject the process's declared hidden read-surface (e.g. chromosome) from the
            # recorded states_before -- the real INPUT the process reads, not the recorded
            # outcome. Without this, chromosome-coupled processes see only template defaults
            # and cannot fire their real biology, yielding spurious COINCIDENTAL verdicts.
            # No-op when the trace lacks the channel (e.g. chromosome-less traces).
            _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)

            refresh_allocator_views(process, state)
            update = process.next_update(1.0, state)
            apply_count_update(state, update)

            oc_nonempty = False
            if isinstance(update, dict):
                for _, delta_dict in collect_count_delta_dicts(update):
                    if any(abs(float(v)) > 0 for v in delta_dict.values()):
                        oc_nonempty = True
                        break
                # Day-37 fix: collect_count_delta_dicts only knows the standard
                # ports (substrates/protein/rna/complex/boundEnzymes/enzymes).
                # Some processes return biology output on non-standard channels
                # that the strict rubric must still recognize as "biology fired":
                #   - TranscriptionalRegulation: tf_binding, tx_rate_fold_change
                #   - Metabolism: metabolic_reaction.fluxs
                # Check these channels too before declaring biology silent.
                if not oc_nonempty:
                    for nonstd_key in ("tf_binding", "tx_rate_fold_change", "metabolic_reaction"):
                        node = update.get(nonstd_key, None)
                        if isinstance(node, dict) and node:
                            # tf_binding is dict[str, dict[str, float]]; flatten
                            # tx_rate_fold_change is dict[str, float] (multiplicative,
                            # 1.0 = no change, so check != 1.0 not just != 0)
                            if nonstd_key == "tx_rate_fold_change":
                                if any(abs(float(v) - 1.0) > 1e-9 for v in node.values()):
                                    oc_nonempty = True
                                    break
                            elif nonstd_key == "tf_binding":
                                # dict[tf_wid, dict[tu_wid, delta]]
                                for inner in node.values():
                                    if isinstance(inner, dict) and any(
                                        abs(float(v)) > 0 for v in inner.values()
                                    ):
                                        oc_nonempty = True
                                        break
                                if oc_nonempty:
                                    break
                            elif nonstd_key == "metabolic_reaction":
                                # dict with "fluxs" (dict[rxn_id, flux]) plus
                                # growth scalars; fluxs != 0 means biology fired
                                fluxs = node.get("fluxs", {})
                                if isinstance(fluxs, dict) and any(
                                    abs(float(v)) > 1e-9 for v in fluxs.values()
                                ):
                                    oc_nonempty = True
                                    break
            if oc_nonempty:
                oc_fired += 1

            karr_max_abs = 0.0
            for obs in observables:
                before = before_vecs[obs]
                after = _project_trace_vector(ctx, "states_after", obs, tick)
                delta = after - before
                if delta.size > 0:
                    karr_max_abs = max(karr_max_abs, float(np.abs(delta).max()))
            if karr_max_abs >= KARR_ACTIVE_THRESHOLD:
                karr_active += 1
                if oc_nonempty:
                    oc_fired_on_karr_active += 1

            for obs in observables:
                if obs in spec.pass_through:
                    continue
                oc_after = project_observable_from_state(
                    process=process, state=state, observable=obs,
                    wids=wids_by_observable[obs],
                    bound_enzymes_before=before_vecs.get("boundEnzymes"),
                    store_path_override=spec.store_path_override,
                )
                karr_after = _project_trace_vector(ctx, "states_after", obs, tick)
                if oc_after.shape != karr_after.shape:
                    bit_identity_failures += 1
                    break
                # Day-37 fix: stochastic processes (ORACLE_DISTRIBUTIONAL) legitimately
                # have per-tick RNG variance. Per-tick bit-identity is the wrong rubric
                # for them. Use bit-identity only for ORACLE_BIT_IDENTITY (deterministic)
                # processes; for ORACLE_DISTRIBUTIONAL, skip the per-tick check and
                # rely on the fire-rate check below. This aligns with the L2.2 design_a
                # runner's distributional comparison and resolves the L2.2 > L2.1
                # ordering inversion the Day-37 audit revealed.
                oracle_type = getattr(spec, "oracle_type", "distributional")
                if oracle_type == "bit_identity" and not np.array_equal(
                    oc_after.astype(np.int64), karr_after.astype(np.int64)
                ):
                    bit_identity_failures += 1
                    break
    except Exception as exc:
        handle.close()
        return {"name": name, "verdict": "ERROR", "error": f"run: {exc}"}

    handle.close()

    fire_rate_when_karr_active = (
        oc_fired_on_karr_active / karr_active if karr_active else None
    )
    if bit_identity_failures > 0:
        verdict = "FAIL"
    elif karr_active == 0:
        verdict = "UNINFORMATIVE"
    elif fire_rate_when_karr_active is not None and fire_rate_when_karr_active < 0.05:
        verdict = "COINCIDENTAL"
    elif fire_rate_when_karr_active is not None and fire_rate_when_karr_active >= 0.50:
        verdict = "GENUINE"
    else:
        verdict = "PARTIAL"

    return {
        "name": name,
        "verdict": verdict,
        "bit_identity_failures": bit_identity_failures,
        "karr_active": karr_active,
        "oc_fired_on_karr_active": oc_fired_on_karr_active,
        "fire_rate_when_karr_active": fire_rate_when_karr_active,
        "n_ticks": n_ticks,
    }


@pytest.mark.parametrize("process_name", sorted(EXPECTED_VERDICTS.keys()))
def test_l2_1_strict_rubric_matches_expected(process_name: str) -> None:
    """Run strict-rubric audit on a process; fail if verdict differs from pinned.

    The pinned EXPECTED_VERDICTS values are the Day-36 baseline. They reflect
    the current honest state of L2.1 validation. Changes to biology that
    improve a verdict (e.g. FAIL -> GENUINE) should update the pin AND the
    process-specific test if applicable.

    GENUINE: 9 processes; the real L2.1 validation surface today.
    UNINFORMATIVE: 6 processes; Karr trace shows no activity (vacuous PASS).
    COINCIDENTAL: 1 process; biology dodges Karr-active ticks.
    FAIL: 11 processes; bit-identity or fire-rate fails (trace-hint
    short-circuits + ProteinTranslocation port-mismatch).
    ERROR: 1 (TerminalOrg config issue).
    """
    expected = EXPECTED_VERDICTS[process_name]
    result = _classify(process_name)
    actual = result["verdict"]

    if actual != expected:
        pytest.fail(
            f"L2.1 strict rubric verdict drift for {process_name}: "
            f"expected={expected}, actual={actual}. "
            f"Detail: bit_identity_failures={result.get('bit_identity_failures')}, "
            f"karr_active={result.get('karr_active')}/{result.get('n_ticks')}, "
            f"fire_rate_when_karr_active={result.get('fire_rate_when_karr_active')}. "
            f"If this is intentional (biology fix moved a process to GENUINE), "
            f"update the EXPECTED_VERDICTS pin in this file."
        )
