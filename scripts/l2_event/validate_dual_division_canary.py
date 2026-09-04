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

from scripts.l2_event import ftsz_pre_division_evidence as ftsz_evidence  # noqa: E402
from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.survey_cytokinesis_onset_span import (  # noqa: E402
    REQUIRED_OBSERVABLES as CYTOKINESIS_REQUIRED_OBSERVABLES,
)
from scripts.l2_event.window_loader import _decode_char_metadata  # noqa: E402

CYTOKINESIS_PROCESS = "Cytokinesis"
CYTOKINESIS_N_TICKS = 4000
FTSZ_PROCESS = "FtsZPolymerization"
FTSZ_N_TICKS = 200


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
    applies."""
    return launcher.AnchorWindowSpec(
        process=CYTOKINESIS_PROCESS,
        seed=seed,
        n_ticks=CYTOKINESIS_N_TICKS,
        required_observables=CYTOKINESIS_REQUIRED_OBSERVABLES,
        scalar_finite_observables=launcher.CYTOKINESIS_SCALAR_FINITE_OBSERVABLES,
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

    status = (
        "PASS"
        if (
            cyt_valid
            and ftsz_valid
            and distinct_paths
            and distinct_content
            and same_completion
            and provider_match
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
