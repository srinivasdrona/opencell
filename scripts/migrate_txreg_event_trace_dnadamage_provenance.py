#!/usr/bin/env python3
"""Coordinated, fail-closed DNADamage provenance migration for the canonical
TranscriptionalRegulation seed-0 4000-tick event trace and its companion
chromosome-RNG ledger.

Why a coordinated pair migration: `load_chromosome_rand_stream_ledger`
(`tests/vivarium/chromosome_rand_stream_ledger.py`) now requires BOTH the
ledger's `dnadamage_source_sha256` AND the trace's
`/metadata/dnadamage_source_resolved_sha256`, and requires them to agree.
Adding the metadata field changes the trace's raw bytes, so the ledger's
`trace_sha256` binding must be recomputed in the same transaction. The MATLAB
license that produced these artifacts is expired, so nothing is regenerated:
the migration only ADDS the DNADamage binding and proves nothing else changed.

Hash convention: the canonical value is
`scripts.l2_event.launcher.current_genuine_dnadamage_source()
["patched_sha256_lf_normalized"]` -- the Python-side mirror of
`karr_bootstrap.m`'s `resolved_sha256_lf_normalized` that the shared extractor
writes into `metadata.dnadamage_source_resolved_sha256` for every trace.

Fail-closed contract (default is a dry run; pass `--apply` to mutate):

1. The ledger's `trace_sha256` must match the exact current trace bytes, and
   its `chromosome_source_sha256` / `randstream_util_source_sha256` must match
   the current sources under the loader's own `resolve_wcm_source_path` /
   `sha256_raw_bytes` conventions.
2. The pre-state must lack BOTH the ledger `dnadamage_source_sha256` and the
   trace `/metadata/dnadamage_source_resolved_sha256`. A half-migrated or
   mismatched pair fails closed; an already-complete pair is a no-op only
   after the real loader succeeds on it.
3. Work happens on sibling temporary copies. The trace copy receives exactly
   one new dataset (a MATLAB-char-encoded clone of the layout of
   `/metadata/mnrnd_provider_sha256`). Every pre-existing HDF5 group/dataset
   (value, shape, dtype, attributes), the 512-byte userblock, and the
   ledger's `per_tick` text must be unchanged; only the ledger's
   `trace_sha256` and the new `dnadamage_source_sha256` may differ.
   `/metadata`'s `MATLAB_fields` attribute is intentionally NOT edited (it is
   a pre-existing attribute; every Python consumer reads the dataset
   directly, and the repo's own frozen tests migrate the same way).
4. The temporary pair must pass the real loader (exactly the expected tick
   count of draw lists, at least one tick with real draws) and the existing
   active-window smoke through the first real TF-binding tick.
5. `--apply` swaps the pair in via targeted sibling backups (renames, never
   broad deletes), re-runs the real loader against the canonical paths, and
   only then removes those exact backup files. Any error restores both
   originals and re-verifies their hashes. Leftover migration siblings from an
   interrupted run make the script refuse to start.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import re
import shutil
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.vivarium.chromosome_rand_stream_ledger import (  # noqa: E402
    _decode_h5_text,
    _read_trace_metadata_text,
    load_chromosome_rand_stream_ledger,
    resolve_wcm_source_path,
    sha256_raw_bytes,
)

TRACE_NAME = "TranscriptionalRegulation_4000ticks.mat"
EVENT_DIR_REL = Path("data/m1_sources/karr_native/per_process_traces_v2_event_s000")
PROCESS_NAME = "TranscriptionalRegulation"
EXPECTED_TICKS = 4000
NEW_METADATA_KEY = "dnadamage_source_resolved_sha256"
LEDGER_KEY = "dnadamage_source_sha256"
TEMPLATE_METADATA_KEY = "mnrnd_provider_sha256"
SMOKE_ACTIVE_TICK = 11
SMOKE_TICKS = 12
TEMP_TAG = "_dnadmgmig_"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_GROUP_DEPTH = 64
_CHUNK_CHILDREN = 500

_SOURCE_PARTS = {
    "chromosome_source_sha256": (
        "src",
        "+edu",
        "+stanford",
        "+covert",
        "+cell",
        "+sim",
        "+state",
        "Chromosome.m",
    ),
    "randstream_util_source_sha256": (
        "src",
        "+edu",
        "+stanford",
        "+covert",
        "+util",
        "RandStream.m",
    ),
}


class MigrationError(RuntimeError):
    """Any fail-closed migration refusal or verification failure."""


def _log(message: str) -> None:
    print(f"[txreg-dnadamage-migration] {message}", flush=True)


def default_trace_path() -> Path:
    root = Path("E:/opencell") if os.name == "nt" else Path("/mnt/e/opencell")
    return root / EVENT_DIR_REL / TRACE_NAME


def ledger_path_for(trace_path: Path) -> Path:
    """The loader's own sidecar derivation (kept identical on purpose)."""
    return trace_path.with_suffix("").with_suffix(".chromosome_rand_stream_ledger.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Logical HDF5 digest
# --------------------------------------------------------------------------


@dataclass
class LogicalDigest:
    entries: dict[str, str]
    userblock_sha256: str
    n_groups: int
    n_datasets: int


def _object_addr(obj_id: Any) -> int:
    return int(h5py.h5o.get_info(obj_id).addr)


class _Digester:
    """Digests objects of one open file. Reference values are hashed as the
    file address of their target (resolving a reference to a *path* makes
    HDF5 search the whole file per reference and takes minutes each here);
    every group/dataset entry also records its own address, so identical
    reference addresses plus identical per-address entries prove each
    reference still points at an identical object. Referenced addresses are
    collected so the caller can prove each one is a digested object."""

    def __init__(self, handle: h5py.File) -> None:
        self.handle = handle
        self.referenced: set[int] = set()

    def feed(self, hasher: Any, value: Any) -> None:
        """Canonical, type-tagged serialization of any value h5py can return.
        Unknown types raise instead of being skipped."""
        if isinstance(value, h5py.Empty):
            hasher.update(b"E" + repr(value.dtype).encode())
        elif isinstance(value, h5py.RegionReference):
            raise MigrationError("HDF5 region references are not supported")
        elif isinstance(value, h5py.Reference):
            if not value:
                hasher.update(b"R<null>")
            else:
                addr = _object_addr(h5py.h5r.dereference(value, self.handle.id))
                self.referenced.add(addr)
                hasher.update(b"R" + str(addr).encode())
        elif isinstance(value, np.ndarray):
            if value.dtype.hasobject:
                hasher.update(b"O" + repr(value.shape).encode())
                for item in value.reshape(-1, order="C"):
                    self.feed(hasher, item)
            else:
                arr = np.ascontiguousarray(value)
                hasher.update(b"N" + arr.dtype.str.encode() + repr(arr.shape).encode())
                hasher.update(arr.tobytes())
        elif isinstance(value, (bytes, np.bytes_)):
            hasher.update(b"B" + str(len(value)).encode() + b":" + bytes(value))
        elif isinstance(value, str):
            encoded = value.encode("utf-8")
            hasher.update(b"S" + str(len(encoded)).encode() + b":" + encoded)
        elif isinstance(value, np.generic):
            hasher.update(b"G" + value.dtype.str.encode() + value.tobytes())
        elif isinstance(value, (bool, int, float)):
            hasher.update(b"P" + type(value).__name__.encode() + repr(value).encode())
        else:
            raise MigrationError(f"cannot canonically hash HDF5 value of type {type(value)!r}")

    def attrs(self, hasher: Any, obj: Any) -> None:
        for name in sorted(obj.attrs.keys()):
            attr_id = obj.attrs.get_id(name)
            hasher.update(b"A" + name.encode("utf-8") + b"\x00")
            hasher.update(repr(attr_id.dtype).encode() + repr(attr_id.shape).encode())
            self.feed(hasher, obj.attrs[name])

    def dataset_entry(self, dataset: h5py.Dataset) -> str:
        hasher = hashlib.sha256()
        hasher.update(repr(dataset.shape).encode() + repr(dataset.dtype).encode())
        hasher.update(repr(dataset.dtype.metadata).encode())
        self.attrs(hasher, dataset)
        self.feed(hasher, dataset[()])
        return f"D:{hasher.hexdigest()}@{_object_addr(dataset.id)}"

    def group_entry(self, group: h5py.Group) -> str:
        hasher = hashlib.sha256()
        self.attrs(hasher, group)
        return f"G:{hasher.hexdigest()}@{_object_addr(group.id)}"

    def children(
        self, group_path: str, names: list[str], entries: dict[str, str], depth: int = 0
    ) -> tuple[int, int]:
        """Digest the named children of `group_path` (recursing into
        sub-groups); returns (n_groups, n_datasets) added to `entries`."""
        if depth > _MAX_GROUP_DEPTH:
            raise MigrationError(f"HDF5 group nesting too deep at {group_path!r}")
        n_groups = n_datasets = 0
        parent = self.handle[group_path]
        base = group_path.rstrip("/")
        for name in names:
            child_path = f"{base}/{name}"
            link = parent.get(name, getlink=True)
            if isinstance(link, h5py.SoftLink):
                entries[child_path] = f"L:soft:{link.path}"
                continue
            if isinstance(link, h5py.ExternalLink):
                entries[child_path] = f"L:ext:{link.filename}:{link.path}"
                continue
            child = parent[name]
            if isinstance(child, h5py.Group):
                entries[child_path] = self.group_entry(child)
                sub_groups, sub_datasets = self.children(
                    child_path, sorted(child.keys()), entries, depth + 1
                )
                n_groups += 1 + sub_groups
                n_datasets += sub_datasets
            elif isinstance(child, h5py.Dataset):
                entries[child_path] = self.dataset_entry(child)
                n_datasets += 1
            else:
                raise MigrationError(f"unsupported HDF5 object at {child_path!r}")
        return n_groups, n_datasets


def _digest_task(
    task: tuple[str, str, list[str]],
) -> tuple[dict[str, str], int, int, set[int]]:
    path, group_path, names = task
    entries: dict[str, str] = {}
    with h5py.File(path, "r") as handle:
        digester = _Digester(handle)
        n_groups, n_datasets = digester.children(group_path, names, entries)
    return entries, n_groups, n_datasets, digester.referenced


def logical_digest(path: Path, *, workers: int = 1) -> LogicalDigest:
    """Per-path digest of every group (attributes) and dataset (shape, dtype,
    attributes, full value), plus the userblock hash. Large top-level groups
    are split into child chunks and digested by `workers` spawned processes;
    the result is independent of the worker count."""
    entries: dict[str, str] = {}
    tasks: list[tuple[str, str, list[str]]] = []
    referenced: set[int] = set()
    with path.open("rb") as raw, h5py.File(path, "r") as handle:
        userblock = raw.read(handle.userblock_size)
        digester = _Digester(handle)
        entries["/"] = digester.group_entry(handle)
        n_groups = 1
        n_datasets = 0
        for name in sorted(handle.keys()):
            top = handle.get(name)
            is_hard = isinstance(handle.get(name, getlink=True), h5py.HardLink)
            if is_hard and isinstance(top, h5py.Group) and len(top) > _CHUNK_CHILDREN:
                top_path = f"/{name}"
                entries[top_path] = digester.group_entry(top)
                n_groups += 1
                names = sorted(top.keys())
                for start in range(0, len(names), _CHUNK_CHILDREN):
                    tasks.append((str(path), top_path, names[start : start + _CHUNK_CHILDREN]))
            else:
                sub_groups, sub_datasets = digester.children("/", [name], entries)
                n_groups += sub_groups
                n_datasets += sub_datasets
        referenced |= digester.referenced

    if workers > 1 and len(tasks) > 1:
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            results = list(pool.map(_digest_task, tasks, chunksize=1))
    else:
        results = [_digest_task(task) for task in tasks]
    for task_entries, task_groups, task_datasets, task_refs in results:
        overlap = entries.keys() & task_entries.keys()
        if overlap:
            raise MigrationError(f"digest task overlap at {sorted(overlap)[:5]!r}")
        entries.update(task_entries)
        n_groups += task_groups
        n_datasets += task_datasets
        referenced |= task_refs

    known = {int(v.rsplit("@", 1)[1]) for v in entries.values() if v[:2] in ("G:", "D:")}
    dangling = sorted(referenced - known)
    if dangling:
        raise MigrationError(
            f"{len(dangling)} references point at undigested objects: {dangling[:5]}"
        )
    return LogicalDigest(entries, hashlib.sha256(userblock).hexdigest(), n_groups, n_datasets)


def diff_digests(before: LogicalDigest, after: LogicalDigest, *, added_path: str) -> list[str]:
    problems: list[str] = []
    if before.userblock_sha256 != after.userblock_sha256:
        problems.append("userblock bytes changed")
    added = sorted(set(after.entries) - set(before.entries))
    removed = sorted(set(before.entries) - set(after.entries))
    if added != [added_path]:
        problems.append(f"added paths {added[:10]!r} != [{added_path!r}]")
    if removed:
        problems.append(f"removed paths {removed[:10]!r}")
    changed = sorted(
        p for p in before.entries if p in after.entries and before.entries[p] != after.entries[p]
    )
    if changed:
        problems.append(f"{len(changed)} pre-existing entries changed, e.g. {changed[:10]!r}")
    if added == [added_path] and not after.entries[added_path].startswith("D:"):
        problems.append(f"{added_path!r} is not a dataset")
    if after.n_datasets != before.n_datasets + 1 or after.n_groups != before.n_groups:
        problems.append("group/dataset counts do not differ by exactly one dataset")
    return problems


# --------------------------------------------------------------------------
# Pre-state verification
# --------------------------------------------------------------------------


def verify_ledger_bindings(payload: dict[str, Any], trace_sha: str, repo_root: Path) -> Path:
    """Verify the pre-existing ledger bindings with the loader's conventions.
    Returns the WholeCell root the ledger's sources were resolved under."""
    recorded_trace = payload.get("trace_sha256")
    if recorded_trace != trace_sha:
        raise MigrationError(
            f"ledger trace_sha256={recorded_trace!r} does not match current trace bytes {trace_sha!r}"
        )
    roots: set[Path] = set()
    for key, parts in _SOURCE_PARTS.items():
        recorded = payload.get(key)
        if not recorded:
            raise MigrationError(f"ledger is missing required {key}")
        source = resolve_wcm_source_path(*parts, repo_root=repo_root)
        if source is None:
            raise MigrationError(f"{parts[-1]} could not be resolved from repo_root={repo_root}")
        actual = sha256_raw_bytes(source)
        if recorded != actual:
            raise MigrationError(f"ledger {key}={recorded!r} != current {parts[-1]} sha {actual!r}")
        roots.add(source.parents[len(parts) - 1])
    if len(roots) != 1:
        raise MigrationError(
            f"ledger sources resolved under different WholeCell roots: {sorted(roots)}"
        )
    return roots.pop()


def canonical_dnadamage_sha(repo_root: Path, wcm_root: Path) -> dict[str, Any]:
    from scripts.l2_event.launcher import (
        current_genuine_dnadamage_source,  # heavy; keep workers light
    )

    info = current_genuine_dnadamage_source(repo_root=repo_root)
    sha = info["patched_sha256_lf_normalized"]
    if not isinstance(sha, str) or not _HEX64.match(sha):
        raise MigrationError(f"repository DNADamage hash is not 64 lowercase hex: {sha!r}")
    if Path(info["wcm_root"]) != wcm_root:
        raise MigrationError(
            f"DNADamage.m resolved under {info['wcm_root']} but ledger sources under {wcm_root}"
        )
    return info


def _trace_state(trace_path: Path) -> dict[str, Any]:
    with h5py.File(trace_path, "r") as handle:
        meta = handle.get("metadata")
        if meta is None:
            raise MigrationError(f"{trace_path} has no /metadata group")
        process_name = _decode_h5_text(meta["process_name"][()]) if "process_name" in meta else None
        n_ticks = int(np.asarray(meta["n_ticks"][()]).reshape(-1)[0]) if "n_ticks" in meta else None
        return {
            "has_metadata_field": NEW_METADATA_KEY in meta,
            "process_name": process_name,
            "n_ticks": n_ticks,
        }


# --------------------------------------------------------------------------
# Migration construction
# --------------------------------------------------------------------------


def add_dnadamage_metadata(trace_path: Path, dna_sha: str) -> None:
    """Add exactly one dataset, cloning dtype/shape/attributes from an existing
    MATLAB char metadata dataset of identical (64, 1) layout."""
    with h5py.File(trace_path, "a") as handle:
        meta = handle["metadata"]
        if NEW_METADATA_KEY in meta:
            raise MigrationError(f"{trace_path} already has /metadata/{NEW_METADATA_KEY}")
        template = meta[TEMPLATE_METADATA_KEY]
        if template.shape != (len(dna_sha), 1) or template.dtype != np.dtype("uint16"):
            raise MigrationError(f"template /metadata/{TEMPLATE_METADATA_KEY} layout unexpected")
        data = np.array([ord(char) for char in dna_sha], dtype=np.uint16).reshape(-1, 1)
        created = meta.create_dataset(NEW_METADATA_KEY, data=data, dtype=template.dtype)
        for name in template.attrs:
            created.attrs.create(
                name, template.attrs[name], dtype=template.attrs.get_id(name).dtype
            )


def verify_new_metadata_layout(trace_path: Path, dna_sha: str) -> None:
    with h5py.File(trace_path, "r") as handle:
        meta = handle["metadata"]
        new, template = meta[NEW_METADATA_KEY], meta[TEMPLATE_METADATA_KEY]
        if new.shape != template.shape or new.dtype != template.dtype:
            raise MigrationError(
                "new metadata dataset shape/dtype differs from the MATLAB char layout"
            )
        if sorted(new.attrs.keys()) != sorted(template.attrs.keys()):
            raise MigrationError("new metadata dataset attribute names differ from the template")
        for name in template.attrs:
            if new.attrs.get_id(name).dtype != template.attrs.get_id(
                name
            ).dtype or not np.array_equal(new.attrs[name], template.attrs[name]):
                raise MigrationError(f"new metadata attribute {name!r} differs from the template")
    if _read_trace_metadata_text(trace_path, NEW_METADATA_KEY) != dna_sha:
        raise MigrationError("new metadata dataset does not decode to the canonical DNADamage hash")


def build_migrated_ledger_text(
    old_text: str, payload: dict[str, Any], *, new_trace_sha: str, dna_sha: str
) -> str:
    """Textual splice so every `per_tick` byte stays identical; verified both
    by reversing the splice and by JSON-level key comparison."""
    old_trace_sha = payload["trace_sha256"]
    old_fragment = f'"trace_sha256":"{old_trace_sha}"'
    new_fragment = f'"trace_sha256":"{new_trace_sha}"'
    anchor = f'"randstream_util_source_sha256":"{payload["randstream_util_source_sha256"]}",'
    insertion = f'"{LEDGER_KEY}":"{dna_sha}",'
    for fragment in (old_fragment, anchor):
        if old_text.count(fragment) != 1:
            raise MigrationError(
                f"ledger layout unexpected: {fragment[:60]!r} occurs {old_text.count(fragment)}x"
            )
    new_text = old_text.replace(old_fragment, new_fragment, 1).replace(
        anchor, anchor + insertion, 1
    )

    if new_text.replace(insertion, "", 1).replace(new_fragment, old_fragment, 1) != old_text:
        raise MigrationError("ledger splice is not exactly reversible")
    marker = '"per_tick":'
    if new_text[new_text.index(marker) :] != old_text[old_text.index(marker) :]:
        raise MigrationError("ledger per_tick text changed")
    expected = {key: value for key, value in payload.items() if key != "per_tick"}
    expected["trace_sha256"] = new_trace_sha
    expected[LEDGER_KEY] = dna_sha
    migrated = {key: value for key, value in json.loads(new_text).items() if key != "per_tick"}
    if migrated != expected:
        raise MigrationError(
            "migrated ledger differs from old ledger beyond trace_sha256 + dnadamage_source_sha256"
        )
    return new_text


# --------------------------------------------------------------------------
# Validation of a candidate pair
# --------------------------------------------------------------------------


def run_active_window_smoke(trace_path: Path, ledgers: list[list[float]]) -> None:
    """The frozen `test_txreg_active_window_evaluates_real_binding_event`
    smoke, run against `trace_path`."""
    from tests.vivarium.test_karr_transcriptional_regulation_l2_replay import (
        _run_replay,
        cell_vector,
    )

    with h5py.File(trace_path, "r") as trace:
        before = cell_vector(trace, "states_before", "enzymes", SMOKE_ACTIVE_TICK)
        after = cell_vector(trace, "states_after", "enzymes", SMOKE_ACTIVE_TICK)
        if np.allclose(before, after):
            raise MigrationError(
                f"tick {SMOKE_ACTIVE_TICK} is not an active tick in the oracle trace"
            )
        _run_replay(trace, SMOKE_TICKS, 0, chromosome_rand_stream_ledger=ledgers[:SMOKE_TICKS])


def run_full_replay(trace_path: Path, ledgers: list[list[float]]) -> None:
    from tests.vivarium.test_karr_transcriptional_regulation_l2_replay import _run_replay

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        _run_replay(trace, n_ticks, 0, chromosome_rand_stream_ledger=ledgers)


def load_and_check(trace_path: Path, *, repo_root: Path, expected_ticks: int) -> list[list[float]]:
    ledgers = load_chromosome_rand_stream_ledger(trace_path, repo_root=repo_root)
    if ledgers is None:
        raise MigrationError(f"loader found no ledger for {trace_path}")
    if len(ledgers) != expected_ticks:
        raise MigrationError(
            f"loader returned {len(ledgers)} tick draw lists, expected {expected_ticks}"
        )
    if not any(ledgers):
        raise MigrationError("ledger has no tick with real draws (no active events)")
    return ledgers


def draws_digest(ledgers: list[list[float]]) -> str:
    return hashlib.sha256(json.dumps(ledgers, separators=(",", ":")).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _rollback(
    *,
    trace: Path,
    ledger: Path,
    trace_bak: Path,
    ledger_bak: Path,
    temps: list[Path],
    old_trace_sha: str,
    old_ledger_sha: str,
) -> None:
    for backup, canonical in ((trace_bak, trace), (ledger_bak, ledger)):
        if backup.exists():
            os.replace(backup, canonical)
    for temp in temps:
        _remove_if_exists(temp)
    if sha256_file(trace) != old_trace_sha or sha256_file(ledger) != old_ledger_sha:
        raise MigrationError(
            "ROLLBACK VERIFICATION FAILED: restored artifacts do not match pre-migration hashes"
        )


def migrate(
    trace_path: Path,
    *,
    apply: bool,
    full_replay: bool = False,
    repo_root: Path = REPO_ROOT,
    expected_ticks: int = EXPECTED_TICKS,
    smoke: Any = run_active_window_smoke,
    workers: int = 1,
) -> dict[str, Any]:
    started = time.monotonic()

    def stamp(message: str) -> None:
        _log(f"[{time.monotonic() - started:7.1f}s] {message}")

    if not trace_path.is_absolute() or trace_path.suffix != ".mat" or "." in trace_path.stem:
        raise MigrationError(
            f"trace path must be an absolute dot-free-stem .mat path: {trace_path}"
        )
    ledger_path = ledger_path_for(trace_path)
    if not trace_path.is_file() or not ledger_path.is_file():
        raise MigrationError(f"trace/ledger pair not found: {trace_path} / {ledger_path}")
    leftovers = sorted(trace_path.parent.glob(f"{trace_path.stem}{TEMP_TAG}*"))
    if leftovers:
        raise MigrationError(
            f"leftover migration siblings from an interrupted run, resolve manually: {leftovers}"
        )

    stamp("hashing current trace/ledger")
    old_trace_sha = sha256_file(trace_path)
    old_ledger_bytes = ledger_path.read_bytes()
    old_ledger_sha = hashlib.sha256(old_ledger_bytes).hexdigest()
    old_text = old_ledger_bytes.decode("utf-8")
    payload = json.loads(old_text)
    if not isinstance(payload, dict):
        raise MigrationError("ledger JSON is not an object")

    wcm_root = verify_ledger_bindings(payload, old_trace_sha, repo_root)
    stamp(f"ledger bindings verified (trace, Chromosome.m, RandStream.m) under {wcm_root}")
    dna_info = canonical_dnadamage_sha(repo_root, wcm_root)
    dna_sha = dna_info["patched_sha256_lf_normalized"]
    stamp(f"canonical DNADamage hash {dna_sha} (overlay_required={dna_info['overlay_required']})")

    trace_state = _trace_state(trace_path)
    if trace_state["process_name"] != PROCESS_NAME or trace_state["n_ticks"] != expected_ticks:
        raise MigrationError(f"unexpected trace identity: {trace_state}")
    ledger_has = LEDGER_KEY in payload
    trace_has = trace_state["has_metadata_field"]
    common = {
        "trace_path": str(trace_path),
        "ledger_path": str(ledger_path),
        "dnadamage_source_sha256": dna_sha,
        "dnadamage_source_path": dna_info["source_path"],
        "dnadamage_overlay_required": dna_info["overlay_required"],
    }

    if ledger_has != trace_has:
        raise MigrationError(
            f"partial state (ledger has field={ledger_has}, trace has field={trace_has})"
        )
    if ledger_has:
        trace_value = _read_trace_metadata_text(trace_path, NEW_METADATA_KEY)
        if payload[LEDGER_KEY] != dna_sha or trace_value != dna_sha:
            raise MigrationError(
                f"existing DNADamage binding mismatch: ledger={payload[LEDGER_KEY]!r} trace={trace_value!r} canonical={dna_sha!r}"
            )
        ledgers = load_and_check(trace_path, repo_root=repo_root, expected_ticks=expected_ticks)
        stamp("pair already migrated and the real loader succeeded; no-op")
        return {
            **common,
            "status": "already_migrated",
            "trace_sha256": old_trace_sha,
            "ledger_sha256": old_ledger_sha,
            "draws_sha256": draws_digest(ledgers),
            "active_draw_ticks": sum(1 for draws in ledgers if draws),
        }

    token = uuid.uuid4().hex[:12]
    base = f"{trace_path.stem}{TEMP_TAG}{token}"
    tmp_trace = trace_path.parent / f"{base}.mat"
    tmp_ledger = ledger_path_for(tmp_trace)
    trace_bak = trace_path.parent / f"{base}_premigration_trace.bak"
    ledger_bak = trace_path.parent / f"{base}_premigration_ledger.bak"
    temps = [tmp_trace, tmp_ledger]
    swapped = False
    try:
        stamp(f"copying trace to {tmp_trace.name}")
        shutil.copyfile(trace_path, tmp_trace)
        if sha256_file(tmp_trace) != old_trace_sha:
            raise MigrationError("temporary trace copy is not byte-identical to the source")

        stamp("hashing pre-migration logical payload")
        before = logical_digest(tmp_trace, workers=workers)
        stamp(f"pre: {before.n_groups} groups / {before.n_datasets} datasets")
        add_dnadamage_metadata(tmp_trace, dna_sha)
        stamp("hashing post-migration logical payload")
        after = logical_digest(tmp_trace, workers=workers)
        problems = diff_digests(before, after, added_path=f"/metadata/{NEW_METADATA_KEY}")
        if problems:
            raise MigrationError(
                "logical trace payload differs beyond the new field: " + "; ".join(problems)
            )
        verify_new_metadata_layout(tmp_trace, dna_sha)
        new_trace_sha = sha256_file(tmp_trace)
        stamp(
            f"trace logical payload identical except new field; migrated trace sha {new_trace_sha}"
        )

        new_text = build_migrated_ledger_text(
            old_text, payload, new_trace_sha=new_trace_sha, dna_sha=dna_sha
        )
        tmp_ledger.write_bytes(new_text.encode("utf-8"))
        new_ledger_sha = sha256_file(tmp_ledger)

        ledgers = load_and_check(tmp_trace, repo_root=repo_root, expected_ticks=expected_ticks)
        stamp(f"real loader accepted temporary pair ({len(ledgers)} tick draw lists)")
        smoke(tmp_trace, ledgers)
        stamp(f"active-window smoke passed through tick {SMOKE_ACTIVE_TICK}")
        if full_replay:
            stamp("running full replay on the temporary pair")
            run_full_replay(tmp_trace, ledgers)
            stamp("full replay on the temporary pair passed")

        if sha256_file(trace_path) != old_trace_sha or sha256_file(ledger_path) != old_ledger_sha:
            raise MigrationError(
                "canonical artifacts changed while the temporary pair was being built"
            )

        result = {
            **common,
            "old_trace_sha256": old_trace_sha,
            "new_trace_sha256": new_trace_sha,
            "old_ledger_sha256": old_ledger_sha,
            "new_ledger_sha256": new_ledger_sha,
            "draws_sha256": draws_digest(ledgers),
            "active_draw_ticks": sum(1 for draws in ledgers if draws),
            "n_tick_draw_lists": len(ledgers),
            "logical_trace_datasets": before.n_datasets,
            "logical_trace_groups": before.n_groups,
            "full_replay_on_temp_pair": bool(full_replay),
        }
        if not apply:
            stamp("dry run complete; canonical artifacts untouched")
            return {**result, "status": "dry_run_ok"}

        stamp("swapping pair in (targeted sibling backups)")
        try:
            os.replace(trace_path, trace_bak)
            os.replace(ledger_path, ledger_bak)
            swapped = True
            os.replace(tmp_trace, trace_path)
            os.replace(tmp_ledger, ledger_path)
            if (
                sha256_file(trace_path) != new_trace_sha
                or sha256_file(ledger_path) != new_ledger_sha
            ):
                raise MigrationError("canonical artifacts do not match the validated migrated pair")
            final = load_and_check(trace_path, repo_root=repo_root, expected_ticks=expected_ticks)
            if draws_digest(final) != result["draws_sha256"]:
                raise MigrationError(
                    "canonical loader draws differ from the validated temporary pair"
                )
            stamp("real loader accepted the canonical migrated pair")
        except BaseException:
            stamp("ERROR during swap/verification; restoring originals")
            _rollback(
                trace=trace_path,
                ledger=ledger_path,
                trace_bak=trace_bak,
                ledger_bak=ledger_bak,
                temps=temps,
                old_trace_sha=old_trace_sha,
                old_ledger_sha=old_ledger_sha,
            )
            stamp("originals restored and re-verified")
            raise
        _remove_if_exists(trace_bak)
        _remove_if_exists(ledger_bak)
        stamp("targeted backups removed")
        return {**result, "status": "applied"}
    finally:
        if not swapped:
            for temp in temps:
                _remove_if_exists(temp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=None,
        help="trace path (default: canonical seed-0 event trace)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="mutate the canonical pair (default: dry run)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(12, os.cpu_count() or 1),
        help="processes for the logical HDF5 digest (result is independent of this)",
    )
    parser.add_argument(
        "--full-replay", action="store_true", help="also run the full replay on the temporary pair"
    )
    args = parser.parse_args(argv)

    trace_path = args.trace if args.trace is not None else default_trace_path()
    try:
        result = migrate(
            trace_path, apply=args.apply, full_replay=args.full_replay, workers=args.workers
        )
    except Exception as exc:
        print(f"FAIL-CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
