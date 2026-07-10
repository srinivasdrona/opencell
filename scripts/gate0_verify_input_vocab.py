"""Gate 0 — input-vocabulary fidelity: Karr source-of-truth vs fixture vs frozen spec.

The frozen input spec (`data/karr_input_spec/*.yaml`) is DERIVED from the extracted
per-process fixtures (`data/karr_fixtures/per_process/*_flat.mat`). Gate 1 proves
spec == fixture, but that is near-tautological — it cannot catch an omission made by
the fixture EXTRACTION itself. Gate 0 closes that gap: it compares the fixtures (and
hence the spec) against an INDEPENDENT, authoritative source-of-truth dumped live
from Karr's fitted simulation.

The authoritative dump `data/karr_input_spec/_gate0_source_truth.json` is produced by
`scripts/matlab/gate0_dump_process_inputs.m` (MATLAB): it bootstraps the fitted Karr
simulation, runs each process's real `initializeConstants`, and records the RESOLVED
`substrate/enzyme/stimuli WholeCellModelIDs`. That dump comes from `Simulation_fitted.mat`,
a DIFFERENT Karr artifact than the `src_test` saved instances the fixtures came from —
so agreement is a genuine cross-source check, not a tautology.

This script (no MATLAB needed once the dump is committed) verifies, per process and per
vocabulary category, that the three agree exactly (ordered WID lists):

    source_truth  ==  fixture  ==  frozen_spec

Exit 0 = PASS (or clean SKIP if the dump is absent); exit 1 = any divergence.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml
from scipy.io import loadmat

_REPO = Path(__file__).resolve().parents[1]
_SRC_TRUTH = _REPO / "data" / "karr_input_spec" / "_gate0_source_truth.json"
_FIXTURE_DIR = _REPO / "data" / "karr_fixtures" / "per_process"
_SPEC_DIR = _REPO / "data" / "karr_input_spec"

_CATS = {
    "substrates": "substrateWholeCellModelIDs",
    "enzymes": "enzymeWholeCellModelIDs",
    "stimuli": "stimuliWholeCellModelIDs",
}


def _fixture_vocab(proc: str) -> dict[str, list[str]]:
    fx = loadmat(
        _FIXTURE_DIR / f"{proc}_flat.mat", squeeze_me=True, struct_as_record=False
    )["data"].fixture

    def g(field: str) -> list[str]:
        v = getattr(fx, field, [])
        arr = np.atleast_1d(v)
        return [str(x) for x in arr] if arr.size else []

    return {cat: g(field) for cat, field in _CATS.items()}


def _spec_vocab(proc: str) -> dict[str, list[str]]:
    voc = yaml.safe_load((_SPEC_DIR / f"{proc}.yaml").read_text()).get("vocabularies", {})
    return {cat: list(voc.get(field, [])) for cat, field in _CATS.items()}


def main() -> int:
    if not _SRC_TRUTH.exists():
        print(
            f"GATE 0: SKIPPED — source-of-truth dump absent at "
            f"{_SRC_TRUTH.relative_to(_REPO)}. Regenerate with MATLAB: "
            "gate0_dump_process_inputs.m"
        )
        return 0

    src = json.loads(_SRC_TRUTH.read_text())
    src_by = {p["name"]: p for p in src["processes"]}

    findings: list[str] = []
    checked = 0
    for proc in sorted(src_by):
        fixture_file = _FIXTURE_DIR / f"{proc}_flat.mat"
        spec_file = _SPEC_DIR / f"{proc}.yaml"
        if not fixture_file.exists() or not spec_file.exists():
            findings.append(f"{proc}: missing fixture or spec file")
            continue
        s = src_by[proc]
        fx = _fixture_vocab(proc)
        sp = _spec_vocab(proc)
        for cat, field in _CATS.items():
            sv = [str(x) for x in s.get(field, [])]
            fv = fx[cat]
            pv = sp[cat]
            checked += 1
            if sv != fv:
                miss = sorted(set(sv) - set(fv))
                extra = sorted(set(fv) - set(sv))
                same_set = set(sv) == set(fv)
                detail = "ORDER-ONLY" if same_set else f"in-source-not-fixture={miss} in-fixture-not-source={extra}"
                findings.append(
                    f"{proc}.{cat}: SOURCE!=FIXTURE (src={len(sv)} fix={len(fv)}) {detail}"
                )
            if fv != pv:
                findings.append(
                    f"{proc}.{cat}: FIXTURE!=SPEC (fix={len(fv)} spec={len(pv)})"
                )

    if findings:
        print(f"GATE 0 (input vocab): FAIL — {len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        return 1

    print(
        f"GATE 0 (input vocab): PASS — {len(src_by)} processes × {len(_CATS)} categories "
        f"({checked} checks); source_truth == fixture == frozen_spec, exact ordered WID lists."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
