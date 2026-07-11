"""Extract each Karr process's ACTUAL global-state usage from the MATLAB source.

Companion to the Gate-0 fidelity artifacts. Karr's base `storeObjectReferences`
(`Process.m:307`) hands EVERY process references to the same 5 state objects
(Geometry, Metabolite, Rna, ProteinMonomer, ProteinComplex) plus subclass
additions (Chromosome, Transcript, RNAPolymerase, ...) — an AVAILABILITY list, not
a USAGE list. So `state_refs` in `_gate0_source_truth.json` overstates what a
process actually reads.

This extracts the USAGE list instead: for each process `.m`, the set of state
classes it actually accesses via `this.<state>.<member>` (a dot access — the bare
`this.rna = simulation.state('Rna')` assignment does NOT match) **within its
runtime methods only**. Init/allocation methods (`initializeConstants`,
`allocateMemory`, the constructor, `storeObjectReferences`, the `compute*Names`
annotation getters) are EXCLUDED, because their state accesses are array-sizing /
ID-list / index-mapping bookkeeping (e.g. `numel(this.rna.wholeCellModelIDs)`),
not per-tick input coupling. That is the authoritative surface Gate 2 must
validate OC against (does OC reach every state Karr's process actually uses at
runtime?). Pure text parse — no MATLAB required.

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

# Method names whose bodies are init/allocation bookkeeping, not runtime input
# usage — their `this.<state>.` accesses are array sizing / ID lists / index maps
# and must NOT count as state usage. The per-class constructor (== process name)
# is excluded separately.
_INIT_METHODS: frozenset[str] = frozenset({
    "initializeconstants",
    "allocatememory",
    "storeobjectreferences",
    "computefixedconstantsnames",
    "computefittedconstantsnames",
    "computelocalstatenames",
    "computeoptionsnames",
})

_FUNCTION_NAME_RE = re.compile(r"function\s+(?:\[?[\w,\s~]*\]?\s*=\s*)?(\w+)\s*\(")
# An occurrence is a WRITE (excluded) if the member access is the LHS of an
# assignment: `this.rna.X = ...` or `this.rna.X(idx) = ...` (but not `==`/`~=`/`<=`/`>=`).
_ASSIGN_AFTER_RE = re.compile(r"\s*(\([^)]*\))?\s*=(?![=])")
# Alias binding: `var = this.<prop>;` (no further member) — lets us follow
# `rnaPols = this.rnaPolymerases; rnaPols.states` as a read of RNAPolymerase.
_ALIAS_RE = re.compile(r"\b([A-Za-z]\w*)\s*=\s*this\.(\w+)\s*;")


def _count_reads(text: str, base: str) -> int:
    """Count member READS of `<base>.<member>` (base = `this.<prop>` or an alias var),
    excluding LHS writes."""
    count = 0
    for match in re.finditer(re.escape(base) + r"\.(\w+)", text):
        if _ASSIGN_AFTER_RE.match(text[match.end():]):
            continue  # write, not a read
        count += 1
    return count

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


def _runtime_text(text: str, process: str) -> str:
    """Return the concatenation of method bodies that are NOT init/allocation.

    Splits the class source on `function` declarations and drops the constructor
    (name == process) and the known init/annotation methods, so only runtime
    methods (evolveState, calcResourceRequirements*, and their helpers) remain.
    """
    matches = list(_FUNCTION_NAME_RE.finditer(text))
    if not matches:
        return text
    excluded = _INIT_METHODS | {process.lower()}
    kept: list[str] = []
    for i, match in enumerate(matches):
        name = match.group(1).lower()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if name not in excluded:
            kept.append(text[start:end])
    return "\n".join(kept)


def extract() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for proc in _PROCESSES:
        raw = (_PROC_DIR / f"{proc}.m").read_text(encoding="utf-8", errors="replace")
        text = _runtime_text(raw, proc)
        counts: dict[str, int] = {}
        # Direct reads: this.<prop>.<member> (excluding writes).
        for prop, cls in _STATE_PROPS.items():
            n = _count_reads(text, f"this.{prop}")
            if n:
                counts[cls] = counts.get(cls, 0) + n
        # Alias reads: `var = this.<prop>;` then `var.<member>` (excluding writes).
        for match in _ALIAS_RE.finditer(text):
            var, prop = match.group(1), match.group(2)
            cls = _STATE_PROPS.get(prop)
            if cls is None or var == "this":
                continue
            n = _count_reads(text, var)
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
