"""H11 verification probe: are per-process tick-0 baselines from different
intra-tick positions in the SAME Karr simulation, or genuinely different cell-cycle
moments?

Hypothesis: the per-process trace extractor (extract_per_process_traces_v2.m)
captures each target process's state at the moment that process runs within
Karr's randperm-ordered per-tick loop. Same simulation, same tick, but
different intra-tick positions = different substrate-pool depletion levels.

If true, the trace tick-0 substrate values for different processes form a
MONOTONIC sequence reflecting the position order:
  - First-position process sees nearly-full ATP (post-Metabolism)
  - Each subsequent process sees less ATP (consumed by predecessors)
  - Last-position process sees the lowest ATP

If FALSE (i.e., truly different cell cycle moments), the values would
follow no consistent ordering and could vary by orders of magnitude in
seemingly unrelated ways.

We load tick-0 substrates_before[ATP] for all available process traces and
print them sorted. Then check: does the sequence show smooth monotonic depletion
(supports same-tick-different-position) or large erratic gaps (supports
different-cell-cycle-moments)?
"""
from __future__ import annotations
from pathlib import Path
import h5py
import numpy as np

TRACE_DIR = Path("/mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2")

# Substrate WIDs to inspect (same as DNAS/Cond catalog)
TARGET_WIDS = ["ATP", "ADP", "PI", "H2O", "H"]


def load_tick0_substrates(process_name: str) -> dict[str, float]:
    """Load tick-0 substrates_before values from this process's trace."""
    path = TRACE_DIR / f"{process_name}_100ticks.mat"
    if not path.exists():
        return None
    with h5py.File(str(path), "r") as f:
        # snapshot_properties tells us field layout
        if "states_before" not in f:
            return None
        subs_grp = f["states_before"].get("substrates")
        if subs_grp is None:
            return None
        # substrates is either a Dataset of per-tick vectors OR a struct of WIDs
        # v2 extractor stores per-tick cells of substrate vectors
        # Check structure
        if isinstance(subs_grp, h5py.Dataset):
            # Probably a (1, n_ticks) array of h5py references to vectors
            if subs_grp.ndim == 2 and subs_grp.dtype.kind == 'O':
                ref0 = subs_grp[0, 0]
                vec = f[ref0][:].flatten()
            else:
                vec = np.asarray(subs_grp[0, :]).flatten()
        else:
            return None
        # We don't have WID names in the trace - need to load metadata
        # snapshot_properties only lists 'substrates' not WID names
        # The order is canonical: substrateWholeCellModelIDs from the proc's MATLAB class
        # For now, just return the first 5 values which correspond to ATP/ADP/PI/H2O/H
        # for DNAS specifically; other processes may have different orderings
        # So this is approximate.
        return {"vec_first_5": vec[:5].tolist(), "vec_len": len(vec)}


def main() -> None:
    processes = [
        "ChromosomeCondensation",
        "ChromosomeSegregation",
        "DNASupercoiling",
        "DNARepair",
        "DNADamage",
        "Replication",
        "ReplicationInitiation",
        "FtsZPolymerization",
        "Cytokinesis",
        "Metabolism",
        "Transcription",
        "Translation",
        "RNADecay",
        "RNAProcessing",
        "RNAModification",
        "tRNAAminoacylation",
        "RibosomeAssembly",
        "ProteinFolding",
        "ProteinTranslocation",
        "ProteinDecay",
        "ProteinModification",
        "ProteinProcessingI",
        "ProteinProcessingII",
        "MacromolecularComplexation",
        "HostInteraction",
        "TerminalOrganelleAssembly",
    ]

    print("=== H11 verification: tick-0 substrates_before vectors for all processes ===\n")
    print(f"Loading from: {TRACE_DIR}\n")

    table = []
    for p in processes:
        result = load_tick0_substrates(p)
        if result is None:
            table.append((p, "missing", 0))
            continue
        table.append((p, result["vec_first_5"], result["vec_len"]))

    # Print
    for p, vec, n in table:
        if vec == "missing":
            print(f"  {p:30s}  <trace not found>")
            continue
        print(f"  {p:30s}  len={n:4d}  first_5_values={vec}")


if __name__ == "__main__":
    main()
