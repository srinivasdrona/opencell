"""L2 Stage-0 inventory probe: G1 (fixture) + G2 (replay test) readiness per process.

Scans a list of Karr process keys, checks:
- G1: per-process npz fixture present at data/karr_fixtures/per_process/<PascalName>.npz
- G2: replay test file present at tests/vivarium/test_karr_<snake_name>_replay.py
      OR any test under tests/ that imports the process AND references "replay"
- Structural notes: does the process module have a `next_update` and use a
  documented ports schema (heuristic).

Outputs CSV to docs/phase_e/L2_INVENTORY_PROBE_RESULTS.csv

Usage:
    py -3.12 scripts/l2_inventory_probe.py --phase 2     # 2-process canary
    py -3.12 scripts/l2_inventory_probe.py --phase 10    # 10-process scale
    py -3.12 scripts/l2_inventory_probe.py --phase 28    # full sweep
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "karr_fixtures" / "per_process"
TESTS_DIR = ROOT / "tests"
PROCESS_DIR = ROOT / "opencell" / "vivarium"

# 28 Karr-in-v6 processes (cell_cycle_coordinator excluded — SHIM, Karr-parity N/A)
PROCESS_KEYS: tuple[str, ...] = (
    "karr_metabolism",
    "karr_transcription",
    "karr_translation",
    "karr_transcriptional_regulation",
    "karr_rna_decay",
    "karr_rna_processing",
    "karr_rna_modification",
    "karr_trna_aminoacylation",
    "karr_ribosome_assembly",
    "karr_protein_processing_i",
    "karr_protein_processing_ii",
    "karr_protein_folding",
    "karr_protein_modification",
    "karr_protein_translocation",
    "karr_protein_activation",
    "karr_protein_decay_light",
    "karr_macromolecular_complexation",
    "karr_replication",
    "karr_replication_initiation",
    "karr_dna_supercoiling",
    "karr_chromosome_condensation",
    "karr_chromosome_segregation",
    "karr_dna_damage",
    "karr_dna_repair",
    "karr_ftsz_polymerization",
    "karr_cytokinesis",
    "karr_terminal_organelle_assembly",
    "karr_host_interaction",
)

# Fixture name mapping: PascalCase Karr name (matches .npz files)
FIXTURE_NAME: dict[str, str] = {
    "karr_metabolism": "Metabolism",
    "karr_transcription": "Transcription",
    "karr_translation": "Translation",
    "karr_transcriptional_regulation": "TranscriptionalRegulation",
    "karr_rna_decay": "RNADecay",
    "karr_rna_processing": "RNAProcessing",
    "karr_rna_modification": "RNAModification",
    "karr_trna_aminoacylation": "tRNAAminoacylation",
    "karr_ribosome_assembly": "RibosomeAssembly",
    "karr_protein_processing_i": "ProteinProcessingI",
    "karr_protein_processing_ii": "ProteinProcessingII",
    "karr_protein_folding": "ProteinFolding",
    "karr_protein_modification": "ProteinModification",
    "karr_protein_translocation": "ProteinTranslocation",
    "karr_protein_activation": "ProteinActivation",
    "karr_protein_decay_light": "ProteinDecay",
    "karr_macromolecular_complexation": "MacromolecularComplexation",
    "karr_replication": "Replication",
    "karr_replication_initiation": "ReplicationInitiation",
    "karr_dna_supercoiling": "DNASupercoiling",
    "karr_chromosome_condensation": "ChromosomeCondensation",
    "karr_chromosome_segregation": "ChromosomeSegregation",
    "karr_dna_damage": "DNADamage",
    "karr_dna_repair": "DNARepair",
    "karr_ftsz_polymerization": "FtsZPolymerization",
    "karr_cytokinesis": "Cytokinesis",
    "karr_terminal_organelle_assembly": "TerminalOrganelleAssembly",
    "karr_host_interaction": "HostInteraction",
}


def check_g1_fixture(process_key: str) -> tuple[bool, str, int]:
    """Return (present, path_or_reason, size_bytes)."""
    pascal = FIXTURE_NAME.get(process_key, "")
    if not pascal:
        return False, "no PascalCase mapping", 0
    npz = FIXTURE_DIR / f"{pascal}.npz"
    if npz.exists():
        return True, str(npz.relative_to(ROOT)), npz.stat().st_size
    return False, f"missing: {npz.relative_to(ROOT)}", 0


def _has_replay_import(text: str) -> bool:
    """Strict G2 sentinel: file must actually wire to a replay/fixture helper.

    Accepts both the L2.0-era (``opencell.validation.replay`` /
    ``replay_one_tick`` / ``load_per_process_fixture``) and the L2.1-era
    (``l2_replay_common``) helpers. A pure name-match scaffold with no
    replay infrastructure import never counts.
    """
    patterns = (
        r"\breplay_one_tick\b",
        r"\bload_per_process_fixture\b",
        r"from\s+opencell\.validation\.replay\b",
        r"from\s+opencell\.validation\.fixtures\b",
        r"\bl2_replay_common\b",
    )
    return any(re.search(p, text) for p in patterns)


def check_g2_replay_test(process_key: str) -> tuple[bool, str, str]:
    """Return (present, primary_path, notes).

    Tightened 2026-05-30: a candidate test only counts as G2=PASS if it
    actually imports ``replay_one_tick`` or ``load_per_process_fixture``
    (or the equivalent module). Pure name-match files (strict-zero
    scaffolds, smoke shells) no longer pass.
    """
    snake = process_key.replace("karr_", "")
    candidates = [
        TESTS_DIR / "vivarium" / f"test_karr_{snake}_replay.py",
        TESTS_DIR / "vivarium" / f"test_karr_{snake}_l2_replay.py",
        TESTS_DIR / "vivarium" / f"test_{snake}_replay.py",
        TESTS_DIR / "unit" / f"test_karr_{snake}_replay.py",
        TESTS_DIR / "integration" / f"test_karr_{snake}_replay.py",
    ]
    for c in candidates:
        if not c.exists():
            continue
        try:
            text = c.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _has_replay_import(text):
            return True, str(c.relative_to(ROOT)), "exact-name match + replay import"
        return False, str(c.relative_to(ROOT)), "exact-name match but NO replay_one_tick/fixture import (strict-zero scaffold)"
    # Heuristic: grep for "replay" referencing this process key AND a real replay import
    hits: list[str] = []
    near_hits: list[str] = []
    for test in TESTS_DIR.rglob("test_*.py"):
        try:
            text = test.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if process_key in text and "replay" in text.lower():
            if _has_replay_import(text):
                hits.append(str(test.relative_to(ROOT)))
            else:
                near_hits.append(str(test.relative_to(ROOT)))
    if hits:
        return True, hits[0], f"heuristic: {len(hits)} file(s) reference process+replay+import"
    if near_hits:
        return False, near_hits[0], f"near-hit: {len(near_hits)} file(s) name-match but no replay import"
    return False, "", "no replay test found"


def check_structural(process_key: str) -> tuple[bool, str]:
    """Heuristic: process module exists, has next_update, declares ports_schema."""
    module = PROCESS_DIR / f"{process_key}.py"
    if not module.exists():
        return False, f"missing module: {module.relative_to(ROOT)}"
    text = module.read_text(encoding="utf-8", errors="ignore")
    has_next = "def next_update" in text
    has_ports = "def ports_schema" in text or "ports_schema =" in text
    if has_next and has_ports:
        return True, "next_update + ports_schema declared"
    issues = []
    if not has_next:
        issues.append("no next_update")
    if not has_ports:
        issues.append("no ports_schema")
    return False, "; ".join(issues)


def probe(process_keys: tuple[str, ...]) -> list[dict]:
    rows = []
    for key in process_keys:
        g1_ok, g1_path, g1_size = check_g1_fixture(key)
        g2_ok, g2_path, g2_notes = check_g2_replay_test(key)
        s_ok, s_notes = check_structural(key)
        ready = g1_ok and g2_ok and s_ok
        rows.append({
            "process": key,
            "ready_for_L2": "YES" if ready else "NO",
            "G1_fixture": "PASS" if g1_ok else "FAIL",
            "G1_path": g1_path,
            "G1_size_bytes": g1_size,
            "G2_replay_test": "PASS" if g2_ok else "FAIL",
            "G2_path": g2_path,
            "G2_notes": g2_notes,
            "structural": "PASS" if s_ok else "FAIL",
            "structural_notes": s_notes,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, choices=[2, 10, 28], default=2,
                        help="Number of processes to probe (2=canary, 10=scale, 28=full)")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "phase_e" / "L2_INVENTORY_PROBE_RESULTS.csv")
    args = parser.parse_args()

    keys = PROCESS_KEYS[: args.phase]
    print(f"L2 inventory probe: phase={args.phase}, {len(keys)} processes")
    print(f"  fixture dir: {FIXTURE_DIR.relative_to(ROOT)}")
    print(f"  tests dir:   {TESTS_DIR.relative_to(ROOT)}")
    rows = probe(keys)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    ready_n = sum(1 for r in rows if r["ready_for_L2"] == "YES")
    print(f"\nResults written: {args.out.relative_to(ROOT)}")
    print(f"L2-ready: {ready_n}/{len(rows)}")
    g1_n = sum(1 for r in rows if r["G1_fixture"] == "PASS")
    g2_n = sum(1 for r in rows if r["G2_replay_test"] == "PASS")
    s_n = sum(1 for r in rows if r["structural"] == "PASS")
    print(f"  G1 fixture present:  {g1_n}/{len(rows)}")
    print(f"  G2 replay test:      {g2_n}/{len(rows)}")
    print(f"  Structural sanity:   {s_n}/{len(rows)}")

    # Print per-process summary
    print("\nPer-process:")
    for r in rows:
        flag = "OK" if r["ready_for_L2"] == "YES" else "--"
        print(f"  {flag} {r['process']:42s} G1={r['G1_fixture']} G2={r['G2_replay_test']} S={r['structural']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
