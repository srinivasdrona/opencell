"""Published PT must not retain eligibility through representative-only attestation.

These are read-only publication contracts, not mutation canaries against an
already-invalid bundle. Source/fixture closure and current-source revalidation
must be restored by reviewed re-attestation/migration or a genuine rerun.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog, generator, schema  # noqa: E402

ENTRY = catalog.in_scope_processes()["ProteinTranslocation"]
EVIDENCE_ROOT = REPO_ROOT / "docs/phase_f/l2_2_design_a/evidence_bundle"
BUNDLE = EVIDENCE_ROOT / ENTRY.name / schema.DESIGN_A_SUBDIR
FIXTURE_RELATIVE = "data/karr_fixtures/per_process/ProteinTranslocation_flat.mat"


def _json(name: str) -> dict[str, Any]:
    return json.loads((BUNDLE / name).read_text())


def _portable_path(record: dict[str, Any]) -> PurePosixPath:
    return PurePosixPath(str(record["path"]).replace("\\", "/"))


def test_ptrans_published_scores_and_thresholds_remain_byte_bound() -> None:
    """Positive control: distinguish incomplete attestation from score tampering."""
    sidecar_hashes = _json(schema.SWEEP_PROVENANCE_FILE)["sidecar_hashes"]
    for name in ("result.json", "thresholds.json", "null_calibration.json"):
        assert hashlib.sha256((BUNDLE / name).read_bytes()).hexdigest() == sidecar_hashes[name]
    result = _json("result.json")
    assert result["process"] == ENTRY.name
    assert result["seeds"] == list(range(ENTRY.n_seeds))
    assert result["ticks"] == ENTRY.m_ticks
    assert set(result["channels"]) == {"substrates", "monomers"}


def test_ptrans_published_attestation_binds_all_resolved_sources() -> None:
    manifest = _json("input_manifest.json")
    assert manifest["resolved_seeds"] == list(range(ENTRY.n_seeds))
    assert manifest["m_ticks"] == ENTRY.m_ticks
    records = [
        record for record in manifest["inputs"]
        if _portable_path(record).name == "ProteinTranslocation_100ticks.mat"
    ]
    assert len(records) == ENTRY.n_seeds, (
        f"PTRANS-COMPLETE-ATTESTATION: {ENTRY.n_seeds} resolved seeds but "
        f"only {len(records)} source records; representative seed0 is insufficient"
    )
    assert len({_portable_path(record) for record in records}) == ENTRY.n_seeds
    assert len({record["sha256"] for record in records}) == ENTRY.n_seeds
    captured_seeds = []
    for record in records:
        directory = _portable_path(record).parent.name
        if directory == "per_process_traces_v2":
            seed = 0
        else:
            match = re.fullmatch(r"per_process_traces_v2_s(\d+)", directory)
            assert match is not None, f"unresolved canonical PT source identity: {record['path']}"
            seed = int(match.group(1))
        captured_seeds.append(seed)
        for identity_key in ("seed", "rng_seed"):
            if identity_key in record:
                assert int(record[identity_key]) == seed
    assert sorted(captured_seeds) == manifest["resolved_seeds"], "no seed0 duplication or missing seeds"


def test_ptrans_published_attestation_binds_its_parameter_fixture() -> None:
    records = [
        record for record in _json("input_manifest.json")["inputs"]
        if _portable_path(record).as_posix().endswith(FIXTURE_RELATIVE)
    ]
    assert len(records) == 1, (
        "PTRANS-COMPLETE-ATTESTATION: bind the actual PT parameter fixture exactly once"
    )
    assert records[0]["sha256"] == hashlib.sha256((REPO_ROOT / FIXTURE_RELATIVE).read_bytes()).hexdigest()


def test_ptrans_published_attestation_is_current_under_strict_verification() -> None:
    row = generator.build_process_row(ENTRY, EVIDENCE_ROOT, strict_input_files=True)
    assert row["mechanical_verdict"] == schema.STATUS_PASS and row["green"], (
        "PTRANS-COMPLETE-ATTESTATION: current verified-byte re-attestation/migration "
        f"or a genuine rerun is required; no blanket hash waiver: {row['reasons']}"
    )
