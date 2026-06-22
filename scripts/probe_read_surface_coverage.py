"""Compute read-surface coverage for each of 28 L2.1/L2.2 processes.

For each process:
  - Read ports = set of (port_path) extracted from next_update body
    (e.g. {'substrates_allocated', 'enzymes', 'protein.counts',
           'protein.unprocessed_counts', 'protein.enzyme_counts',
           'protein.location', 'complex.counts'} for Translocation)
  - Mapped ports = set of state-port paths the harness's observables overlay
    can populate (e.g. observables=[substrates, enzymes, boundEnzymes, monomers]
    -> ['substrates', 'enzymes', 'boundEnzymes', 'protein.unprocessed_counts',
        'protein.counts', 'substrates_allocated'])
  - Coverage = |Read ∩ Mapped| / |Read|

Coverage < 100% means the L2.1/L2.2 harness ran the biology with some reads
returning template-default values (typically zero), and any PASS at affected
ticks is coincidental rather than biological.

This script computes the per-process coverage and prints a brutal summary.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VIVARIUM = REPO / "opencell" / "vivarium"
HARNESS = REPO / "tests" / "vivarium" / "l2_2_replay_common_v2.py"


OBSERVABLE_TO_PORTS = {
    "substrates": {"substrates", "substrates_allocated"},
    "enzymes": {"enzymes"},
    "boundEnzymes": {"boundEnzymes"},
    "complexs": {"complex.counts"},
    "RNAs": {"rna.counts"},
    "monomers": {"protein.counts", "protein.unprocessed_counts"},
    "foldedMonomers": {"protein.counts"},
    "unfoldedMonomers": {"protein.unfolded_counts"},
    "modifiedMonomers": {"protein.counts"},
    "unmodifiedMonomers": {"protein.counts"},
    "processedMonomers": {"protein.counts", "protein.processed_counts"},
    "unprocessedMonomers": {"protein.counts", "protein.unprocessed_counts"},
    "freeRNAs": {"rna.counts"},
    "aminoacylatedRNAs": {"rna.aminoacylated_counts"},
    "modifiedRNAs": {"rna.modified_counts", "rna.counts"},
    "unmodifiedRNAs": {"rna.counts"},
    "processedRNAs": {"rna.counts"},
    "unprocessedRNAs": {"rna.counts"},
}

HIDDEN_PORT_MAP = {
    "chromosome": {"chromosome"},
    "stimulus.values": {"stimulus"},
    "rnaPolymerase.supercoilingBindingProbFoldChange": {"rnaPolymerase"},
}


def parse_specs() -> dict[str, dict]:
    """Parse _PROCESS_SPECS from harness — return {name: {observables, hidden_read_surface}}."""
    text = HARNESS.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    # Match each _ProcessSpec block per process
    pat = re.compile(
        r'"(?P<name>[A-Za-z]+)":\s*_ProcessSpec\((?P<body>(?:[^()]|\([^()]*\))*?)\)\s*,',
        re.S,
    )
    for m in pat.finditer(text):
        name = m.group("name")
        body = m.group("body")
        obs_m = re.search(r"observables=\(([^)]+)\)", body)
        obs = set()
        if obs_m:
            for o in obs_m.group(1).split(","):
                o = o.strip().strip("\"'")
                if o:
                    obs.add(o)
        hrs_m = re.search(r"hidden_read_surface=\(([^)]*)\)", body)
        hrs = set()
        if hrs_m:
            for h in hrs_m.group(1).split(","):
                h = h.strip().strip("\"'")
                if h:
                    hrs.add(h)
        out[name] = {"observables": obs, "hidden_read_surface": hrs}
    return out


def extract_all_reads(module_path: Path) -> set[str]:
    """All state-port reads in next_update."""
    if not module_path.exists():
        return set()
    text = module_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    in_next_update = False
    indent = None
    reads: set[str] = set()
    bindings: dict[str, str] = {}

    pat_chain = re.compile(
        r'(?:states?|state)\s*\.\s*get\s*\(\s*["\'](\w+)["\'][^)]*\)\s*\.\s*get\s*\(\s*["\'](\w+)["\']'
    )
    pat_bind = re.compile(
        r'^\s*(\w+)\s*=\s*(?:states?|state)\s*\.\s*get\s*\(\s*["\'](\w+)["\']'
    )
    pat_state_get = re.compile(
        r'(?:states?|state)\s*\.\s*get\s*\(\s*["\'](\w+)["\']'
    )
    pat_state_idx = re.compile(
        r'(?:states?|state)\s*\[\s*["\'](\w+)["\']'
    )
    pat_var_get = re.compile(r'(\w+)\s*\.\s*get\s*\(\s*["\'](\w+)["\']')

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
                reads.add(f"{m.group(1)}.{m.group(2)}")

            bm = pat_bind.search(line)
            if bm:
                bindings[bm.group(1)] = bm.group(2)

            for m in pat_state_get.finditer(line):
                reads.add(m.group(1))
            for m in pat_state_idx.finditer(line):
                reads.add(m.group(1))

            for m in pat_var_get.finditer(line):
                var, sub = m.group(1), m.group(2)
                if var in bindings:
                    reads.add(f"{bindings[var]}.{sub}")
    return reads


def mapped_ports(observables: set[str], hidden_read_surface: set[str]) -> set[str]:
    out: set[str] = {"substrates_allocated", "requests"}  # always wired by harness
    for o in observables:
        out |= OBSERVABLE_TO_PORTS.get(o, set())
    for h in hidden_read_surface:
        out |= HIDDEN_PORT_MAP.get(h, set())
        # base name match as well — process may read at any nested level
        if h in HIDDEN_PORT_MAP:
            out.add(next(iter(HIDDEN_PORT_MAP[h])))
    # Also include top-level forms for substrates / enzymes / etc.
    return out


def is_covered(read: str, mapped: set[str]) -> bool:
    if read in mapped:
        return True
    base = read.split(".")[0]
    return base in mapped


PROCESS_MODULES = {
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


def main() -> int:
    specs = parse_specs()
    print("# L2.1/L2.2 read-surface coverage audit\n")
    print(f"{'Process':<28} {'Reads':>6} {'Mapped':>7} {'Uncov':>6} {'Cov%':>6}  Uncovered reads")
    print("-" * 130)

    rows = []
    for proc, fname in PROCESS_MODULES.items():
        path = VIVARIUM / fname
        spec = specs.get(proc, {})
        obs = spec.get("observables", set())
        hrs = spec.get("hidden_read_surface", set())
        reads = extract_all_reads(path)
        # Drop noise: 'trace_hint' is well-known short-circuit (already audited)
        reads_for_coverage = {r for r in reads if not r.startswith("trace_hint")}
        mapped = mapped_ports(obs, hrs)
        uncovered = {r for r in reads_for_coverage if not is_covered(r, mapped)}
        covered = reads_for_coverage - uncovered
        n_read = len(reads_for_coverage)
        n_cov = len(covered)
        cov_pct = (100.0 * n_cov / n_read) if n_read else 100.0
        rows.append((proc, n_read, n_cov, len(uncovered), cov_pct, sorted(uncovered)))
        unc_str = ", ".join(sorted(uncovered)) if uncovered else "-"
        print(f"{proc:<28} {n_read:>6} {n_cov:>7} {len(uncovered):>6} {cov_pct:>5.0f}%  {unc_str}")

    print("\n## Summary buckets")
    full_cov = [r for r in rows if r[4] >= 99.0]
    partial = [r for r in rows if 50 <= r[4] < 99]
    poor = [r for r in rows if r[4] < 50]
    print(f"  Full coverage (>=99%): {len(full_cov)} processes")
    for r in full_cov:
        print(f"    {r[0]}")
    print(f"\n  Partial coverage (50-98%): {len(partial)} processes")
    for r in partial:
        print(f"    {r[0]}  ({r[4]:.0f}% — uncovered: {r[5]})")
    print(f"\n  Poor coverage (<50%): {len(poor)} processes")
    for r in poor:
        print(f"    {r[0]}  ({r[4]:.0f}% — uncovered: {r[5]})")

    print(f"\nTotal processes: {len(rows)}")
    print(f"Mean coverage: {sum(r[4] for r in rows) / len(rows):.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
