"""FtsZPolymerization honest-mode (no-hint) windowed canary.

Turn-2 deliverable for the L2.event -> continuous/windowed reclassification
of FtsZPolymerization (see docs/phase_f/l2_windowed/FTSZ_WINDOWED_PROFILE_SPEC.md).

> **2026-08-05 update:** this N=1, non-division-anchored diagnostic is
> superseded for CATALOG CONFORMANCE (live PROCESS_CATALOG.yaml row:
> `bucket: EVENT_CLASS`, `N_seeds: 50`, `M_ticks: 200`,
> `seed_window.tick_range_from_division: [-200, 0]`) by the pre-division
> event-window evidence path in
> `scripts/l2_event/ftsz_pre_division_evidence.py` and
> `tests/scripts/test_ftsz_pre_division_evidence.py` (spec:
> `docs/phase_f/l2_windowed/FTSZ_PRE_DIVISION_EVENT_WINDOW_SPEC.md`). This
> file is NOT deleted -- its N=1, non-division-anchored, no-hint invariant
> checks remain valid evidence in their own right -- but it is no longer
> the process's catalog-conformance evidence path.

WHAT THIS TEST IS
- Runs `KarrFtsZPolymerizationProcess.next_update` per-tick against the only
  on-disk FtsZ trace (seed 0, 100 ticks,
  data/m1_sources/karr_native/per_process_traces_v2/FtsZPolymerization_100ticks.mat)
  with NO `trace_hint` ever populated, so the ODE / discretize / substrate-clamp
  biology path (`evolveState` equivalent) is what actually runs -- not the
  `enzymes_next` short-circuit described in
  docs/phase_f/L2_5_HONEST_MODE_HINT_LEAKAGE_FINDING.md.
- Enforces exact (zero-fudge-factor) structural invariants that hold
  unconditionally in the Karr algebra regardless of ensemble size: monomer-count
  conservation, GTP/GDP/PI/H2O/H stoichiometric self-consistency, and
  finite/nonnegative/integer emitted deltas.
- Reports raw per-tick discrepancy telemetry (OC honest-mode vs Karr) for the
  `enzymes` (primary/gate) and `substrates` (secondary/conservation) channels.
  `boundEnzymes` and the OC-only `cell.ftsz_ring_count`/`ftsz_ring_complete`
  channels are diagnostics only and are excluded from the gate set.

WHAT THIS TEST IS NOT
- It is NOT a gate. With N=1 seed / M=100 ticks on disk (catalog requires
  N_seeds=50), no distributional claim is supportable (event-style
  single-seed-ensemble refusal rules apply conceptually here too). The test
  therefore always concludes with `pytest.skip(INSUFFICIENT_ENSEMBLE ...)`
  once structural invariants have been checked -- it can fail (invariant
  violation, oracle leakage, WID mismatch) but it can never PASS/report a
  green fidelity verdict. The eventual N=50 gate must use a Karr-only
  seed-cluster / split-half null with a W1 (Wasserstein) or other
  preregistered multivariate metric -- see
  `wasserstein_over_wid_intersection` in l2_replay_common.py and the "Future
  N=50 gate contract" section of FTSZ_WINDOWED_PROFILE_SPEC.md. No such
  threshold is invented in this file.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import h5py
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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    audit_trace_mutated_ticks,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
    resolve_trace_path,
)

from opencell.vivarium.karr_ftsz_polymerization import (  # noqa: E402
    KarrFtsZPolymerizationProcess,
)

_TRACE_PROCESS_NAME = "FtsZPolymerization"
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes")
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
}

# Gate-eligible channels for the (future) N=50 verdict. `boundEnzymes` (Karr
# never mutates it for this process -- 0/100 ticks) and the OC-only derived
# `cell.ftsz_ring_count`/`ftsz_ring_complete` aggregate (no independent Karr
# ground truth channel exists for it) are diagnostics only and MUST NOT be
# promoted into this set without a separate, explicit decision.
GATE_CHANNELS = ("enzymes", "substrates")
DIAGNOSTIC_ONLY_CHANNELS = ("boundEnzymes", "cell.ftsz_ring_count", "cell.ftsz_ring_complete")

REQUIRED_N_SEEDS = (
    50  # PROCESS_CATALOG.yaml N_seeds for FtsZPolymerization (unchanged, not edited here)
)
ACTUAL_N_SEEDS = 1  # measured: identical seed-0 trace hash across every worktree + main + mirrors

# Provenance anchor for the N=1 seed this canary actually exercises. This is the
# full SHA256 of the exact file `resolve_trace_path` resolves to, NOT the
# `per_process_replay/FtsZPolymerization.npz` artifact (SHA256
# 348db55cf64c97c11fc5e94f7f9d2b93f77a9da7edf93647d8e41570a311fdaf) referenced
# elsewhere in this repo's inventory notes -- that NPZ is a *different* replay
# run (divergent RNG pools/state produced by a separate harness invocation) and
# is not the extraction target of this canary. The canary reads directly from
# the HDF5 `.mat` trace below via `resolve_trace_path`/`cell_vector`.
TRACE_SHA256 = "c0797bcb84fa6041875caddf6a7c195362fdad64fd80412a34946a914aaa9ee1"

# Reference (checked-in, read-only) telemetry snapshot. The test NEVER writes
# to this path -- it is compared against a freshly computed run (written to
# pytest's `tmp_path`) as a reproducibility assertion. Regenerating this
# reference (if the honest-mode trajectory ever legitimately changes) is a
# deliberate, reviewed act, not a side effect of running the test suite.
_EXPECTED_TELEMETRY_ARTIFACT = (
    _REPO_ROOT / "docs" / "phase_f" / "l2_windowed" / "ftsz_seed0_honest_mode_telemetry.json"
)

# Fields that are legitimately environment-dependent (absolute paths differ by
# worktree/machine) and therefore excluded from the strict reproducibility
# comparison against the checked-in reference.
_TELEMETRY_ENV_DEPENDENT_FIELDS = ("trace_path",)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_ensemble_support(n_seeds: int, required_n_seeds: int = REQUIRED_N_SEEDS) -> str:
    """Pure classification, no thresholds invented: mirrors the L2.event
    registry's own single-seed-ensemble refusal (docs/phase_f/l2_event/
    event_registry.yaml `required_n_seeds`). n_seeds < required_n_seeds can
    NEVER classify as sufficient -- there is no partial-credit branch."""
    if n_seeds < required_n_seeds:
        return "INSUFFICIENT_ENSEMBLE"
    return "SUFFICIENT_ENSEMBLE"


def _assert_no_oracle_leakage(state: dict[str, Any]) -> None:
    """Prove the honest-mode harness itself never injects a trace_hint. Combined
    with `forbid_sut_oracle_file_io` around the `next_update` call, this proves
    no oracle-after channel reaches the biology path this tick."""
    hint = state.get("trace_hint")
    assert not hint, (
        "honest-mode canary must never populate trace_hint (found: "
        f"{hint!r}); this would silently re-enable the enzymes_next "
        "short-circuit documented in L2_5_HONEST_MODE_HINT_LEAKAGE_FINDING.md"
    )


def _monomer_conservation_delta(
    process: KarrFtsZPolymerizationProcess, enzyme_delta: dict[str, float]
) -> int:
    delta_vec = np.asarray(
        [float(enzyme_delta.get(wid, 0.0)) for wid in process.enzyme_wids], dtype=np.float64
    )
    return int(np.rint(float(np.dot(process.n_monomers, delta_vec))))


def _check_substrate_stoichiometry(
    process: KarrFtsZPolymerizationProcess,
    *,
    enzyme_delta: dict[str, float],
    substrate_delta: dict[str, float],
    tick: int,
) -> None:
    """Exact (integer-arithmetic) self-consistency check derived directly from
    `apply_substrate_limits`'s own algebra (FtsZPolymerization.m:403-433;
    karr_ftsz_polymerization.py `apply_substrate_limits`), independent of any
    reimplementation of the internal clamp-loop branching:

        shortfall := PI_delta  (PI has no other source term than the
                                 GDP-shortfall hydrolysis compensation)
        H2O_delta  == -shortfall
        H_delta    == +shortfall
        GDP_delta  == -n_gdp . d_enzyme + shortfall
        GTP_delta  == -n_gtp . d_enzyme - shortfall

    MUST be called unconditionally, on every tick, even when `substrate_delta`
    is `{}` (a genuinely-zero-delta tick, or -- the failure mode this guards
    against -- a bug that drops the substrates key from the update entirely).
    An empty dict means every `.get(wid, 0.0)` below defaults to 0.0, which is
    only a valid stoichiometric outcome when `n_gtp_dot == n_gdp_dot == 0`; if
    enzymes changed (nonzero `n_gtp_dot`/`n_gdp_dot`) while `substrate_delta`
    is empty, the GDP/GTP equations below correctly fail. See the inversion
    test `test_empty_substrate_delta_fails_on_nonzero_coupling_ticks` in
    test_karr_ftsz_polymerization_honest_canary_inversions.py, which forces
    `substrate_delta={}` and proves this raises on exactly the ticks where
    real GTP/GDP coupling is nonzero.
    """
    delta_vec = np.asarray(
        [float(enzyme_delta.get(wid, 0.0)) for wid in process.enzyme_wids], dtype=np.float64
    )
    n_gtp_dot = float(np.dot(process.n_gtp, delta_vec))
    n_gdp_dot = float(np.dot(process.n_gdp, delta_vec))

    pi_delta = float(substrate_delta.get(process.pi_wid, 0.0))
    h2o_delta = float(substrate_delta.get(process.h2o_wid, 0.0))
    h_delta = float(substrate_delta.get(process.h_wid, 0.0))
    gdp_delta = float(substrate_delta.get(process.gdp_wid, 0.0))
    gtp_delta = float(substrate_delta.get(process.gtp_wid, 0.0))

    assert pi_delta >= -1e-9, f"tick={tick}: PI shortfall proxy went negative: {pi_delta}"
    assert abs(h2o_delta - (-pi_delta)) < 1e-6, (
        f"tick={tick}: H2O_delta={h2o_delta} != -PI_delta={-pi_delta}"
    )
    assert abs(h_delta - pi_delta) < 1e-6, f"tick={tick}: H_delta={h_delta} != PI_delta={pi_delta}"
    assert abs(gdp_delta - (-n_gdp_dot + pi_delta)) < 1e-6, (
        f"tick={tick}: GDP_delta={gdp_delta} != -n_gdp.d_enzyme({-n_gdp_dot}) + PI_delta({pi_delta})"
    )
    assert abs(gtp_delta - (-n_gtp_dot - pi_delta)) < 1e-6, (
        f"tick={tick}: GTP_delta={gtp_delta} != -n_gtp.d_enzyme({-n_gtp_dot}) - PI_delta({pi_delta})"
    )


def _substrate_coupling_flags(
    process: KarrFtsZPolymerizationProcess,
    *,
    enzyme_delta: dict[str, float],
    substrate_delta: dict[str, float],
) -> dict[str, bool]:
    """Per-tick clause-coverage flags for the stoichiometry check above.
    These report which branches of the formula were actually exercised by
    THIS one seed/trace -- exact invariant correctness (asserted every tick
    regardless) is a separate claim from "this branch's value range was ever
    nonzero in the data we have". Both are reported in telemetry so the two
    claims are never conflated."""
    delta_vec = np.asarray(
        [float(enzyme_delta.get(wid, 0.0)) for wid in process.enzyme_wids], dtype=np.float64
    )
    n_gtp_dot = float(np.dot(process.n_gtp, delta_vec))
    n_gdp_dot = float(np.dot(process.n_gdp, delta_vec))
    pi_delta = float(substrate_delta.get(process.pi_wid, 0.0))
    return {
        "gtp_coupling": abs(n_gtp_dot) > 1e-9,
        "gdp_coupling": abs(n_gdp_dot) > 1e-9,
        "hydrolysis_shortfall": pi_delta > 1e-9,
    }


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_ftsz_polymerization_honest_mode_windowed_canary(
    rng_seed: int, tmp_path: Path
) -> None:
    from l2_replay_common import forbid_sut_oracle_file_io

    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    actual_trace_sha256 = _sha256_file(trace_path)
    assert actual_trace_sha256 == TRACE_SHA256, (
        f"trace file at {trace_path} has sha256={actual_trace_sha256}, expected "
        f"{TRACE_SHA256}. This is the N=1 provenance anchor for this canary -- "
        "if this legitimately changed (e.g. a deliberate re-extraction), update "
        "TRACE_SHA256 as part of that reviewed change, not silently here."
    )

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        mutated_obs = (
            "enzymes",
            "substrates",
        )  # boundEnzymes excluded: 0/100 mutated ticks, pass-through only
        mutated_tick_counts = audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                "honest-mode canary N/A: no-op trace. Per-observable nonzero-delta "
                f"counts: {mutated_tick_counts}."
            )

        process = KarrFtsZPolymerizationProcess({"rng_seed": int(rng_seed)})
        state_template = build_state_template(process)

        wids_by_observable: dict[str, list[str]] = {}
        for observable in _OBSERVABLES:
            karr_before = cell_vector(trace, "states_before", observable, 0)
            wids_by_observable[observable] = infer_wids_for_observable(
                process,
                state_template,
                observable,
                karr_len=int(karr_before.shape[0]),
                explicit_attr=_OBSERVABLE_TO_WIDS_ATTR.get(observable),
            )

        # Inversion guard: wrong-WID-order. If this ever drifts, every downstream
        # exact invariant below (monomer conservation, stoichiometry) becomes
        # meaningless because `process.n_monomers`/`n_gtp`/`n_gdp` are indexed by
        # `process.enzyme_wids` order, not by whatever order infer_wids_for_observable
        # happened to return.
        assert wids_by_observable["enzymes"] == list(process.enzyme_wids), (
            "enzymes WID order drift between harness inference and process fixture "
            "order -- monomer/stoichiometry invariants below would silently "
            "validate against the wrong species."
        )

        oc_nonvacuous_ticks = 0
        telemetry: dict[str, Any] = {
            "process": _TRACE_PROCESS_NAME,
            "trace_path": str(trace_path),
            "trace_sha256": actual_trace_sha256,
            "rng_seed": int(rng_seed),
            "n_ticks": n_ticks,
            "n_seeds_available": ACTUAL_N_SEEDS,
            "n_seeds_required_by_catalog": REQUIRED_N_SEEDS,
            "ensemble_status": classify_ensemble_support(ACTUAL_N_SEEDS),
            "gate_channels": list(GATE_CHANNELS),
            "diagnostic_only_channels": list(DIAGNOSTIC_ONLY_CHANNELS),
            "karr_mutated_tick_counts": mutated_tick_counts,
            "per_tick": [],
        }
        gtp_coupling_ticks = 0
        gdp_coupling_ticks = 0
        hydrolysis_shortfall_ticks = 0

        for tick in range(n_ticks):
            state = build_state_template(process)
            _assert_no_oracle_leakage(state)

            before_vectors = {
                observable: cell_vector(trace, "states_before", observable, tick)
                for observable in _OBSERVABLES
            }
            after_vectors = {
                observable: cell_vector(trace, "states_after", observable, tick)
                for observable in _OBSERVABLES
            }

            for observable in _OBSERVABLES:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                )
            # Deliberately NOT calling overlay_trace_after_hint here (honest mode).
            refresh_allocator_views(process, state)
            _assert_no_oracle_leakage(state)

            with forbid_sut_oracle_file_io():
                update = process.next_update(1.0, state)

            deltas_by_label = dict(collect_count_delta_dicts(update))
            enzyme_delta = deltas_by_label.get("enzymes", {})
            substrate_delta = deltas_by_label.get("substrates", {})

            for label, deltas in deltas_by_label.items():
                for wid, delta in deltas.items():
                    delta_f = float(delta)
                    assert np.isfinite(delta_f), (
                        f"tick={tick}: non-finite delta {label}/{wid}={delta_f}"
                    )
                    assert delta_f == float(np.rint(delta_f)), (
                        f"tick={tick}: non-integral delta {label}/{wid}={delta_f}"
                    )

            monomer_delta = _monomer_conservation_delta(process, enzyme_delta)
            assert monomer_delta == 0, (
                f"tick={tick}: FtsZ total-monomer conservation violated: "
                f"n_monomers.d_enzymes={monomer_delta} (expected 0)"
            )

            # Called unconditionally (not `if substrate_delta:`): an empty
            # substrate_delta dict means zero deltas by construction
            # (`.get(wid, 0.0)` defaults), which the check below only accepts
            # when enzyme deltas also imply zero GTP/GDP coupling this tick.
            # See _check_substrate_stoichiometry's docstring and the
            # corresponding mutation-inversion test.
            _check_substrate_stoichiometry(
                process, enzyme_delta=enzyme_delta, substrate_delta=substrate_delta, tick=tick
            )
            coupling_flags = _substrate_coupling_flags(
                process, enzyme_delta=enzyme_delta, substrate_delta=substrate_delta
            )
            gtp_coupling_ticks += int(coupling_flags["gtp_coupling"])
            gdp_coupling_ticks += int(coupling_flags["gdp_coupling"])
            hydrolysis_shortfall_ticks += int(coupling_flags["hydrolysis_shortfall"])

            if any(abs(float(v)) > 0.0 for v in enzyme_delta.values()):
                oc_nonvacuous_ticks += 1

            from l2_replay_common import apply_count_update

            apply_count_update(state, update)

            oc_after_enzymes = project_observable_from_state(
                process=process,
                state=state,
                observable="enzymes",
                wids=wids_by_observable["enzymes"],
                bound_enzymes_before=before_vectors.get("boundEnzymes"),
            )
            oc_after_substrates = project_observable_from_state(
                process=process,
                state=state,
                observable="substrates",
                wids=wids_by_observable["substrates"],
                bound_enzymes_before=before_vectors.get("boundEnzymes"),
            )

            assert np.all(np.isfinite(oc_after_enzymes)), f"tick={tick}: non-finite enzymes state"
            assert np.all(oc_after_enzymes >= -1e-9), (
                f"tick={tick}: negative enzymes state {oc_after_enzymes}"
            )
            assert np.all(np.isfinite(oc_after_substrates)), (
                f"tick={tick}: non-finite substrates state"
            )
            assert np.all(oc_after_substrates >= -1e-9), (
                f"tick={tick}: negative substrates state {oc_after_substrates}"
            )

            karr_after_enzymes = after_vectors["enzymes"]
            karr_after_substrates = after_vectors["substrates"]
            enzymes_l1 = float(np.sum(np.abs(oc_after_enzymes - karr_after_enzymes)))
            enzymes_linf = float(np.max(np.abs(oc_after_enzymes - karr_after_enzymes)))
            substrates_l1 = float(np.sum(np.abs(oc_after_substrates - karr_after_substrates)))
            substrates_linf = float(np.max(np.abs(oc_after_substrates - karr_after_substrates)))

            telemetry["per_tick"].append(
                {
                    "tick": tick,
                    "enzymes_l1": enzymes_l1,
                    "enzymes_linf": enzymes_linf,
                    "substrates_l1": substrates_l1,
                    "substrates_linf": substrates_linf,
                }
            )

        assert oc_nonvacuous_ticks > 0, (
            "honest-mode OC trajectory is constant across all "
            f"{n_ticks} ticks (0 nonzero enzyme deltas) -- this would be a "
            "quiet/constant-trajectory fake pass; Karr's own trace is "
            f"non-vacuous ({mutated_tick_counts})."
        )
        telemetry["oc_nonvacuous_ticks"] = oc_nonvacuous_ticks

        # Clause-coverage counters (see _substrate_coupling_flags docstring):
        # these are NOT a pass/fail gate -- they record, honestly, which
        # branches of the (exactly-checked-every-tick) stoichiometry formula
        # actually took a nonzero value in this one seed/trace. In particular
        # the PI/H2O/H hydrolysis-shortfall branch is *never* exercised
        # (0/100) in this trace: the formula's shortfall terms are checked
        # (as `== 0`) every tick, but their nonzero-value behavior is
        # unvalidated by this seed. This distinguishes "the invariant holds
        # everywhere we checked" from "every branch of the invariant was
        # exercised with a nonzero value".
        telemetry["substrate_stoichiometry_clause_coverage"] = {
            "gtp_coupling_nonzero_ticks": gtp_coupling_ticks,
            "gdp_coupling_nonzero_ticks": gdp_coupling_ticks,
            "hydrolysis_shortfall_nonzero_ticks": hydrolysis_shortfall_ticks,
            "n_ticks": n_ticks,
            "note": (
                "Exact invariant equality is asserted on all n_ticks ticks "
                "unconditionally (see _check_substrate_stoichiometry). These "
                "counts report how many of those ticks had a nonzero value "
                "for each term -- i.e. branch/clause coverage, not "
                "invariant-correctness coverage. hydrolysis_shortfall_nonzero_ticks"
                "=0 means the PI/H2O/H shortfall-compensation branch was "
                "checked as identically zero on every tick in this seed, "
                "never validated against a nonzero shortfall value."
            ),
        }

        enz_l1_values = [row["enzymes_l1"] for row in telemetry["per_tick"]]
        sub_l1_values = [row["substrates_l1"] for row in telemetry["per_tick"]]
        telemetry["summary"] = {
            "enzymes_l1_mean": float(np.mean(enz_l1_values)),
            "enzymes_l1_max": float(np.max(enz_l1_values)),
            "enzymes_l1_zero_ticks": int(sum(1 for v in enz_l1_values if v == 0.0)),
            "substrates_l1_mean": float(np.mean(sub_l1_values)),
            "substrates_l1_max": float(np.max(sub_l1_values)),
            "substrates_l1_zero_ticks": int(sum(1 for v in sub_l1_values if v == 0.0)),
        }

        # Write the freshly computed telemetry to pytest's tmp_path ONLY --
        # this test must never dirty the tracked reference artifact as a side
        # effect of running. The tracked file
        # (_EXPECTED_TELEMETRY_ARTIFACT) is a checked-in, human-reviewed
        # reference snapshot; regenerating it is a deliberate, separate act.
        fresh_telemetry_path = tmp_path / "ftsz_seed0_honest_mode_telemetry.json"
        fresh_telemetry_path.write_text(json.dumps(telemetry, indent=2, sort_keys=True) + "\n")

        # Reproducibility assertion: the honest-mode trajectory is fully
        # deterministic given rng_seed=0 (process.next_update draws from a
        # per-instance np.random.default_rng seeded once at construction, and
        # the same process instance is reused for all n_ticks ticks). Compare
        # the freshly computed telemetry against the checked-in reference,
        # ignoring only the environment-dependent absolute path field.
        assert _EXPECTED_TELEMETRY_ARTIFACT.exists(), (
            f"expected reference telemetry artifact missing: "
            f"{_EXPECTED_TELEMETRY_ARTIFACT}. This file is a checked-in "
            "baseline, not test output -- it must exist in the repo."
        )
        expected_telemetry = json.loads(_EXPECTED_TELEMETRY_ARTIFACT.read_text())
        fresh_comparable = {
            k: v for k, v in telemetry.items() if k not in _TELEMETRY_ENV_DEPENDENT_FIELDS
        }
        expected_comparable = {
            k: v for k, v in expected_telemetry.items() if k not in _TELEMETRY_ENV_DEPENDENT_FIELDS
        }
        assert fresh_comparable == expected_comparable, (
            "freshly computed honest-mode telemetry does not match the "
            f"checked-in reference at {_EXPECTED_TELEMETRY_ARTIFACT} (ignoring "
            f"environment-dependent fields {_TELEMETRY_ENV_DEPENDENT_FIELDS}). "
            "Either the honest-mode trajectory genuinely changed (update the "
            "reference as a deliberate, reviewed change) or this run is "
            f"non-reproducible. Fresh output written to {fresh_telemetry_path} "
            "for diffing."
        )

        status = classify_ensemble_support(ACTUAL_N_SEEDS)
        assert (
            status == "INSUFFICIENT_ENSEMBLE"
        )  # N=1 can never promote itself (see inversion test)
        pytest.skip(
            f"{status}: N={ACTUAL_N_SEEDS} seed(s) available, "
            f"N={REQUIRED_N_SEEDS} required by PROCESS_CATALOG.yaml for a gated "
            "verdict. Structural invariants (monomer conservation, substrate "
            "stoichiometry, finite/nonnegative/integer state) held for all "
            f"{n_ticks} honest-mode ticks (unconditionally, incl. zero-delta "
            "ticks); no trace_hint reached next_update. Clause coverage: GTP "
            f"coupling nonzero on {gtp_coupling_ticks}/{n_ticks} ticks, GDP "
            f"coupling nonzero on {gdp_coupling_ticks}/{n_ticks}, PI/H2O/H "
            f"hydrolysis-shortfall nonzero on {hydrolysis_shortfall_ticks}/{n_ticks} "
            "(unexercised branch -- checked as zero every tick, not validated "
            "nonzero). Discrepancy telemetry (seed 0, trace sha256="
            f"{actual_trace_sha256[:12]}...): enzymes L1 mean="
            f"{telemetry['summary']['enzymes_l1_mean']:.4f} max="
            f"{telemetry['summary']['enzymes_l1_max']:.4f} "
            f"zero-ticks={telemetry['summary']['enzymes_l1_zero_ticks']}/{n_ticks}; "
            f"substrates L1 mean={telemetry['summary']['substrates_l1_mean']:.4f} "
            f"max={telemetry['summary']['substrates_l1_max']:.4f} "
            f"zero-ticks={telemetry['summary']['substrates_l1_zero_ticks']}/{n_ticks}. "
            f"Full per-tick telemetry (fresh, tmp): {fresh_telemetry_path}; "
            f"reference: {_EXPECTED_TELEMETRY_ARTIFACT}."
        )
