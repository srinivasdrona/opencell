"""A4-followthrough: ingest real Karr parameters from parameters.json
into the A3 provenance store, using the unit map recovered from .m
source files. Demonstrates the M-phase ingestion pattern end-to-end.

Output: artifacts/karr_a4f_provenance.jsonl with N events, classified
by units-recovery confidence (verified vs inferred vs UNVERIFIED).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from opencell.provenance import ProvenanceStore


PARAMETERS_JSON = Path("data/karr_fixtures/parameters.json")
UNIT_MAP_YAML   = Path("data/karr_fixtures/karr_parameters_unit_map.yaml")
STORE_PATH      = Path("artifacts/karr_a4f_provenance.jsonl")
SOURCE_URL      = "https://github.com/CovertLab/WholeCell/blob/master/data/parameters.json"


def main() -> int:
    raw_blob = PARAMETERS_JSON.read_bytes()
    json_sha = hashlib.sha256(raw_blob).hexdigest()
    raw = json.loads(raw_blob)

    unit_map = yaml.safe_load(UNIT_MAP_YAML.read_text())

    if STORE_PATH.exists():
        STORE_PATH.unlink()
    store = ProvenanceStore(STORE_PATH)

    counts = {"verified": 0, "inferred": 0, "unverified": 0}

    # Walk states section
    for category in ("states", "processes"):
        for class_name, params_block in unit_map.get(category, {}).items():
            for param_name, spec in params_block.items():
                value = raw[category][class_name].get(param_name)
                if value is None:
                    print(f"  SKIP missing: {category}.{class_name}.{param_name}")
                    continue
                unit = spec["unit"]
                verified = spec.get("verified", True)  # only Time entries omit it
                source_note = spec.get("source", "")
                if not verified:
                    bucket = "unverified"
                    unit_str = unit + " [UNVERIFIED]"
                elif "UNVERIFIED" in source_note or "inferred" in source_note.lower():
                    bucket = "inferred"
                    unit_str = unit
                else:
                    bucket = "verified"
                    unit_str = unit
                counts[bucket] += 1

                store.record_measured(
                    param_name=f"karr2012.{category}.{class_name}.{param_name}",
                    value=value,
                    unit=unit_str,
                    source_kind="model_artifact",
                    source_ref=f"{SOURCE_URL}#sha256:{json_sha}",
                    scope={
                        "organism": "Mycoplasma genitalium G37",
                        "model": "Karr2012",
                        category[:-1]: class_name,  # state= or process=
                    },
                    transformation_lineage=[
                        f"raw value from data/parameters.json[{category}][{class_name}][{param_name}]",
                        f"unit recovered: {source_note[:200]}",
                    ],
                    recorded_by="agent:A4_followthrough",
                    notes=f"Confidence bucket: {bucket}",
                )

    events = store.all()
    print(f"\n=== A4-followthrough ingestion ===")
    print(f"events written:     {len(events)}")
    print(f"  verified:         {counts['verified']}  (units recovered from .m source or universal convention with cross-check)")
    print(f"  inferred:         {counts['inferred']}  (unit follows universal convention but not yet cross-checked)")
    print(f"  UNVERIFIED:       {counts['unverified']}  (unit guessed; must be reviewed before kinetic use)")
    print(f"\nstore path:         {STORE_PATH}")
    print(f"first event id:     {events[0].event_id}")
    print(f"last event id:      {events[-1].event_id}")

    # Sanity check the cross-check we baked into the YAML
    growth = raw["states"]["MetabolicReaction"]["meanInitialGrowthRate"]
    cyc = raw["states"]["Time"]["cellCycleLength"]
    import math
    expected_cyc = math.log(2) / growth
    rel_err = abs(expected_cyc - cyc) / cyc
    print(f"\ncross-check: ln(2)/meanInitialGrowthRate = {expected_cyc:.1f} s vs cellCycleLength = {cyc:.1f} s  (rel err {rel_err*100:.2f}%)")
    if rel_err < 0.01:
        print("PASS — Time.cellCycleLength and MetabolicReaction.meanInitialGrowthRate are mutually consistent.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
