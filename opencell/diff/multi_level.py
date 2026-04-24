"""Multi-level simulation diff tool (Phase 4 / A5 v0.1).

Implements the four equivalence classes from A6 §5:

  Level 1 — STRUCTURAL: port names, units, updaters, topology shape.
            Two simulations are structurally equivalent iff every port
            and store path agree by name and kind.
  Level 2 — INVARIANT: non-negativity, conservation, integrality, etc.
            Per-simulation; reports per-trajectory violations.
            Wraps ``opencell.invariants``.
  Level 3 — TRAJECTORY NORM: L2 / L_inf over each declared comparable
            variable. Tolerances are per-variable (A6 §5.1 defaults).
  Level 4 — PHENOTYPE: scalar final-state and phenotype-bin diffs.
            Most aggressive lossy compression of the trajectory.

Usage:

    from opencell.diff import DiffSpec, run_diff
    spec = DiffSpec(
        engine_a_name="hybrid_run",
        engine_b_name="vivarium",
        comparable_variables={
            ("metabolites", "cglcex"): {"abs": 0.2, "rel": 0.05, "kind": "concentration"},
            ("signal", "f_met"): {"abs": 0.05, "rel": 0.10, "kind": "signal"},
        },
        scalar_phenotypes=["cglcex_final", "f_met_final"],
    )
    report = run_diff(traj_a, traj_b, spec=spec, ...)
    print(report.summary())

The tool deliberately reports findings at every level rather than
short-circuiting on the first failure. Tampering with a tolerance to
silence one level should not silence later levels — they tell different
stories about the same simulation pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from opencell.invariants import (
    InvariantSuite,
    InvariantSuiteReport,
    check_bounded,
    check_count_integrality,
    check_non_negativity,
)


PortPath = tuple[str, ...]
TrajectoryDict = dict[str, Any]


# ---------------------------------------------------------------------------
# Spec & report dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DiffSpec:
    engine_a_name: str
    engine_b_name: str
    comparable_variables: dict[PortPath, dict[str, Any]]
    """Map (port, var) -> {abs: float, rel: float, kind: 'concentration'|'count'|'signal'}.
    The (port, var) tuple navigates the trajectory dict (e.g. ('metabolites', 'cglcex'))."""
    scalar_phenotypes: list[str] = field(default_factory=list)
    """Names recognized by ``compute_phenotypes`` (built-in: cglcex_final,
    f_met_final, gene_state_final_<species>, traj_max_<port>_<var>)."""
    structural_required_paths: list[PortPath] | None = None
    """If supplied, Level 1 fails when any of these (port, var) is absent
    from either trajectory."""
    structural_required_kinds: dict[PortPath, str] | None = None
    """Optional declaration of expected variable kind per path. Used to
    catch updater-swap mistakes (e.g. count where concentration expected)."""


@dataclass
class LevelFinding:
    level: int
    name: str
    severity: str    # "ok" | "warn" | "fail"
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiffReport:
    spec: DiffSpec
    level1_findings: list[LevelFinding] = field(default_factory=list)
    level2_a_invariants: InvariantSuiteReport | None = None
    level2_b_invariants: InvariantSuiteReport | None = None
    level3_findings: list[LevelFinding] = field(default_factory=list)
    level4_findings: list[LevelFinding] = field(default_factory=list)

    @property
    def all_findings(self) -> list[LevelFinding]:
        out: list[LevelFinding] = []
        out.extend(self.level1_findings)
        out.extend(self.level3_findings)
        out.extend(self.level4_findings)
        return out

    @property
    def passed(self) -> bool:
        if any(f.severity == "fail" for f in self.all_findings):
            return False
        if self.level2_a_invariants and not self.level2_a_invariants.passed:
            return False
        if self.level2_b_invariants and not self.level2_b_invariants.passed:
            return False
        return True

    def summary(self) -> str:
        lines = [
            f"Diff '{self.spec.engine_a_name}' vs '{self.spec.engine_b_name}': "
            f"{'PASS' if self.passed else 'FAIL'}",
            f"  Level 1 STRUCTURAL: {_count_severities(self.level1_findings)}",
            f"  Level 2 INVARIANT (A): "
            f"{self.level2_a_invariants.violation_count if self.level2_a_invariants else 0} viol",
            f"  Level 2 INVARIANT (B): "
            f"{self.level2_b_invariants.violation_count if self.level2_b_invariants else 0} viol",
            f"  Level 3 TRAJECTORY:  {_count_severities(self.level3_findings)}",
            f"  Level 4 PHENOTYPE:   {_count_severities(self.level4_findings)}",
        ]
        for f in self.all_findings:
            if f.severity != "ok":
                lines.append(f"    L{f.level} {f.severity.upper()}: {f.name} — {f.message}")
        return "\n".join(lines)


def _count_severities(findings: list[LevelFinding]) -> str:
    n_ok = sum(1 for f in findings if f.severity == "ok")
    n_warn = sum(1 for f in findings if f.severity == "warn")
    n_fail = sum(1 for f in findings if f.severity == "fail")
    return f"{n_ok} ok, {n_warn} warn, {n_fail} fail"


# ---------------------------------------------------------------------------
# Level 1 — structural
# ---------------------------------------------------------------------------


def _navigate(traj: TrajectoryDict, path: PortPath):
    node = traj
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node


def diff_structural(traj_a: TrajectoryDict, traj_b: TrajectoryDict,
                    spec: DiffSpec) -> list[LevelFinding]:
    findings: list[LevelFinding] = []

    # 1a. Required paths present in both
    if spec.structural_required_paths:
        for path in spec.structural_required_paths:
            in_a = _navigate(traj_a, path) is not None
            in_b = _navigate(traj_b, path) is not None
            if in_a and in_b:
                findings.append(LevelFinding(
                    1, "required_path_present",
                    "ok", f"{path} present in both",
                ))
            else:
                findings.append(LevelFinding(
                    1, "required_path_present",
                    "fail",
                    f"{path} missing: A={in_a}, B={in_b}",
                    {"path": list(path), "in_a": in_a, "in_b": in_b},
                ))

    # 1b. All comparable variables present in both
    for path in spec.comparable_variables:
        in_a = _navigate(traj_a, path) is not None
        in_b = _navigate(traj_b, path) is not None
        if not (in_a and in_b):
            findings.append(LevelFinding(
                1, "comparable_path_present",
                "fail",
                f"{path} declared comparable but missing: A={in_a}, B={in_b}",
                {"path": list(path)},
            ))

    # 1c. Trajectory length parity (engines must report identical step count)
    a_len = len(traj_a.get("time", []))
    b_len = len(traj_b.get("time", []))
    if a_len != b_len:
        findings.append(LevelFinding(
            1, "timeseries_length",
            "fail",
            f"Length mismatch A={a_len}, B={b_len}",
            {"a_len": a_len, "b_len": b_len},
        ))
    else:
        findings.append(LevelFinding(
            1, "timeseries_length", "ok",
            f"Both have {a_len} timesteps",
        ))

    # 1d. Kind declaration consistency (warn-level: documentation hygiene)
    if spec.structural_required_kinds:
        for path, kind in spec.structural_required_kinds.items():
            decl = spec.comparable_variables.get(path, {}).get("kind")
            if decl is not None and decl != kind:
                findings.append(LevelFinding(
                    1, "kind_consistency", "warn",
                    f"{path} declared kind '{decl}' != required '{kind}'",
                    {"path": list(path), "decl": decl, "required": kind},
                ))

    return findings


# ---------------------------------------------------------------------------
# Level 2 — invariants (per-simulation)
# ---------------------------------------------------------------------------


def build_default_invariant_suite(
    name: str, traj: TrajectoryDict, spec: DiffSpec,
) -> InvariantSuite:
    """Construct a default A7 suite from the comparable-variable declarations.

    Picks invariants based on each variable's declared ``kind``:

      * concentration — non-negativity
      * signal        — bounded [0, 1.05]   (matches A6 §2.4 wording)
      * count         — non-negativity + integrality
    """
    suite = InvariantSuite(name=name)

    times = np.asarray(traj.get("time", []), dtype=np.float64)
    by_kind: dict[str, dict[str, np.ndarray]] = {
        "concentration": {}, "signal": {}, "count": {},
    }
    for path, decl in spec.comparable_variables.items():
        kind = decl.get("kind", "concentration")
        node = _navigate(traj, path)
        if node is None:
            continue
        var_label = ".".join(path)
        by_kind.setdefault(kind, {})[var_label] = np.asarray(node, dtype=np.float64)

    if by_kind["concentration"]:
        vals = by_kind["concentration"]
        suite.add(lambda v=vals: check_non_negativity(times=times, values=v))
    if by_kind["signal"]:
        vals = by_kind["signal"]
        bounds = {k: (0.0, 1.05) for k in vals}
        suite.add(lambda v=vals, b=bounds: check_bounded(
            times=times, values=v, bounds=b, name="signal_bounds",
        ))
    if by_kind["count"]:
        vals = by_kind["count"]
        suite.add(lambda v=vals: check_non_negativity(
            times=times, values=v, name="count_non_negativity",
        ))
        suite.add(lambda v=vals: check_count_integrality(
            times=times, values=v,
        ))
    return suite


# ---------------------------------------------------------------------------
# Level 3 — trajectory norm
# ---------------------------------------------------------------------------


def diff_trajectory(traj_a: TrajectoryDict, traj_b: TrajectoryDict,
                    spec: DiffSpec) -> list[LevelFinding]:
    findings: list[LevelFinding] = []
    for path, decl in spec.comparable_variables.items():
        a = _navigate(traj_a, path)
        b = _navigate(traj_b, path)
        if a is None or b is None:
            continue
        a_arr = np.asarray(a, dtype=np.float64)
        b_arr = np.asarray(b, dtype=np.float64)
        if a_arr.shape != b_arr.shape:
            findings.append(LevelFinding(
                3, "shape_mismatch", "fail",
                f"{path}: shapes {a_arr.shape} vs {b_arr.shape}",
                {"path": list(path)},
            ))
            continue
        diff = a_arr - b_arr
        l_inf_abs = float(np.max(np.abs(diff)))
        ref_scale = max(float(np.max(np.abs(b_arr))), 1e-12)
        l_inf_rel = l_inf_abs / ref_scale
        l2_abs = float(np.sqrt(np.mean(diff ** 2)))
        abs_tol = float(decl.get("abs", 1e-3))
        rel_tol = float(decl.get("rel", 1e-2))
        ok_abs = l_inf_abs <= abs_tol
        ok_rel = l_inf_rel <= rel_tol
        severity = "ok" if (ok_abs or ok_rel) else "fail"
        findings.append(LevelFinding(
            3, "trajectory_norm",
            severity,
            f"{path}: L_inf_abs={l_inf_abs:.3e} (tol {abs_tol}), "
            f"L_inf_rel={l_inf_rel:.3e} (tol {rel_tol})",
            {
                "path": list(path),
                "L_inf_abs": l_inf_abs,
                "L_inf_rel": l_inf_rel,
                "L2_abs": l2_abs,
                "abs_tol": abs_tol,
                "rel_tol": rel_tol,
                "ok_abs": ok_abs,
                "ok_rel": ok_rel,
            },
        ))
    return findings


# ---------------------------------------------------------------------------
# Level 4 — phenotype
# ---------------------------------------------------------------------------


def compute_default_phenotypes(traj: TrajectoryDict) -> dict[str, float]:
    """Built-in phenotypes derivable from a Chassagnole+Vilar trajectory.

    Custom whole-cell phenotypes (Karr's 28) are added by callers via
    extra phenotype functions.
    """
    out: dict[str, float] = {}
    cglcex = _navigate(traj, ("metabolites", "cglcex"))
    if cglcex is not None:
        arr = np.asarray(cglcex, dtype=np.float64)
        out["cglcex_final"] = float(arr[-1])
        out["cglcex_initial"] = float(arr[0])
    f_met = _navigate(traj, ("signal", "f_met"))
    if f_met is not None:
        arr = np.asarray(f_met, dtype=np.float64)
        out["f_met_final"] = float(arr[-1])
        out["f_met_min"] = float(arr.min())
    gene = traj.get("gene_state")
    if isinstance(gene, dict):
        for s, v in gene.items():
            arr = np.asarray(v, dtype=np.float64)
            out[f"gene_final_{s}"] = float(arr[-1])
    return out


def diff_phenotypes(
    traj_a: TrajectoryDict, traj_b: TrajectoryDict, spec: DiffSpec,
    phenotype_fn: Callable[[TrajectoryDict], dict[str, float]] | None = None,
    abs_tol: float = 1e-3, rel_tol: float = 0.5,
) -> list[LevelFinding]:
    """Level-4 lossy diff of scalar phenotype values.

    ``rel_tol`` is intentionally loose by default (0.5) — phenotype
    diffs across engines are expected to differ at the order-of-magnitude
    level for stochastic counts at low expression. Callers tighten for
    deterministic phenotypes.
    """
    fn = phenotype_fn or compute_default_phenotypes
    pa = fn(traj_a)
    pb = fn(traj_b)
    findings: list[LevelFinding] = []
    keys = sorted(set(pa) | set(pb))
    keys = [k for k in keys
            if not spec.scalar_phenotypes or k in spec.scalar_phenotypes]
    for k in keys:
        va = pa.get(k)
        vb = pb.get(k)
        if va is None or vb is None:
            findings.append(LevelFinding(
                4, "phenotype_missing", "warn",
                f"{k}: present in only one engine (A={va}, B={vb})",
            ))
            continue
        d = abs(va - vb)
        scale = max(abs(vb), 1e-12)
        rel = d / scale
        ok = d <= abs_tol or rel <= rel_tol
        findings.append(LevelFinding(
            4, "phenotype",
            "ok" if ok else "fail",
            f"{k}: A={va:.4g} B={vb:.4g} abs_diff={d:.3e} rel={rel:.3f}",
            {"phenotype": k, "a": va, "b": vb, "abs_diff": d, "rel_diff": rel},
        ))
    return findings


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def run_diff(
    traj_a: TrajectoryDict, traj_b: TrajectoryDict, *,
    spec: DiffSpec,
    invariant_suite_a: InvariantSuite | None = None,
    invariant_suite_b: InvariantSuite | None = None,
    phenotype_fn: Callable[[TrajectoryDict], dict[str, float]] | None = None,
    phenotype_abs_tol: float = 1e-3,
    phenotype_rel_tol: float = 0.5,
) -> DiffReport:
    """Run all four diff levels and return the aggregated report."""
    report = DiffReport(spec=spec)
    report.level1_findings = diff_structural(traj_a, traj_b, spec)
    suite_a = invariant_suite_a or build_default_invariant_suite(
        f"{spec.engine_a_name}_invariants", traj_a, spec,
    )
    suite_b = invariant_suite_b or build_default_invariant_suite(
        f"{spec.engine_b_name}_invariants", traj_b, spec,
    )
    report.level2_a_invariants = suite_a.run()
    report.level2_b_invariants = suite_b.run()
    report.level3_findings = diff_trajectory(traj_a, traj_b, spec)
    report.level4_findings = diff_phenotypes(
        traj_a, traj_b, spec, phenotype_fn=phenotype_fn,
        abs_tol=phenotype_abs_tol, rel_tol=phenotype_rel_tol,
    )
    return report
