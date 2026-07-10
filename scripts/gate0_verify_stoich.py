"""Gate 0 (stoichiometry) — Karr source-of-truth reaction matrices vs fixture.

Companion to gate0_verify_input_vocab.py. The frozen input spec froze each process's
reaction stoichiometry (shape + sha256 + per-reaction breakdown) DERIVED from the
extracted fixture. This confirms the fixture's stoichiometry matrices are faithful to
the live source, so the freeze does not lock in an extraction-level matrix error.

Authoritative dump: `data/karr_input_spec/_gate0_source_stoich.json`, produced by
`scripts/matlab/gate0_dump_process_stoich.m` (bootstraps Simulation_fitted, dumps each
live process's reactionStoichiometryMatrix / reactionSmallMoleculeStoichiometryMatrix /
reactionDNAStoichiometryMatrix as exact sparse nonzero triples: 1-based column-major
linear indices + values + shape).

This comparator (no MATLAB needed once the dump is committed) loads each fixture's same
matrix, extracts the identical column-major nonzero representation, and asserts an EXACT
match (shape + indices + values). Exit 0 = PASS / clean SKIP; exit 1 = any divergence.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

_REPO = Path(__file__).resolve().parents[1]
_SRC_STOICH = _REPO / "data" / "karr_input_spec" / "_gate0_source_stoich.json"
_FIXTURE_DIR = _REPO / "data" / "karr_fixtures" / "per_process"


def _fixture_matrix(proc: str, field: str) -> np.ndarray | None:
    fx = loadmat(
        _FIXTURE_DIR / f"{proc}_flat.mat", squeeze_me=True, struct_as_record=False
    )["data"].fixture
    m = getattr(fx, field, None)
    if m is None:
        return None
    arr = np.asarray(m, dtype=np.float64)
    return arr


def _colmajor_nonzero(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Column-major (Fortran-order) 1-based linear indices + values of nonzeros,
    matching MATLAB `find(M)` / `M(find(M))`."""
    flat = arr.flatten(order="F")
    idx = np.flatnonzero(flat)
    return (idx + 1).astype(np.int64), flat[idx].astype(np.float64)


def main() -> int:
    if not _SRC_STOICH.exists():
        print(
            f"GATE 0 (stoichiometry): SKIPPED — source dump absent at "
            f"{_SRC_STOICH.relative_to(_REPO)}. Regenerate: gate0_dump_process_stoich.m"
        )
        return 0

    src = json.loads(_SRC_STOICH.read_text())
    findings: list[str] = []
    n_matrices = 0
    n_procs_with_stoich = 0

    for entry in src["processes"]:
        proc = entry["name"]
        mats = entry.get("matrices") or {}
        if not mats:
            continue
        n_procs_with_stoich += 1
        for field, m in mats.items():
            n_matrices += 1
            src_size = [int(x) for x in m["size"]]
            src_idx = np.asarray(m["nz_idx"], dtype=np.int64).reshape(-1)
            src_val = np.asarray(m["nz_val"], dtype=np.float64).reshape(-1)

            fx = _fixture_matrix(proc, field)
            if fx is None:
                findings.append(f"{proc}.{field}: present in SOURCE, ABSENT in fixture")
                continue

            fx_size = list(fx.shape)
            # MATLAB squeezes trailing singleton dims; align by trimming/padding.
            if fx_size != src_size:
                # tolerate trailing-singleton differences (e.g. [n,m] vs [n,m,1])
                a = fx_size + [1] * (len(src_size) - len(fx_size))
                b = src_size + [1] * (len(fx_size) - len(src_size))
                if a != b:
                    findings.append(
                        f"{proc}.{field}: SHAPE mismatch src={src_size} fixture={fx_size}"
                    )
                    continue

            fx_idx, fx_val = _colmajor_nonzero(fx)

            if fx_idx.shape != src_idx.shape or not np.array_equal(fx_idx, src_idx):
                only_src = np.setdiff1d(src_idx, fx_idx)
                only_fix = np.setdiff1d(fx_idx, src_idx)
                findings.append(
                    f"{proc}.{field}: NONZERO-INDEX mismatch "
                    f"(src_nnz={src_idx.size} fix_nnz={fx_idx.size}; "
                    f"idx_only_in_source={only_src[:8].tolist()} "
                    f"idx_only_in_fixture={only_fix[:8].tolist()})"
                )
                continue

            if not np.array_equal(fx_val, src_val):
                bad = int(np.flatnonzero(fx_val != src_val)[0])
                findings.append(
                    f"{proc}.{field}: VALUE mismatch at nz#{bad} "
                    f"(src={src_val[bad]} fixture={fx_val[bad]})"
                )

    if findings:
        print(f"GATE 0 (stoichiometry): FAIL — {len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        return 1

    print(
        f"GATE 0 (stoichiometry): PASS — {n_procs_with_stoich} processes, "
        f"{n_matrices} matrices; source_truth == fixture, exact (shape + nonzero indices + values)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
