import sys
sys.dont_write_bytecode = True
from review_common import *
import pytest

publication = ROOT / "tests/scripts/test_ptrans_published_attestation.py"
original_hash = sha(publication)
reports = []
configuration = []


class CandidateOnly:
    def pytest_collection_modifyitems(self, items):
        modules = {item.module for item in items
                   if Path(str(item.path)).resolve() == publication}
        assert len(modules) == 1
        for module in modules:
            old = {"EVIDENCE_ROOT": str(module.EVIDENCE_ROOT), "BUNDLE": str(module.BUNDLE)}
            module.EVIDENCE_ROOT = CANDIDATE
            module.BUNDLE = CANDIDATE / module.ENTRY.name / schema.DESIGN_A_SUBDIR
            configuration.append({"module": str(publication), "original_sha256": original_hash,
                                  "old_constants": old,
                                  "new_constants": {"EVIDENCE_ROOT": str(module.EVIDENCE_ROOT),
                                                    "BUNDLE": str(module.BUNDLE)},
                                  "assertions_or_code_modified": False})
        save("publication_candidate_input_configuration.json", configuration)

    def pytest_runtest_logreport(self, report):
        reports.append({"nodeid": report.nodeid, "when": report.when,
                        "outcome": report.outcome, "duration_s": report.duration,
                        "wasxfail": getattr(report, "wasxfail", None),
                        "longrepr": str(report.longrepr) if report.longrepr else None})
        save("pytest_reports.json", reports)


from scripts.l22_evidence import schema
args = [
    "-q", "-s", "-rsxX", "-p", "no:cacheprovider",
    "--basetemp=artifacts/m1_cohort/m1_pt/independent_acceptance/scratch/pytest/controls_retry1",
    "--junitxml=artifacts/m1_cohort/m1_pt/independent_acceptance/controls_retry1.xml",
    "tests/vivarium/test_protein_translocation_sample_isolation.py",
    "tests/scripts/test_ptrans_published_attestation.py",
    "tests/vivarium/test_karr_protein_translocation_l2_replay.py",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_1_translocation_adapter_preserves_2892_compartment_positions",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_2_load_v2_ensemble_returns_2892_monomer_vectors",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_3_run_protein_translocation_tick_preserves_non_authority_monomers",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_4_planted_collapsed_sum_mutation_canary",
    "tests/vivarium/test_l2_no_oracle_dependency.py::test_l2_process_source_does_not_depend_on_replay_oracle[karr_protein_translocation.py]",
    "tests/vivarium/test_karr_protein_translocation.py",
    "tests/unit/test_karr_protein_translocation_strict_zero.py",
    "tests/vivarium/test_protein_translocation_stage2.py::test_c11_persistent_stream_and_fixture_order",
    "tests/vivarium/test_protein_translocation_stage2.py::test_canary_rejects_reseed_rng",
    "tests/vivarium/test_protein_translocation_stage2.py::test_canary_rejects_repeated_selection_stream_with_advancing_rng",
]
event("fresh_frozen_controls_start", pytest_args=args, candidate_configuration="ONLY publication module EVIDENCE_ROOT/BUNDLE retargeted")
rc = pytest.main(args, plugins=[CandidateOnly()])
assert sha(publication) == original_hash
skipped = [r for r in reports if r["outcome"] == "skipped" or r["wasxfail"] is not None]
failures = [r for r in reports if r["outcome"] == "failed"]
passed = [r for r in reports if r["when"] == "call" and r["outcome"] == "passed" and not r["wasxfail"]]
event("fresh_frozen_controls_complete", exit_code=int(rc), passed=len(passed),
      skipped_or_xfail=skipped, failures=failures,
      xml="controls_retry1.xml", publication_original_sha256=original_hash)
assert int(rc) == 0 and not skipped and not failures
