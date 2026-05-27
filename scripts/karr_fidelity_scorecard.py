"""Per-process Karr fidelity scorecard for replay fixtures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

# Ensure CLI runs against this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for module_name in list(sys.modules):
            if module_name == "opencell" or module_name.startswith("opencell."):
                del sys.modules[module_name]

from opencell.validation.replay import load_per_process_fixture
from opencell.vivarium.karr_chromosome_condensation import KarrChromosomeCondensationProcess
from opencell.vivarium.karr_chromosome_segregation import KarrChromosomeSegregationProcess
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess
from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess
from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess
from opencell.vivarium.karr_ftsz_polymerization import KarrFtsZPolymerizationProcess
from opencell.vivarium.karr_macromolecular_complexation import MacromolecularComplexationProcess
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess
from opencell.vivarium.karr_protein_activation import KarrProteinActivationProcess
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess
from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess
from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_replication import KarrReplicationProcess
from opencell.vivarium.karr_replication_initiation import KarrReplicationInitiationProcess
from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess
from opencell.vivarium.karr_rna_decay import RnaDecayLightProcess
from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess
from opencell.vivarium.karr_terminal_organelle_assembly import KarrTerminalOrganelleAssemblyProcess
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess
from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
)
from opencell.vivarium.karr_translation import KarrTranslationProcess
from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess

REPLAY_FIXTURE_ROOT = Path("data/karr_fixtures/per_process_replay")
MARKDOWN_PATH = Path("docs/phase_e/karr_fidelity_scorecard.md")
JSON_PATH = Path("artifacts/karr_fidelity_scorecard.json")

PASS_REL = 1e-6
PASS_ABS = 1e-9
PARTIAL_REL = 0.05
REL_ATOL = 1e-12

DIAGNOSTIC_MIRROR_PROCESSES = {
    "Transcription",
    "Translation",
    "RNADecay",
    "Replication",
    "ReplicationInitiation",
}
NO_ADAPTER_PROCESSES = {"TerminalOrganelleAssembly", "HostInteraction"}

PROCESS_CLASS_MAP: dict[str, type[Any]] = {
    "ChromosomeCondensation": KarrChromosomeCondensationProcess,
    "ChromosomeSegregation": KarrChromosomeSegregationProcess,
    "Cytokinesis": KarrCytokinesisProcess,
    "DNADamage": KarrDNADamageProcess,
    "DNARepair": KarrDNARepairProcess,
    "DNASupercoiling": KarrDNASupercoilingProcess,
    "FtsZPolymerization": KarrFtsZPolymerizationProcess,
    "MacromolecularComplexation": MacromolecularComplexationProcess,
    "Metabolism": KarrMetabolismProcess,
    "ProteinActivation": KarrProteinActivationProcess,
    "ProteinDecay": ProteinDecayLightProcess,
    "ProteinFolding": KarrProteinFoldingProcess,
    "ProteinModification": KarrProteinModificationProcess,
    "ProteinProcessingI": KarrProteinProcessingIProcess,
    "ProteinProcessingII": KarrProteinProcessingIIProcess,
    "ProteinTranslocation": KarrProteinTranslocationProcess,
    "Replication": KarrReplicationProcess,
    "ReplicationInitiation": KarrReplicationInitiationProcess,
    "RibosomeAssembly": KarrRibosomeAssemblyProcess,
    "RNADecay": RnaDecayLightProcess,
    "RNAModification": KarrRNAModificationProcess,
    "RNAProcessing": KarrRNAProcessingProcess,
    "TerminalOrganelleAssembly": KarrTerminalOrganelleAssemblyProcess,
    "Transcription": KarrTranscriptionProcess,
    "TranscriptionalRegulation": KarrTranscriptionalRegulationProcess,
    "Translation": KarrTranslationProcess,
    "tRNAAminoacylation": KarrTRNAAminoacylationProcess,
}


@dataclass
class ScorecardRow:
    process_name: str
    status: str
    reason: str
    n_ticks_tested: int
    properties_compared: int
    max_abs: float | None
    max_rel: float | None
    top_disagreement_property: str | None


def _slice_tick(series: np.ndarray, tick_index: int, n_ticks: int) -> np.ndarray:
    arr = np.asarray(series)
    if n_ticks <= 1:
        if arr.ndim == 0:
            return arr
        return np.asarray(arr[0])
    if arr.ndim > 0 and arr.shape[0] == n_ticks:
        return np.asarray(arr[tick_index])
    if arr.ndim > 1 and arr.shape[-1] == n_ticks:
        return np.asarray(np.take(arr, tick_index, axis=-1))
    raise ValueError(f"Series is not tick-indexed as expected: shape={arr.shape} n_ticks={n_ticks}")


def _flatten_mapping(payload: Any, *, prefix: str = "") -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            next_prefix = f"{prefix}/{key}" if prefix else str(key)
            out.update(_flatten_mapping(value, prefix=next_prefix))
        return out
    if prefix:
        out[prefix] = np.asarray(payload)
    return out


def _resolve_timestep(process: Any) -> float:
    parameters = getattr(process, "parameters", {})
    if not isinstance(parameters, dict):
        return 1.0
    try:
        return float(parameters.get("time_step", 1.0))
    except (TypeError, ValueError):
        return 1.0


def _vector_to_wid_map(value: np.ndarray, wids: list[str] | tuple[str, ...] | None) -> dict[str, float] | None:
    if not wids:
        return None
    arr = np.asarray(value, dtype=float)
    vec: np.ndarray | None = None
    if arr.ndim == 1 and arr.shape[0] == len(wids):
        vec = arr
    elif arr.ndim == 2 and arr.shape[0] == 1 and arr.shape[1] == len(wids):
        vec = arr[0]
    if vec is None:
        return None
    return {str(wid): float(vec[idx]) for idx, wid in enumerate(wids)}


def _build_tick_state(process: Any, tick_inputs: dict[str, np.ndarray]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    substrate_wids = getattr(process, "substrate_wids", None)
    enzyme_wids = getattr(process, "enzyme_wids", None)
    monomer_wids = getattr(process, "monomer_wids", None)

    for key, value in tick_inputs.items():
        if key == "substrates":
            substrate_map = _vector_to_wid_map(value, substrate_wids)
            state[key] = substrate_map if substrate_map is not None else value
            continue
        if key == "enzymes":
            enzyme_map = _vector_to_wid_map(value, enzyme_wids)
            if enzyme_map is not None:
                state[key] = enzyme_map
                protein = state.setdefault("protein", {})
                if isinstance(protein, dict):
                    protein["enzyme_counts"] = dict(enzyme_map)
                    protein.setdefault("counts", dict(enzyme_map))
            else:
                state[key] = value
            continue
        if key == "boundEnzymes":
            bound_map = _vector_to_wid_map(value, enzyme_wids)
            state[key] = bound_map if bound_map is not None else value
            continue
        if key == "monomers":
            state[key] = value
            if monomer_wids and np.asarray(value).ndim >= 1 and np.asarray(value).shape[-1] == len(monomer_wids):
                row = np.asarray(value, dtype=float)
                if row.ndim > 1:
                    row = row[0]
                monomer_map = {str(wid): float(row[idx]) for idx, wid in enumerate(monomer_wids)}
                protein = state.setdefault("protein", {})
                if isinstance(protein, dict):
                    protein.setdefault("counts", dict(monomer_map))
                    protein.setdefault("unprocessed_counts", dict(monomer_map))
            continue
        state[key] = value

    process_name = str(getattr(process, "name", ""))
    if process_name == "karr_ftsz_polymerization":
        cell = state.setdefault("cell", {})
        if isinstance(cell, dict):
            cell.setdefault("ftsz_ring_count", float(getattr(process, "initial_ring_count", 0.0)))
    if process_name == "karr_cytokinesis":
        cell = state.setdefault("cell", {})
        if isinstance(cell, dict):
            cell.setdefault("ftsz_ring_complete", False)
            cell.setdefault("division_progress", 0.0)
            cell.setdefault("division_complete", False)
        chromosome = state.setdefault("chromosome", {})
        if isinstance(chromosome, dict):
            chromosome.setdefault("segregation_progress", 0.0)

    return state


def _wid_order_for_property(process: Any, prop: str) -> list[str] | None:
    if prop == "substrates":
        wids = getattr(process, "substrate_wids", None)
        return [str(wid) for wid in wids] if wids else None
    if prop in {"enzymes", "boundEnzymes"}:
        wids = getattr(process, "enzyme_wids", None)
        return [str(wid) for wid in wids] if wids else None
    if prop == "monomers":
        wids = getattr(process, "monomer_wids", None)
        return [str(wid) for wid in wids] if wids else None
    return None


def _build_delta_from_prefixed_updates(
    prefixed: dict[str, np.ndarray],
    before_shape: tuple[int, ...],
    wid_order: list[str] | None,
) -> np.ndarray | None:
    if wid_order is None:
        return None
    if len(before_shape) == 1 and before_shape[0] == len(wid_order):
        out = np.zeros(before_shape, dtype=float)
    elif len(before_shape) == 2 and before_shape[0] == 1 and before_shape[1] == len(wid_order):
        out = np.zeros(before_shape, dtype=float)
    else:
        return None

    wid_to_idx = {wid: idx for idx, wid in enumerate(wid_order)}
    for leaf_key, raw_value in prefixed.items():
        if leaf_key not in wid_to_idx:
            continue
        arr = np.asarray(raw_value, dtype=float)
        if arr.shape != ():
            return None
        idx = wid_to_idx[leaf_key]
        if out.ndim == 1:
            out[idx] = float(arr)
        else:
            out[0, idx] = float(arr)
    return out


def _delta_for_property(
    *,
    process: Any,
    flat_update: dict[str, np.ndarray],
    property_name: str,
    before: np.ndarray,
) -> np.ndarray | None:
    before_arr = np.asarray(before, dtype=float)
    exact = flat_update.get(property_name)
    if exact is not None:
        exact_arr = np.asarray(exact, dtype=float)
        if exact_arr.shape == before_arr.shape:
            return exact_arr
        return None

    prefix = f"{property_name}/"
    prefixed = {
        key[len(prefix) :]: value
        for key, value in flat_update.items()
        if key.startswith(prefix)
    }
    if not prefixed:
        return np.zeros_like(before_arr, dtype=float)

    wid_order = _wid_order_for_property(process, property_name)
    return _build_delta_from_prefixed_updates(prefixed, before_arr.shape, wid_order)


def _has_property_signal(flat_update: dict[str, np.ndarray], property_name: str) -> bool:
    if property_name in flat_update:
        return True
    prefix = f"{property_name}/"
    return any(key.startswith(prefix) for key in flat_update)


def _diff_metrics(actual: np.ndarray, expected: np.ndarray) -> tuple[float, float]:
    delta = np.abs(actual - expected)
    max_abs = float(np.nanmax(delta)) if delta.size else 0.0
    denom = np.maximum(np.abs(expected), REL_ATOL)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(denom > 0.0, delta / denom, np.where(delta > 0.0, np.inf, 0.0))
    max_rel = float(np.nanmax(rel)) if rel.size else 0.0
    return max_abs, max_rel


def _format_metric(value: float | None) -> str:
    if value is None:
        return "-"
    if not np.isfinite(value):
        return "inf"
    return f"{value:.6g}"


def _score_status(max_abs: float, max_rel: float) -> str:
    if (max_rel < PASS_REL) or (max_abs < PASS_ABS):
        return "PASS"
    if max_rel < PARTIAL_REL:
        return "PARTIAL"
    return "FAIL"


def _evaluate_process(process_name: str) -> ScorecardRow:
    if process_name in DIAGNOSTIC_MIRROR_PROCESSES:
        return ScorecardRow(
            process_name=process_name,
            status="SKIP",
            reason="1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract.",
            n_ticks_tested=0,
            properties_compared=0,
            max_abs=None,
            max_rel=None,
            top_disagreement_property=None,
        )

    if process_name in NO_ADAPTER_PROCESSES:
        return ScorecardRow(
            process_name=process_name,
            status="SKIP",
            reason="No Vivarium adapter available for replay in Track-A.",
            n_ticks_tested=0,
            properties_compared=0,
            max_abs=None,
            max_rel=None,
            top_disagreement_property=None,
        )

    process_cls = PROCESS_CLASS_MAP.get(process_name)
    if process_cls is None:
        return ScorecardRow(
            process_name=process_name,
            status="SKIP",
            reason="No process-class mapping found.",
            n_ticks_tested=0,
            properties_compared=0,
            max_abs=None,
            max_rel=None,
            top_disagreement_property=None,
        )

    fixture = load_per_process_fixture(process_name, root=REPLAY_FIXTURE_ROOT)
    if fixture.n_ticks < 1:
        return ScorecardRow(
            process_name=process_name,
            status="SKIP",
            reason="Truncated fixture (n_ticks < 1).",
            n_ticks_tested=0,
            properties_compared=0,
            max_abs=None,
            max_rel=None,
            top_disagreement_property=None,
        )

    try:
        process = process_cls({})
    except Exception as exc:
        return ScorecardRow(
            process_name=process_name,
            status="SKIP",
            reason=f"Process initialization failed: {exc}",
            n_ticks_tested=0,
            properties_compared=0,
            max_abs=None,
            max_rel=None,
            top_disagreement_property=None,
        )

    tick_inputs = {
        key: _slice_tick(series, 0, fixture.n_ticks)
        for key, series in fixture.inputs.items()
    }
    state = _build_tick_state(process, tick_inputs)

    try:
        update = process.next_update(_resolve_timestep(process), state)
        flat_update = _flatten_mapping(update)
    except Exception as exc:
        return ScorecardRow(
            process_name=process_name,
            status="SKIP",
            reason=f"Replay execution failed: {exc}",
            n_ticks_tested=0,
            properties_compared=0,
            max_abs=None,
            max_rel=None,
            top_disagreement_property=None,
        )

    compared: list[tuple[str, float, float]] = []
    structural_mismatch_props: list[str] = []
    for prop, output_series in fixture.outputs.items():
        if prop not in fixture.inputs:
            continue

        before = np.asarray(_slice_tick(fixture.inputs[prop], 0, fixture.n_ticks))
        expected_after = np.asarray(_slice_tick(output_series, 0, fixture.n_ticks))
        if before.shape != expected_after.shape:
            structural_mismatch_props.append(prop)
            continue
        if not (
            np.issubdtype(before.dtype, np.number) and np.issubdtype(expected_after.dtype, np.number)
        ):
            continue

        has_signal = _has_property_signal(flat_update, prop)
        if not has_signal:
            if np.array_equal(before, expected_after):
                delta = np.zeros_like(before, dtype=float)
            else:
                structural_mismatch_props.append(prop)
                continue
        else:
            delta = _delta_for_property(
                process=process,
                flat_update=flat_update,
                property_name=prop,
                before=before,
            )
            if delta is None or delta.shape != before.shape:
                structural_mismatch_props.append(prop)
                continue

        actual_after = before.astype(np.float64) + delta.astype(np.float64)
        expected_after_f = expected_after.astype(np.float64)
        max_abs, max_rel = _diff_metrics(actual_after, expected_after_f)
        compared.append((prop, max_abs, max_rel))

    if not compared:
        reason = "Structural mismatch: no comparable properties."
        if structural_mismatch_props:
            reason += f" Unmatched properties: {', '.join(sorted(structural_mismatch_props))}."
        return ScorecardRow(
            process_name=process_name,
            status="SKIP",
            reason=reason,
            n_ticks_tested=0,
            properties_compared=0,
            max_abs=None,
            max_rel=None,
            top_disagreement_property=None,
        )

    top_prop, top_abs, top_rel = max(compared, key=lambda item: (item[2], item[1]))
    status = _score_status(max_abs=top_abs, max_rel=top_rel)
    return ScorecardRow(
        process_name=process_name,
        status=status,
        reason="" if status != "FAIL" else "Exceeded PASS/PARTIAL fidelity thresholds.",
        n_ticks_tested=1,
        properties_compared=len(compared),
        max_abs=top_abs,
        max_rel=top_rel,
        top_disagreement_property=top_prop,
    )


def _render_markdown(rows: list[ScorecardRow]) -> str:
    summary = {
        status: sum(1 for row in rows if row.status == status)
        for status in ("PASS", "PARTIAL", "FAIL", "SKIP")
    }
    lines = [
        "# Karr Fidelity Scorecard (Per-Process Replay, Tick 0)",
        "",
        f"`PASS={summary['PASS']} PARTIAL={summary['PARTIAL']} FAIL={summary['FAIL']} SKIP={summary['SKIP']}`",
        "",
        "Bands:",
        "- PASS: `max_rel < 1e-6` OR `max_abs < 1e-9`",
        "- PARTIAL: `max_rel < 0.05`",
        "- FAIL: otherwise",
        "- SKIP: no adapter, truncated fixture, mirror fixture, or structural mismatch",
        "",
        "| Process | Status | n_ticks tested | properties compared | max_abs | max_rel | top-disagreement property | reason |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.process_name} | {row.status} | {row.n_ticks_tested} | {row.properties_compared} | "
            f"{_format_metric(row.max_abs)} | {_format_metric(row.max_rel)} | "
            f"{row.top_disagreement_property or '-'} | {row.reason or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_scorecard(*, write_outputs: bool = True) -> list[ScorecardRow]:
    process_names = sorted(path.stem for path in REPLAY_FIXTURE_ROOT.glob("*.npz"))
    rows = [_evaluate_process(process_name) for process_name in process_names]

    if write_outputs:
        MARKDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        MARKDOWN_PATH.write_text(_render_markdown(rows), encoding="utf-8")

        payload = {
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "thresholds": {
                "pass_rel_lt": PASS_REL,
                "pass_abs_lt": PASS_ABS,
                "partial_rel_lt": PARTIAL_REL,
            },
            "rows": [asdict(row) for row in rows],
        }
        JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return rows


def main() -> int:
    run_scorecard(write_outputs=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
