"""Standalone, RepInit-scoped trace-identity + anti-cheat verification (R11).

fix(l2.2): RepInit M-aware trace identity, current-main-safe closure, round 2.

This test file supersedes an earlier version written for a REJECTED
integration candidate that placed genuine 200-tick ReplicationInitiation
data at the generic, hardcoded `_100ticks.mat` path (relying on the
unmodified loader never validating tick depth against the filename). An
independent integration review correctly rejected that candidate: the
filename tick token is part of this project's trace-identity contract, not
a non-authoritative legacy label, and a seed-0/canonical-trace "temporal
swap" procedure was required just to generate the evidence at all -- both
unacceptable for a durable, mechanically-verifiable candidate.

THIS closure (R11) instead:

1. Stores all 50 genuine seed traces at their ACTUAL, honest names:
   `per_process_traces_v2_s{NNN:03d}/ReplicationInitiation_200ticks.mat`
   for seeds 0-49 (including seed 0 -- no special-casing, no unsuffixed
   canonical-path involvement, no collision, no swap). The canonical L2.1
   100-tick replay trace remains independently, permanently, at the
   UNSUFFIXED `per_process_traces_v2/ReplicationInitiation_100ticks.mat`
   path; the two never share a directory or a filename.
2. Extracts ReplicationInitiation's OWN trace-path resolution + identity
   validation into a new sibling module,
   `tests/vivarium/_l2_2_repinit_runner_helpers.py`, registered as a
   process-specific dependency
   (`schema.PROCESS_DEPENDENCY_FILES["ReplicationInitiation"]
   ["repinit_runner_helpers_module"]`) exactly mirroring R7's
   DNASupercoiling tick-runner extraction. `_v2_seed_mat_path()` and
   `load_karr_oracle()` in the shared, universally-hashed
   `_l2_2_design_a_runner_helpers.py` each gain a single two-line redirect
   to this module for ReplicationInitiation ONLY -- see
   `test_shared_files_r11_delta_is_exactly_the_documented_redirect` below,
   which verifies this is the ONLY diff from published main `543c737`,
   line by line, not merely a hash claim.
3. `schema.py`'s `runner_helpers_generic_hash()` DELETES (never
   placeholders) this exact redirect scaffolding when computing the
   shared `"helpers"` provenance hash, so it is IDENTICAL whether
   evaluated against `543c737` or the current tree -- verified by
   `test_redacted_helpers_hash_unchanged_vs_published_main` below,
   the mechanical precondition `scripts/l22_evidence/
   migrate_r11_repinit_provenance.py` requires before migrating any other
   row.

Fail-closed identity enforced by `_l2_2_repinit_runner_helpers.
repinit_v2_seed_mat_path`, and independently re-verified here: filename
tick token == `metadata/n_ticks` == live `PROCESS_CATALOG.yaml` `M_ticks`
== every non-chromosome channel's own tick dimension, for every genuine
seed file, PLUS anti-cheat reproductions of the exact prior-rejected
mislabeling shape (a `_100ticks.mat`-named file with `metadata/n_ticks`
claiming 200) and its inverse (a `_200ticks.mat`-named file whose
metadata or channel data actually diverges from 200).
"""

from __future__ import annotations

import shutil
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
import _l2_2_repinit_runner_helpers as repinit_helpers  # noqa: E402

from scripts.l22_evidence import migrate_helpers_provenance as mhp  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

_PROCESS_NAME = "ReplicationInitiation"
_CATALOG_PATH = _REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"
_N_SEEDS = 50
_KARR_NATIVE_ROOT = _REPO_ROOT / "data" / "m1_sources" / "karr_native"

_RUNNER_SCRIPT = _REPO_ROOT / "tests" / "vivarium" / "l2_2_design_a_runner.py"
_RUNNER_HELPERS_MODULE = _REPO_ROOT / "tests" / "vivarium" / "_l2_2_design_a_runner_helpers.py"
_PUBLISHED_MAIN_BASE_SHA = "543c737ebf51a0f190fa434b170360ca5ecd5a3d"
# `l2_2_design_a_runner.py` is completely untouched by R11 (only the
# helpers module gets the two-line redirects).
_EXPECTED_RUNNER_SCRIPT_SHA256 = "5cd107f5e64b252dbe4b2bc41b493d2687450636e5b69e976d3571337422abee"


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_show(ref: str, rel_path: str) -> str:
    """`git show <ref>:<rel_path>` -- delegates to `migrate_helpers_
    provenance.git_show_text`, which resolves the correct `--git-dir` for
    a linked worktree (a plain `git -C <worktree> show` can fail there)."""
    return mhp.git_show_text(ref, rel_path, repo_root=_REPO_ROOT)


def _catalog_m_ticks(process_name: str) -> int:
    document = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8"))
    for entry in document.get("processes") or ():
        if isinstance(entry, dict) and entry.get("name") == process_name:
            return int(entry["M_ticks"])
    raise AssertionError(f"{process_name} not found in {_CATALOG_PATH}")


def _canonical_l21_path() -> Path:
    return _KARR_NATIVE_ROOT / "per_process_traces_v2" / f"{_PROCESS_NAME}_100ticks.mat"


def _genuine_seed_path(seed: int) -> Path:
    return _KARR_NATIVE_ROOT / f"per_process_traces_v2_s{int(seed):03d}" / f"{_PROCESS_NAME}_200ticks.mat"


def _skip_if_raw_data_absent() -> None:
    if not all(_genuine_seed_path(seed).exists() for seed in range(_N_SEEDS)):
        pytest.skip(
            "Genuine gitignored RepInit raw seed traces are not present on this "
            "machine/checkout; this is a local-evidence verification test, not a "
            "CI-portable one."
        )


# --- Catalog + shared-file isolation ----------------------------------------


def test_catalog_m_ticks_is_200_for_replication_initiation() -> None:
    assert _catalog_m_ticks(_PROCESS_NAME) == 200


def test_runner_script_is_byte_identical_to_published_main() -> None:
    """`l2_2_design_a_runner.py` (unlike the helpers module) is completely
    untouched by R11 -- no redirect of any kind lives there."""
    assert _RUNNER_SCRIPT.is_file()
    actual = _sha256_file(_RUNNER_SCRIPT)
    assert actual == _EXPECTED_RUNNER_SCRIPT_SHA256, (
        f"tests/vivarium/l2_2_design_a_runner.py sha256 changed from the published-main "
        f"({_PUBLISHED_MAIN_BASE_SHA}) baseline to {actual}. R11 never touches this file."
    )


def test_redacted_helpers_hash_unchanged_vs_published_main() -> None:
    """The mechanical precondition R11's provenance migration
    (`scripts/l22_evidence/migrate_r11_repinit_provenance.py`) depends on:
    `schema.runner_helpers_generic_hash()` -- which DELETES the R11
    ReplicationInitiation redirect scaffolding before hashing -- must be
    IDENTICAL whether evaluated against published main `543c737`'s blob or
    the current tree. If this ever fails, R11's redaction is broken and
    every OTHER process's migrated `"helpers"` provenance is suspect."""
    pre_ref_text = _git_show(_PUBLISHED_MAIN_BASE_SHA, "tests/vivarium/_l2_2_design_a_runner_helpers.py")
    pre_ref_hash = schema.runner_helpers_generic_hash(source=pre_ref_text)
    current_hash = schema.runner_helpers_generic_hash()
    assert pre_ref_hash == current_hash, (
        f"Redacted 'helpers' hash changed between published main {_PUBLISHED_MAIN_BASE_SHA!r} "
        f"({str(pre_ref_hash)[:12]!r}..) and the current tree ({str(current_hash)[:12]!r}..) -- "
        "either R11's redaction is broken, or real shared/generic code changed."
    )


def test_shared_files_r11_delta_is_exactly_the_documented_redirect() -> None:
    """Stronger than the hash-equality check above: line-diffs
    `_l2_2_design_a_runner_helpers.py` against published main `543c737`
    and asserts every ADDED line is one of the four expected R11 additions
    (the sibling-module import statement, and the two-line redirect guard
    each in `_v2_seed_mat_path`/`load_karr_oracle`), and that NO line was
    REMOVED or MODIFIED anywhere else in the file."""
    import difflib

    pre_ref_text = _git_show(_PUBLISHED_MAIN_BASE_SHA, "tests/vivarium/_l2_2_design_a_runner_helpers.py")
    current_text = _RUNNER_HELPERS_MODULE.read_text(encoding="utf-8")
    pre_ref_lines = pre_ref_text.splitlines()
    current_lines = current_text.splitlines()

    matcher = difflib.SequenceMatcher(a=pre_ref_lines, b=current_lines, autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed.extend(pre_ref_lines[i1:i2])
        added.extend(current_lines[j1:j2])

    assert removed == [], f"R11 must never remove/modify a pre-existing line; found removed/changed: {removed!r}"

    expected_added = {
        '    if process_name == "ReplicationInitiation":',
        "        return _repinit_v2_seed_mat_path(int(seed))",
        '    if process == "ReplicationInitiation":',
        "        return _load_replication_initiation_v2_ensemble()",
        "from _l2_2_repinit_runner_helpers import (  # noqa: E402",
        "    load_replication_initiation_v2_ensemble as _load_replication_initiation_v2_ensemble,",
        "    repinit_v2_seed_mat_path as _repinit_v2_seed_mat_path,",
        ")",
    }
    unexpected = [line for line in added if line not in expected_added]
    assert unexpected == [], f"R11 added unexpected line(s) beyond the documented redirect: {unexpected!r}"
    assert set(added) == expected_added, f"R11's added lines do not match every expected redirect line: got {set(added)!r}"


def test_v2_canonical_and_suffixed_seed0_helpers_never_invoked_for_repinit() -> None:
    """`_v2_seed_mat_path` must redirect to the sibling module BEFORE
    calling `_v2_canonical_seed0_mat_path`/`_v2_suffixed_seed_mat_path` for
    ReplicationInitiation -- proven here by making both raise
    unconditionally and confirming resolution still succeeds for every
    seed 0-49."""

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must never be called for ReplicationInitiation")

    original_canonical = runner_helpers._v2_canonical_seed0_mat_path
    original_suffixed = runner_helpers._v2_suffixed_seed_mat_path
    runner_helpers._v2_canonical_seed0_mat_path = _boom
    runner_helpers._v2_suffixed_seed_mat_path = _boom
    try:
        for seed in range(_N_SEEDS):
            path = runner_helpers._v2_seed_mat_path(_PROCESS_NAME, seed)
            assert path.name == "ReplicationInitiation_200ticks.mat"
    finally:
        runner_helpers._v2_canonical_seed0_mat_path = original_canonical
        runner_helpers._v2_suffixed_seed_mat_path = original_suffixed


# --- Genuine trace layout / identity ----------------------------------------


def test_all_50_seeds_resolve_to_genuine_200tick_named_paths() -> None:
    """No seed-0 special case, no collision: every seed 0-49 resolves to
    its OWN seed-padded directory with the honest `_200ticks.mat` name."""
    _skip_if_raw_data_absent()
    canonical = _canonical_l21_path()
    for seed in range(_N_SEEDS):
        path = runner_helpers._v2_seed_mat_path(_PROCESS_NAME, seed)
        assert path != canonical
        assert path.parent.name == f"per_process_traces_v2_s{seed:03d}"
        assert path.name == "ReplicationInitiation_200ticks.mat"
        assert path == _genuine_seed_path(seed)


def test_all_50_repinit_seed_traces_have_genuine_200_tick_identity() -> None:
    """Independent (does not call `repinit_v2_seed_mat_path`'s own
    validation) four-way re-derivation per seed file: filename token ==
    metadata/n_ticks == live catalog M_ticks == every non-chromosome
    channel's own tick dimension."""
    _skip_if_raw_data_absent()
    catalog_m = _catalog_m_ticks(_PROCESS_NAME)
    assert catalog_m == 200
    for seed in range(_N_SEEDS):
        path = _genuine_seed_path(seed)
        assert path.name == f"{_PROCESS_NAME}_{catalog_m}ticks.mat"
        with h5py.File(path, "r") as handle:
            metadata_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
            assert metadata_ticks == catalog_m, f"seed {seed}: metadata/n_ticks={metadata_ticks} != {catalog_m}"
            for section in ("states_before", "states_after"):
                group = handle[section]
                for channel_name in group:
                    if str(channel_name) == "chromosome":
                        continue
                    ds = group[channel_name]
                    actual_ticks = ds.shape[1] if ds.shape[0] == 1 else ds.shape[0]
                    assert actual_ticks == catalog_m, (
                        f"seed {seed} {section}/{channel_name} has {actual_ticks} ticks, expected {catalog_m}"
                    )


def test_manifest_hashes_match_current_seed_files() -> None:
    """`REPINIT_SEED_MANIFEST.json`'s recorded sha256/rng_seed per seed
    must match the CURRENT, renamed on-disk files exactly."""
    import json

    _skip_if_raw_data_absent()
    manifest_path = _REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "REPINIT_SEED_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) == _N_SEEDS
    for entry in manifest:
        seed = entry["seed"]
        recorded_path = _KARR_NATIVE_ROOT / entry["path"]
        assert recorded_path == _genuine_seed_path(seed), f"seed {seed}: manifest path {recorded_path} != {_genuine_seed_path(seed)}"
        actual_sha = _sha256_file(recorded_path)
        assert actual_sha.upper() == entry["sha256"].upper(), f"seed {seed}: manifest sha256 mismatch"
        with h5py.File(recorded_path, "r") as handle:
            actual_rng_seed = int(np.asarray(handle["metadata/rng_seed"][()]).reshape(-1)[0])
        assert actual_rng_seed == entry["rng_seed"], f"seed {seed}: manifest rng_seed {entry['rng_seed']} != actual {actual_rng_seed}"


def test_canonical_l21_trace_preserved_and_untouched() -> None:
    """The canonical L2.1 100-tick trace exists, is genuinely 100 ticks,
    and matches the accepted sha256 -- permanently, with no swap/archival
    procedure of any kind involved in R11."""
    canonical = _canonical_l21_path()
    assert canonical.exists(), f"Canonical L2.1 trace missing at {canonical}."
    expected_sha256 = "0c61c816e3903e771550e674db36fedaa76a546687891a99e46f163703550c0f"
    actual_sha256 = _sha256_file(canonical)
    assert actual_sha256 == expected_sha256, (
        f"Canonical L2.1 trace {canonical} sha256 {actual_sha256} does not match "
        f"the accepted {expected_sha256} -- it has changed or been replaced."
    )
    with h5py.File(canonical, "r") as handle:
        n_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100


# --- Anti-cheat: reproduce the exact prior-rejected mislabeling shapes ------


def test_rejects_legacy_100ticks_filename_even_when_genuine_200tick_data_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduces the PRIOR REJECTED candidate's exact shape: a genuine
    200-tick trace sitting at a `_100ticks.mat`-named path. Must be
    rejected -- the resolver looks ONLY for `_200ticks.mat` and never
    falls back to a differently-named file, no matter what its own
    metadata claims."""
    _skip_if_raw_data_absent()
    fake_root = tmp_path / "karr_native"
    seed_dir = fake_root / "per_process_traces_v2_s000"
    seed_dir.mkdir(parents=True)
    # Genuine 200-tick bytes, but at the legacy, now-forbidden filename.
    shutil.copy(_genuine_seed_path(0), seed_dir / f"{_PROCESS_NAME}_100ticks.mat")

    monkeypatch.setattr(repinit_helpers, "_KARR_NATIVE_ROOT", fake_root)
    with pytest.raises(repinit_helpers.RepInitTraceIdentityError, match="Missing genuine"):
        repinit_helpers.repinit_v2_seed_mat_path(0)


def test_rejects_200ticks_filename_whose_metadata_disagrees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Inverse mismatch: a correctly-NAMED `_200ticks.mat` file whose OWN
    `metadata/n_ticks` has been tampered to 100. Filename token and catalog
    M_ticks agree (both 200); the file's internal metadata is the one that
    lies. Must be rejected."""
    _skip_if_raw_data_absent()
    fake_root = tmp_path / "karr_native"
    seed_dir = fake_root / "per_process_traces_v2_s000"
    seed_dir.mkdir(parents=True)
    target = seed_dir / f"{_PROCESS_NAME}_200ticks.mat"
    shutil.copy(_genuine_seed_path(0), target)
    with h5py.File(target, "r+") as handle:
        handle["metadata/n_ticks"][...] = 100.0

    monkeypatch.setattr(repinit_helpers, "_KARR_NATIVE_ROOT", fake_root)
    with pytest.raises(repinit_helpers.RepInitTraceIdentityError, match="metadata/n_ticks"):
        repinit_helpers.repinit_v2_seed_mat_path(0)


def test_rejects_channel_tick_dimension_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Filename token and metadata both correctly say 200, but one
    non-chromosome channel's own tick dimension has been truncated to 150
    (e.g. a partial/corrupted extraction). Must be rejected."""
    _skip_if_raw_data_absent()
    fake_root = tmp_path / "karr_native"
    seed_dir = fake_root / "per_process_traces_v2_s000"
    seed_dir.mkdir(parents=True)
    target = seed_dir / f"{_PROCESS_NAME}_200ticks.mat"
    shutil.copy(_genuine_seed_path(0), target)
    with h5py.File(target, "r+") as handle:
        truncated = handle["states_before/substrates"][:, :150]
        del handle["states_before/substrates"]
        handle.create_dataset("states_before/substrates", data=truncated)

    monkeypatch.setattr(repinit_helpers, "_KARR_NATIVE_ROOT", fake_root)
    with pytest.raises(repinit_helpers.RepInitTraceIdentityError, match="tick dimension"):
        repinit_helpers.repinit_v2_seed_mat_path(0)


def test_rejects_missing_seed_file_outright(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No file at all for a requested seed must fail closed, never
    silently substitute another seed's data."""
    fake_root = tmp_path / "karr_native"
    (fake_root / "per_process_traces_v2_s000").mkdir(parents=True)
    monkeypatch.setattr(repinit_helpers, "_KARR_NATIVE_ROOT", fake_root)
    with pytest.raises(repinit_helpers.RepInitTraceIdentityError, match="Missing genuine"):
        repinit_helpers.repinit_v2_seed_mat_path(0)
