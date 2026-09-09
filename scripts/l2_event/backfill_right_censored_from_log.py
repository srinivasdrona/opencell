"""Backfill a mechanically source-bound RIGHT_CENSORED
``division_window_attempt.json`` from a PRESERVED MATLAB job log, for a
seed whose real right-censoring attempt predates this session's
attempt-record writer (``scripts/matlab/extract_dual_division_window.m``'s
``write_division_window_attempt_record``).

WHY THIS EXISTS

Two seeds (6 and 18) are known to have run a real
``extract_dual_division_window(seed, struct('max_search_ticks', 100000))``
attempt whose MATLAB stdout/stderr log survives on disk
(``artifacts/seed{N}_100k_probe.log``/``.status`` in the relevant worker
worktree) but which never wrote a ``division_window_attempt.json`` sidecar
(that writer did not exist yet when those runs executed). Per this task's
explicit "never fabricate" rule, this module does NOT invent a censor
record from prose/plan.md narrative alone -- it only accepts a real,
parseable log whose:

* exact extractor error text (``seed N: division-completion signal did
  not fire within max_search_ticks=M ticks``) names the SAME seed and a
  ``max_search_ticks`` equal to the CURRENT selection-contract horizon;
* referenced DNADamage source overlay file (the log's own
  ``[karr_bootstrap] using generated DNADamage overlay: <path>`` line)
  still exists on disk and independently hashes (LF-normalized SHA-256,
  the SAME algorithm ``scripts.l2_event.launcher.lf_normalized_sha256_hex``
  uses) to BYTE-IDENTICAL agreement with the CURRENT worktree's
  dec-005-resolved patched DNADamage source
  (``launcher.current_genuine_dnadamage_source()['patched_sha256_lf_normalized']``);
* referenced mnrnd provider line (``[karr_bootstrap] mnrnd provider:
  <path> (<release>, toolbox <version>)``) names the SAME path/release/
  toolbox version as the CURRENT genuine provider
  (``launcher.current_genuine_mnrnd_provider()``).

If ANY of these checks fails, :class:`BackfillEvidenceError` is raised --
this module NEVER falls back to writing a record anyway. A seed whose log
does not meet this bar (e.g. seed 6, whose probe was still RUNNING as of
this task) must be re-attempted through the normal extractor instead;
see ``docs/phase_f/l2_event/DIVISION_WINDOW_MIGRATION.md`` for the exact
command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import launcher  # noqa: E402
from scripts.l2_event.division_cohort_selector import (  # noqa: E402
    RIGHT_CENSORED,
    CohortContractError,
    event_window_dir,
)
from scripts.l2_event.division_window_spec import (  # noqa: E402
    attempt_record_filename,
    selection_horizon_max_search_ticks,
)
from scripts.l2_event.evidence import _translate_windows_gitdir  # noqa: E402
from scripts.l2_event.validate_dual_division_canary import (  # noqa: E402
    CYTOKINESIS_N_TICKS,
    FTSZ_N_TICKS,
)

_ERROR_PATTERN = re.compile(
    r"seed (\d+): division-completion signal did not fire within max_search_ticks=(\d+) ticks"
)
_OVERLAY_LINE_PATTERN = re.compile(r"\[karr_bootstrap\] using generated DNADamage overlay: (.+)")
_MNRND_LINE_PATTERN = re.compile(
    r"\[karr_bootstrap\] mnrnd provider: (.+?) \((\S+), toolbox ([\d.]+)\)"
)
# karr_bootstrap.m's own log line names the overlay's "src" ROOT directory
# (e.g. ".../tmp/wcm_source_overlay/src"), not the DNADamage.m file itself
# -- mirrors launcher._DNADAMAGE_SOURCE_RELATIVE_PATH's tail (everything
# after the "src" component, since the logged root already IS that "src"
# directory).
_DNADAMAGE_RELATIVE_PATH_UNDER_SRC = (
    Path("+edu") / "+stanford" / "+covert" / "+cell" / "+sim" / "+process" / "DNADamage.m"
)


class BackfillEvidenceError(Exception):
    """Raised when the preserved log/overlay evidence is insufficient to
    mechanically bind a source-identity-verified RIGHT_CENSORED record.
    Never silently degraded to a fabricated record -- callers must treat
    this as "leave the gap open, provide the reattempt command", never
    "write something anyway"."""


@dataclass(frozen=True)
class ParsedCensorEvidence:
    seed: int
    max_search_ticks: int
    overlay_path: Path
    mnrnd_provider_path: str
    mnrnd_release: str
    mnrnd_toolbox_version: str
    error_text: str
    log_path: Path


def parse_right_censored_log(log_path: Path) -> ParsedCensorEvidence:
    """Extract the seed/horizon/overlay-source/mnrnd-provider identity a
    preserved MATLAB job log records for a real
    ``extract_dual_division_window`` right-censoring attempt. Raises
    :class:`BackfillEvidenceError` if any required line is absent --
    never returns a partial/best-effort result."""
    if not log_path.is_file():
        raise BackfillEvidenceError(f"log file does not exist: {log_path}")
    text = log_path.read_text(encoding="utf-8", errors="replace")

    error_match = _ERROR_PATTERN.search(text)
    if error_match is None:
        raise BackfillEvidenceError(
            f"{log_path}: does not contain the expected 'seed N: division-completion signal did "
            "not fire within max_search_ticks=M ticks' error text -- this is not a genuine "
            "right-censoring log (or the extractor's error wording has changed)"
        )
    seed = int(error_match.group(1))
    max_search_ticks = int(error_match.group(2))

    overlay_match = _OVERLAY_LINE_PATTERN.search(text)
    if overlay_match is None:
        raise BackfillEvidenceError(
            f"{log_path}: no '[karr_bootstrap] using generated DNADamage overlay: ...' line found -- "
            "cannot mechanically bind the DNADamage source identity used for this run"
        )
    overlay_root_raw = overlay_match.group(1).strip()
    if os.name != "nt":
        # This process is running under WSL/Linux (bin/oc-py's canonical
        # execution environment); the log's overlay path was written by a
        # Windows-hosted MATLAB process and is a Windows absolute path --
        # translate it to the equivalent /mnt/<drive>/... mount path
        # before checking existence, mirroring evidence.py's identical
        # gitdir-path translation need.
        translated = _translate_windows_gitdir(overlay_root_raw)
        overlay_root = Path(translated) if translated is not None else Path(overlay_root_raw)
    else:
        overlay_root = Path(overlay_root_raw)
    overlay_path = overlay_root / _DNADAMAGE_RELATIVE_PATH_UNDER_SRC

    mnrnd_match = _MNRND_LINE_PATTERN.search(text)
    if mnrnd_match is None:
        raise BackfillEvidenceError(
            f"{log_path}: no '[karr_bootstrap] mnrnd provider: ...' line found -- cannot bind the "
            "genuine RNG provider identity used for this run"
        )

    return ParsedCensorEvidence(
        seed=seed,
        max_search_ticks=max_search_ticks,
        overlay_path=overlay_path,
        mnrnd_provider_path=mnrnd_match.group(1).strip(),
        mnrnd_release=mnrnd_match.group(2).strip(),
        mnrnd_toolbox_version=mnrnd_match.group(3).strip(),
        error_text=error_match.group(0),
        log_path=log_path,
    )


def verify_evidence(evidence: ParsedCensorEvidence) -> dict[str, object]:
    """Independently re-verify every claim :func:`parse_right_censored_log`
    extracted against the CURRENT run's genuine identity. Raises
    :class:`BackfillEvidenceError` on any mismatch; returns the verified
    ``dnadamage_source_resolved_sha256``/``mnrnd_provider_sha256`` values
    to embed in the backfilled record on success."""
    required_horizon = selection_horizon_max_search_ticks()
    if evidence.max_search_ticks != required_horizon:
        raise BackfillEvidenceError(
            f"{evidence.log_path}: log's max_search_ticks={evidence.max_search_ticks} != required "
            f"selection-contract horizon {required_horizon} -- cannot certify this as a valid "
            "censor under the current contract"
        )

    if not evidence.overlay_path.is_file():
        raise BackfillEvidenceError(
            f"referenced overlay source file no longer exists on disk: {evidence.overlay_path} -- "
            "cannot independently verify the DNADamage source identity used for this run"
        )
    recorded_overlay_sha = launcher.lf_normalized_sha256_hex(evidence.overlay_path)
    expected_dnadamage_sha = launcher.current_genuine_dnadamage_source()["patched_sha256_lf_normalized"]
    if recorded_overlay_sha != expected_dnadamage_sha:
        raise BackfillEvidenceError(
            f"overlay source at {evidence.overlay_path} hashes to {recorded_overlay_sha}, which does "
            f"NOT match the current dec-005-resolved patched DNADamage source "
            f"{expected_dnadamage_sha} -- this run is not comparable evidence about the current model"
        )

    current_mnrnd = launcher.current_genuine_mnrnd_provider()
    current_provider_path = str(launcher.genuine_mnrnd_path())
    logged_provider_path = evidence.mnrnd_provider_path
    if os.name != "nt":
        # Same Windows-vs-WSL path-form mismatch as the overlay path above
        # -- the log's provider path was written by a Windows-hosted
        # MATLAB process, but launcher.genuine_mnrnd_path() (running here
        # under WSL/Linux) resolves to a /mnt/<drive>/... path.
        translated = _translate_windows_gitdir(logged_provider_path)
        if translated is not None:
            logged_provider_path = translated
    if (
        logged_provider_path != current_provider_path
        or evidence.mnrnd_release != current_mnrnd["matlab_release"]
        or evidence.mnrnd_toolbox_version != current_mnrnd["toolbox_version"]
    ):
        raise BackfillEvidenceError(
            f"log's mnrnd provider ({logged_provider_path}, {evidence.mnrnd_release}, "
            f"toolbox {evidence.mnrnd_toolbox_version}) does not match the current genuine provider "
            f"({current_provider_path}, {current_mnrnd['matlab_release']}, toolbox "
            f"{current_mnrnd['toolbox_version']}) -- cannot bind the RNG provider identity"
        )

    return {
        "dnadamage_source_resolved_sha256": recorded_overlay_sha,
        "mnrnd_provider_sha256": current_mnrnd["sha256_lf_normalized"],
    }


def build_attempt_record(evidence: ParsedCensorEvidence, verified_identity: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "seed": evidence.seed,
        "status": RIGHT_CENSORED,
        "max_search_ticks": evidence.max_search_ticks,
        "extractor": "extract_dual_division_window",
        "recorded_at": None,
        "mnrnd_provider_sha256": verified_identity["mnrnd_provider_sha256"],
        "dnadamage_source_resolved_sha256": verified_identity["dnadamage_source_resolved_sha256"],
        "cytokinesis_n_ticks": CYTOKINESIS_N_TICKS,
        "ftsz_n_ticks": FTSZ_N_TICKS,
        "onset_tick": None,
        "completion_tick": None,
        "cytokinesis_trace_sha256": None,
        "ftsz_trace_sha256": None,
        "reason": evidence.error_text,
        "backfilled_from_log": str(evidence.log_path),
        "backfill_tool": "scripts/l2_event/backfill_right_censored_from_log.py",
    }


def backfill_right_censored_seed(
    log_path: Path, *, karr_native_root: Path, force: bool = False
) -> Path:
    """The single write entry point: parse+verify ``log_path``, then
    atomically write the resulting RIGHT_CENSORED
    ``division_window_attempt.json`` into
    ``karr_native_root/per_process_traces_v2_event_s{seed:03d}/``. Refuses
    (raises :class:`CohortContractError`) if that seed directory already
    has either trace file (mutual exclusivity) or an existing attempt
    record (unless ``force=True``). Never touches any ``.mat`` file."""
    evidence = parse_right_censored_log(log_path)
    verified_identity = verify_evidence(evidence)
    record = build_attempt_record(evidence, verified_identity)

    out_dir = event_window_dir(evidence.seed, karr_native_root=karr_native_root)
    cyt_path = out_dir / f"Cytokinesis_{CYTOKINESIS_N_TICKS}ticks.mat"
    ftsz_path = out_dir / f"FtsZPolymerization_{FTSZ_N_TICKS}ticks.mat"
    if cyt_path.exists() or ftsz_path.exists():
        raise CohortContractError(
            f"seed {evidence.seed}: refusing to backfill a RIGHT_CENSORED record at {out_dir} -- "
            f"a trace file already exists there (cytokinesis={cyt_path.exists()}, "
            f"ftsz={ftsz_path.exists()}); mutual exclusivity would be violated"
        )
    record_path = out_dir / attempt_record_filename()
    if record_path.exists() and not force:
        raise CohortContractError(
            f"seed {evidence.seed}: an attempt record already exists at {record_path} -- refusing "
            "to overwrite; pass force=True to explicitly replace it after review"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = out_dir / f".tmp-backfill-{attempt_record_filename()}"
    tmp_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(record_path)
    return record_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-path", type=Path, required=True, help="Preserved MATLAB job log to backfill from.")
    parser.add_argument(
        "--karr-native-root", type=Path, required=True, help="karr_native root to write the record into."
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing attempt record.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Parse and verify only; print the record but do not write it."
    )
    args = parser.parse_args(argv)

    evidence = parse_right_censored_log(args.log_path)
    verified_identity = verify_evidence(evidence)
    record = build_attempt_record(evidence, verified_identity)
    print(json.dumps(record, indent=2, sort_keys=True))
    if args.dry_run:
        print("[backfill] --dry-run: not writing any file.")
        return 0

    record_path = backfill_right_censored_seed(
        args.log_path, karr_native_root=args.karr_native_root, force=args.force
    )
    print(f"[backfill] wrote {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
