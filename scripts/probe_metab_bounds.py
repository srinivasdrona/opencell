from __future__ import annotations

from dataclasses import dataclass

from opencell.vivarium.karr_metabolism import KarrMetabolismProcess


@dataclass(frozen=True)
class ExpectedDelta:
    before: float | None
    expected_delta: float


EXPECTED = {
    "ATP": ExpectedDelta(before=0.0, expected_delta=3626.0),
    "ADP": ExpectedDelta(before=3622.0, expected_delta=-3622.0),
    "ACCOA": ExpectedDelta(before=None, expected_delta=-3622.0),
    "H2O": ExpectedDelta(before=0.0, expected_delta=9195.0),
    "H": ExpectedDelta(before=13042.0, expected_delta=-11323.0),
}
TOL = 10.0


def build_states_before(proc: KarrMetabolismProcess) -> dict:
    substrate_defaults = {
        sid: float(leaf.get("_default", 1.0))
        for sid, leaf in proc.ports_schema()["substrates"].items()
    }
    for sid, spec in EXPECTED.items():
        if spec.before is not None and sid in substrate_defaults:
            substrate_defaults[sid] = float(spec.before)
    return {"substrates": substrate_defaults}


def main() -> int:
    proc = KarrMetabolismProcess({"dynamic_bounds": True})
    states_before = build_states_before(proc)
    update = proc.next_update(1.0, states_before)
    observed = update.get("substrates", {})

    print("Probe: dynamic-bounds next_update(1.0, states_before)")
    print("Observed substrate deltas:")
    for sid in sorted(EXPECTED):
        print(f"  {sid}: {float(observed.get(sid, 0.0)):.6f}")

    print()
    print("Comparison vs Karr tick-0 expected deltas (tolerance +/-10 counts):")
    all_match = True
    for sid in ("ATP", "ADP", "ACCOA", "H2O", "H"):
        exp = EXPECTED[sid].expected_delta
        got = float(observed.get(sid, 0.0))
        diff = abs(got - exp)
        ok = diff <= TOL
        all_match = all_match and ok
        print(
            f"  {sid}: expected={exp:.3f}, observed={got:.3f}, |diff|={diff:.3f}, within_tol={ok}"
        )

    print()
    if all_match:
        print("HYPOTHESIS RESULT: PASS (CONFIRMED)")
        print(
            "Next-step fix shape: route enable_static_substrate_writeback=True through the "
            "bound-aware dynamic/replay update path, not static S@v writeback."
        )
        return 0

    print("HYPOTHESIS RESULT: FAIL (REJECTED)")
    print(
        "Observed dynamic path does not reproduce Karr deltas on ATP/ADP/ACCOA/H2O/H. "
        "Fix shape should be a replay-specific bound-aware update that mirrors MATLAB "
        "evolveState substrate terms rather than raw cytosol S@v writeback."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
