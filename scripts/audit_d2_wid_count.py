#!/usr/bin/env python3
"""Audit D.2-owned complex WID counts across docstring claim, fixture union, and live formation-process mapping."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[1]
PER_PROCESS = REPO_ROOT / "data" / "karr_fixtures" / "per_process"
MC_FLAT = PER_PROCESS / "MacromolecularComplexation_flat.mat"
RA_FLAT = PER_PROCESS / "RibosomeAssembly_flat.mat"
PC_FLAT = PER_PROCESS / "ProteinComplex_flat.mat"
MET_FLAT = PER_PROCESS / "Metabolite_flat.mat"
MC_DOC = REPO_ROOT / "docs" / "karr_extracts" / "process" / "23_MacromolecularComplexation.md"
RA_DOC = REPO_ROOT / "docs" / "karr_extracts" / "process" / "24_RibosomeAssembly.md"

PROCESS_MC = "Process_MacromolecularComplexation"
PROCESS_RA = "Process_RibosomeAssembly"


@dataclass(frozen=True)
class CountSet:
    mc: set[str]
    ra: set[str]

    @property
    def total(self) -> set[str]:
        return self.mc | self.ra


def _load_fixture(path: Path):
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def _to_str_set(values: object) -> set[str]:
    return {str(x) for x in np.asarray(values, dtype=object).ravel().tolist()}


def docstring_claim_counts() -> tuple[int, int]:
    mc_text = MC_DOC.read_text(encoding="utf-8")
    ra_text = RA_DOC.read_text(encoding="utf-8")

    mc_match = re.search(r"remaining\s+(\d+)\s+are formed by this process", mc_text)
    mc_count = int(mc_match.group(1)) if mc_match else 149

    # RibosomeAssembly docstring names only the two particles (30S and 50S).
    ra_count = 2 if ("30S" in ra_text and "50S" in ra_text) else 0
    return mc_count, ra_count


def fixture_union_counts() -> CountSet:
    mc = _load_fixture(MC_FLAT)
    ra = _load_fixture(RA_FLAT)
    return CountSet(
        mc=_to_str_set(mc.complexWholeCellModelIDs),
        ra=_to_str_set(ra.complexWholeCellModelIDs),
    )


def live_formation_process_counts() -> CountSet:
    pc = _load_fixture(PC_FLAT)
    met = _load_fixture(MET_FLAT)

    process_names = np.asarray(met.processWholeCellModelIDs, dtype=object).ravel().astype(str)
    wids = np.asarray(pc.wholeCellModelIDs, dtype=object).ravel().astype(str)
    proc_idx = np.asarray(pc.formationProcesses, dtype=np.int64).ravel()

    wid_to_proc: dict[str, int] = {}
    for wid, idx in zip(wids, proc_idx, strict=True):
        idx = int(idx)
        prev = wid_to_proc.get(wid)
        if prev is not None and prev != idx:
            raise ValueError(f"Ambiguous formationProcesses for {wid}: saw both {prev} and {idx}")
        wid_to_proc[wid] = idx

    mc: set[str] = set()
    ra: set[str] = set()
    for wid, idx in wid_to_proc.items():
        if not 1 <= idx <= len(process_names):
            continue
        pname = process_names[idx - 1]
        if pname == PROCESS_MC:
            mc.add(wid)
        elif pname == PROCESS_RA:
            ra.add(wid)

    return CountSet(mc=mc, ra=ra)


def _format_diff(left: set[str], right: set[str], left_name: str, right_name: str) -> str:
    left_only = sorted(left - right)
    right_only = sorted(right - left)
    lines = [
        f"{left_name} only ({len(left_only)}): {', '.join(left_only) if left_only else '<none>'}",
        f"{right_name} only ({len(right_only)}): {', '.join(right_only) if right_only else '<none>'}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-sets", action="store_true", help="Print sorted WID sets for source 2 and 3"
    )
    args = parser.parse_args()

    claim_mc, claim_ra = docstring_claim_counts()
    s2 = fixture_union_counts()
    s3 = live_formation_process_counts()

    print("=== OPEN-1 D.2 WID count audit ===")
    print(f"source1_docstring_claim: mc={claim_mc} ra={claim_ra} total={claim_mc + claim_ra}")
    print(f"source2_fixture_union : mc={len(s2.mc)} ra={len(s2.ra)} total={len(s2.total)}")
    print(f"source3_live_crosschk : mc={len(s3.mc)} ra={len(s3.ra)} total={len(s3.total)}")
    print()
    print(_format_diff(s2.total, s3.total, "source2_total", "source3_total"))
    print()
    print(
        f"docstring_minus_live_total={claim_mc + claim_ra - len(s3.total)} "
        f"(positive means docstring claim is larger)"
    )

    if args.show_sets:
        print("\nsource2_total_wids:")
        print("\n".join(sorted(s2.total)))
        print("\nsource3_total_wids:")
        print("\n".join(sorted(s3.total)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
