"""DNADamage stimulus-conditioned fixed-window cohort planner/preflight.

This module never launches MATLAB. It reads the frozen, source-backed
DNADamage stress spec and builds two condition-specific 50-seed x 20-tick
fixed-window extraction plans:

* ``uvb_mechanism``
* ``gamma_mechanism``

Each condition gets its own parent directory under
``data/m1_sources/karr_native/dnadamage_stimulus_cohort/`` so traces from
different stimuli cannot collide on path identity alone, while the leaf
event-window directory name stays the canonical
``per_process_traces_v2_event_s{seed}`` shape the loader already recognizes.

The actual fixed-window planning/validation/atomic-regeneration semantics are
delegated to ``scripts.l2_event.launcher``. This module's added value is the
DNADamage-specific authoritative contract: frozen UVB/gamma doses, required
20-tick window, 50-seed cohort, condition-specific output roots, and the
exact metadata identity payload each trace must persist to be reusable.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import launcher  # noqa: E402

SPEC_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "stress"
    / "DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json"
)

PROCESS_NAME = "DNADamage"
CONDITION_ROOT_DIRNAME = "dnadamage_stimulus_cohort"
CONDITION_NAMES = ("uvb_mechanism", "gamma_mechanism")
REQUIRED_OBSERVABLES = ("chromosome", "substrates")
IDENTITY_SCHEMA_VERSION = 1
# Frozen stress-spec RNG labels: process seed ids 2000..2049. The MATLAB
# extractor exposes a single seed surface (`rng_seed`) rather than the OC-only
# dual-stream canary schedule, so these labels are used directly as the 50
# extraction seed ids for the real Karr cohort.
DEFAULT_SEED_IDS = tuple(range(2000, 2050))


def load_stimulus_spec() -> dict[str, Any]:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _support_n_seeds(spec: dict[str, Any]) -> int:
    return int(spec["support_design"]["n_seeds"])


def _support_m_ticks(spec: dict[str, Any]) -> int:
    return int(spec["support_design"]["m_ticks"])


def condition_output_root(
    condition_name: str,
    *,
    karr_native_root: Path = launcher.KARR_NATIVE_ROOT,
) -> Path:
    return karr_native_root / CONDITION_ROOT_DIRNAME / condition_name


def condition_output_path_pattern(
    condition_name: str,
    *,
    karr_native_root: Path = launcher.KARR_NATIVE_ROOT,
) -> str:
    root = condition_output_root(condition_name, karr_native_root=karr_native_root)
    filename = f"{PROCESS_NAME}_{_support_m_ticks(load_stimulus_spec())}ticks.mat"
    return str(root / "per_process_traces_v2_event_s{seed}" / filename)


def condition_override_map(spec: dict[str, Any], condition_name: str) -> dict[str, float]:
    condition = spec["conditions"][condition_name]
    return {str(condition["radiation_wid"]): float(condition["injected_radiation_value"])}


def condition_identity_payload(spec: dict[str, Any], condition_name: str) -> dict[str, Any]:
    condition = spec["conditions"][condition_name]
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "process": PROCESS_NAME,
        "condition": condition_name,
        "window_contract": "fixed",
        "tick_offset": 0,
        "n_ticks": _support_m_ticks(spec),
        "required_n_seeds": _support_n_seeds(spec),
        "radiation_wid": condition["radiation_wid"],
        "injected_radiation_value": float(condition["injected_radiation_value"]),
        "allowed_chromosome_fields": list(condition["allowed_chromosome_fields"]),
        "spec_ref": str(SPEC_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
    }


def condition_identity_json(spec: dict[str, Any], condition_name: str) -> str:
    return json.dumps(condition_identity_payload(spec, condition_name), sort_keys=True, separators=(",", ":"))


def fixed_window_spec_for_seed(
    condition_name: str,
    seed: int,
    *,
    spec: dict[str, Any] | None = None,
) -> launcher.FixedWindowSpec:
    resolved_spec = load_stimulus_spec() if spec is None else spec
    identity_json = condition_identity_json(resolved_spec, condition_name)
    return launcher.FixedWindowSpec(
        process=PROCESS_NAME,
        seed=int(seed),
        tick_offset=0,
        required_observables=REQUIRED_OBSERVABLES,
        n_ticks=_support_m_ticks(resolved_spec),
        extraction_identity_json=identity_json,
        matlab_extraction_opts={
            "condition_label": condition_name,
            "metadata_identity_json": identity_json,
            "per_process_substrate_overrides": {
                PROCESS_NAME: condition_override_map(resolved_spec, condition_name),
            },
        },
    )


def _count_actions(plan_payload: dict[str, Any]) -> dict[str, int]:
    counts = {"skip_valid": 0, "generate_missing": 0, "regenerate_invalid": 0}
    for decision in plan_payload["decisions"]:
        action = decision["action"]
        counts[action] = counts.get(action, 0) + 1
    return counts


def plan_conditioned_cohort(
    condition_name: str,
    *,
    seed_ids: tuple[int, ...] = DEFAULT_SEED_IDS,
    karr_native_root: Path = launcher.KARR_NATIVE_ROOT,
    validate_existing: bool = True,
) -> dict[str, Any]:
    spec = load_stimulus_spec()
    specs = [fixed_window_spec_for_seed(condition_name, seed, spec=spec) for seed in seed_ids]
    output_root = condition_output_root(condition_name, karr_native_root=karr_native_root)
    plan = launcher.plan_event_window_extraction(
        specs,
        karr_native_root=output_root,
        validate_existing=validate_existing,
    )
    payload = plan.to_dict()
    condition = spec["conditions"][condition_name]
    return {
        "condition": condition_name,
        "radiation_wid": condition["radiation_wid"],
        "injected_radiation_value": float(condition["injected_radiation_value"]),
        "allowed_chromosome_fields": list(condition["allowed_chromosome_fields"]),
        "output_root": str(output_root),
        "output_path_pattern": condition_output_path_pattern(condition_name, karr_native_root=karr_native_root),
        "identity_payload": condition_identity_payload(spec, condition_name),
        "plan": payload,
        "action_counts": _count_actions(payload),
    }


def build_cohort_plan(
    *,
    seed_ids: tuple[int, ...] = DEFAULT_SEED_IDS,
    karr_native_root: Path = launcher.KARR_NATIVE_ROOT,
    validate_existing: bool = True,
) -> dict[str, Any]:
    spec = load_stimulus_spec()
    conditions = [
        plan_conditioned_cohort(
            condition_name,
            seed_ids=seed_ids,
            karr_native_root=karr_native_root,
            validate_existing=validate_existing,
        )
        for condition_name in CONDITION_NAMES
    ]
    total_jobs = sum(len(condition["plan"]["jobs"]) for condition in conditions)
    total_decisions = sum(len(condition["plan"]["decisions"]) for condition in conditions)
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "process": PROCESS_NAME,
        "spec_ref": str(SPEC_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "preflight_status": "READY_FOR_MATLAB",
        "required_n_seeds": _support_n_seeds(spec),
        "required_m_ticks": _support_m_ticks(spec),
        "planned_seed_ids": list(seed_ids),
        "required_observables": list(REQUIRED_OBSERVABLES),
        "condition_root_dirname": CONDITION_ROOT_DIRNAME,
        "validate_existing": bool(validate_existing),
        "total_decisions": total_decisions,
        "total_jobs": total_jobs,
        "conditions": conditions,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Write the JSON cohort preflight/plan to this path.")
    parser.add_argument("--no-validate", action="store_true", help="Existence-only skip mode (debug only).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    payload = build_cohort_plan(validate_existing=not args.no_validate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[dna_damage_stimulus_cohort] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
