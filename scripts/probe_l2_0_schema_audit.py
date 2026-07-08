"""L2.0 observable-schema audit.

For each of the 28 Karr processes, compares:
  karr_obs = top-level keys under `states_before/` in the per-process .mat oracle
  oc_obs   = top-level keys returned by the OC process's `ports_schema()`

Emits three sets per process (overlap, karr_only, oc_only) and a verdict:
  GREEN  : karr_obs ⊆ oc_obs  (overlap == karr_obs)
  AMBER  : overlap ⊂ karr_obs and overlap ≠ ∅  (partial port — model debt)
  RED    : overlap == ∅  (no shared channels — vacuous gate, blocks L2.1)
  ERROR  : process could not be instantiated; reason recorded

Writes:
  docs/phase_e/L2_0_SCHEMA_AUDIT.md
  docs/phase_e/L2_0_SCHEMA_AUDIT.json
"""
from __future__ import annotations

import importlib
import json
import traceback
from pathlib import Path
from typing import Any

import h5py

REPO = Path(__file__).resolve().parents[1]
MATS_DIR = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces"
OUT_MD = REPO / "docs" / "phase_e" / "L2_0_SCHEMA_AUDIT.md"
OUT_JSON = REPO / "docs" / "phase_e" / "L2_0_SCHEMA_AUDIT.json"

# .mat stem (without _100ticks) -> (module_name, class_name)
PROCESS_MAP: dict[str, tuple[str, str]] = {
    "ChromosomeCondensation": ("karr_chromosome_condensation", "KarrChromosomeCondensationProcess"),
    "ChromosomeSegregation": ("karr_chromosome_segregation", "KarrChromosomeSegregationProcess"),
    "Cytokinesis": ("karr_cytokinesis", "KarrCytokinesisProcess"),
    "DNADamage": ("karr_dna_damage", "KarrDNADamageProcess"),
    "DNARepair": ("karr_dna_repair", "KarrDNARepairProcess"),
    "DNASupercoiling": ("karr_dna_supercoiling", "KarrDNASupercoilingProcess"),
    "FtsZPolymerization": ("karr_ftsz_polymerization", "KarrFtsZPolymerizationProcess"),
    "HostInteraction": ("karr_host_interaction", "KarrHostInteractionProcess"),
    "MacromolecularComplexation": ("karr_macromolecular_complexation", "MacromolecularComplexationProcess"),
    "Metabolism": ("karr_metabolism", "KarrMetabolismProcess"),
    "ProteinActivation": ("karr_protein_activation", "KarrProteinActivationProcess"),
    "ProteinDecay": ("karr_protein_decay_light", "ProteinDecayLightProcess"),
    "ProteinFolding": ("karr_protein_folding", "KarrProteinFoldingProcess"),
    "ProteinModification": ("karr_protein_modification", "KarrProteinModificationProcess"),
    "ProteinProcessingI": ("karr_protein_processing_i", "KarrProteinProcessingIProcess"),
    "ProteinProcessingII": ("karr_protein_processing_ii", "KarrProteinProcessingIIProcess"),
    "ProteinTranslocation": ("karr_protein_translocation", "KarrProteinTranslocationProcess"),
    "Replication": ("karr_replication", "KarrReplicationProcess"),
    "ReplicationInitiation": ("karr_replication_initiation", "KarrReplicationInitiationProcess"),
    "RibosomeAssembly": ("karr_ribosome_assembly", "KarrRibosomeAssemblyProcess"),
    "RNADecay": ("karr_rna_decay", "RnaDecayLightProcess"),
    "RNAModification": ("karr_rna_modification", "KarrRNAModificationProcess"),
    "RNAProcessing": ("karr_rna_processing", "KarrRNAProcessingProcess"),
    "TerminalOrganelleAssembly": ("karr_terminal_organelle_assembly", "KarrTerminalOrganelleAssemblyProcess"),
    "Transcription": ("karr_transcription", "KarrTranscriptionProcess"),
    "TranscriptionalRegulation": ("karr_transcriptional_regulation", "KarrTranscriptionalRegulationProcess"),
    "Translation": ("karr_translation", "KarrTranslationProcess"),
    "tRNAAminoacylation": ("karr_trna_aminoacylation", "KarrTRNAAminoacylationProcess"),
}


def karr_observables(mat_path: Path) -> set[str]:
    with h5py.File(mat_path, "r") as f:
        if "states_before" not in f:
            raise KeyError(f"states_before missing in {mat_path}")
        return {str(k) for k in f["states_before"].keys()}


def oc_schema_keys(module_name: str, class_name: str) -> tuple[set[str], str | None]:
    """Instantiate process with empty config and return ports_schema() top-level keys.

    Returns (keys, error_message). error_message is None on success.
    """
    try:
        mod = importlib.import_module(f"opencell.vivarium.{module_name}")
        cls = getattr(mod, class_name)
        inst = cls({})  # try empty config first
        schema = inst.ports_schema()
        return {str(k) for k in schema.keys()}, None
    except Exception as e:
        return set(), f"{type(e).__name__}: {e}"


def verdict(karr: set[str], oc: set[str], err: str | None) -> str:
    if err is not None:
        return "ERROR"
    overlap = karr & oc
    if not overlap:
        return "RED"
    if overlap == karr:
        return "GREEN"
    return "AMBER"


def _gate_result(
    rows: list[dict[str, Any]], counts: dict[str, int], expected_n: int
) -> tuple[int, str]:
    """Pure gate decision — no I/O, unit-testable without oracle .mat inputs.

    Returns ``(returncode, message)``:
      (1, ...) incomplete oracle set (fewer than ``expected_n`` processes)
      (1, ...) one or more processes not GREEN
      (0, ...) all GREEN
    """
    total = sum(counts.values())
    if total < expected_n:
        missing = expected_n - total
        return 1, (
            f"L2.0 SCHEMA GATE: FAIL — incomplete oracle set "
            f"({total}/{expected_n} mapped processes present, {missing} missing)."
        )
    non_green = counts["AMBER"] + counts["RED"] + counts["ERROR"]
    if non_green:
        offenders = [
            f"{r['process']}={r['verdict']}" for r in rows if r["verdict"] != "GREEN"
        ]
        return 1, (
            f"L2.0 SCHEMA GATE: FAIL — {non_green} process(es) not GREEN: "
            + ", ".join(offenders)
        )
    return 0, (
        f"L2.0 SCHEMA GATE: PASS ({counts['GREEN']}/{expected_n} processes GREEN, "
        "karr_obs ⊆ oc_obs)"
    )


def main() -> int:
    """Run the L2.0 schema audit as a gate.

    Exit semantics (so CI can enforce it):
      0  PASS  — all 28 processes GREEN (karr_obs ⊆ oc_obs)
      0  SKIP  — oracle .mat inputs absent (gitignored external artifacts;
                 enforced locally / in the nightly full-source run, mirroring the
                 L1b wiring gate's MATLAB-anchor skip)
      1  FAIL  — any AMBER/RED/ERROR verdict, or an incomplete oracle set
                 (fewer than the 28 mapped processes present)
    """
    expected_n = len(PROCESS_MAP)
    mats = sorted(MATS_DIR.glob("*_100ticks.mat")) if MATS_DIR.exists() else []
    if not mats:
        try:
            shown = MATS_DIR.relative_to(REPO)
        except ValueError:
            shown = MATS_DIR
        print(
            f"L2.0 SCHEMA GATE: SKIPPED — oracle inputs absent at {shown} "
            "(gitignored external artifacts). "
            "Run locally or in the nightly full-source job to enforce."
        )
        return 0

    rows: list[dict[str, Any]] = []
    for mat in mats:
        stem = mat.stem.replace("_100ticks", "")
        if stem not in PROCESS_MAP:
            print(f"SKIP unmapped: {stem}")
            continue
        mod_name, cls_name = PROCESS_MAP[stem]
        try:
            karr = karr_observables(mat)
        except Exception as e:
            karr = set()
            karr_err = f"{type(e).__name__}: {e}"
        else:
            karr_err = None
        oc, oc_err = oc_schema_keys(mod_name, cls_name)
        err = karr_err or oc_err
        v = verdict(karr, oc, err)
        overlap = karr & oc
        rows.append({
            "process": stem,
            "module": mod_name,
            "class": cls_name,
            "karr_obs": sorted(karr),
            "oc_obs": sorted(oc),
            "overlap": sorted(overlap),
            "karr_only": sorted(karr - oc),
            "oc_only": sorted(oc - karr),
            "verdict": v,
            "error": err,
        })
        marker = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴", "ERROR": "⚪"}[v]
        print(f"{marker} {stem:30s} karr={len(karr):2d} oc={len(oc):2d} overlap={len(overlap):2d} verdict={v}"
              + (f"  ERR: {err[:80]}" if err else ""))

    # Summary counts
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0, "ERROR": 0}
    for r in rows:
        counts[r["verdict"]] += 1

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"counts": counts, "rows": rows}, indent=2))

    md = [
        "# L2.0 Observable-Schema Audit",
        "",
        "Static comparison of `karr_obs` (top-level keys under `states_before/` in each",
        "per-process .mat oracle) vs `oc_obs` (top-level keys returned by the OC process's",
        "`ports_schema()`).",
        "",
        "**Verdict rules:**",
        "- 🟢 GREEN: `karr_obs ⊆ oc_obs` (OC emits every channel Karr's oracle records; `oc_only` is informational)",
        "- 🟡 AMBER: `overlap ⊂ karr_obs` and `overlap ≠ ∅` (partial port — channels in `karr_only` are model debt)",
        "- 🔴 RED: `overlap = ∅` (no shared channels — vacuous gate, blocks L2.1 for this process)",
        "- ⚪ ERROR: process could not be instantiated for schema introspection (see error column)",
        "",
        "## Summary",
        "",
        f"- 🟢 GREEN: {counts['GREEN']}",
        f"- 🟡 AMBER: {counts['AMBER']}",
        f"- 🔴 RED: {counts['RED']}",
        f"- ⚪ ERROR: {counts['ERROR']}",
        f"- **Total**: {sum(counts.values())}",
        "",
        "## Per-process verdicts",
        "",
        "| Process | Verdict | karr_obs | oc_obs | overlap | karr_only | oc_only |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for r in rows:
        marker = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴", "ERROR": "⚪"}[r["verdict"]]
        karr_only_str = ", ".join(r["karr_only"]) if r["karr_only"] else "—"
        oc_only_str = ", ".join(r["oc_only"][:4]) + (f" (+{len(r['oc_only'])-4} more)" if len(r["oc_only"]) > 4 else "") if r["oc_only"] else "—"
        md.append(
            f"| {r['process']} | {marker} {r['verdict']} | {len(r['karr_obs'])} | "
            f"{len(r['oc_obs'])} | {len(r['overlap'])} | {karr_only_str} | {oc_only_str} |"
        )

    md.extend(["", "## Errors (if any)", ""])
    errs = [r for r in rows if r["error"]]
    if errs:
        for r in errs:
            md.append(f"- **{r['process']}** ({r['class']}): {r['error']}")
    else:
        md.append("(none)")

    md.extend([
        "",
        "## Methodology notes",
        "",
        "- This is a **static** schema audit. Each process is instantiated with an empty config (`cls({})`)",
        "  and its `ports_schema()` is introspected for top-level port keys. Processes that require a non-empty",
        "  config (e.g., fixture paths) will appear as ERROR and need a per-process probe config.",
        "- A GREEN verdict here does **not** imply L2.1 (bit-identity) passes — it only confirms the schema",
        "  surfaces match. L2.1 is a behavioural check on overlap channels.",
        "- A RED verdict blocks L2.1 entirely: there is nothing to compare bit-for-bit. The process either",
        "  needs port-completeness work (start emitting the karr-recorded channels) or the .mat oracle needs",
        "  re-extraction at a layer that does emit shared channels.",
        "",
    ])

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    print(f"Counts: {counts}")

    # ── Gate verdict ──────────────────────────────────────────────────────
    code, message = _gate_result(rows, counts, expected_n)
    print(f"\n{message}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
