"""Freeze actual cold-import and live mass-constructor input bindings.

Not an oracle/statistical gate or a historical hash re-attestation. A cold
registered producer import really requires mass/observer code; parameter
fixtures are distinguished from that import and must be bound when the actual
shared mass readers construct/use their mapping. Current omissions are RED.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COLD_CODE = ("opencell/analysis/cell_mass.py", "opencell/vivarium/karr_observability_step.py")
OWNER_CODE = ("opencell/vivarium/protein_state.py", "opencell/vivarium/karr_protein_activation.py")
FACTORIES = {
    "RNAProcessing": "_rna_processing_process",
    "RNAModification": "_rna_modification_process",
    "ProteinTranslocation": "_protein_translocation_process",
    "ProteinProcessingII": "_protein_processing_ii_process",
    "ProteinModification": "_protein_modification_process",
}


def _probe(process, output, blocked=None):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests/vivarium"))
    phase = "cold_import"
    executed = set()
    executed_sha = {}
    consumed = {}
    calls = set()
    called_code = {}
    busy = False

    def relative(value):
        if not isinstance(value, (str, bytes, Path)):
            return None
        path = Path(value.decode() if isinstance(value, bytes) else value).resolve()
        return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else None

    def audit(event, args):
        nonlocal busy
        if busy:
            return
        if event == "exec":
            name = relative(args[0].co_filename)
            if name and name.endswith(".py") and (ROOT / name).is_file():
                busy = True
                try:
                    executed_sha[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                finally:
                    busy = False
            if name in COLD_CODE:
                if blocked == name:
                    raise RuntimeError("blocked required cold source: " + name)
                executed.add(name)
        if event == "open" and phase not in {"capture_before", "done"}:
            name = relative(args[0])
            if name and name.startswith("data/karr_fixtures/") and Path(name).suffix in {".mat", ".npz", ".json"}:
                busy = True
                try:
                    digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                finally:
                    busy = False
                item = consumed.setdefault(name, {"sha256": digest, "phases": []})
                assert item["sha256"] == digest, "source changed while being consumed"
                if phase not in item["phases"]:
                    item["phases"].append(phase)

    def profile(frame, event, arg):
        if event == "call":
            filename = frame.f_code.co_filename
            if filename.endswith(("cell_mass.py", "karr_observability_step.py", "run_chassis_v6_32400t.py")):
                calls.add((phase, frame.f_code.co_name))
            if phase.startswith(("mass_", "live_csv_", "registered_constructor:")):
                prefix = str(ROOT) + "/"
                if filename.startswith(prefix):
                    name = filename[len(prefix):]
                    if name.startswith(("opencell/", "tests/vivarium/")):
                        called_code.setdefault(phase, set()).add(name)

    sys.addaudithook(audit)
    sys.setprofile(profile)
    try:
        import _l2_2_design_a_runner_helpers as registered

        captures = {}
        producers = {}
        for name in (FACTORIES if process == "all" else (process,)):
            phase = "capture_before"
            captures[name] = registered.capture_runtime_inputs(name)
            phase = "registered_constructor:" + name
            factory = getattr(registered, FACTORIES[name])
            producer = getattr(factory, "__wrapped__", factory)(0)
            producers[name] = {"class": type(producer).__name__, "module": type(producer).__module__}
        phase = "mass_observer_constructor"
        from opencell.vivarium.karr_observability_step import KarrObservabilityStep

        observer = KarrObservabilityStep()
        observer.next_update(1.0, {})
        phase = "mass_helper"
        from opencell.analysis.cell_mass import compute_cell_mass

        models = (observer.m1_model, observer.m2_model, observer.m3_model)
        assert compute_cell_mass({}, *models).total_g == 0
        phase = "live_csv_constructor"
        from scripts.run_chassis_v6_32400t import MassEstimator

        assert MassEstimator.build(*models).dry_mass_g({}) == 0
        result = {
            "process": process, "producers": producers,
            "executed_cold_mass_code": sorted(executed),
            "actual_executed_source_sha256": executed_sha,
            "actual_parameter_reads": consumed, "actual_calls": sorted(calls),
            "actual_called_source_files": {phase: sorted(files) for phase, files in called_code.items()},
            "owner_code_used_by_projection": [
                Path(sys.modules[name].__file__).resolve().relative_to(ROOT).as_posix()
                for name in ("opencell.vivarium.protein_state", "opencell.vivarium.karr_protein_activation")
            ],
            "captured_before_constructor": captures,
        }
    except RuntimeError as exc:
        if not blocked or "blocked required cold source:" not in str(exc):
            raise
        result = {"blocked": blocked, "constructor_completed": False, "error": str(exc)}
    finally:
        phase = "done"
        sys.setprofile(None)
    Path(output).write_text(json.dumps(result, indent=2) + "\n")


def _invoke(process, tmp_path, blocked=None):
    output = tmp_path / f"{process}_{Path(blocked).stem if blocked else 'normal'}.json"
    args = [sys.executable, str(Path(__file__).relative_to(ROOT)),
            "--probe", process, str(output.relative_to(ROOT))]
    if blocked:
        args.append(blocked)
    subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(output.read_text())


def _required(report):
    # Import-only execution is not called a parameter read. Mass-constructor
    # files are required because this finite shared boundary actually uses them.
    return set(report["executed_cold_mass_code"]) | set(report["owner_code_used_by_projection"]) | {
        name for name, item in report["actual_parameter_reads"].items()
        if any(phase.startswith(("cold_import", "mass_", "live_csv_")) for phase in item["phases"])
    } | {name for phase, files in report["actual_called_source_files"].items()
         if phase.startswith(("mass_", "live_csv_", "registered_constructor:" + report["process"]))
         for name in files if name != "scripts/run_chassis_v6_32400t.py"}


@pytest.fixture(scope="module")
def full_capture(tmp_path_factory):
    # One cold program derives and joins all five actual constructors. The
    # common mass-reader parameter loads are measured once, not fanned out.
    return _invoke("all", tmp_path_factory.mktemp("mass_binding_capture"))


def _require_bound(report, sources):
    bound = {Path(item["path"]).resolve().relative_to(ROOT).as_posix(): item for item in sources}
    missing = sorted(_required(report) - set(bound))
    assert not missing, "Actual shared-mass consumed inputs absent from capture: " + ", ".join(missing)
    for name in _required(report) & set(report["actual_parameter_reads"]):
        assert bound[name]["sha256"] == report["actual_parameter_reads"][name]["sha256"], (
            "Captured parameter bytes differ from actual consumption: " + name
        )
    for name in _required(report) & set(report["actual_executed_source_sha256"]):
        assert bound[name]["sha256"] == report["actual_executed_source_sha256"][name], (
            "Captured source bytes differ from actual execution: " + name
        )


@pytest.mark.parametrize("process", FACTORIES)
def test_actual_cold_and_mass_constructor_sources_are_bound(process, full_capture, record_property):
    report = {**full_capture, "process": process}
    calls = {tuple(call) for call in report["actual_calls"]}
    assert set(COLD_CODE) <= set(report["executed_cold_mass_code"])
    assert (f"registered_constructor:{process}", "build") not in calls, (
        "Do not claim registered producer construction itself uses mass mapping"
    )
    assert ("mass_observer_constructor", "build") in calls
    assert ("mass_helper", "compute_cell_mass") in calls
    assert ("live_csv_constructor", "dry_mass_g") in calls
    assert set(OWNER_CODE) <= set(report["owner_code_used_by_projection"])
    assert report["producers"][process]["module"].startswith("opencell.vivarium.")
    for name in ("Rna", "ProteinMonomer", "ProteinActivation"):
        path = f"data/karr_fixtures/per_process/{name}_flat.mat"
        assert "mass_observer_constructor" in report["actual_parameter_reads"][path]["phases"]
    record_property("consumed_scope_receipt", "mass_binding_capture*/all_normal.json")
    record_property("required_source_count", len(_required(report)))
    _require_bound(report, report["captured_before_constructor"][process])


@pytest.mark.parametrize("source", COLD_CODE)
def test_cold_registered_constructor_really_requires_mass_code(source, tmp_path):
    report = _invoke("RNAProcessing", tmp_path, source)
    assert report["blocked"] == source and not report["constructor_completed"]


def test_guard_and_existing_hash_verifier_reject_omission_and_drift(full_capture):
    sys.path.insert(0, str(ROOT / "tests/vivarium"))
    import _l2_2_design_a_runner_helpers as registered

    report = {**full_capture, "process": "RNAProcessing"}
    sources = [registered.capture_input_source(ROOT / name) for name in sorted(_required(report))]
    _require_bound(report, sources)
    registered.verify_input_sources(sources)
    for i in range(len(sources)):
        with pytest.raises(AssertionError, match="absent from capture"):
            _require_bound(report, sources[:i] + sources[i + 1:])
        changed = [{**item} for item in sources]
        changed[i]["sha256"] = "0" * len(changed[i]["sha256"])
        with pytest.raises(ValueError, match="hash drift"):
            registered.verify_input_sources(changed)


if __name__ == "__main__":
    assert sys.argv[1] == "--probe"
    _probe(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
