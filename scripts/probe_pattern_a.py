"""Probe Pattern A wid-length drift across all 7 affected processes."""
from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

from l2_replay_common import cell_vector, resolve_trace_path  # noqa: E402

# (process_name, ProcessClass module path, class name, observables, attr-map)
PATTERN_A = [
    ("Cytokinesis", "opencell.vivarium.karr_cytokinesis", "KarrCytokinesisProcess",
     ("substrates", "enzymes", "boundEnzymes"),
     {"substrates": "substrate_wids", "enzymes": "enzyme_wids", "boundEnzymes": "enzyme_wids"}),
    ("Metabolism", "opencell.vivarium.karr_metabolism", "KarrMetabolismProcess",
     ("substrates", "enzymes", "boundEnzymes"),
     {"substrates": "substrate_wids", "enzymes": "enzyme_wids", "boundEnzymes": "enzyme_wids"}),
    ("ProteinDecay", "opencell.vivarium.karr_protein_decay", "KarrProteinDecayProcess",
     ("substrates", "enzymes", "boundEnzymes"),
     {"substrates": "substrate_wids", "enzymes": "enzyme_wids", "boundEnzymes": "enzyme_wids"}),
    ("ProteinModification", "opencell.vivarium.karr_protein_modification", "KarrProteinModificationProcess",
     ("substrates", "enzymes", "boundEnzymes"),
     {"substrates": "substrate_wids", "enzymes": "enzyme_wids", "boundEnzymes": "enzyme_wids"}),
    ("ProteinTranslocation", "opencell.vivarium.karr_protein_translocation", "KarrProteinTranslocationProcess",
     ("substrates", "enzymes", "boundEnzymes"),
     {"substrates": "substrate_wids", "enzymes": "enzyme_wids", "boundEnzymes": "enzyme_wids"}),
    ("RNAModification", "opencell.vivarium.karr_rna_modification", "KarrRNAModificationProcess",
     ("substrates", "enzymes", "boundEnzymes"),
     {"substrates": "substrate_wids", "enzymes": "enzyme_wids", "boundEnzymes": "enzyme_wids"}),
    ("ProteinActivation", "opencell.vivarium.karr_protein_activation", "KarrProteinActivationProcess",
     ("substrates", "enzymes", "boundEnzymes"),
     {"substrates": "substrate_wids", "enzymes": "enzyme_wids", "boundEnzymes": "enzyme_wids"}),
]


def _probe_one(proc_name: str, mod_path: str, cls_name: str, observables, attr_map):
    print(f"\n=== {proc_name} ===")
    try:
        mod = __import__(mod_path, fromlist=[cls_name])
        Cls = getattr(mod, cls_name)
        proc = Cls({"rng_seed": 0})
    except Exception as e:
        print(f"  PROCESS_LOAD_ERROR: {type(e).__name__}: {e}")
        return

    try:
        trace_path = resolve_trace_path(proc_name)
    except FileNotFoundError as e:
        print(f"  TRACE_MISSING: {e}")
        return

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        for obs in observables:
            attr = attr_map.get(obs)
            proc_attr_val = getattr(proc, attr, None) if attr else None
            proc_len = len(proc_attr_val) if proc_attr_val is not None else None

            kb0 = cell_vector(trace, "states_before", obs, 0)
            ka0 = cell_vector(trace, "states_after", obs, 0)
            # Probe at later ticks for variance
            shapes_before = {int(cell_vector(trace, "states_before", obs, t).shape[0]) for t in range(min(n_ticks, 10))}
            shapes_after = {int(cell_vector(trace, "states_after", obs, t).shape[0]) for t in range(min(n_ticks, 10))}
            print(f"  {obs:14s} proc.{attr}={proc_len}  karr_before[0]={kb0.shape[0]}  karr_after[0]={ka0.shape[0]}  "
                  f"before_shapes(t<10)={sorted(shapes_before)}  after_shapes(t<10)={sorted(shapes_after)}")


def main():
    for entry in PATTERN_A:
        try:
            _probe_one(*entry)
        except Exception as e:
            print(f"  UNHANDLED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
