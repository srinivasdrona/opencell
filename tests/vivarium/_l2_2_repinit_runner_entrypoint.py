"""ReplicationInitiation-specific Design-A L2.2 runner entrypoint (R12).

Context (2026-09 RepInit M-aware closure, integration-review round 3):
the OFFICIAL evidence-generation path (`sweep.py run` -> `l2_2_design_a_
runner.py`'s CLI `--ticks`/`--m-ticks` argument -> `run_design_a(...,
m_ticks=...)`) never validated the REQUESTED tick count against anything
before evaluating: `run_design_a` calls `runner_helpers.load_karr_oracle
(process)` with NO `m_ticks` argument at all, then `_normalize_seed_axis`
silently SLICES whatever the oracle returned down to the requested
`m_ticks` -- a no-op when the two happen to agree, but a SILENT
TRUNCATION when they do not. Round 2's identity guard
(`_l2_2_repinit_runner_helpers.repinit_v2_seed_mat_path`) validates every
on-disk trace file's OWN internal identity (filename == metadata ==
catalog M_ticks == channel tick dimension) but has no way to see what
tick count the CALLER actually requested via `--ticks` -- so an operator
invoking the ordinary runner with `--process ReplicationInitiation
--ticks 100` (RepInit's catalog M_ticks is 200) would silently evaluate a
truncated, non-catalog-conformant 100-tick slice of the genuine 200-tick
oracle and produce a fake, meaningless verdict, with nothing anywhere
failing closed.

This module closes that gap for the OFFICIAL evidence-generation path
specifically: it is a thin, process-specific entrypoint that parses the
SAME CLI (`--process`/`--seeds`/`--ticks`/`--m-ticks`/`--output-dir`/
`--out`/`--thresholds`/`--bootstrap-B`) `l2_2_design_a_runner.py` itself
accepts, but BEFORE doing anything else -- before any oracle file is
opened, before any simulation tick runs -- validates:
  - `--process` is literally `"ReplicationInitiation"` (this entrypoint
    refuses to run for any other process, even though `sweep.py` only
    ever routes ReplicationInitiation jobs here -- defense in depth, not
    trust in the caller), and
  - the requested `--ticks`/`--m-ticks` value EXACTLY equals
    `PROCESS_CATALOG.yaml`'s live `ReplicationInitiation` `M_ticks` entry
    (read fresh every invocation via `_l2_2_repinit_runner_helpers.
    _catalog_m_ticks`, never hardcoded).
Only if BOTH hold does it delegate -- via a plain in-process function
call, `l2_2_design_a_runner.main(argv)`, with the EXACT SAME argv it was
given -- to the ordinary, otherwise-completely-unmodified shared runner.
No subprocess-within-a-subprocess: this IS the process `sweep.py`
launches for ReplicationInitiation jobs (see `sweep.runner_command`'s
per-process dispatch), so delegation is a direct Python call.

Registered as a process-specific dependency of ReplicationInitiation ONLY
(`scripts/l22_evidence/schema.py::PROCESS_DEPENDENCY_FILES
["ReplicationInitiation"]["repinit_runner_entrypoint_module"]`), mirroring
`_l2_2_repinit_runner_helpers.py`'s own registration -- editing this file
stales only ReplicationInitiation's row. `scripts/l22_evidence/sweep.py`
itself is NOT a registered/hashed dependency of ANY row (verified by
direct inspection: it appears in none of `SWEEP_PROVENANCE_SOURCE_FILES`/
`PROCESS_DEPENDENCY_FILES`/`HARNESS_DEPENDENCY_FILES`, since it is the
launcher/orchestrator, not part of the harness whose bytes the recorded
evidence is bound to), so making `sweep.runner_command` select this
entrypoint only for ReplicationInitiation requires NO migration of any
other row's provenance.

Together with round 2's on-disk identity guard, the OFFICIAL path now
mechanically establishes, before any evaluation: requested M (this
module) == catalog M_ticks (this module, and independently re-checked by
`_l2_2_repinit_runner_helpers`) == filename token == metadata/n_ticks ==
every channel's own tick dimension (both the latter two enforced by
`_l2_2_repinit_runner_helpers.repinit_v2_seed_mat_path`, including
`chromosome`, on every seed, every call).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_VIVARIUM_TESTS_DIR = Path(__file__).resolve().parent
if str(_VIVARIUM_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS_DIR))

_REPO_ROOT = _VIVARIUM_TESTS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from _l2_2_repinit_runner_helpers import _catalog_m_ticks  # noqa: E402

_PROCESS_NAME = "ReplicationInitiation"

__all__ = ["RepInitEntrypointError", "validate_requested_m", "main"]


class RepInitEntrypointError(ValueError):
    """Raised when this entrypoint is invoked for a process other than
    ReplicationInitiation, or with a requested `--ticks`/`--m-ticks` value
    that does not equal ReplicationInitiation's live catalog `M_ticks`.
    Raised BEFORE any oracle file is opened or any simulation tick runs --
    a `ValueError` subclass, handled the same way `l2_2_design_a_runner.
    main()` already handles any other `ValueError` (printed to stderr,
    exit code 2), so this entrypoint's own failures are indistinguishable
    in kind from the shared runner's pre-existing CLI-validation errors."""


def _parse_process_and_ticks(argv: list[str]) -> tuple[str | None, int | None]:
    """Extract just `--process` and `--ticks`/`--m-ticks` from `argv`
    without requiring every other argument the full runner CLI needs --
    `parse_known_args` on a minimal, permissive parser, so this pre-check
    never has to duplicate (and risk drifting from) the shared runner's
    own full `argparse` definition. Returns `(None, None)` fields for
    whichever flag is absent; `main()` decides whether that is fatal."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--process")
    parser.add_argument("--ticks", "--m-ticks", dest="ticks", type=int)
    known, _unknown = parser.parse_known_args(argv)
    return known.process, known.ticks


def validate_requested_m(argv: list[str]) -> None:
    """Fail closed (raise `RepInitEntrypointError`) unless `argv` requests
    `--process ReplicationInitiation` with a `--ticks`/`--m-ticks` value
    exactly equal to the live catalog `M_ticks`. Never truncates, never
    coerces, never silently proceeds on a partial match."""
    process, ticks = _parse_process_and_ticks(argv)
    if process != _PROCESS_NAME:
        raise RepInitEntrypointError(
            f"This entrypoint is registered ONLY for {_PROCESS_NAME!r}; got --process {process!r}."
        )
    if ticks is None:
        raise RepInitEntrypointError("--ticks/--m-ticks is required and was not provided.")
    catalog_m = _catalog_m_ticks()
    if int(ticks) != catalog_m:
        raise RepInitEntrypointError(
            f"Requested M (--ticks {ticks}) does not equal {_PROCESS_NAME!r}'s live catalog "
            f"M_ticks={catalog_m}. Refusing before any oracle loading or evaluation -- this is "
            "exactly the silent-truncation gap an independent integration review required closed "
            "(the ordinary shared runner's _normalize_seed_axis would otherwise slice the genuine "
            f"{catalog_m}-tick oracle down to {ticks} ticks without ever raising)."
        )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        validate_requested_m(args)
    except RepInitEntrypointError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    import l2_2_design_a_runner

    return l2_2_design_a_runner.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
