"""Standalone, RepInit-scoped trace-identity verification.

fix(l2.2): RepInit M-aware trace identity, current-main-safe closure.

This test file exists because the previous integration attempt
(`fix/l22-repinit-m-aware`, see STATUS_l22_repinit_m_aware.md in that
worktree) closed ReplicationInitiation's L2.2 gate by editing
`tests/vivarium/_l2_2_design_a_runner_helpers.py` /
`l2_2_design_a_runner.py` to make trace-path resolution catalog-M-aware.
Both files are universally-hashed `SWEEP_PROVENANCE_SOURCE_FILES`
dependencies of EVERY `design_a_per_tick` process (verified: applying
only those two files' edits atop a separately-clean main checkout
reproduces the exact same PASS:18->2 collapse with no other change) --
so that fix, while scientifically correct, was not integration-safe: it
would stale DNAS and all 17 other currently-PASSING rows.

THIS closure takes a different, zero-shared-file-edit path instead:

1. `_v2_seed_mat_path`/`_v2_canonical_seed0_mat_path`/`load_karr_oracle`
   in `_l2_2_design_a_runner_helpers.py` are BYTE-IDENTICAL to published
   main (`543c737`) -- confirmed by this test's own
   `test_shared_runner_helper_files_are_byte_identical_to_published_main`
   below. No process's sentinel is affected by this closure.
2. RepInit's genuine 50-seed x 200-tick evidence lives at the standard,
   UNMODIFIED `per_process_traces_v2_s{NNN}/ReplicationInitiation_100ticks.mat`
   discovery path (seeds 0-49) -- the historical hardcoded `_100ticks.mat`
   literal, which the unmodified loader has always expected. The genuine
   per-seed .mat files' OWN internal `metadata/n_ticks` is 200 (verified
   below); the FILENAME token `100ticks` is a KNOWN, DISCLOSED legacy
   artifact of not touching the shared resolver -- it is NEVER treated as
   authoritative by this test or by any human/reviewer reading this file.
   Real identity is enforced here via metadata + actual per-tick channel
   array length + catalog `M_ticks`, independently of the filename.
3. The canonical L2.1 100-tick trace lives at the UNSUFFIXED
   `per_process_traces_v2/ReplicationInitiation_100ticks.mat` path (seed
   0's canonical slot). Because `_v2_seed_mat_path` unconditionally
   prefers the canonical unsuffixed file over any suffixed `_s000/`
   alternative for seed 0 (see that function's own docstring), that path
   MUST NOT be used as one of RepInit's 50 L2.2 seeds -- if it were, the
   loader would either silently pick up the wrong (100-tick, L2.1) trace
   for "seed 0" or hard-fail on a tick-count-drift schema mismatch,
   exactly the failure mode that originally demoted this row. This
   closure uses the SUFFIXED `per_process_traces_v2_s001/...s049/`
   directories for seeds 1-49 (never the unsuffixed slot), so those 49
   seeds and L2.1's canonical trace coexist at disjoint, non-colliding
   paths with zero code change.
3b. Seed 0 specifically cannot use the suffixed `_s000/` fallback either:
   `_v2_seed_mat_path`'s seed-0 branch unconditionally prefers the
   canonical unsuffixed file whenever it exists, and hard-fails
   (`ValueError: Seed-0 conflict`) if a differing suffixed `_s000/` file
   ALSO exists -- so the two cannot both sit at their natural discovery
   paths at once. This closure's worktree therefore keeps its RESTING
   state as: canonical L2.1 trace present at the unsuffixed path (so
   L2.1 tests pass and seed 0 resolves there, per
   `test_resting_state_seed0_resolves_to_canonical_l21_trace_not_archived_data`),
   and the genuine, hash-verified seed-0 200-tick L2.2 trace ARCHIVED
   (not deleted) at
   `per_process_traces_v2_l22_repinit_seed0_archived/ReplicationInitiation_200ticks_genuine.mat`.
   The tracked L2.2 evidence for RepInit was genuinely generated using
   this seed-0 file (at its natural `_s000/` path, with the canonical
   trace temporarily absent) plus seeds 1-49; regenerating it requires
   repeating that same temporary swap (see
   `test_regenerating_l22_evidence_requires_temporarily_moving_canonical_aside`,
   which mechanically proves the fail-closed behavior if the swap is
   skipped, and STATUS_l22_repinit_m_aware_current.md for the exact
   procedure).

Fail-closed identity enforced below, per seed file actually used to
GENERATE the tracked evidence: catalog `M_ticks` (read live from
`PROCESS_CATALOG.yaml`, never hardcoded) == `metadata/n_ticks` == actual
per-tick channel array count, for every one of the 50 files, plus the
seed-1-to-49-collision regression guard (2) and a genuine independent
re-hash of every file used
(never trusting a previously-recorded hash).
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402

_PROCESS_NAME = "ReplicationInitiation"
_CATALOG_PATH = _REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
_N_SEEDS = 50

# The two shared files this closure deliberately leaves untouched. Hashes
# recorded here are those of published main `543c737` (the base this
# integration branch was created from) -- NOT asserted as unchanging
# forever (a legitimate unrelated future edit to these files is expected
# eventually), but as a strong, reviewable regression guard for THIS
# specific commit: if this test starts failing because these files
# changed, that is real, actionable information (either this closure
# accidentally touched them, or main moved on and this pin needs a
# deliberate, disclosed refresh), never a reason to silently update the
# pin without investigating which case it is.
_RUNNER_SCRIPT = _REPO_ROOT / "tests" / "vivarium" / "l2_2_design_a_runner.py"
_RUNNER_HELPERS_MODULE = _REPO_ROOT / "tests" / "vivarium" / "_l2_2_design_a_runner_helpers.py"
_PUBLISHED_MAIN_BASE_SHA = "543c737ebf51a0f190fa434b170360ca5ecd5a3d"
_EXPECTED_RUNNER_SCRIPT_SHA256 = "5cd107f5e64b252dbe4b2bc41b493d2687450636e5b69e976d3571337422abee"
_EXPECTED_RUNNER_HELPERS_SHA256 = "e26d8dd573ae7d9670778e6c78c61d1bd56cd2273ae960ae66b25aeb34b8138a"


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _catalog_m_ticks(process_name: str) -> int:
    document = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8"))
    for entry in document.get("processes") or ():
        if isinstance(entry, dict) and entry.get("name") == process_name:
            return int(entry["M_ticks"])
    raise AssertionError(f"{process_name} not found in {_CATALOG_PATH}")


def _canonical_l21_path() -> Path:
    return (
        _REPO_ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces_v2"
        / f"{_PROCESS_NAME}_100ticks.mat"
    )


def _archived_seed0_path() -> Path:
    return (
        _REPO_ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces_v2_l22_repinit_seed0_archived"
        / "ReplicationInitiation_200ticks_genuine.mat"
    )


def _generation_time_seed_paths() -> list[Path]:
    """The 50 paths actually used to GENERATE the tracked L2.2 evidence:
    the archived seed-0 file (see module docstring point 3b) plus the 49
    live-discoverable suffixed seeds 1-49. This is NOT the same as calling
    `_v2_seed_mat_path` for seed 0 in the worktree's current resting state
    (canonical restored, seed-0 archived) -- see
    `test_resting_state_seed0_no_longer_resolves_to_archived_l22_data`."""
    return [_archived_seed0_path()] + [
        runner_helpers._v2_seed_mat_path(_PROCESS_NAME, seed) for seed in range(1, _N_SEEDS)
    ]


def test_catalog_m_ticks_is_200_for_replication_initiation() -> None:
    assert _catalog_m_ticks(_PROCESS_NAME) == 200


def test_shared_runner_helper_files_are_byte_identical_to_published_main() -> None:
    """This closure's entire safety argument depends on this being true.
    Fails loudly (not silently) if `_l2_2_design_a_runner_helpers.py` or
    `l2_2_design_a_runner.py` differ from what published main `543c737`
    had -- i.e. if this integration accidentally touched either file."""
    assert _RUNNER_SCRIPT.is_file()
    assert _RUNNER_HELPERS_MODULE.is_file()
    runner_hash = _sha256_file(_RUNNER_SCRIPT)
    helpers_hash = _sha256_file(_RUNNER_HELPERS_MODULE)
    assert runner_hash == _EXPECTED_RUNNER_SCRIPT_SHA256, (
        f"tests/vivarium/l2_2_design_a_runner.py sha256 changed from the published-main "
        f"({_PUBLISHED_MAIN_BASE_SHA}) baseline ({_EXPECTED_RUNNER_SCRIPT_SHA256}) to "
        f"{runner_hash}. This closure MUST NOT edit this shared, universally-hashed file; "
        "if it changed for a legitimate unrelated reason, refresh this pin deliberately "
        "and re-verify the full 18-row board, never just silently update it here."
    )
    assert helpers_hash == _EXPECTED_RUNNER_HELPERS_SHA256, (
        f"tests/vivarium/_l2_2_design_a_runner_helpers.py sha256 changed from the "
        f"published-main ({_PUBLISHED_MAIN_BASE_SHA}) baseline "
        f"({_EXPECTED_RUNNER_HELPERS_SHA256}) to {helpers_hash}. This closure MUST NOT "
        "edit this shared, universally-hashed file; if it changed for a legitimate "
        "unrelated reason, refresh this pin deliberately and re-verify the full "
        "18-row board, never just silently update it here."
    )


def test_seeds_1_to_49_never_resolve_to_the_canonical_unsuffixed_l21_path() -> None:
    """Regression guard for the exact incident this closure fixes: seeds
    1-49 must all resolve to SUFFIXED `_s0NN/` directories, never the
    unsuffixed canonical path L2.1's 100-tick trace also lives at. (Seed 0
    is handled separately -- see the two tests below -- because the
    unmodified resolver's seed-0 special-casing structurally cannot
    discover BOTH the canonical L2.1 trace and a same-named 200-tick L2.2
    trace at once; see module docstring point 3.)"""
    canonical = _canonical_l21_path()
    for seed in range(1, _N_SEEDS):
        path = runner_helpers._v2_seed_mat_path(_PROCESS_NAME, seed)
        assert path != canonical
        assert path.parent.name == f"per_process_traces_v2_s{seed:03d}", (
            f"seed {seed} unexpectedly resolved outside its own suffixed directory: {path}"
        )


def test_resting_state_seed0_resolves_to_canonical_l21_trace_not_archived_data() -> None:
    """In this worktree's RESTING state (canonical L2.1 trace present,
    genuine L2.2 seed-0 data archived aside -- see module docstring point
    3b), the unmodified resolver's seed-0 special case correctly returns
    the CANONICAL L2.1 trace, never a stale/silent read of the archived
    L2.2 file. This is the direct, load-bearing proof that L2.1 and this
    closure's L2.2 evidence do not collide in the committed resting
    state."""
    canonical = _canonical_l21_path()
    if not canonical.exists():
        pytest.skip("Canonical L2.1 trace not present on this machine/checkout.")
    resolved = runner_helpers._v2_seed_mat_path(_PROCESS_NAME, 0)
    assert resolved == canonical


def test_regenerating_l22_evidence_requires_temporarily_moving_canonical_aside() -> None:
    """Documents and mechanically proves the operational constraint this
    closure's design accepts: as long as the canonical L2.1 trace sits at
    the unsuffixed path, a full range(0..49) sweep re-run for RepInit
    reads a 100-tick, 4-channel trace for seed 0 and genuine 200-tick,
    6-channel traces for seeds 1-49, and MUST fail closed (never silently
    succeed with mixed schemas/depths) via `_load_seeded_mat_channels`'s
    schema-drift (channel-set mismatch) or tick-count-drift check -- in
    practice the schema check fires first, since it runs before any
    channel data is loaded. To regenerate this evidence, the canonical
    trace must be moved aside first (see
    STATUS_l22_repinit_m_aware_current.md), exactly as this closure's own
    generation run did."""
    canonical = _canonical_l21_path()
    if not canonical.exists():
        pytest.skip("Canonical L2.1 trace not present on this machine/checkout.")
    _skip_if_raw_data_absent_for_seeds_1_to_49()
    seed_paths = [runner_helpers._v2_seed_mat_path(_PROCESS_NAME, seed) for seed in range(_N_SEEDS)]
    assert seed_paths[0] == canonical
    with pytest.raises(ValueError, match="Schema drift|Tick-count drift"):
        runner_helpers._load_seeded_mat_channels(seed_paths, process_name=_PROCESS_NAME)


def _skip_if_raw_data_absent_for_seeds_1_to_49() -> None:
    paths = [runner_helpers._v2_seed_mat_path(_PROCESS_NAME, seed) for seed in range(1, _N_SEEDS)]
    if not all(p.exists() for p in paths):
        pytest.skip(
            "Genuine gitignored RepInit raw seed traces are not present on this "
            "machine/checkout; this is a local-evidence verification test, not a "
            "CI-portable one."
        )


def test_all_50_repinit_seed_traces_have_genuine_200_tick_identity() -> None:
    """Fail-closed three-way check per seed file actually used to GENERATE
    the tracked evidence (archived seed 0 + live seeds 1-49): catalog
    M_ticks == metadata/n_ticks == actual per-tick channel array length.
    The filename token (`_100ticks.mat`/`_200ticks_genuine.mat`, legacy/
    archival naming -- see module docstring) is deliberately NOT part of
    this check; it is not authoritative and this test exists precisely so
    a human/reviewer never has to rely on it."""
    _skip_if_raw_data_absent_for_seeds_1_to_49()
    if not _archived_seed0_path().exists():
        pytest.skip("Archived genuine seed-0 L2.2 trace not present on this machine/checkout.")
    catalog_m = _catalog_m_ticks(_PROCESS_NAME)
    assert catalog_m == 200
    for seed, path in enumerate(_generation_time_seed_paths()):
        with h5py.File(path, "r") as handle:
            assert "metadata" in handle and "n_ticks" in handle["metadata"], (
                f"seed {seed} trace {path} has no metadata/n_ticks field."
            )
            metadata_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
            assert metadata_ticks == catalog_m, (
                f"seed {seed} trace {path}: metadata/n_ticks={metadata_ticks} != "
                f"catalog M_ticks={catalog_m}."
            )
            for section in ("states_before", "states_after"):
                group = handle[section]
                assert "substrates" in group, f"seed {seed} {path} missing {section}/substrates"
                ds = group["substrates"]
                actual_ticks = ds.shape[1] if ds.shape[0] == 1 else ds.shape[0]
                assert actual_ticks == catalog_m, (
                    f"seed {seed} trace {path} {section}/substrates has {actual_ticks} "
                    f"tick entries, catalog requires {catalog_m}."
                )


def test_canonical_l21_trace_preserved_and_untouched() -> None:
    """The canonical L2.1 100-tick trace must exist, be genuinely 100
    ticks, and match the accepted sha256 -- untouched by this closure."""
    canonical = _canonical_l21_path()
    if not canonical.exists():
        pytest.skip(
            "Canonical L2.1 trace not present on this machine/checkout at this "
            "moment (this closure intentionally keeps it ABSENT while regenerating "
            "L2.2 evidence, then restores it -- see module docstring point 3 and "
            "STATUS_l22_repinit_m_aware_current.md). Re-run after restoration."
        )
    expected_sha256 = "0c61c816e3903e771550e674db36fedaa76a546687891a99e46f163703550c0f"
    actual_sha256 = _sha256_file(canonical)
    assert actual_sha256 == expected_sha256, (
        f"Canonical L2.1 trace {canonical} sha256 {actual_sha256} does not match "
        f"the accepted {expected_sha256} -- it has changed or been replaced."
    )
    with h5py.File(canonical, "r") as handle:
        n_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100
