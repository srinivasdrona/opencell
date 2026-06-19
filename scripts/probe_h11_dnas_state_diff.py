"""H11 probe: capture DNAS no-hints sampler inputs in composition vs isolation.

H8 confirmed harness arithmetic OK.
H9 fixed substrate baseline (own-snapshot).
H10 rejected allocator-budget squeeze (ATP=907, H2O=9080624 both modes).
Yet DNAS in composition emits only -4 ATP vs -60 in isolation.

So something OTHER than substrate baseline / allocator budget differs between
the two modes' `states` dict at the moment DNAS.next_update is called.

This probe captures, at that exact moment, a structured snapshot of the
state subkeys DNAS reads, in both composition and isolation. We then diff
to find what's different.
"""
from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from typing import Any

import numpy as np

import opencell.vivarium.karr_dna_supercoiling as dnasc_mod
from tests.vivarium.l2_2_replay_common_v2 import run_integrated_replay_v2

CAPTURED: list[dict] = []


def _summarize_state(states: dict) -> dict:
    """Capture only the subkeys DNAS reads in its no-hints branch."""
    out = {}
    out["substrates_keys"] = sorted((states.get("substrates") or {}).keys())[:10]
    out["substrates_ATP"] = (states.get("substrates") or {}).get("ATP")
    out["substrates_H2O"] = (states.get("substrates") or {}).get("H2O")

    alloc = states.get("substrates_allocated") or {}
    out["substrates_allocated_keys_top"] = sorted(alloc.keys())
    dnas_alloc = alloc.get("karr_dna_supercoiling") or alloc.get("DNASupercoiling") or {}
    out["alloc_DNAS_ATP"] = dnas_alloc.get("ATP")
    out["alloc_DNAS_H2O"] = dnas_alloc.get("H2O")

    enz = states.get("enzymes") or {}
    out["enzymes_DNA_GYRASE"] = enz.get("DNA_GYRASE")
    out["enzymes_TOPOIV"] = enz.get("MG_203_204_TETRAMER")
    out["enzymes_TOPOI"] = enz.get("MG_122_MONOMER")

    bound = states.get("boundEnzymes") or {}
    out["boundEnzymes_DNA_GYRASE"] = bound.get("DNA_GYRASE")
    out["boundEnzymes_TOPOIV"] = bound.get("MG_203_204_TETRAMER")

    chrom = states.get("chromosome") or {}
    if isinstance(chrom, dict):
        out["chromosome_keys"] = sorted(chrom.keys())
        out["chromosome_replication_state"] = chrom.get("replication_state")
        out["chromosome_supercoiled"] = chrom.get("supercoiled")
        out["chromosome_supercoil_density"] = chrom.get("supercoil_density")
        lnk = chrom.get("linkingNumbers")
        if isinstance(lnk, dict):
            out["lnk_keys"] = sorted(lnk.keys())[:5]
            if "values" in lnk and isinstance(lnk["values"], list):
                out["lnk_values_first5"] = lnk["values"][:5]
        polyreg = chrom.get("polymerizedRegions")
        if isinstance(polyreg, dict):
            out["polyreg_keys"] = sorted(polyreg.keys())[:5]
            if "values" in polyreg and isinstance(polyreg["values"], list):
                out["polyreg_values_first5"] = polyreg["values"][:5]
            if "row" in polyreg and hasattr(polyreg["row"], "__len__"):
                out["polyreg_n_rows"] = len(polyreg["row"])
        cbs = chrom.get("complexBoundSites")
        if isinstance(cbs, dict):
            out["cbs_keys"] = sorted(cbs.keys())[:5]
            if "row" in cbs and hasattr(cbs["row"], "__len__"):
                out["cbs_n_rows"] = len(cbs["row"])
    return out


@contextmanager
def capture_dnas_state(tag: str):
    """Monkey-patch DNAS.next_update to record states at tick 0."""
    cls = dnasc_mod.KarrDNASupercoilingProcess
    orig = cls.next_update
    tick_counter = {"n": 0}

    def wrapped(self, timestep, states):
        if tick_counter["n"] == 0:
            CAPTURED.append({"tag": tag, "tick": 0, "snapshot": _summarize_state(states)})
        tick_counter["n"] += 1
        return orig(self, timestep, states)

    cls.next_update = wrapped
    try:
        yield
    finally:
        cls.next_update = orig


def main() -> None:
    print("=== H11 probe: DNAS sampler input comparison composition vs isolation ===\n")
    # Composition
    try:
        with capture_dnas_state("composition"):
            run_integrated_replay_v2(
                under_test_processes=["ChromosomeCondensation", "DNASupercoiling"],
                rng_seed=0,
                disable_trace_hints=True,
            )
    except BaseException as e:
        print(f"composition run completed/failed as expected: {type(e).__name__}\n")

    # Isolation
    try:
        with capture_dnas_state("isolation"):
            run_integrated_replay_v2(
                under_test_processes=["DNASupercoiling"],
                rng_seed=0,
                disable_trace_hints=True,
            )
    except BaseException as e:
        print(f"isolation run completed: {type(e).__name__}\n")

    # Print both snapshots side by side
    if len(CAPTURED) < 2:
        print(f"ERROR: only captured {len(CAPTURED)} snapshots")
        for s in CAPTURED:
            print(s)
        return

    comp = next((c for c in CAPTURED if c["tag"] == "composition"), None)
    iso = next((c for c in CAPTURED if c["tag"] == "isolation"), None)
    if not comp or not iso:
        print("ERROR: missing one tag")
        return

    print("--- COMPOSITION snapshot ---")
    print(json.dumps(comp["snapshot"], indent=2, default=str))
    print("\n--- ISOLATION snapshot ---")
    print(json.dumps(iso["snapshot"], indent=2, default=str))
    print("\n--- DIFF: keys with different values ---")
    all_keys = set(comp["snapshot"].keys()) | set(iso["snapshot"].keys())
    for k in sorted(all_keys):
        cv = comp["snapshot"].get(k, "<MISSING>")
        iv = iso["snapshot"].get(k, "<MISSING>")
        if cv != iv:
            print(f"  {k}:")
            print(f"    composition: {cv}")
            print(f"    isolation:   {iv}")


if __name__ == "__main__":
    main()
