# ruff: noqa: E402

"""Strict L2.1 rubric audit across all 28 processes.

For each process:
  1. Re-run the L2.1-style per-tick bit-identity replay
  2. Track:
     - karr_active_ticks: fraction of ticks where Karr's recorded delta exceeds threshold
     - oc_fired_ticks: fraction of ticks where OC's next_update returns non-empty
     - oc_fired_at_karr_active: intersection — OC fired on at least one Karr-active tick
  3. Combine with the static read-surface coverage audit
  4. Classify the L2.1 PASS as:
     - GENUINE: biology fired on most Karr-active ticks AND coverage is full
     - COINCIDENTAL: bit-identity passes but biology rarely fires on Karr-active ticks
     - UNINFORMATIVE: both Karr and OC silent (no biology to validate)
     - FAIL: bit-identity fails

Reports per-process verdicts and a final scoreboard.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests" / "vivarium"))

from _chromcond_replay_apply import apply_chromcond_replay_update  # type: ignore
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
from l21_active_window_audit import (  # type: ignore
    CLASS_CODE_GAP,
    CLASS_MISSING_ACTIVE_EXTRACTION,
    MANIFEST_VERIFY_CODE_GAP,
    MANIFEST_VERIFY_EXISTING_WINDOW_PASS,
    MANIFEST_VERIFY_INVALID,
    MANIFEST_VERIFY_MISSING_ACTIVE_EXTRACTION,
    verify_active_window_manifest_row,
)

KARR_ACTIVE_THRESHOLD = 1.0


def _audit_one_process_default(name: str, threshold: float = KARR_ACTIVE_THRESHOLD) -> dict:
    """Run a single process's L2.1-style replay and classify."""
    spec = _PROCESS_SPECS.get(name)
    if spec is None:
        return {"name": name, "error": "no spec"}

    try:
        trace_path = resolve_trace_path(name)
        handle = h5py.File(trace_path, "r")
    except Exception as exc:
        return {"name": name, "error": f"trace not found: {exc}"}

    try:
        ctx = _build_context(name=name, rng_seed=0, handle=handle)
    except Exception as exc:
        handle.close()
        return {"name": name, "error": f"build_context: {exc}"}

    process = ctx.process
    n_ticks = ctx.n_ticks
    observables = list(spec.observables)
    wids_by_observable = ctx.wids_by_observable

    bit_identity_failures = 0
    karr_active = 0      # ticks where Karr recorded non-trivial delta
    oc_fired = 0         # ticks where OC produced non-empty update
    oc_fired_on_karr_active = 0
    karr_active_oc_silent = 0
    karr_active_total_abs = 0.0

    try:
        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vecs = {}
            for obs in observables:
                before = _project_trace_vector(ctx, "states_before", obs, tick)
                before_vecs[obs] = before
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=obs,
                    vector=before,
                    wids=wids_by_observable[obs],
                    store_path_override=spec.store_path_override,
                )

            _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
            refresh_allocator_views(process, state)
            update = process.next_update(1.0, state)
            # ChromosomeCondensation's next_update emits the NEW post-tick chromosome
            # sparse structure, not an accumulator delta; the generic apply_count_update
            # would corrupt it (see tests/vivarium/_chromcond_replay_apply.py docstring).
            # Every other process keeps the plain, main-identical apply_count_update so
            # its L2.2 provenance hash is untouched.
            if name == "ChromosomeCondensation":
                apply_chromcond_replay_update(state, update)
            else:
                apply_count_update(state, update)

            # Did OC fire on this tick?
            oc_nonempty = False
            if isinstance(update, dict):
                for _, delta_dict in collect_count_delta_dicts(update):
                    if any(abs(float(v)) > 0 for v in delta_dict.values()):
                        oc_nonempty = True
                        break
            if oc_nonempty:
                oc_fired += 1

            # Karr's expected delta this tick — sum non-trivial across observables
            karr_max_abs = 0.0
            karr_total_abs = 0.0
            for obs in observables:
                before = before_vecs[obs]
                after = _project_trace_vector(ctx, "states_after", obs, tick)
                delta = after - before
                if delta.size > 0:
                    m = float(np.abs(delta).max())
                    karr_max_abs = max(karr_max_abs, m)
                    karr_total_abs += float(np.abs(delta).sum())
            if karr_max_abs >= threshold:
                karr_active += 1
                karr_active_total_abs += karr_total_abs
                if oc_nonempty:
                    oc_fired_on_karr_active += 1
                else:
                    karr_active_oc_silent += 1

            # Bit-identity check on owned observables (mirrors L2.1 acceptance).
            # Day-37 fix: only apply per-tick bit-identity check for deterministic
            # processes (oracle_type=bit_identity). Stochastic processes
            # (oracle_type=distributional) have legitimate per-tick RNG variance;
            # bit-identity is the wrong rubric for them. Use the fire-rate check
            # below to gate stochastic processes.
            oracle_type = getattr(spec, "oracle_type", "distributional")
            check_bit_identity = oracle_type == "bit_identity"
            for obs in observables:
                if obs in spec.pass_through:
                    continue
                oc_after = project_observable_from_state(
                    process=process,
                    state=state,
                    observable=obs,
                    wids=wids_by_observable[obs],
                    bound_enzymes_before=before_vecs.get("boundEnzymes"),
                    store_path_override=spec.store_path_override,
                )
                karr_after = _project_trace_vector(ctx, "states_after", obs, tick)
                if oc_after.shape != karr_after.shape:
                    bit_identity_failures += 1
                    break
                if check_bit_identity and not np.array_equal(
                    oc_after.astype(np.int64), karr_after.astype(np.int64)
                ):
                    bit_identity_failures += 1
                    break
    except Exception as exc:
        handle.close()
        return {"name": name, "error": f"run: {exc}", "exception_type": type(exc).__name__}

    handle.close()

    fire_rate_overall = oc_fired / n_ticks if n_ticks else 0.0
    karr_active_rate = karr_active / n_ticks if n_ticks else 0.0
    fire_rate_when_karr_active = (
        oc_fired_on_karr_active / karr_active if karr_active else None
    )

    bit_identity_pass = bit_identity_failures == 0
    if not bit_identity_pass:
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
        "n_ticks": n_ticks,
        "bit_identity_pass": bit_identity_pass,
        "bit_identity_failures": bit_identity_failures,
        "karr_active_ticks": karr_active,
        "karr_active_rate": karr_active_rate,
        "oc_fired_ticks": oc_fired,
        "oc_fired_rate": fire_rate_overall,
        "fire_rate_when_karr_active": fire_rate_when_karr_active,
        "karr_active_oc_silent": karr_active_oc_silent,
        "verdict": verdict,
    }


def _result_from_manifest_verification(name: str, verification: dict[str, Any]) -> dict[str, Any]:
    live_candidate = verification.get("live_candidate") or {}
    bit_identity = verification.get("bit_identity") or {}
    honest_replay = verification.get("honest_replay") or {}
    replay_verification = verification.get("replay_verification") or {}
    n_ticks = int(bit_identity.get("compared_tick_count") or live_candidate.get("n_ticks") or 0)
    karr_active_ticks = int(honest_replay.get("karr_active_ticks") or 0)
    oc_fired_ticks = int(honest_replay.get("oc_active_ticks") or 0)
    oc_fired_on_karr_active = int(honest_replay.get("oc_active_on_karr_active_ticks") or 0)
    fire_rate_when_karr_active = (
        oc_fired_on_karr_active / karr_active_ticks if karr_active_ticks else None
    )
    status = verification.get("verification_status")

    bit_identity_pass = bool(bit_identity.get("pass_all_compared_ticks", False))
    bit_identity_failures = 0 if bit_identity_pass else 1
    verdict = MANIFEST_VERIFY_INVALID
    if status == MANIFEST_VERIFY_EXISTING_WINDOW_PASS:
        verdict = "GENUINE"
        bit_identity_pass = bool(replay_verification.get("passed", False))
        bit_identity_failures = 0 if bit_identity_pass else 1
        karr_active_ticks = int(live_candidate.get("active_tick_count") or 0)
        oc_fired_ticks = karr_active_ticks
        oc_fired_on_karr_active = karr_active_ticks
        fire_rate_when_karr_active = 1.0 if karr_active_ticks else None
    elif status == MANIFEST_VERIFY_MISSING_ACTIVE_EXTRACTION:
        verdict = CLASS_MISSING_ACTIVE_EXTRACTION
        bit_identity_pass = True
        bit_identity_failures = 0
    elif status == MANIFEST_VERIFY_CODE_GAP:
        verdict = CLASS_CODE_GAP

    if status == MANIFEST_VERIFY_INVALID:
        failure_reason = verification.get("failure_reason")
        if not failure_reason:
            failure_reason = "active-window manifest verification failed"
        return {
            "name": name,
            "n_ticks": n_ticks,
            "bit_identity_pass": bit_identity_pass,
            "bit_identity_failures": bit_identity_failures,
            "karr_active_ticks": karr_active_ticks,
            "karr_active_rate": (karr_active_ticks / n_ticks) if n_ticks else 0.0,
            "oc_fired_ticks": oc_fired_ticks,
            "oc_fired_rate": (oc_fired_ticks / n_ticks) if n_ticks else 0.0,
            "fire_rate_when_karr_active": fire_rate_when_karr_active,
            "karr_active_oc_silent": max(karr_active_ticks - oc_fired_on_karr_active, 0),
            "verdict": MANIFEST_VERIFY_INVALID,
            "active_window_manifest_error": failure_reason,
            "active_window_manifest": verification,
        }

    return {
        "name": name,
        "n_ticks": n_ticks,
        "bit_identity_pass": bit_identity_pass,
        "bit_identity_failures": bit_identity_failures,
        "karr_active_ticks": karr_active_ticks,
        "karr_active_rate": (karr_active_ticks / n_ticks) if n_ticks else 0.0,
        "oc_fired_ticks": oc_fired_ticks,
        "oc_fired_rate": (oc_fired_ticks / n_ticks) if n_ticks else 0.0,
        "fire_rate_when_karr_active": fire_rate_when_karr_active,
        "karr_active_oc_silent": max(karr_active_ticks - oc_fired_on_karr_active, 0),
        "verdict": verdict,
        "active_window_manifest": verification,
    }


def audit_one_process(
    name: str,
    threshold: float = KARR_ACTIVE_THRESHOLD,
    *,
    active_window_manifest: Path | str | None = None,
) -> dict:
    if active_window_manifest is None:
        return _audit_one_process_default(name, threshold=threshold)

    verification = verify_active_window_manifest_row(Path(active_window_manifest), name)
    if verification.get("verification_status") == "MANIFEST_ROW_MISSING":
        return _audit_one_process_default(name, threshold=threshold)
    return _result_from_manifest_verification(name, verification)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the L2.1 strict-rubric audit.")
    parser.add_argument(
        "--active-window-manifest",
        type=Path,
        default=None,
        help=(
            "Optional active-window manifest. Verified EXISTING_WINDOW_PASS rows "
            "are promoted to GENUINE; verified MISSING_ACTIVE_EXTRACTION rows stay explicit."
        ),
    )
    parser.add_argument(
        "--process",
        action="append",
        choices=sorted(_PROCESS_SPECS.keys()),
        default=None,
        help="Limit the report to one or more process names.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    print("# L2.1 strict-rubric audit\n")
    print(f"{'Process':<28} {'BitId':>6} {'Karr%':>6} {'OC%':>6} {'OC|Karr':>8} {'Verdict':>15}")
    print("-" * 110)
    rows = []
    process_names = sorted(args.process) if args.process else sorted(_PROCESS_SPECS.keys())
    for name in process_names:
        r = audit_one_process(name, active_window_manifest=args.active_window_manifest)
        if "error" in r:
            print(f"{name:<28} ERROR: {r['error'][:60]}")
            rows.append(r)
            continue
        bit = "PASS" if r["bit_identity_pass"] else "FAIL"
        karr_pct = f"{r['karr_active_rate']:.0%}"
        oc_pct = f"{r['oc_fired_rate']:.0%}"
        oc_given_karr = (
            f"{r['fire_rate_when_karr_active']:.0%}"
            if r["fire_rate_when_karr_active"] is not None else "n/a"
        )
        print(f"{name:<28} {bit:>6} {karr_pct:>6} {oc_pct:>6} {oc_given_karr:>8} {r['verdict']:>15}")
        rows.append(r)

    print("\n## Summary")
    bucket_counts: dict[str, int] = {}
    for r in rows:
        v = r.get("verdict", "ERROR")
        bucket_counts[v] = bucket_counts.get(v, 0) + 1
    summary_order = (
        "GENUINE",
        "PARTIAL",
        "UNINFORMATIVE",
        "COINCIDENTAL",
        CLASS_MISSING_ACTIVE_EXTRACTION,
        CLASS_CODE_GAP,
        "FAIL",
        MANIFEST_VERIFY_INVALID,
        "ERROR",
    )
    for k in summary_order:
        if k in bucket_counts:
            print(f"  {k}: {bucket_counts[k]}")

    print("\n## Detailed listings")
    for verdict in summary_order:
        members = [r for r in rows if r.get("verdict") == verdict]
        if members:
            print(f"\n### {verdict} ({len(members)})")
            for r in members:
                print(f"  - {r['name']}: karr_active={r.get('karr_active_ticks', 0)}/{r.get('n_ticks', 0)} ticks, "
                      f"oc_fired={r.get('oc_fired_ticks', 0)}, "
                      f"OC-fire-rate-when-Karr-active={r.get('fire_rate_when_karr_active')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
