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
import uuid
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

from scripts.l2_event import evidence, metrics
from scripts.l2_event.adapters.cytokinesis import (
    find_completion_tick,
    find_onset_tick,
    karr_pinched_diameter_sequence,
)
from scripts.l2_event.registry import registry_sha256
from scripts.l2_event.schema import (
    SCHEMA_VERSION,
    InputManifest,
    InputManifestEntry,
    NullCalibrationDoc,
    ProvenanceDoc,
    ResultDoc,
)
from scripts.l2_event.window_loader import _decode_char_metadata, classify_trace_dir, load_event_window

PROCESS = "Cytokinesis"
ADAPTER_ID = "cytokinesis.karr_only_smoke.v1"

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


def build_evidence(trace_path: Path, *, seed: int, registry_path: Path | None = None) -> Path:
    window = load_event_window(trace_path, required_observables=REQUIRED_OBSERVABLES)

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

    run_id = f"seed{seed:03d}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    generated_at = datetime.now(timezone.utc).isoformat()

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
        registry_sha256=registry_sha256(registry_path) if registry_path else registry_sha256(),
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
