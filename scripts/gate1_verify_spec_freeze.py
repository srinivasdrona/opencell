"""Gate 1 — freeze the derived Karr input-spec artifact.

This gate enforces that the committed frozen input-spec YAMLs remain a pure,
mechanically derived artifact of the tracked per-process fixtures:

1. MANIFEST completeness: exactly the expected 28 process entries.
2. Hash-lock: committed spec/fixture bytes match the committed MANIFEST hashes.
3. Determinism: re-deriving from fixtures reproduces byte-identical YAMLs and
   MANIFEST.json.

No MATLAB is required. If the tracked fixtures are absent, the gate SKIPs
cleanly (exit 0), mirroring other oracle-backed gates in this repository.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
_DERIVE_SPEC = importlib.util.spec_from_file_location(
    "_gate1_derive_input_spec",
    SCRIPT_DIR / "derive_input_spec.py",
)
assert _DERIVE_SPEC is not None and _DERIVE_SPEC.loader is not None
derive_input_spec = importlib.util.module_from_spec(_DERIVE_SPEC)
_DERIVE_SPEC.loader.exec_module(derive_input_spec)

REPO_ROOT = derive_input_spec.REPO_ROOT
PROCESS_NAMES = derive_input_spec.PROCESS_NAMES
DEFAULT_SPEC_DIR = derive_input_spec.OUTPUT_ROOT
DEFAULT_FIXTURE_DIR = derive_input_spec.FIXTURE_ROOT


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


@contextlib.contextmanager
def _override_fixture_root(fixture_dir: Path) -> Iterator[None]:
    original = derive_input_spec.FIXTURE_ROOT
    derive_input_spec.FIXTURE_ROOT = fixture_dir
    try:
        yield
    finally:
        derive_input_spec.FIXTURE_ROOT = original


def _derive_all_specs(*, fixture_dir: Path, output_dir: Path) -> dict[str, Any]:
    with _override_fixture_root(fixture_dir), contextlib.redirect_stdout(io.StringIO()):
        return derive_input_spec.derive_input_specs(output_dir=output_dir)


def _gate_result(
    *,
    spec_dir: Path = DEFAULT_SPEC_DIR,
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    manifest_path: Path | None = None,
    process_names: tuple[str, ...] = PROCESS_NAMES,
) -> tuple[int, str]:
    if manifest_path is None:
        manifest_path = spec_dir / "MANIFEST.json"

    expected = tuple(process_names)
    expected_set = set(expected)

    if not fixture_dir.exists():
        return 0, (
            f"GATE 1 (spec freeze): SKIPPED — fixtures absent at "
            f"{_display_path(fixture_dir)}."
        )

    missing_fixture_files = [
        process_name
        for process_name in expected
        if not (fixture_dir / f"{process_name}_flat.mat").exists()
    ]
    if missing_fixture_files:
        preview = ", ".join(missing_fixture_files[:4])
        if len(missing_fixture_files) > 4:
            preview += f", +{len(missing_fixture_files) - 4} more"
        return 0, (
            "GATE 1 (spec freeze): SKIPPED — fixtures absent for "
            f"{len(missing_fixture_files)}/{len(expected)} expected process(es): {preview}."
        )

    findings: list[str] = []
    manifest: dict[str, Any] = {}

    if not manifest_path.exists():
        findings.append(f"missing committed manifest file: {_display_path(manifest_path)}")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                f"invalid JSON in committed manifest {_display_path(manifest_path)}: {exc}"
            )
            manifest = {}

    manifest_keys = set(manifest)
    missing_manifest = sorted(expected_set - manifest_keys)
    extra_manifest = sorted(manifest_keys - expected_set)
    if missing_manifest:
        findings.append(
            "MANIFEST completeness drift: missing process entries "
            + ", ".join(missing_manifest)
        )
    if extra_manifest:
        findings.append(
            "MANIFEST completeness drift: unexpected process entries "
            + ", ".join(extra_manifest)
        )

    for process_name in expected:
        spec_path = spec_dir / f"{process_name}.yaml"
        fixture_path = fixture_dir / f"{process_name}_flat.mat"
        entry = manifest.get(process_name)

        if not spec_path.exists():
            findings.append(
                f"{process_name}: missing committed spec file {_display_path(spec_path)}"
            )
            continue

        if not isinstance(entry, dict):
            findings.append(f"{process_name}: missing or invalid MANIFEST entry")
            continue

        expected_spec_hash = entry.get("spec_sha256")
        expected_fixture_hash = entry.get("fixture_sha256")
        if not isinstance(expected_spec_hash, str):
            findings.append(f"{process_name}: MANIFEST missing spec_sha256")
        if not isinstance(expected_fixture_hash, str):
            findings.append(f"{process_name}: MANIFEST missing fixture_sha256")

        committed_spec_hash = _sha256_file(spec_path)
        committed_fixture_hash = _sha256_file(fixture_path)

        if isinstance(expected_spec_hash, str) and committed_spec_hash != expected_spec_hash:
            findings.append(
                f"{process_name}: spec hash drift "
                f"(committed={committed_spec_hash}, manifest={expected_spec_hash})"
            )
        if (
            isinstance(expected_fixture_hash, str)
            and committed_fixture_hash != expected_fixture_hash
        ):
            findings.append(
                f"{process_name}: fixture hash drift "
                f"(fixture={committed_fixture_hash}, manifest={expected_fixture_hash})"
            )

    with tempfile.TemporaryDirectory() as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        summary = _derive_all_specs(fixture_dir=fixture_dir, output_dir=tmp_dir)

        if summary["missing_fixtures"]:
            preview = ", ".join(summary["missing_fixtures"][:4])
            if len(summary["missing_fixtures"]) > 4:
                preview += f", +{len(summary['missing_fixtures']) - 4} more"
            return 0, (
                "GATE 1 (spec freeze): SKIPPED — fixture re-derivation inputs absent for "
                f"{len(summary['missing_fixtures'])}/{len(expected)} expected process(es): {preview}."
            )

        produced = set(summary["produced_processes"])
        missing_produced = sorted(expected_set - produced)
        extra_produced = sorted(produced - expected_set)
        if missing_produced:
            findings.append(
                "re-derivation omitted expected process specs " + ", ".join(missing_produced)
            )
        if extra_produced:
            findings.append(
                "re-derivation produced unexpected process specs " + ", ".join(extra_produced)
            )

        for process_name in expected:
            committed_spec_path = spec_dir / f"{process_name}.yaml"
            rederived_spec_path = tmp_dir / f"{process_name}.yaml"
            if not committed_spec_path.exists() or not rederived_spec_path.exists():
                continue
            if committed_spec_path.read_bytes() != rederived_spec_path.read_bytes():
                findings.append(
                    f"{process_name}: spec bytes drift from fixture-derived output"
                )

        committed_manifest_bytes = b""
        if manifest_path.exists():
            committed_manifest_bytes = manifest_path.read_bytes()
        rederived_manifest_path = tmp_dir / "MANIFEST.json"
        rederived_manifest_bytes = rederived_manifest_path.read_bytes()

        if committed_manifest_bytes != rederived_manifest_bytes:
            rederived_manifest = json.loads(rederived_manifest_bytes.decode("utf-8"))
            differing_entries = sorted(
                process_name
                for process_name in expected_set | set(rederived_manifest)
                if manifest.get(process_name) != rederived_manifest.get(process_name)
            )
            if differing_entries:
                findings.append(
                    "MANIFEST.json drift for process entries " + ", ".join(differing_entries)
                )
            else:
                findings.append("MANIFEST.json byte drift from fixture-derived output")

    if findings:
        bullet_lines = "\n".join(f"- {finding}" for finding in findings)
        return 1, (
            f"GATE 1 (spec freeze): FAIL — {len(findings)} finding(s).\n{bullet_lines}"
        )

    return 0, (
        "GATE 1 (spec freeze): PASS — 28 processes; "
        "spec==fixture (byte-identical re-derivation) + MANIFEST hash-lock verified."
    )


def main() -> int:
    code, message = _gate_result()
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
