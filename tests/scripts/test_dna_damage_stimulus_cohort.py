"""DNADamage stimulus-conditioned cohort planner tests.

These cover the MATLAB-free preflight/preregistration surface in
``scripts/l2_event/dna_damage_stimulus_cohort.py``:

* authoritative 50-seed x 20-tick UVB/gamma cohort planning
* condition-specific output roots with canonical event-leaf names
* exact metadata identity binding for reuse validation
* CLI JSON emission without launching MATLAB
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import dna_damage_stimulus_cohort as cohort  # noqa: E402


def test_fixed_window_spec_for_seed_binds_condition_identity_and_overrides() -> None:
    spec = cohort.load_stimulus_spec()
    window = cohort.fixed_window_spec_for_seed("uvb_mechanism", 2000, spec=spec)
    identity = cohort.condition_identity_json(spec, "uvb_mechanism")

    assert window.process == "DNADamage"
    assert window.seed == 2000
    assert window.tick_offset == 0
    assert window.n_ticks == 20
    assert window.required_observables == ("chromosome", "substrates")
    assert window.extraction_identity_json == identity
    assert window.matlab_extraction_opts == {
        "condition_label": "uvb_mechanism",
        "metadata_identity_json": identity,
        "per_process_substrate_overrides": {
            "DNADamage": {
                "UVB_radiation": spec["conditions"]["uvb_mechanism"]["injected_radiation_value"],
            }
        },
    }


def test_build_cohort_plan_preregisters_two_condition_fifty_seed_cohort(tmp_path: Path) -> None:
    payload = cohort.build_cohort_plan(karr_native_root=tmp_path, validate_existing=True)

    assert payload["preflight_status"] == "READY_FOR_MATLAB"
    assert payload["process"] == "DNADamage"
    assert payload["required_n_seeds"] == 50
    assert payload["required_m_ticks"] == 20
    assert payload["planned_seed_ids"] == list(range(2000, 2050))
    assert payload["required_observables"] == ["chromosome", "substrates"]
    assert payload["condition_root_dirname"] == "dnadamage_stimulus_cohort"
    assert payload["validate_existing"] is True
    assert payload["total_jobs"] == 100
    assert payload["total_decisions"] == 100

    conditions = {entry["condition"]: entry for entry in payload["conditions"]}
    assert set(conditions) == {"uvb_mechanism", "gamma_mechanism"}

    uvb = conditions["uvb_mechanism"]
    gamma = conditions["gamma_mechanism"]

    assert uvb["output_root"] == str(tmp_path / "dnadamage_stimulus_cohort" / "uvb_mechanism")
    assert gamma["output_root"] == str(tmp_path / "dnadamage_stimulus_cohort" / "gamma_mechanism")
    assert uvb["output_path_pattern"].endswith(
        "dnadamage_stimulus_cohort/uvb_mechanism/per_process_traces_v2_event_s{seed}/DNADamage_20ticks.mat"
    )
    assert gamma["output_path_pattern"].endswith(
        "dnadamage_stimulus_cohort/gamma_mechanism/per_process_traces_v2_event_s{seed}/DNADamage_20ticks.mat"
    )
    assert uvb["plan"]["contract_version"] == "M4"
    assert gamma["plan"]["contract_version"] == "M4"
    assert {row["window_contract"] for row in uvb["plan"]["input_specs"]} == {"fixed"}
    assert {row["window_contract"] for row in gamma["plan"]["input_specs"]} == {"fixed"}
    assert uvb["action_counts"] == {"skip_valid": 0, "generate_missing": 50, "regenerate_invalid": 0}
    assert gamma["action_counts"] == {"skip_valid": 0, "generate_missing": 50, "regenerate_invalid": 0}
    assert len(uvb["plan"]["jobs"]) == 50
    assert len(gamma["plan"]["jobs"]) == 50
    assert uvb["identity_payload"]["condition"] == "uvb_mechanism"
    assert gamma["identity_payload"]["condition"] == "gamma_mechanism"
    assert uvb["identity_payload"]["required_n_seeds"] == 50
    assert gamma["identity_payload"]["required_n_seeds"] == 50


def test_cli_writes_preflight_json(tmp_path: Path, monkeypatch) -> None:
    expected = {"preflight_status": "READY_FOR_MATLAB", "conditions": []}
    monkeypatch.setattr(cohort, "build_cohort_plan", lambda validate_existing=True: expected)

    out_path = tmp_path / "cohort_plan.json"
    rc = cohort.main(["--out", str(out_path)])

    assert rc == 0
    assert json.loads(out_path.read_text(encoding="utf-8")) == expected
