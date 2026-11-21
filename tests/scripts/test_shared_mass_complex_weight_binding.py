"""ProteinComplex row MW is a required domain input, not an unused import.

The source-proven existing particle guard requires the future-correct mass
mapping to consume this fixture and bind its exact bytes before use. Existing
cold/constructor capture controls remain unchanged.
"""

from pathlib import Path

import test_shared_mass_input_binding as capture

ROOT = capture.ROOT
full_capture = capture.full_capture

COMPLEX_WEIGHT_SOURCE = "data/karr_fixtures/per_process/ProteinComplex_flat.mat"


def test_physical_complex_weight_fixture_is_consumed_and_bound(full_capture, record_property):
    actual = full_capture["actual_parameter_reads"].get(COMPLEX_WEIGHT_SOURCE)
    phases = [] if actual is None else actual["phases"]
    record_property("required_weight_source", COMPLEX_WEIGHT_SOURCE)
    record_property("actual_weight_read_phases", ",".join(phases))
    assert any(phase.startswith(("mass_", "live_csv_")) for phase in phases), (
        "Complete physical complex mapping has not consumed ProteinComplex row MW "
        "in the actual mass reader constructors; cold/process-only reads do not suffice"
    )
    for process, sources in full_capture["captured_before_constructor"].items():
        bound = {
            Path(item["path"]).resolve().relative_to(ROOT).as_posix(): item
            for item in sources
        }
        assert COMPLEX_WEIGHT_SOURCE in bound, f"{process} omitted required complex weight input"
        assert bound[COMPLEX_WEIGHT_SOURCE]["sha256"] == actual["sha256"]
