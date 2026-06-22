"""Audit OC karr_*.py processes for port-mismatch bugs.

The Translocation bug pattern (discovered Day-36):
  next_update reads from a state port (e.g. protein.enzyme_counts) that is
  NOT in the process's declared observables list. The harness overlays
  declared observables from Karr's trace at each tick. Ports NOT in
  observables are template-default (usually 0).

  In L2.1 isolation: port stays empty -> biology returns trivially zero
  -> happens to match Karr's expected delta (which is also zero for ticks
  where this rate-limiting port mattered) -> L2.1 PASSES coincidentally.

  In L2.5 composition: upstream process's overlay populates the port
  (e.g. ProteinFolding writes protein.enzyme_counts for chaperonins) ->
  biology runs events Karr never intended -> L2.5 FAILS.

This script: for each karr_*.py, list the state ports it reads in
next_update, compare to the observables declared in the harness's
_ProcessSpec table, and flag mismatches.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VIVARIUM = REPO / "opencell" / "vivarium"
HARNESS = REPO / "tests" / "vivarium" / "l2_2_replay_common_v2.py"


def parse_process_specs() -> dict[str, set[str]]:
    """Parse _PROCESS_SPECS from the harness — return {name: set(observables)}."""
    text = HARNESS.read_text(encoding="utf-8")
    out: dict[str, set[str]] = {}
    pat = re.compile(
        r'"(?P<name>[A-Za-z]+)":\s*_ProcessSpec\([^)]*?observables=\((?P<obs>[^)]+)\)',
        re.S,
    )
    for m in pat.finditer(text):
        name = m.group("name")
        obs_raw = m.group("obs")
        obs = {o.strip().strip('"').strip("'") for o in obs_raw.split(",") if o.strip()}
        obs.discard("")
        out[name] = obs
    return out


# Map declared `observables` to canonical state port paths the harness routes them to.
# (Derived from l2_replay_common.py:_OBS_STORE_PATHS plus the dynamic
# `monomers` -> protein.unprocessed_counts fallback.)
OBSERVABLE_TO_PORTS = {
    "substrates": ["substrates", "substrates_allocated"],
    "enzymes": ["enzymes"],
    "boundEnzymes": ["boundEnzymes"],
    "complexs": ["complex.counts"],
    "RNAs": ["rna.counts"],
    "monomers": ["protein.counts", "protein.unprocessed_counts"],
    "foldedMonomers": ["protein.counts"],
    "unfoldedMonomers": ["protein.unfolded_counts"],
    "modifiedMonomers": ["protein.counts"],
    "unmodifiedMonomers": ["protein.counts"],
    "processedMonomers": ["protein.counts", "protein.processed_counts"],
    "unprocessedMonomers": ["protein.counts", "protein.unprocessed_counts"],
    "freeRNAs": ["rna.counts"],
    "aminoacylatedRNAs": ["rna.aminoacylated_counts"],
    "modifiedRNAs": ["rna.modified_counts", "rna.counts"],
    "unmodifiedRNAs": ["rna.counts"],
    "processedRNAs": ["rna.counts"],
    "unprocessedRNAs": ["rna.counts"],
}

# Hidden-read-surface channels (injected separately, not via observable overlay)
HIDDEN_PORTS = {
    "chromosome": "chromosome (hidden_read_surface)",
    "stimulus": "stimulus.values (hidden_read_surface)",
    "rnaPolymerase": "rnaPolymerase.* (hidden_read_surface)",
}


def covered_ports(observables: set[str]) -> set[str]:
    """Set of state-port paths the harness's overlay can populate."""
    covered = set()
    for obs in observables:
        for path in OBSERVABLE_TO_PORTS.get(obs, []):
            covered.add(path)
    # Always present via the allocator refresh
    covered.add("substrates_allocated")
    return covered


def extract_state_reads(module_path: Path) -> list[tuple[int, str]]:
    """Find all states[...].get(...) and states.get(...) read patterns in
    next_update. Returns list of (line_no, path_expression)."""
    if not module_path.exists():
        return []
    text = module_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    # Heuristic: only consider lines within next_update body.
    in_next_update = False
    indent = None
    reads: list[tuple[int, str]] = []

    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("def next_update"):
            in_next_update = True
            indent = len(line) - len(stripped)
            continue
        if in_next_update:
            # End of next_update when we hit another def at same or lower indent
            if stripped.startswith("def ") and (len(line) - len(stripped)) <= indent:
                in_next_update = False
                continue
            # Pattern: states.get("X", ...) or state.get("X", ...) or states["X"]
            for m in re.finditer(r'(?:states?|state)\s*\.\s*get\s*\(\s*["\'](\w+)["\']', line):
                reads.append((i, m.group(1)))
            for m in re.finditer(r'(?:states?|state)\s*\[\s*["\'](\w+)["\']\s*\]', line):
                reads.append((i, m.group(1)))
    return reads


def extract_nested_reads(module_path: Path) -> list[tuple[int, str]]:
    """Look for nested .get() chains like states.get('protein',{}).get('counts',{}).
    Also catches the two-line pattern:
        x = states.get('protein', {})
        y = x.get('counts', {})

    Returns list of (line_no, 'protein.counts'-style key)."""
    if not module_path.exists():
        return []
    text = module_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    in_next_update = False
    indent = None
    out: list[tuple[int, str]] = []

    # Pattern A: single-line chained get
    pat_chain = re.compile(
        r'(?:states?|state)\s*\.\s*get\s*\(\s*["\'](\w+)["\'][^)]*\)\s*\.\s*get\s*\(\s*["\'](\w+)["\']'
    )
    # Pattern B: variable bound to states.get(...)
    pat_bind = re.compile(
        r'^(\s*)(\w+)\s*=\s*(?:states?|state)\s*\.\s*get\s*\(\s*["\'](\w+)["\']'
    )
    # Pattern C: var.get('sub', ...) where var was bound above
    pat_var_get = re.compile(
        r'(\w+)\s*\.\s*get\s*\(\s*["\'](\w+)["\']'
    )

    # Track bindings as we walk next_update body
    bindings: dict[str, str] = {}

    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("def next_update"):
            in_next_update = True
            indent = len(line) - len(stripped)
            bindings = {}
            continue
        if in_next_update:
            if stripped.startswith("def ") and (len(line) - len(stripped)) <= indent:
                in_next_update = False
                continue

            for m in pat_chain.finditer(line):
                out.append((i, f"{m.group(1)}.{m.group(2)}"))

            bm = pat_bind.search(line)
            if bm:
                bindings[bm.group(2)] = bm.group(3)

            # For each var.get('sub') where var is bound, record port.sub
            for m in pat_var_get.finditer(line):
                var, sub = m.group(1), m.group(2)
                if var in bindings:
                    out.append((i, f"{bindings[var]}.{sub}"))
    return out


def main() -> int:
    specs = parse_process_specs()
    print(f"# OC karr_*.py port-mismatch audit\n")
    print(f"# Process specs parsed from harness: {len(specs)}\n")

    process_modules = {
        "Translation": "karr_translation.py",
        "Transcription": "karr_transcription.py",
        "ReplicationInitiation": "karr_replication_initiation.py",
        "DNARepair": "karr_dna_repair.py",
        "Replication": "karr_replication.py",
        "DNASupercoiling": "karr_dna_supercoiling.py",
        "RNAProcessing": "karr_rna_processing.py",
        "RNAModification": "karr_rna_modification.py",
        "RNADecay": "karr_rna_decay.py",
        "tRNAAminoacylation": "karr_trna_aminoacylation.py",
        "ProteinModification": "karr_protein_modification.py",
        "ProteinFolding": "karr_protein_folding.py",
        "ProteinDecay": "karr_protein_decay_light.py",
        "ProteinTranslocation": "karr_protein_translocation.py",
        "MacromolecularComplexation": "karr_macromolecular_complexation.py",
        "RibosomeAssembly": "karr_ribosome_assembly.py",
        "FtsZPolymerization": "karr_ftsz_polymerization.py",
        "Cytokinesis": "karr_cytokinesis.py",
        "Metabolism": "karr_metabolism.py",
        "DNADamage": "karr_dna_damage.py",
        "ProteinProcessingI": "karr_protein_processing_i.py",
        "ProteinProcessingII": "karr_protein_processing_ii.py",
        "ChromosomeCondensation": "karr_chromosome_condensation.py",
        "ChromosomeSegregation": "karr_chromosome_segregation.py",
        "HostInteraction": "karr_host_interaction.py",
        "ProteinActivation": "karr_protein_activation.py",
        "TerminalOrganelleAssembly": "karr_terminal_organelle_assembly.py",
        "TranscriptionalRegulation": "karr_transcriptional_regulation.py",
    }

    findings: list[dict] = []
    for proc_name, fname in process_modules.items():
        path = VIVARIUM / fname
        if not path.exists():
            continue
        obs = specs.get(proc_name, set())
        nested = extract_nested_reads(path)
        unique_paths = sorted({p for _, p in nested})

        covered = covered_ports(obs)
        suspect_paths = []
        for p in unique_paths:
            base = p.split(".")[0]
            # Filter out reads of declared observables' canonical paths
            if p in covered:
                continue
            if base in covered:
                continue
            if base == "substrates_allocated":
                continue
            if base in ("requests",):
                continue
            suspect_paths.append(p)

        if suspect_paths:
            findings.append({
                "process": proc_name,
                "observables": sorted(obs),
                "suspect_nested_reads": suspect_paths,
                "all_nested_reads": unique_paths,
            })

    print("## Processes with NESTED reads to ports NOT covered by their observables")
    print("(These are candidates for the Translocation-class port-mismatch bug)\n")
    if not findings:
        print("  (none — every process reads only from ports its observables cover)")
    else:
        for f in findings:
            print(f"### {f['process']}")
            print(f"  observables : {f['observables']}")
            print(f"  suspect reads (port NOT in observables): {f['suspect_nested_reads']}")
            print(f"  all nested reads: {f['all_nested_reads']}")
            print()

    print(f"\n## Summary: {len(findings)} of {len(process_modules)} processes have potential port-mismatch bugs")
    for f in findings:
        print(f"  - {f['process']}: reads {f['suspect_nested_reads']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
