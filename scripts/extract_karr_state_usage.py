"""Extract each Karr process's ACTUAL global-state usage from the MATLAB source.

Companion to the Gate-0 fidelity artifacts. Karr's base `storeObjectReferences`
(`Process.m:307`) hands EVERY process references to the same 5 state objects
(Geometry, Metabolite, Rna, ProteinMonomer, ProteinComplex) plus subclass
additions (Chromosome, Transcript, RNAPolymerase, ...) — an AVAILABILITY list, not
a USAGE list. So `state_refs` in `_gate0_source_truth.json` overstates what a
process actually reads.

This extracts the USAGE list instead: for each process `.m`, the set of state
classes it actually accesses via `this.<state>.<member>` (a dot access — the bare
`this.rna = simulation.state('Rna')` assignment does NOT match). That is the
authoritative surface Gate 2 must validate OC against (does OC reach every state
Karr's process actually uses?). Pure text parse — no MATLAB required.

Output: `data/karr_input_spec/_karr_state_usage.json`
  { "<Process>": {"states_used": [<StateClass>, ...],
                   "counts": {<StateClass>: <n dot-accesses>}}, ... }
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PROC_DIR = (
    _REPO
    / "data" / "m1_sources" / "WholeCell" / "src"
    / "+edu" / "+stanford" / "+covert" / "+cell" / "+sim" / "+process"
)
_OUT = _REPO / "data" / "karr_input_spec" / "_karr_state_usage.json"

# state property name (as accessed via this.<prop>) -> Karr state class.
# Derived from every `this.<prop> = simulation.state('<Class>')` across the source.
_STATE_PROPS: dict[str, str] = {
    "geometry": "Geometry",
    "stimulus": "Stimulus",
    "metabolite": "Metabolite",
    "rna": "Rna",
    "monomer": "ProteinMonomer",
    "complex": "ProteinComplex",
    "chromosome": "Chromosome",
    "transcript": "Transcript",
    "transcripts": "Transcript",
    "rnaPolymerase": "RNAPolymerase",
    "rnaPolymerases": "RNAPolymerase",
    "ribosome": "Ribosome",
    "ftsZRing": "FtsZRing",
    "host": "Host",
    "mass": "Mass",
    "polypeptide": "Polypeptide",
    "metabolicReaction": "MetabolicReaction",
}

# Process spec name -> <Process>.m stem (identical for all 28).
_PROCESSES: tuple[str, ...] = (
    "ChromosomeCondensation", "ChromosomeSegregation", "Cytokinesis", "DNADamage",
    "DNARepair", "DNASupercoiling", "FtsZPolymerization", "HostInteraction",
    "MacromolecularComplexation", "Metabolism", "ProteinActivation", "ProteinDecay",
    "ProteinFolding", "ProteinModification", "ProteinProcessingI", "ProteinProcessingII",
    "ProteinTranslocation", "Replication", "ReplicationInitiation", "RibosomeAssembly",
    "RNADecay", "RNAModification", "RNAProcessing", "TerminalOrganelleAssembly",
    "Transcription", "TranscriptionalRegulation", "Translation", "tRNAAminoacylation",
)


def extract() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for proc in _PROCESSES:
        text = (_PROC_DIR / f"{proc}.m").read_text(encoding="utf-8", errors="replace")
        counts: dict[str, int] = {}
        for prop, cls in _STATE_PROPS.items():
            n = len(re.findall(r"this\." + re.escape(prop) + r"\.", text))
            if n:
                counts[cls] = counts.get(cls, 0) + n
        result[proc] = {
            "states_used": sorted(counts),
            "counts": {k: counts[k] for k in sorted(counts)},
        }
    return result


def main() -> int:
    data = extract()
    _OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    n_states = sum(len(v["states_used"]) for v in data.values())  # type: ignore[arg-type]
    print(
        f"wrote {_OUT.relative_to(_REPO)} — {len(data)} processes, "
        f"{n_states} (process, state) usage edges."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
