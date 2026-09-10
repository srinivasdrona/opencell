"""ReplicationInitiation-specific Design-A L2.2 trace resolver + identity guard.

Context (2026-09 RepInit M-aware closure, integration-review round 2):
`_l2_2_design_a_runner_helpers.py`'s generic v2 trace-path resolver
(`_v2_seed_mat_path`/`_v2_canonical_seed0_mat_path`/`_v2_suffixed_seed_mat_path`)
hardcodes `f"{process_name}_100ticks.mat"` for EVERY process -- correct for
the 17 other `design_a_per_tick` processes (catalog `M_ticks: 100`), but
ReplicationInitiation's catalog `M_ticks` is 200. A first integration
candidate placed genuine 200-tick RepInit data at that hardcoded, WRONG
`_100ticks.mat` path (relying on the generic loader never validating tick
depth) -- an independent integration review REJECTED this: the filename
token is part of this project's trace-identity contract, not a
non-authoritative legacy label, and a genuine 200-tick file must be named
`_200ticks.mat`, full stop. A second attempt made the shared, universally-
hashed `_v2_seed_mat_path`/`load_karr_oracle` itself catalog-M-aware, which
would have mechanically staled all 18 unrelated `design_a_per_tick` rows'
`sweep_provenance.json["source_hashes"]["helpers"]` at once -- exactly the
class of bug R7 (DNASupercoiling's tick-runner extraction) already fixed
for the SAME shared file, just at a different call site (oracle/trace
loading rather than per-tick execution).

This module is therefore extracted the same way DNASupercoiling's own
tick-runner was: a REGISTERED, process-specific runtime dependency of
ReplicationInitiation ONLY
(`scripts/l22_evidence/schema.py::PROCESS_DEPENDENCY_FILES
["ReplicationInitiation"]["repinit_runner_helpers_module"]`). Editing this
file changes ONLY ReplicationInitiation's provenance. `_l2_2_design_a_runner_
helpers.py`'s `load_karr_oracle()` and `_v2_seed_mat_path()` each gain a
single, minimal `if process_name == "ReplicationInitiation": return
<this module's function>(...)` redirect at their very top -- see that
module's own docstring notes at those two call sites, and
`scripts/l22_evidence/schema.py`'s "R11" section for how the redirect's own
source text is excluded from the shared, process-agnostic `"helpers"` hash
(mirroring R7's redaction of DNASupercoiling's `_tick_dispatch()` entry) so
this module (and any future change to it) stales ONLY ReplicationInitiation's
row.

Every function here resolves paths and validates identity from first
principles every time -- no caching of "trust" across calls -- and fails
CLOSED (raises `RepInitTraceIdentityError`, a `ValueError` subclass) on any
of the following:
  - the resolved path does not exist,
  - the file's name does not match `ReplicationInitiation_<N>ticks.mat`,
  - the filename's `<N>` does not equal `PROCESS_CATALOG.yaml`'s
    `ReplicationInitiation` entry's `M_ticks` (200, read fresh from disk,
    never hardcoded, so a future catalog change is honored automatically),
  - the file's own `metadata/n_ticks` does not equal that same catalog
    `M_ticks`,
  - any non-chromosome `states_before`/`states_after` channel's own tick
    dimension does not equal that same catalog `M_ticks`.
This four-way equality (filename token == metadata == catalog M_ticks ==
channel tick dimension) is exactly the anti-cheat contract an independent
integration review required; the previous (rejected) `_100ticks.mat`-named
genuine-200-tick-data candidate would trip the very first check here
(filename token 100 != catalog M_ticks 200) if anyone ever tried it again.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

_VIVARIUM_TESTS_DIR = Path(__file__).resolve().parent
if str(_VIVARIUM_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS_DIR))

_REPO_ROOT = _VIVARIUM_TESTS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_PROCESS_NAME = "ReplicationInitiation"
_KARR_NATIVE_ROOT = _REPO_ROOT / "data" / "m1_sources" / "karr_native"
_CATALOG_PATH = _REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
_FILENAME_TICKS_RE = re.compile(r"^ReplicationInitiation_(\d+)ticks\.mat$")

__all__ = [
    "RepInitTraceIdentityError",
    "repinit_v2_seed_mat_path",
    "load_replication_initiation_v2_ensemble",
]


class RepInitTraceIdentityError(ValueError):
    """Raised when a ReplicationInitiation L2.2 seed trace's filename token,
    metadata/n_ticks, catalog M_ticks, or per-channel tick dimension do not
    all mutually agree. Never silently truncated/coerced/waived."""


def _catalog_entry() -> dict[str, Any]:
    """`PROCESS_CATALOG.yaml`'s process entries live under a flat top-level
    `processes:` list (verified directly against the tracked file; `buckets:`
    is separate bucket-level metadata, not a container of process rows --
    see `l2_2_design_a_runner.py::_load_catalog_document`/`_load_catalog`,
    which reads this exact same top-level `processes:` list)."""
    document = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8"))
    for entry in document.get("processes", []) if isinstance(document, dict) else []:
        if isinstance(entry, dict) and entry.get("name") == _PROCESS_NAME:
            return entry
    raise RepInitTraceIdentityError(f"{_PROCESS_NAME!r} not found in {_CATALOG_PATH}'s 'processes:' list.")


def _catalog_m_ticks() -> int:
    entry = _catalog_entry()
    m_ticks = entry.get("M_ticks")
    if not isinstance(m_ticks, int):
        raise RepInitTraceIdentityError(
            f"PROCESS_CATALOG.yaml's {_PROCESS_NAME!r} entry has no integer M_ticks (got {m_ticks!r})."
        )
    return int(m_ticks)


def _catalog_n_seeds() -> int:
    entry = _catalog_entry()
    n_seeds = entry.get("N_seeds")
    if not isinstance(n_seeds, int):
        raise RepInitTraceIdentityError(
            f"PROCESS_CATALOG.yaml's {_PROCESS_NAME!r} entry has no integer N_seeds (got {n_seeds!r})."
        )
    return int(n_seeds)


def _channel_tick_dimension(dataset: h5py.Dataset) -> int:
    if dataset.ndim != 2 or 1 not in dataset.shape:
        raise RepInitTraceIdentityError(
            f"MATLAB trace channel {dataset.name!r} must be a 2D cell array with a "
            f"singleton axis; got shape={dataset.shape}."
        )
    return int(dataset.shape[1] if dataset.shape[0] == 1 else dataset.shape[0])


def repinit_v2_seed_mat_path(seed: int) -> Path:
    """Resolve AND validate seed `seed`'s genuine ReplicationInitiation L2.2
    trace. Never returns a path without having verified, right now, that its
    filename token, `metadata/n_ticks`, the live catalog `M_ticks`, and every
    non-chromosome channel's own tick dimension are all mutually equal.

    Seed 0 is NOT special-cased: it lives at the SAME seed-padded
    `per_process_traces_v2_s000/` path every other seed does, genuinely
    named `ReplicationInitiation_200ticks.mat` -- there is no collision
    with, dependency on, or swap involving the canonical L2.1 replay trace
    at the unsuffixed `per_process_traces_v2/ReplicationInitiation_100ticks.mat`
    path, because this function never looks there and the L2.1 harness never
    looks here.
    """
    catalog_m = _catalog_m_ticks()
    seed_dir = _KARR_NATIVE_ROOT / f"per_process_traces_v2_s{int(seed):03d}"
    path = seed_dir / f"{_PROCESS_NAME}_{catalog_m}ticks.mat"
    if not path.is_file():
        raise RepInitTraceIdentityError(
            f"Missing genuine L2.2 trace for {_PROCESS_NAME} seed {seed} at {path} "
            f"(filename must encode catalog M_ticks={catalog_m}; a differently-named "
            f"file in {seed_dir} -- e.g. a legacy '_100ticks.mat' -- is never treated "
            "as a substitute, even if its metadata claims 200 ticks internally)."
        )
    match = _FILENAME_TICKS_RE.match(path.name)
    if match is None:
        raise RepInitTraceIdentityError(
            f"{path.name!r} does not match the required "
            f"'{_PROCESS_NAME}_<N>ticks.mat' filename pattern."
        )
    filename_ticks = int(match.group(1))
    if filename_ticks != catalog_m:
        raise RepInitTraceIdentityError(
            f"Filename tick token {filename_ticks} for {path} does not equal "
            f"catalog M_ticks {catalog_m}."
        )
    with h5py.File(path, "r") as handle:
        if "metadata" not in handle or "n_ticks" not in handle["metadata"]:
            raise RepInitTraceIdentityError(f"{path} is missing metadata/n_ticks.")
        metadata_n_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
        if metadata_n_ticks != catalog_m:
            raise RepInitTraceIdentityError(
                f"{path}: metadata/n_ticks={metadata_n_ticks} does not equal catalog "
                f"M_ticks={catalog_m} (filename token and catalog otherwise agree -- this "
                "is exactly the mislabeled-file shape an earlier integration candidate "
                "used and an independent review correctly rejected)."
            )
        for section in ("states_before", "states_after"):
            if section not in handle:
                raise RepInitTraceIdentityError(f"{path} is missing the {section!r} group.")
            group = handle[section]
            for channel_name in group:
                if str(channel_name) == "chromosome":
                    # Structured sparse-triple group, validated separately by
                    # `load_chromosome_oracle_for_process`'s own tick-range read
                    # (which, for ReplicationInitiation, resolves through THIS
                    # module via `_v2_seed_mat_path`'s redirect too).
                    continue
                tick_dim = _channel_tick_dimension(group[channel_name])
                if tick_dim != catalog_m:
                    raise RepInitTraceIdentityError(
                        f"{path}: channel {section}/{channel_name} tick dimension "
                        f"{tick_dim} does not equal catalog M_ticks={catalog_m}."
                    )
    return path


def load_replication_initiation_v2_ensemble() -> dict[str, Any]:
    """Load ReplicationInitiation's genuine N=`catalog N_seeds`/
    M=`catalog M_ticks` L2.2 ensemble oracle, with every seed's identity
    independently verified by `repinit_v2_seed_mat_path` before any channel
    is stacked. Reuses the shared, process-agnostic stacking/formatting
    helpers (`_load_seeded_mat_channels`/`_format_ensemble_oracle`) via a
    deferred import -- `_l2_2_design_a_runner_helpers.py` imports THIS
    module's `load_replication_initiation_v2_ensemble` at module scope (to
    bind `_load_replication_initiation_v2_ensemble`), so importing it back
    at our own module scope would be a circular import whose success
    depends on which module a caller happens to import first; resolving it
    lazily here sidesteps that entirely (mirrors
    `_l2_2_dnas_runner_helpers.run_dna_supercoiling_tick`'s identical
    pattern)."""
    import _l2_2_design_a_runner_helpers as _shared

    catalog_m = _catalog_m_ticks()
    n_seeds = _catalog_n_seeds()
    seed_paths = [repinit_v2_seed_mat_path(seed) for seed in range(n_seeds)]
    before_channels, after_channels, n_ticks_loaded = _shared._load_seeded_mat_channels(
        seed_paths, process_name=_PROCESS_NAME
    )
    if n_ticks_loaded != catalog_m:
        raise RepInitTraceIdentityError(
            f"Stacked ensemble tick dimension {n_ticks_loaded} does not equal catalog "
            f"M_ticks={catalog_m} across the {len(seed_paths)} verified seed paths."
        )
    return _shared._format_ensemble_oracle(
        process_name=_PROCESS_NAME,
        oracle_path=seed_paths[0],
        seed_paths=seed_paths,
        before_channels=before_channels,
        after_channels=after_channels,
    )
