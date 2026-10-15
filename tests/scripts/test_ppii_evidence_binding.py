"""PP2 evidence-binding contracts, independent of its frozen biological verdict.

Synthetic catalog-sized tensors exercise the real loader, runner metadata writer,
sweep attestation and strict generator. The tick callback is arithmetic only:
these files/results are test fixtures, never biological evidence or promotion.
Every tampering canary first proves a fresh current-schema strict PASS.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VIVARIUM_TESTS = REPO_ROOT / "tests/vivarium"
if str(VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(VIVARIUM_TESTS))

import _l2_2_design_a_runner_helpers as helpers
import l2_2_design_a_runner as runner

from scripts.l22_evidence import catalog, generator, schema, sweep
from tests.scripts._l22_ast_import_audit import first_party_import_files
from tests.scripts._l22_evidence_fixtures import write_valid_sweep_provenance
from tests.vivarium.test_l2_2_design_a_ensemble_loader import _write_mat_trace

ENTRY = catalog.in_scope_processes()["ProteinProcessingII"]
AUTHORITY = REPO_ROOT / "opencell/vivarium/protein_state.py"
FIXTURE_NAMES = (
    "ProteinProcessingII_flat.mat",
    "ProteinTranslocation_flat.mat",
    "TerminalOrganelleAssembly_flat.mat",
)
ORIGINAL_PROCESS_DEPENDENCIES = dict(schema.PROCESS_DEPENDENCY_FILES.get(ENTRY.name, {}))
ORIGINAL_HARNESS_DEPENDENCIES = dict(schema.HARNESS_DEPENDENCY_FILES.get(ENTRY.harness_type, {}))
ORIGINAL_SHARED_FILES = dict(schema.shared_source_files_for_harness(ENTRY.harness_type))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class BindingBundle:
    root: Path
    output: Path
    seed_paths: list[Path]
    fixture_paths: dict[str, Path]
    authority: Path
    job: sweep.SweepJob
    result_bytes: bytes
    input_hashes: dict[Path, str]
    artifact_bytes: dict[str, bytes]

    def manifest(self) -> dict[str, Any]:
        return json.loads((self.output / "input_manifest.json").read_text())

    def strict_row(self) -> dict[str, Any]:
        return generator.build_process_row(
            ENTRY, self.root / "evidence", strict_input_files=True,
        )


def _redirect_existing_authority(entries: dict[str, Path], replacement: Path) -> dict[str, Path]:
    # Never add the missing dependency in the test: an absent registration
    # must remain absent and make the canaries RED. Only isolate real entries.
    return {
        key: replacement if path.resolve() == AUTHORITY.resolve() else path
        for key, path in entries.items()
    }


@pytest.fixture(scope="module")
def binding_bundle() -> Any:
    root = (Path.cwd() / "artifacts/ppii_evidence_binding_tests").resolve()
    assert root.is_relative_to(REPO_ROOT) and not root.exists(), root
    root.mkdir(parents=True)
    patches = pytest.MonkeyPatch()
    try:
        for relative in (
            ENTRY.oc_module,
            "opencell/vivarium/protein_state.py",
            "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
            *(f"data/karr_fixtures/per_process/{name}" for name in FIXTURE_NAMES),
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO_ROOT / relative).read_bytes())
        authority = root / "opencell/vivarium/protein_state.py"
        patches.setitem(
            schema.PROCESS_DEPENDENCY_FILES, ENTRY.name,
            _redirect_existing_authority(ORIGINAL_PROCESS_DEPENDENCIES, authority),
        )
        patches.setitem(
            schema.HARNESS_DEPENDENCY_FILES, ENTRY.harness_type,
            _redirect_existing_authority(ORIGINAL_HARNESS_DEPENDENCIES, authority),
        )
        patches.setattr(
            schema, "SWEEP_PROVENANCE_SOURCE_FILES",
            _redirect_existing_authority(dict(schema.SWEEP_PROVENANCE_SOURCE_FILES), authority),
        )
        patches.setattr(catalog, "REPO_ROOT", root)
        patches.setattr(sweep, "REPO_ROOT", root)
        patches.setattr(runner, "_REPO_ROOT", root)
        patches.setattr(helpers, "_REPO_ROOT", root)
        patches.chdir(root)
        assert ENTRY.n_seeds == 50 and ENTRY.m_ticks == 20
        sample = helpers._protein_processing_ii_process(0)
        n_sub, n_enz, n_mono = (
            len(sample.substrate_wids), len(sample.enzyme_wids),
            len(sample.unprocessed_monomer_wids),
        )
        seed_paths = []
        # Actual HDF5 files with unique seed identities/hashes. Shared constant
        # frame references keep metadata fixtures small; these are not biology.
        for seed in range(ENTRY.n_seeds):
            path = helpers._v2_seed_mat_path(ENTRY.name, seed)
            before = {
                "substrates": [np.full(n_sub, 100 + seed)],
                "enzymes": [np.ones(n_enz)],
                "boundEnzymes": [np.zeros(n_enz)],
                "unprocessedMonomers": [np.full(n_mono, 100 + seed)],
                "processedMonomers": [np.zeros(n_mono)],
                "signalSequenceMonomers": [np.zeros(n_mono)],
            }
            after = {
                **before,
                "substrates": [v - 2 for v in before["substrates"]],
                "unprocessedMonomers": [v - 2 for v in before["unprocessedMonomers"]],
                "processedMonomers": [v + 2 for v in before["processedMonomers"]],
            }
            _write_mat_trace(path, states_before=before, states_after=after)
            with h5py.File(path, "a") as trace:
                for section in ("states_before", "states_after"):
                    group = trace[section]
                    for channel in list(group):
                        reference = group[channel][0, 0]
                        del group[channel]
                        frames = group.create_dataset(channel, (1, 100), dtype=h5py.ref_dtype)
                        frames[0, :] = np.asarray([reference] * 100, dtype=h5py.ref_dtype)
                trace["metadata"].create_dataset("rng_seed", data=[seed])
                trace["metadata"].create_dataset("n_ticks", data=[100])
            seed_paths.append(path.resolve())

        def arithmetic_tick(process_name: str, seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
            assert process_name == ENTRY.name
            return {
                "substrates": np.asarray(state["oracle_before_substrates"]) - 1,
                "monomers": np.asarray(state["oracle_before_monomers"]) - 1,
                "sample_seed": helpers._sample_seed(seed, tick),
            }

        def no_biology(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("evidence-binding unit test must not execute PP2 biology")

        patches.setattr(helpers, "run_oc_tick", arithmetic_tick)
        patches.setattr(helpers.KarrProteinProcessingIIProcess, "next_update", no_biology)
        output = root / "evidence" / ENTRY.name / schema.DESIGN_A_SUBDIR
        runner.run_design_a(
            process=ENTRY.name, seeds=list(range(ENTRY.n_seeds)), m_ticks=ENTRY.m_ticks,
            out_dir=output, thresholds_path=output / "thresholds.json", bootstrap_B=8,
        )
        manifest = json.loads((output / "input_manifest.json").read_text())
        verified, reason = sweep._verify_input_manifest(manifest, repo_root=root)
        assert verified, reason
        sweep._normalize_input_manifest_file(output, repo_root=root)
        write_valid_sweep_provenance(
            output, process=ENTRY.name, n_seeds=ENTRY.n_seeds, m_ticks=ENTRY.m_ticks,
            oc_module=ENTRY.oc_module, harness_type=ENTRY.harness_type,
        )
        job = sweep.SweepJob(
            process=ENTRY.name, seeds=ENTRY.n_seeds, m_ticks=ENTRY.m_ticks,
            output_dir=output, log_path=root / "unit-run.log", oc_module=ENTRY.oc_module,
        )
        fixture_paths = {
            name: root / "data/karr_fixtures/per_process" / name for name in FIXTURE_NAMES
        }
        assert len(set(seed_paths)) == ENTRY.n_seeds
        assert len({_sha(path) for path in seed_paths}) == ENTRY.n_seeds
        for seed, path in enumerate(seed_paths):
            with h5py.File(path, "r") as trace:
                assert int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0]) == seed
        artifact_names = {
            *schema.REQUIRED_AUTHORITY_FILES, *schema.MANDATORY_SIDECAR_FILES,
            schema.SWEEP_PROVENANCE_FILE,
        }
        bundle = BindingBundle(
            root, output, seed_paths, fixture_paths, authority, job,
            (output / "result.json").read_bytes(),
            {path: _sha(path) for path in (*seed_paths, *fixture_paths.values(), authority)},
            {name: (output / name).read_bytes() for name in artifact_names},
        )
        _assert_valid_baseline(bundle)
        yield bundle
    finally:
        patches.undo()
        # This fixture owns this new, non-junction project subtree only.
        assert root.is_relative_to(REPO_ROOT / "artifacts")
        shutil.rmtree(root)


def _assert_valid_baseline(bundle: BindingBundle) -> None:
    row = bundle.strict_row()
    assert row["mechanical_verdict"] == schema.STATUS_PASS and row["green"], row["reasons"]
    assert row["reasons"] == []
    valid, reason = sweep.evidence_is_valid(bundle.job)
    assert valid, reason
    verified, reason = sweep._verify_input_manifest(bundle.manifest(), repo_root=bundle.root)
    assert verified, reason
    assert all(_sha(path) == digest for path, digest in bundle.input_hashes.items())
    _assert_evidence_unchanged(bundle)


def _assert_evidence_unchanged(bundle: BindingBundle) -> None:
    for name, original in bundle.artifact_bytes.items():
        assert (bundle.output / name).read_bytes() == original, f"evidence rewritten: {name}"


@contextlib.contextmanager
def _one_file_change(path: Path, mutation: str) -> Any:
    original = path.read_bytes()
    try:
        if mutation == "changed":
            path.write_bytes(original + b"#")
        else:
            assert mutation == "missing"
            path.unlink()
        yield
    finally:
        path.write_bytes(original)


def test_ppii_registry_covers_its_actual_protein_authority_import() -> None:
    imported = first_party_import_files(REPO_ROOT, REPO_ROOT / ENTRY.oc_module)
    assert AUTHORITY.resolve() in imported
    registered = {
        path.resolve()
        for paths in (ORIGINAL_PROCESS_DEPENDENCIES, ORIGINAL_HARNESS_DEPENDENCIES, ORIGINAL_SHARED_FILES)
        for path in paths.values()
    }
    assert AUTHORITY.resolve() in registered, (
        "PP2 evidence source-hash closure omits its actual protein_state.py authority import"
    )


def test_ppii_binding_fixture_is_a_current_strict_mechanical_pass(binding_bundle: BindingBundle) -> None:
    _assert_valid_baseline(binding_bundle)
    result = json.loads(binding_bundle.result_bytes)
    assert result["seeds"] == list(range(ENTRY.n_seeds))
    assert result["ticks"] == ENTRY.m_ticks
    assert set(result["channels"]) == {"substrates", "monomers"}


@pytest.mark.parametrize("mutation", ["changed", "missing"])
def test_ppii_authority_change_invalidates_previously_valid_pass(
    binding_bundle: BindingBundle, mutation: str,
) -> None:
    bundle = binding_bundle
    _assert_valid_baseline(bundle)
    before = generator._current_source_hashes(ENTRY)
    with _one_file_change(bundle.authority, mutation):
        row = bundle.strict_row()
        _assert_evidence_unchanged(bundle)
        assert not row["green"] and row["mechanical_verdict"] != schema.STATUS_PASS, (
            f"strict evidence stayed PASS after one {mutation} protein_state.py dependency"
        )
        assert generator._current_source_hashes(ENTRY) != before
        assert not sweep.evidence_is_valid(bundle.job)[0]


def test_ppii_manifest_binds_every_consumed_seed_and_parameter_file(binding_bundle: BindingBundle) -> None:
    bundle = binding_bundle
    _assert_valid_baseline(bundle)
    manifest = bundle.manifest()
    assert manifest["resolved_seeds"] == list(range(ENTRY.n_seeds))
    assert manifest["m_ticks"] == ENTRY.m_ticks
    records = {
        (Path(record["path"]) if Path(record["path"]).is_absolute() else bundle.root / record["path"]).resolve(): record
        for record in manifest["inputs"]
    }
    assert len(records) == len(manifest["inputs"]), "deduplicate shared files by resolved path"
    expected = set(bundle.seed_paths) | set(bundle.fixture_paths.values())
    missing = sorted(str(path.relative_to(bundle.root)) for path in expected - set(records))
    assert expected <= set(records), (
        f"{len(missing)} unbound consumed inputs (first five): {missing[:5]}"
    )
    assert len({_sha(path) for path in bundle.seed_paths}) == ENTRY.n_seeds
    for seed, path in enumerate(bundle.seed_paths):
        with h5py.File(path, "r") as trace:
            assert int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0]) == seed
        assert records[path]["sha256"] == _sha(path)
        for identity_key in ("seed", "rng_seed"):
            if identity_key in records[path]:
                assert int(records[path][identity_key]) == seed
    for path in bundle.fixture_paths.values():
        assert records[path]["sha256"] == _sha(path)


@pytest.mark.parametrize("target", ["seed0", "seed1", *FIXTURE_NAMES])
@pytest.mark.parametrize("mutation", ["changed", "missing"])
def test_ppii_strict_inputs_reject_one_change_after_valid_pass(
    binding_bundle: BindingBundle, target: str, mutation: str,
) -> None:
    bundle = binding_bundle
    _assert_valid_baseline(bundle)
    path = (
        bundle.seed_paths[int(target[-1])]
        if target in {"seed0", "seed1"} else bundle.fixture_paths[target]
    )
    with _one_file_change(path, mutation):
        row = bundle.strict_row()
        verified, reason = sweep._verify_input_manifest(bundle.manifest(), repo_root=bundle.root)
        _assert_evidence_unchanged(bundle)
        assert not row["green"] and row["mechanical_verdict"] != schema.STATUS_PASS, (
            f"--verify-input-files re-derived PASS after one {mutation} {target}"
        )
        assert not verified, f"inputs_verified still true after {mutation} {target}: {reason}"
