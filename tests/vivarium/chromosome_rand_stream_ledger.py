"""Shared loader for Karr's shared-Chromosome-stream per-tick raw-draw
ledger (`scripts/matlab/reconstruct_chromosome_draw_ledger.m`'s output),
used by BOTH `tests/vivarium/test_karr_dna_damage_l2_replay.py` (the
process-specific L2.1 replay test) and `scripts/l21_active_window_audit.py`
(via `tests/vivarium/l2_2_replay_common_v2.py`, the shared multi-process
L2.1 audit harness) -- one hash-bound loader, reused rather than
duplicated, so both call sites fail closed identically on a missing,
tampered, or short/long ledger.

This module is test/audit-tier (it reads a companion oracle-adjacent
sidecar file), never imported by `opencell/vivarium/karr_dna_damage.py`
or `karr_dna_damage_rng.py` themselves -- see
`docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` Rule 8 ("a `_static_replay.py`
helper consumed only by tests is fine ... not under `opencell/vivarium/`").
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


class ChromosomeRandStreamLedgerError(RuntimeError):
    """Raised for any chromosome_rand_stream_state ledger provenance
    failure: an unresolvable/missing source file, a source-hash
    mismatch (against either the CURRENT on-disk MATLAB source, for
    Chromosome.m/RandStream.m, or the trace's OWN recorded
    resolved-source hash, for DNADamage.m -- see
    `load_chromosome_rand_stream_ledger`'s docstring), or a malformed/
    internally-inconsistent ledger payload. Deliberately a plain,
    explicit exception class -- not a bare `assert` -- because `assert`
    statements are stripped entirely under `python -O`, which would
    silently disable every fail-closed check in this module in that
    mode; every failure path below raises this (or lets an underlying
    stdlib exception, e.g. `json.JSONDecodeError`, propagate) rather
    than asserting."""


def sha256_raw_bytes(path: Path) -> str:
    """Plain SHA-256 of a file's raw on-disk bytes, with NO line-ending
    normalization. Matches `scripts/matlab/reconstruct_chromosome_draw_ledger.m`'s
    own `sha256_of_file` local helper (`fread(fid, Inf, '*uint8')`,
    hashed verbatim) -- the producer convention actually used for this
    ledger's `chromosome_source_sha256`/`randstream_util_source_sha256`
    fields. Do NOT confuse with `sha256_lf_normalized` below, which is a
    DIFFERENT MATLAB helper's convention
    (`karr_bootstrap.m`/`ensure_dnadamage_signed_zero_overlay`'s
    `resolved_sha256_lf_normalized`, used only for the trace's own
    `dnadamage_source_resolved_sha256` metadata field, cross-checked
    separately below -- never recomputed against a live file here, see
    that check's own docstring for why)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_lf_normalized(path: Path) -> str:
    """Match `scripts/matlab/karr_bootstrap.m`'s DNADamage-source-overlay
    machinery (`ensure_dnadamage_signed_zero_overlay`/
    `verify_resolved_dnadamage_source`, whose hashes feed
    `extract_per_process_traces_v2.m`'s
    `metadata.dnadamage_source_resolved_sha256`): strip CR bytes
    (`\\r`), then SHA-256 the remaining bytes. Retained for any future
    direct-file cross-check against that convention; the current
    DNADamage-source verification in this module instead compares the
    ledger's `dnadamage_source_sha256` against the TRACE's own recorded
    `dnadamage_source_resolved_sha256` metadata (see
    `load_chromosome_rand_stream_ledger`), because the actually-resolved
    DNADamage.m may be an overlay-patched copy elsewhere on the MATLAB
    path rather than the pristine on-disk WholeCell source file, and
    reproducing that overlay resolution logic here would silently
    assume a source layout this module cannot verify independently."""
    raw = path.read_bytes()
    raw = raw.replace(b"\r", b"")
    return hashlib.sha256(raw).hexdigest()


def _resolve_main_checkout_wcm_root(repo_root: Path) -> Path | None:
    """Find the main `opencell` checkout's WholeCell source tree,
    portably, from ANY worktree path -- Windows
    (`E:\\opencell-worktrees\\<name>`) or WSL
    (`/mnt/e/opencell-worktrees/<name>`) -- by locating the
    `opencell-worktrees` path segment shared by every worktree layout in
    this project and substituting the sibling `opencell` directory,
    rather than hardcoding a single OS-specific absolute path. The prior
    implementation hardcoded the literal string `E:\\opencell\\...`,
    which silently NEVER resolves under WSL (this project's mandated
    execution environment -- see `SESSION_CONTEXT.md`): `repo_root`
    there is already a POSIX path like
    `/mnt/e/opencell-worktrees/<name>`, and `Path("E:/opencell/...")`
    under a POSIX pathlib flavour is not a Windows path at all -- it is
    a relative POSIX path segment literally named `E:`, which never
    exists, so the old fallback candidate was always missing and the
    caller's `if source_path is None: continue` silently skipped BOTH
    Chromosome.m/RandStream.m source-hash checks on every WSL run.
    Returns None (never a guessed/partial path) if `repo_root` is not
    inside an `opencell-worktrees` directory at all (e.g. `repo_root` IS
    already the main checkout, handled by the caller's worktree-root
    check before this is ever consulted)."""
    parts = repo_root.parts
    try:
        idx = parts.index("opencell-worktrees")
    except ValueError:
        return None
    root = Path(*parts[:idx]) / "opencell" / "data" / "m1_sources" / "WholeCell"
    return root if root.exists() else None


def resolve_wcm_source_path(*parts: str, repo_root: Path) -> Path | None:
    """Mirror `karr_bootstrap.m`'s worktree-first-then-main-checkout WCM
    source resolution (worktree `data/m1_sources/WholeCell` if it has a
    fitted-simulation snapshot, else the main `opencell` checkout's copy,
    resolved portably via `_resolve_main_checkout_wcm_root`).
    `repo_root` is the CALLER's own worktree root (never inferred from
    this shared module's own `__file__`, so it resolves correctly
    regardless of which worktree/repo the caller runs from). Returns
    None only when the source genuinely cannot be located anywhere --
    callers of this function MUST treat a None result as a hard failure
    for any ledger field that records a hash for it, never as license to
    silently skip that field's verification (see
    `load_chromosome_rand_stream_ledger`)."""
    worktree_root = repo_root / "data" / "m1_sources" / "WholeCell"
    if (worktree_root / "data" / "Simulation_fitted.mat").exists():
        candidate = worktree_root.joinpath(*parts)
        return candidate if candidate.exists() else None

    fallback_root = _resolve_main_checkout_wcm_root(repo_root)
    if fallback_root is None:
        return None
    candidate = fallback_root.joinpath(*parts)
    return candidate if candidate.exists() else None


def _decode_h5_text(value: Any) -> str:
    """Decode an HDF5/.mat scalar-or-char-array value into a plain str.
    Mirrors `scripts/l22_evidence/dna_damage_event_verifier.py::_decode_text`
    (kept independent/duplicated rather than imported, since that module
    lives under `scripts/l22_evidence/` and pulls in unrelated heavy
    imports; this is the same small decoding logic, not new behavior)."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    arr = np.asarray(value)
    if arr.dtype.kind in {"U", "S"}:
        flat = arr.reshape(-1)
        if arr.dtype.kind == "S":
            return (
                b"".join(
                    bytes(item) if isinstance(item, (bytes, bytearray)) else str(item).encode("utf-8")
                    for item in flat
                )
                .decode("utf-8", errors="replace")
                .rstrip("\x00")
            )
        return "".join(str(item) for item in flat).rstrip("\x00")
    if arr.dtype.kind in {"u", "i"}:
        return "".join(chr(int(code)) for code in arr.reshape(-1) if int(code) != 0)
    return str(value)


def _read_trace_metadata_text(trace_path: Path, key: str) -> str | None:
    """Read a single string-valued `/metadata/<key>` field from a
    `.mat` (HDF5) trace file, or None if the group/key is absent."""
    with h5py.File(trace_path, "r") as handle:
        meta = handle.get("metadata")
        if meta is None or key not in meta:
            return None
        return _decode_h5_text(meta[key][()])


def load_chromosome_rand_stream_ledger(trace_path: Path, *, repo_root: Path) -> list[list[float]] | None:
    """Load the companion per-tick raw-draw ledger for Karr's SHARED
    `Chromosome.randStream` (see `scripts/matlab/
    reconstruct_chromosome_draw_ledger.m`), if present, hash-bound and
    validated against the CURRENT trace file and CURRENT/resolved MATLAB
    source. Fails closed -- raises `ChromosomeRandStreamLedgerError` (or
    lets a malformed-JSON `json.JSONDecodeError` propagate) -- on any
    provenance mismatch, unresolvable source, or malformed shape; never
    silently skips a check or falls back to a partial/guessed ledger.
    Returns None ONLY when the sidecar file itself is simply absent (an
    older/other trace, or a different seed, that predates/lacks this
    closure entirely -- callers fall back to the pre-existing
    freshly-seeded stand-in stream for those, a documented, unaffected
    baseline, not a provenance failure).

    Three independent source-hash checks are performed once the sidecar
    is found and its `trace_sha256` binding to `trace_path` itself is
    confirmed:

    1. `chromosome_source_sha256` / `randstream_util_source_sha256` --
       compared via `sha256_raw_bytes` (the ledger PRODUCER's own
       convention, see that function's docstring) against
       `Chromosome.m`/`RandStream.m` resolved via
       `resolve_wcm_source_path`. If that resolution fails (returns
       None), this is a HARD FAILURE, not a skip: a ledger that records
       a hash for a source this loader cannot even locate must never be
       silently treated as verified.
    2. `dnadamage_source_sha256` -- cross-checked against `trace_path`'s
       OWN `/metadata/dnadamage_source_resolved_sha256` field (i.e.
       ledger-vs-trace source-revision agreement), not recomputed from
       a live on-disk file, since the actually-resolved DNADamage.m may
       be an overlay-patched copy (see `sha256_lf_normalized`'s
       docstring for why). Both a missing ledger field and a missing/
       absent trace metadata field are hard failures.

    `repo_root` must be the CALLER's own worktree root (e.g. the audit
    script's `_REPO_ROOT`, or a test file's own `_REPO_ROOT`) -- this
    module never infers it from its own location, so the SAME loader
    behaves identically no matter which worktree/repo imports it."""
    ledger_path = trace_path.with_suffix("").with_suffix(".chromosome_rand_stream_ledger.json")
    if not ledger_path.exists():
        return None

    payload = json.loads(ledger_path.read_text(encoding="utf-8"))

    recorded_trace_sha = payload.get("trace_sha256")
    actual_trace_sha = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    if recorded_trace_sha != actual_trace_sha:
        raise ChromosomeRandStreamLedgerError(
            f"chromosome_rand_stream_state ledger {ledger_path} is bound to a DIFFERENT trace file "
            f"(recorded trace_sha256={recorded_trace_sha!r}, actual={actual_trace_sha!r}) -- "
            "refusing to reuse a stale ledger against a re-extracted/edited trace"
        )

    # (1) Chromosome.m / RandStream.m -- raw-byte hash (producer convention),
    # portable WCM resolution, hard-fail (never silently continue) if the
    # recorded field is missing or the source cannot be resolved on disk.
    for source_key, source_parts in (
        ("chromosome_source_sha256", ("src", "+edu", "+stanford", "+covert", "+cell", "+sim", "+state", "Chromosome.m")),
        ("randstream_util_source_sha256", ("src", "+edu", "+stanford", "+covert", "+util", "RandStream.m")),
    ):
        recorded = payload.get(source_key)
        if not recorded:
            raise ChromosomeRandStreamLedgerError(
                f"chromosome_rand_stream_state ledger {ledger_path} is missing its required "
                f"{source_key} provenance field -- refusing to trust a ledger with no source binding"
            )
        source_name = source_parts[-1]
        source_path = resolve_wcm_source_path(*source_parts, repo_root=repo_root)
        if source_path is None:
            raise ChromosomeRandStreamLedgerError(
                f"chromosome_rand_stream_state ledger {ledger_path} records {source_key}={recorded!r} "
                f"but {source_name} could not be resolved on disk from repo_root={repo_root} (checked "
                "the worktree's own data/m1_sources/WholeCell and the main opencell checkout via "
                "resolve_wcm_source_path) -- refusing to silently skip source-hash verification for "
                "an unresolvable source"
            )
        actual = sha256_raw_bytes(source_path)
        if recorded != actual:
            raise ChromosomeRandStreamLedgerError(
                f"chromosome_rand_stream_state ledger {ledger_path} is bound to a DIFFERENT "
                f"{source_name} ({source_key}={recorded!r}, current on-disk={actual!r}) -- "
                "refusing to reuse a ledger reconstructed against stale MATLAB source"
            )

    # (2) DNADamage.m -- cross-check the ledger's recorded resolved-source
    # hash against the TRACE's own recorded resolved-source hash (both
    # ledger and trace must agree on which DNADamage.m revision was live
    # when each was produced); see this function's docstring for why this
    # is a cross-check rather than a live-file recompute.
    recorded_dnadamage_sha = payload.get("dnadamage_source_sha256")
    if not recorded_dnadamage_sha:
        raise ChromosomeRandStreamLedgerError(
            f"chromosome_rand_stream_state ledger {ledger_path} is missing its required "
            "dnadamage_source_sha256 provenance field -- refusing to trust a ledger with no "
            "DNADamage.m source binding"
        )
    trace_dnadamage_sha = _read_trace_metadata_text(trace_path, "dnadamage_source_resolved_sha256")
    if not trace_dnadamage_sha:
        raise ChromosomeRandStreamLedgerError(
            f"trace {trace_path} has no dnadamage_source_resolved_sha256 metadata field to "
            f"cross-check ledger {ledger_path}'s recorded dnadamage_source_sha256 against -- "
            "refusing to silently skip this check"
        )
    if recorded_dnadamage_sha != trace_dnadamage_sha:
        raise ChromosomeRandStreamLedgerError(
            f"chromosome_rand_stream_state ledger {ledger_path}'s dnadamage_source_sha256="
            f"{recorded_dnadamage_sha!r} does not match trace {trace_path}'s own "
            f"dnadamage_source_resolved_sha256={trace_dnadamage_sha!r} -- the ledger was "
            "reconstructed against a DIFFERENT DNADamage.m source revision than the one that "
            "produced this trace"
        )

    per_tick = payload.get("per_tick")
    if not (isinstance(per_tick, list) and len(per_tick) > 0):
        raise ChromosomeRandStreamLedgerError(
            f"chromosome_rand_stream_state ledger {ledger_path} has a missing/empty per_tick array"
        )
    ledgers: list[list[float]] = []
    for entry in per_tick:
        draws = entry.get("draws")
        if isinstance(draws, (int, float)) and not isinstance(draws, bool) and entry.get("n_draws") == 1:
            # MATLAB's `jsonencode` collapses a length-1 numeric array to
            # a bare scalar (not a 1-element array) -- a known, documented
            # jsonencode quirk (e.g. `jsonencode([1.5])` produces `1.5`,
            # not `[1.5]`), not a malformed ledger. Safe to normalize back
            # into a 1-element list ONLY when this entry's own recorded
            # `n_draws` confirms exactly one draw was captured for this
            # tick; any other bare-scalar `draws` value (n_draws != 1)
            # falls through to the hard failure below unchanged.
            draws = [float(draws)]
        if not isinstance(draws, list):
            raise ChromosomeRandStreamLedgerError(
                f"chromosome_rand_stream_state ledger {ledger_path} tick {entry.get('tick')!r} "
                f"has a malformed/missing draws array: {draws!r}"
            )
        if entry.get("n_draws") != len(draws):
            raise ChromosomeRandStreamLedgerError(
                f"chromosome_rand_stream_state ledger {ledger_path} tick {entry.get('tick')!r} "
                f"n_draws={entry.get('n_draws')!r} does not match len(draws)={len(draws)}"
            )
        ledgers.append([float(v) for v in draws])
    return ledgers
