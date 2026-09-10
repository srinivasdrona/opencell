"""Combined canary validation for the one-pass dual-tap
Cytokinesis + FtsZPolymerization division-window extractor
(``scripts/matlab/extract_dual_division_window.m``).

This module writes NO new validation logic for either process: it reuses,
unmodified, the two existing fail-closed validators the task requires:

* Cytokinesis: ``scripts.l2_event.launcher.validate_existing_event_window``
  against an ``AnchorWindowSpec`` built from the same catalog-authoritative
  constants ``scripts/l2_event/survey_cytokinesis_onset_span.py`` and
  ``scripts/l2_event/prepare_cytokinesis_cohort.py`` already use (process=
  "Cytokinesis", n_ticks=4000, required_observables=REQUIRED_OBSERVABLES,
  scalar_finite_observables=CYTOKINESIS_SCALAR_FINITE_OBSERVABLES). This is
  the exact check ``prepare_cytokinesis_cohort.py``'s
  ``_validate_event_candidate`` applies to every discovered Cytokinesis
  trace.
* FtsZPolymerization: ``scripts.l2_event.ftsz_pre_division_evidence.
  validate_seed_window``, the exact function
  ``audit_pre_division_evidence`` applies to every discovered
  FtsZPolymerization trace.

Additional dual-tap-specific cross-checks this module DOES add (not
duplicating either validator, but checking the property this task
specifically requires and neither single-process validator has any reason
to check on its own):

* Distinctness: the two output files must not be byte-identical, and must
  not resolve to the same path.
* Same-completion-tick requirement: both windows' ``metadata.window_anchor``
  must be numerically equal (the task's explicit "same real geometry
  pinchedDiameter completion tick" requirement for FtsZPolymerization).
* Genuine-provider parity: both files must report the identical
  ``mnrnd_provider_sha256`` (both came from the same single
  ``karr_bootstrap()`` call in one process, so any drift would indicate the
  two files were NOT actually produced by one dual-tap run).
* Full-simulation source-hash binding (decisions/dec-005, 2026-09-04): both
  files must report the identical ``dnadamage_source_resolved_sha256`` --
  and each file's Cytokinesis-side validation independently requires that
  hash to match the CURRENT worktree's karr_bootstrap.m resolution (see
  ``scripts.l2_event.launcher.current_genuine_dnadamage_source``). DNADamage
  participates in the shared 28-process scheduler every tick, so its
  source version affects every other process's real trajectory -- a trace
  produced under a different DNADamage source is not comparable evidence,
  even for a process whose own source never changed.
* Provisional-margin gate (Opus final review, 2026-09-04): Cytokinesis's
  real inclusive onset-to-completion span (``window_anchor - onset_tick +
  1``) must leave a STRICTLY POSITIVE margin against ``CYTOKINESIS_N_TICKS``
  -- a zero-or-negative margin (``inclusive_span >= CYTOKINESIS_N_TICKS``)
  fails closed here even though the MATLAB extractor's own capture
  invariant (left unchanged) would have allowed exactly-M_ticks. See
  ``scripts.l2_event.division_window_spec.check_inclusive_span_margin``/
  ``ProvisionalMarginOverrunError``.

Fail-closed: :func:`validate_dual_division_canary` never returns a
combined-PASS verdict unless BOTH underlying validators independently
accept their own file. A single-sided PASS is reported as a FAIL with the
exact reason, never partially promoted or silently accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import h5py

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l2_event import division_window_spec, launcher  # noqa: E402
from scripts.l2_event import ftsz_pre_division_evidence as ftsz_evidence  # noqa: E402
from scripts.l2_event.division_window_spec import (  # noqa: E402
    m_ticks_for,
    selection_horizon_max_search_ticks,
)
from scripts.l2_event.survey_cytokinesis_onset_span import (  # noqa: E402
    REQUIRED_OBSERVABLES as CYTOKINESIS_REQUIRED_OBSERVABLES,
)
from scripts.l2_event.window_loader import _decode_char_metadata  # noqa: E402

CYTOKINESIS_PROCESS = "Cytokinesis"
# Single source of truth: docs/phase_f/l2_event/division_window_spec.json
# (read via scripts.l2_event.division_window_spec). Do NOT hardcode this
# value here -- see the 2026-09-04 Cytokinesis window preregistration fix
# (STATUS_DUAL_CYT_WINDOW_FIX.md). Was a literal 4000 before that fix.
CYTOKINESIS_N_TICKS = m_ticks_for(CYTOKINESIS_PROCESS)
FTSZ_PROCESS = "FtsZPolymerization"
FTSZ_N_TICKS = m_ticks_for(FTSZ_PROCESS)
# Full-simulation source-hash binding (decisions/dec-005, 2026-09-04): see
# scripts/l2_event/prepare_cytokinesis_cohort.py's identical constant for
# the full rationale. Computed once at import time.
REQUIRED_DNADAMAGE_SOURCE_SHA256 = launcher.current_genuine_dnadamage_source()["patched_sha256_lf_normalized"]
# Division-censor-contract (2026-09-08, wired 2026-09-09 per Opus
# re-review): the selection contract's common censoring horizon
# (docs/phase_f/l2_event/division_window_spec.json's selection_contract.
# max_search_ticks). Used to build fresh AnchorWindowSpecs for both
# planning NEW extractions (build_matlab_command bakes this into the
# generated MATLAB call) and validating existing traces -- the latter is
# safe against legacy (smaller-horizon) traces because
# launcher.validate_existing_event_window checks max_search_ticks as a
# MONOTONE MINIMUM against spec.n_ticks, never an exact match against
# this value (see that function's inline rationale).
REQUIRED_MAX_SEARCH_TICKS = selection_horizon_max_search_ticks()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_metadata_string(path: Path, key: str) -> str | None:
    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None or key not in metadata:
            return None
        return _decode_char_metadata(metadata[key][()])


def _read_metadata_int(path: Path, key: str) -> int | None:
    import numpy as np

    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None or key not in metadata:
            return None
        return int(np.asarray(metadata[key][()]).reshape(-1)[0])


def cytokinesis_anchor_spec(seed: int) -> launcher.AnchorWindowSpec:
    """The exact spec ``prepare_cytokinesis_cohort._anchor_spec`` builds --
    reused verbatim (not re-derived) so this module's Cytokinesis check is
    the same check the existing cohort-preparation tooling already
    applies. ``max_search_ticks`` is the division-censor-contract's
    ``selection_horizon_max_search_ticks()`` (100000), not the launcher's
    older ``DEFAULT_MAX_SEARCH_TICKS`` (50000) -- safe for validating
    legacy (smaller-recorded-horizon) traces because of the
    monotone-minimum policy (see ``REQUIRED_MAX_SEARCH_TICKS``)."""
    return launcher.AnchorWindowSpec(
        process=CYTOKINESIS_PROCESS,
        seed=seed,
        n_ticks=CYTOKINESIS_N_TICKS,
        max_search_ticks=REQUIRED_MAX_SEARCH_TICKS,
        required_observables=CYTOKINESIS_REQUIRED_OBSERVABLES,
        scalar_finite_observables=launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES,
        required_dnadamage_source_sha256=REQUIRED_DNADAMAGE_SOURCE_SHA256,
    )


def event_window_dir(seed: int, *, karr_native_root: Path | None = None) -> Path:
    root = karr_native_root if karr_native_root is not None else launcher.KARR_NATIVE_ROOT
    return root / f"per_process_traces_v2_event_s{int(seed):03d}"


@dataclass
class DualDivisionCanaryReport:
    seed: int
    cytokinesis_path: str
    ftsz_path: str
    cytokinesis_valid: bool
    cytokinesis_reason: str
    ftsz_valid: bool
    ftsz_reason: str
    distinct_paths: bool
    distinct_content: bool
    same_completion_tick: bool
    cytokinesis_window_anchor: int | None
    ftsz_window_anchor: int | None
    provider_sha256_match: bool
    cytokinesis_provider_sha256: str | None
    ftsz_provider_sha256: str | None
    dnadamage_source_match: bool
    cytokinesis_dnadamage_source_sha256: str | None
    ftsz_dnadamage_source_sha256: str | None
    margin_ok: bool
    cytokinesis_onset_tick: int | None
    inclusive_span_ticks: int | None
    cytokinesis_sha256: str | None = None
    ftsz_sha256: str | None = None
    status: str = "FAIL"
    reasons: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def validate_dual_division_canary(
    seed: int, *, karr_native_root: Path | None = None
) -> DualDivisionCanaryReport:
    """Fail-closed combined validation for one seed's dual-tap outputs.

    Never reports ``status="PASS"`` unless every one of the checks listed
    in the module docstring independently holds. Missing files are
    reported as an explicit FAIL reason, never silently skipped.
    """
    out_dir = event_window_dir(seed, karr_native_root=karr_native_root)
    cyt_path = out_dir / f"{CYTOKINESIS_PROCESS}_{CYTOKINESIS_N_TICKS}ticks.mat"
    ftsz_path = out_dir / f"{FTSZ_PROCESS}_{FTSZ_N_TICKS}ticks.mat"

    reasons: list[str] = []

    cyt_valid = False
    cyt_reason = "file does not exist"
    if cyt_path.exists():
        cyt_valid, cyt_reason = launcher.validate_existing_event_window(
            cyt_path, cytokinesis_anchor_spec(seed)
        )
    if not cyt_valid:
        reasons.append(f"cytokinesis: {cyt_reason}")

    ftsz_valid = False
    ftsz_reason = "file does not exist"
    if ftsz_path.exists():
        try:
            ftsz_evidence.validate_seed_window(seed, ftsz_path)
            ftsz_valid = True
            ftsz_reason = ""
        except Exception as exc:  # noqa: BLE001 - fail-closed: any exception is a real FAIL reason
            ftsz_valid = False
            ftsz_reason = str(exc)
    if not ftsz_valid:
        reasons.append(f"ftsz: {ftsz_reason}")

    distinct_paths = cyt_path.resolve() != ftsz_path.resolve()
    if not distinct_paths:
        reasons.append("cytokinesis and ftsz outputs resolve to the same path")

    distinct_content = True
    cyt_sha = None
    ftsz_sha = None
    if cyt_path.exists() and ftsz_path.exists():
        cyt_sha = _sha256_file(cyt_path)
        ftsz_sha = _sha256_file(ftsz_path)
        distinct_content = cyt_sha != ftsz_sha
        if not distinct_content:
            reasons.append("cytokinesis and ftsz outputs are byte-identical (not two distinct taps)")

    cyt_anchor = None
    ftsz_anchor = None
    same_completion = False
    if cyt_path.exists() and ftsz_path.exists():
        cyt_anchor = _read_metadata_int(cyt_path, "window_anchor")
        ftsz_anchor = _read_metadata_int(ftsz_path, "window_anchor")
        same_completion = cyt_anchor is not None and cyt_anchor == ftsz_anchor
        if not same_completion:
            reasons.append(
                f"window_anchor mismatch: cytokinesis={cyt_anchor!r} ftsz={ftsz_anchor!r} "
                "(both taps must end at the same real geometry pinchedDiameter completion tick)"
            )

    provider_match = False
    cyt_provider_sha = None
    ftsz_provider_sha = None
    if cyt_path.exists() and ftsz_path.exists():
        cyt_provider_sha = _read_metadata_string(cyt_path, "mnrnd_provider_sha256")
        ftsz_provider_sha = _read_metadata_string(ftsz_path, "mnrnd_provider_sha256")
        provider_match = (
            cyt_provider_sha is not None and cyt_provider_sha == ftsz_provider_sha
        )
        if not provider_match:
            reasons.append(
                f"mnrnd_provider_sha256 mismatch: cytokinesis={cyt_provider_sha!r} "
                f"ftsz={ftsz_provider_sha!r} (both taps must have come from the same "
                "single karr_bootstrap() call)"
            )

    # Full-simulation source-hash binding (decisions/dec-005, 2026-09-04):
    # both taps must report the SAME dnadamage_source_resolved_sha256 (proof
    # they came from the same single karr_bootstrap() call's overlay
    # resolution, exactly mirroring the mnrnd_provider_sha256 check above).
    # Missing metadata on either side fails closed (never silently treated
    # as "no check needed") -- a pre-fix trace lacking this metadata is
    # exactly the failure mode this binding exists to catch.
    dnadamage_match = False
    cyt_dnadamage_sha = None
    ftsz_dnadamage_sha = None
    if cyt_path.exists() and ftsz_path.exists():
        cyt_dnadamage_sha = _read_metadata_string(cyt_path, "dnadamage_source_resolved_sha256")
        ftsz_dnadamage_sha = _read_metadata_string(ftsz_path, "dnadamage_source_resolved_sha256")
        dnadamage_match = (
            cyt_dnadamage_sha is not None and cyt_dnadamage_sha == ftsz_dnadamage_sha
        )
        if not dnadamage_match:
            reasons.append(
                f"dnadamage_source_resolved_sha256 mismatch or missing: cytokinesis={cyt_dnadamage_sha!r} "
                f"ftsz={ftsz_dnadamage_sha!r} (both taps must have resolved the same DNADamage.m source "
                "from the same single karr_bootstrap() call -- decisions/dec-005)"
            )

    # Provisional-margin gate (Opus final review, 2026-09-04): the real
    # inclusive onset-to-completion span (completion - onset + 1) must
    # leave a strictly positive margin against CYTOKINESIS_N_TICKS --
    # a zero-or-negative margin fails closed here even though the MATLAB
    # extractor's own capture invariant (unchanged) would have allowed
    # exactly-M_ticks. Only computed when Cytokinesis's own file exists
    # and independently validated (cyt_valid): a file that already fails
    # cyt_valid may not even have a reliable onset_tick to read.
    margin_ok = False
    cyt_onset = None
    inclusive_span: int | None = None
    if cyt_path.exists():
        cyt_onset = _read_metadata_int(cyt_path, "onset_tick")
        if cyt_onset is not None and cyt_anchor is not None:
            inclusive_span = cyt_anchor - cyt_onset + 1
            try:
                division_window_spec.check_inclusive_span_margin(cyt_onset, cyt_anchor, CYTOKINESIS_N_TICKS)
                margin_ok = True
            except division_window_spec.ProvisionalMarginOverrunError as exc:
                margin_ok = False
                reasons.append(f"provisional-margin gate: {exc}")
        else:
            reasons.append(
                "provisional-margin gate: missing onset_tick or window_anchor metadata -- "
                "cannot evaluate margin"
            )

    status = (
        "PASS"
        if (
            cyt_valid
            and ftsz_valid
            and distinct_paths
            and distinct_content
            and same_completion
            and provider_match
            and dnadamage_match
            and margin_ok
        )
        else "FAIL"
    )

    return DualDivisionCanaryReport(
        seed=seed,
        cytokinesis_path=str(cyt_path),
        ftsz_path=str(ftsz_path),
        cytokinesis_valid=cyt_valid,
        cytokinesis_reason=cyt_reason,
        ftsz_valid=ftsz_valid,
        ftsz_reason=ftsz_reason,
        distinct_paths=distinct_paths,
        distinct_content=distinct_content,
        same_completion_tick=same_completion,
        cytokinesis_window_anchor=cyt_anchor,
        ftsz_window_anchor=ftsz_anchor,
        provider_sha256_match=provider_match,
        cytokinesis_provider_sha256=cyt_provider_sha,
        ftsz_provider_sha256=ftsz_provider_sha,
        dnadamage_source_match=dnadamage_match,
        cytokinesis_dnadamage_source_sha256=cyt_dnadamage_sha,
        ftsz_dnadamage_source_sha256=ftsz_dnadamage_sha,
        margin_ok=margin_ok,
        cytokinesis_onset_tick=cyt_onset,
        inclusive_span_ticks=inclusive_span,
        cytokinesis_sha256=cyt_sha,
        ftsz_sha256=ftsz_sha,
        status=status,
        reasons=reasons,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--karr-native-root", type=Path, default=None)
    args = parser.parse_args(argv)

    report = validate_dual_division_canary(args.seed, karr_native_root=args.karr_native_root)
    print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    return 0 if report.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
