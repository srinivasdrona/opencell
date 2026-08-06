"""Canary D closeout: write process-local L2.event evidence for Cytokinesis
seed-0, Karr-side-only (this trace's snapshot does not carry the full
``geometry``/``ftsZRing``/``chromosome`` objects a real OC-vs-Karr replay
would need -- see docs/phase_f/l2_event/CYTOKINESIS_ADAPTER_REPORT.md and
this task's own investigation notes; fabricating those fields to force an
OC comparison would be a synthetic biology event, which is explicitly
forbidden).

This intentionally mirrors ``scripts/l2_event/runner.py``'s
``run_structural_smoke``/``_write_smoke_evidence`` pattern (RibosomeAssembly
Canary A) but is a STANDALONE script rather than a change to
``runner.py``'s CLI (which today hard-refuses any process other than
RibosomeAssembly in smoke mode) -- see this task's scope notes.

Hard rule compliance:
* Writes ONLY to the gitignored live evidence root
  (``artifacts/l2_event/Cytokinesis/<run_id>/``) and the tracked,
  process-local bundle (``docs/phase_f/l2_event/evidence_bundle/Cytokinesis/``)
  via :func:`scripts.l2_event.evidence.write_run_artifacts` and
  :func:`scripts.l2_event.evidence.bundle_run`.
* NEVER calls :func:`scripts.l2_event.evidence.write_index` /
  ``build_index`` -- the shared ``evidence_index.json`` is not touched.
* ``verdict="NOT_APPLICABLE"`` / ``mode="structural_smoke"`` throughout --
  nothing here can be mistaken for a computed gate PASS/FAIL.
"""

from __future__ import annotations

import argparse
import subprocess
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import h5py
import numpy as np

from scripts.l2_event import evidence, metrics
from scripts.l2_event.adapters.cytokinesis import (
    CytokinesisEventAdapter,
    find_completion_tick,
    find_onset_tick,
    karr_pinched_diameter_sequence,
)
from scripts.l2_event.registry import REGISTRY_PATH, registry_sha256
from scripts.l2_event.schema import (
    SCHEMA_VERSION,
    InputManifest,
    InputManifestEntry,
    NullCalibrationDoc,
    ProvenanceDoc,
    ResultDoc,
)
from scripts.l2_event.window_loader import (
    _decode_char_metadata,
    classify_trace_dir,
    load_event_window,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADAPTER_MODULE_PATH = _REPO_ROOT / "scripts" / "l2_event" / "adapters" / "cytokinesis.py"

PROCESS = "Cytokinesis"
#: This resolves to the REAL, registered `CytokinesisEventAdapter`'s own
#: `adapter_id` -- never a bespoke/invented label. Only its read-only
#: Karr-side helpers (`karr_pinched_diameter_sequence`/`find_onset_tick`/
#: `find_completion_tick`) are exercised here (see module docstring on
#: why this evidence cannot be a full OC-vs-Karr comparison yet); the
#: adapter identity is real even though today's *use* of it is smoke-only.
ADAPTER_ID = CytokinesisEventAdapter.adapter_id

REQUIRED_OBSERVABLES = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "pinchedDiameter",
    "ftsZRing_numEdgesOneStraight",
    "ftsZRing_numEdgesTwoStraight",
    "ftsZRing_numEdgesTwoBent",
    "ftsZRing_numResidualBent",
    "chromosome_segregated",
)


def _read_metadata_scalar_int(handle: h5py.File, key: str) -> int:
    return int(np.asarray(handle["metadata"][key][()]).reshape(-1)[0])


def _read_metadata_string(handle: h5py.File, key: str) -> str:
    return _decode_char_metadata(np.asarray(handle["metadata"][key][()]))


def _resolve_git_dir_args() -> list[str]:
    """Returns the ``--git-dir=...`` args (or ``[]``) needed to run ``git``
    against THIS worktree from a WSL-hosted git binary. Mirrors
    ``scripts/l2_event/evidence.py``'s ``current_git_sha()`` fallback
    exactly: a Windows-git-created linked worktree's ``.git`` gitlink
    stores a Windows-style absolute ``gitdir:`` path that a WSL-hosted
    git cannot resolve directly (plain ``git status`` fails outright with
    "not a git repository" -- confirmed empirically in this worktree).
    Without this translation, :func:`_git_porcelain_status` would
    silently return empty/failed output and the dirty-tree guard below
    would never fire under the WSL execution this project mandates for
    all Python/tests -- exactly the "fail open" bug this exists to avoid."""
    probe = subprocess.run(
        ["git", "rev-parse", "--git-dir"], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10
    )
    if probe.returncode == 0:
        return []
    git_file = _REPO_ROOT / ".git"
    if not git_file.is_file():
        return []
    content = git_file.read_text().strip()
    if not content.startswith("gitdir:"):
        return []
    gitdir = content.split(":", 1)[1].strip()
    translated = evidence._translate_windows_gitdir(gitdir)
    if translated is None:
        return []
    return [f"--git-dir={translated}"]


def _git_porcelain_status(paths: Sequence[Path]) -> str:
    """Thin, mockable wrapper around ``git status --porcelain -- <paths>``
    (worktree-gitdir-aware, see :func:`_resolve_git_dir_args`). Isolated
    into its own function so tests can monkeypatch it directly (rather
    than shelling out to a real git repo) to exercise both the clean and
    dirty branches of :func:`_assert_registry_and_adapter_committed`
    deterministically."""
    result = subprocess.run(
        ["git", *_resolve_git_dir_args(), "status", "--porcelain", "--", *[str(p) for p in paths]],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout


def _assert_registry_and_adapter_committed(registry_path: Path) -> None:
    """Two-commit reproducibility guard (Opus review, 2026-08-05 item 3):
    ``provenance.json``'s ``git_sha`` must name a commit that actually
    CONTAINS the exact registry/adapter state this evidence was generated
    against. Refuses (raises) if the registry file or the Cytokinesis
    adapter module has uncommitted working-tree changes at generation
    time -- the sanctioned workflow is: commit code/registry fixes FIRST,
    THEN regenerate evidence in a follow-up commit, never in the same
    dirty tree. (If ``git`` itself is unavailable -- e.g. a stripped CI
    image -- ``git status`` simply returns a non-zero/empty result and
    this check is skipped rather than blocking evidence generation on an
    unrelated environment gap; the reproducibility guarantee this exists
    for is a worktree-local discipline, not a hard runtime dependency.)"""
    status = _git_porcelain_status([registry_path, _ADAPTER_MODULE_PATH])
    if status.strip():
        raise RuntimeError(
            "refusing to generate evidence: the registry and/or the Cytokinesis "
            f"adapter module have uncommitted working-tree changes:\n{status}"
            "Commit code/registry fixes FIRST, then regenerate evidence in a "
            "follow-up commit so provenance.git_sha names a commit that actually "
            "contains this exact registry_sha256 (two-commit reproducibility)."
        )


def build_evidence(trace_path: Path, *, seed: int, registry_path: Path | None = None) -> Path:
    window = load_event_window(trace_path, required_observables=REQUIRED_OBSERVABLES)

    if window.process_name != PROCESS:
        raise ValueError(
            f"trace metadata process_name={window.process_name!r} != expected {PROCESS!r}; "
            "refusing to write Cytokinesis evidence bound to a different process's trace "
            "(fail-closed)."
        )
    if window.seed != seed:
        raise ValueError(
            f"trace metadata seed={window.seed} != requested --seed {seed}; refusing to write "
            "evidence bound to the wrong seed (fail-closed)."
        )

    resolved_registry_path = registry_path if registry_path is not None else REGISTRY_PATH
    _assert_registry_and_adapter_committed(resolved_registry_path)

    before, after = karr_pinched_diameter_sequence(window)
    onset_offset = find_onset_tick(before, after)
    completion_offset = find_completion_tick(before, after)
    if onset_offset is None or completion_offset is None:
        raise ValueError(
            "trace loaded (M4 contract satisfied) but the Karr-side pinchedDiameter "
            f"sequence itself has no detectable onset/completion transition "
            f"(onset_offset={onset_offset!r} completion_offset={completion_offset!r}); "
            "refusing to write a fabricated-complete evidence bundle."
        )
    onset_abs = window.absolute_tick(onset_offset)
    completion_abs = window.absolute_tick(completion_offset)
    # Cross-check: the extractor's own persisted onset_tick/window_anchor
    # metadata must agree with this adapter's independent recomputation
    # from the raw pinchedDiameter sequence -- any mismatch is a real bug
    # to surface, never to paper over.
    if window.onset_tick != onset_abs or window.window_anchor != completion_abs:
        raise ValueError(
            "onset/completion recomputed from the raw pinchedDiameter sequence "
            f"(onset={onset_abs}, completion={completion_abs}) disagrees with the "
            f"trace's own persisted metadata (onset_tick={window.onset_tick}, "
            f"window_anchor={window.window_anchor}); refusing to launder this "
            "discrepancy into evidence."
        )

    with h5py.File(trace_path, "r") as handle:
        mnrnd_shim_version = _read_metadata_scalar_int(handle, "mnrnd_shim_version")
        mnrnd_shim_sha256 = _read_metadata_string(handle, "mnrnd_shim_sha256")
        projection_version = _read_metadata_scalar_int(handle, "event_observable_projection_version")

    division_relative_onset = onset_abs - completion_abs
    division_relative_completion = completion_abs - completion_abs  # == 0 by definition

    run_id = f"seed{seed:03d}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    generated_at = datetime.now(UTC).isoformat()

    result_doc = ResultDoc(
        schema_version=SCHEMA_VERSION,
        process=PROCESS,
        adapter_id=ADAPTER_ID,
        event_timing_model="single_firing",
        mode="structural_smoke",
        verdict="NOT_APPLICABLE",
        channels=[],
        oc_only_fire_ticks={},
        n_seeds_karr=1,
        n_seeds_oc=0,
        reasons=[
            "karr_only_structural_smoke: Canary D retry after the mnrnd shim repair. "
            "Proves the extractor/loader/adapter round-trip on one real anchor-mode "
            "seed; this is NOT a calibrated ensemble gate verdict and is NOT an "
            "OC-vs-Karr comparison (the anchor snapshot only carries boundEnzymes/"
            "enzymes/substrates + the 6 flattened diameter-anchor scalars, not full "
            "geometry/ftsZRing/chromosome objects -- an OC replay would require "
            "fabricating those fields, which is forbidden).",
            f"onset_tick={onset_abs} (contraction onset: first strict pinchedDiameter decrease)",
            f"completion_tick={completion_abs} (geometry pinch completion: first positive->zero transition)",
            f"tick_start={window.tick_start} n_ticks={window.n_ticks} stride_contract_ok={window.stride_contract_ok}",
            f"division_relative_onset_tick={division_relative_onset} "
            f"division_relative_completion_tick={division_relative_completion} "
            "(completion == the division-relative origin by this canary's own timing definition)",
            f"mnrnd_shim_version={mnrnd_shim_version} mnrnd_shim_sha256={mnrnd_shim_sha256}",
            f"event_observable_projection_version={projection_version}",
        ],
    )

    input_manifest = InputManifest(
        schema_version=SCHEMA_VERSION,
        process=PROCESS,
        inputs=[
            InputManifestEntry(
                path=str(trace_path.resolve()),
                sha256=evidence.sha256_file(trace_path),
                seed=seed,
                n_ticks=window.n_ticks,
                tick_offset=window.tick_offset,
                trace_kind=classify_trace_dir(trace_path),
            )
        ],
    )

    null_calibration = NullCalibrationDoc(
        schema_version=SCHEMA_VERSION,
        process=PROCESS,
        channel="n/a",
        statistic_name="n/a",
        b_resamples=0,
        q95_null=0.0,
    )

    provenance = ProvenanceDoc(
        schema_version=SCHEMA_VERSION,
        process=PROCESS,
        adapter_id=ADAPTER_ID,
        adapter_module="scripts.l2_event.adapters.cytokinesis",
        karr_source=str(trace_path.parent.resolve()),
        git_sha=evidence.current_git_sha(),
        registry_sha256=registry_sha256(resolved_registry_path),
        generated_at=generated_at,
        k_eng_provenance=metrics.K_ENG_PROVENANCE,
    )

    summary = {
        "process": PROCESS,
        "seed": seed,
        "mode": "structural_smoke",
        "verdict": "NOT_APPLICABLE",
        "onset_tick": onset_abs,
        "completion_tick": completion_abs,
        "tick_start": window.tick_start,
        "n_ticks": window.n_ticks,
        "stride_contract_ok": window.stride_contract_ok,
        "division_relative_onset_tick": division_relative_onset,
        "division_relative_completion_tick": division_relative_completion,
        "mnrnd_shim_version": mnrnd_shim_version,
        "mnrnd_shim_sha256": mnrnd_shim_sha256,
        "event_observable_projection_version": projection_version,
        "generated_at": generated_at,
    }

    run_dir = evidence.write_run_artifacts(
        PROCESS,
        run_id,
        {
            "result.json": result_doc.to_json(),
            "input_manifest.json": input_manifest.to_json(),
            "null_calibration.json": null_calibration.to_json(),
            "provenance.json": provenance.to_json(),
            "SUMMARY.json": summary,
        },
    )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-path", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--registry-path", type=Path, default=None)
    args = parser.parse_args(argv)

    run_dir = build_evidence(args.trace_path, seed=args.seed, registry_path=args.registry_path)
    bundle_dir = evidence.bundle_run(run_dir, PROCESS)
    print(f"live evidence written: {evidence.relative_to_repo(run_dir)}")
    print(f"tracked bundle written: {evidence.relative_to_repo(bundle_dir)}")
    print("evidence_index.json NOT touched (process-local only, per hard rule).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
