"""Build canonical Karr archive: .mat -> npz + JSON manifest.

Reads every .mat in data/m1_sources/karr_flat/ and packages all fields actually
consumed by the karr_native_ingest_*.py scripts into a single committed archive
under data/karr_archive/. After this lands, no Python runtime needs MATLAB
or raw .mat files; ingestion scripts read from the archive instead.

The archive contains:
  - karr_archive.npz       -- all numeric arrays, keyed "<basename>__<dotted.path>"
  - karr_archive_strings.json  -- string arrays + nested string scalars
  - karr_archive_manifest.json -- per-field metadata: source, dtype, shape, sha256

Re-run this only when extract_karr_targeted.m is modified (i.e. when ingestion
needs a NEW field not yet in the archive). Day-to-day Python work never touches
MATLAB or .mat.
"""
from __future__ import annotations
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import loadmat

try:
    import h5py
except ImportError:
    h5py = None  # only needed for v7.3 .mat files (metabolism_dynamics)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "m1_sources" / "karr_flat"
DST = ROOT / "data" / "karr_archive"
DST.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Whitelist: which fields each .mat exposes to the archive.
# Derived from grepping karr_native_ingest_*.py for attribute access.
# Entries are dotted paths under data.<root> in the .mat file.
# Special: "<struct_array>.field" means walk a struct array and pull "field"
# from every element into a parallel column.
# ---------------------------------------------------------------------------

ARCHIVE_SPEC = {
    # m3 (translation): all 25 fields are flat arrays under data.* -- take all.
    "proteins_targeted": {
        "fields": [
            "matureIndexs", "nascentIndexs", "processedIIndexs", "processedIIIndexs",
            "foldedIndexs", "inactivatedIndexs", "boundIndexs", "misfoldedIndexs",
            "damagedIndexs", "signalSequenceIndexs",
            "lengths", "halfLives", "decayRates", "molecularWeights",
            "compartments", "counts", "baseCounts",
            "wholeCellModelIDs", "names",
            "kb_wholeCellModelIDs", "kb_geneWholeCellModelIDs", "kb_geneIndex",
            "kb_compartmentWholeCellModelIDs",
            "translation_ribosomeElongationRate", "translation_tmRNABindingProbability",
        ],
        "consumer": "karr_native_ingest_m3.py",
    },
    # m2 (transcription) State_Rna: all 22 fields needed for MW/counts re-extract.
    "rnas_targeted": {
        "fields": [
            "matureIndexs", "nascentIndexs", "processedIndexs", "intergenicIndexs",
            "boundIndexs", "misfoldedIndexs", "damagedIndexs", "aminoacylatedIndexs",
            "molecularWeights", "lengths", "halfLives", "decayRates",
            "compartments", "counts", "expression",
            "wholeCellModelIDs", "names", "baseCounts",
            "kb_gene_wholeCellModelIDs", "kb_tu_wholeCellModelIDs",
            "kb_gene_to_tu_index", "kb_tu_to_gene_indices",
        ],
        "consumer": "karr_native_ingest_m2.py",
    },
    # m1 protein-complexes: 4 top-level + struct array of 201 complexes (flatten).
    "protein_complexes": {
        "fields": [
            "complex_wids_201", "monomer_wids_482",
            "metabolite_wids_722", "compartment_wids_6",
            "x_source_file", "x_matlab_release", "x_extract_timestamp_utc",
        ],
        "struct_arrays": {
            "complexes": {
                "scalars": [
                    "wholeCellModelID", "name", "idx", "numSubunits",
                    "numDistinctSubunits", "dnaFootprint", "density",
                    "activationRule", "formation_compartment_wid",
                ],
                "nested_struct_arrays": {
                    # complexes[i].monomers[j] etc. are all struct arrays
                    "monomers": [
                        "molecule_wid", "coefficient",
                        "compartment_wid", "molecule_idx_1based",
                    ],
                    "subcomplexes": [
                        "molecule_wid", "coefficient",
                        "compartment_wid", "molecule_idx_1based",
                    ],
                    "metabolites": [
                        "molecule_wid", "coefficient",
                        "compartment_wid", "molecule_idx_1based",
                    ],
                    "prosthetic": [
                        "molecule_wid", "coefficient",
                        "compartment_wid", "molecule_idx_1based",
                    ],
                    "chaperones": [
                        "molecule_wid", "coefficient",
                        "compartment_wid", "molecule_idx_1based",
                    ],
                    "rnas": [
                        "molecule_wid", "coefficient",
                        "compartment_wid", "molecule_idx_1based",
                    ],
                },
            },
        },
        "consumer": "karr_native_ingest_complexes.py",
    },
    # m1 sim_fitted: a curated slice of state + process snapshots.
    "sim_fitted_targeted": {
        "fields": [
            # ---- Mass parameters (top-level scalars under data.parameters) ----
            "parameters.states.Mass.cellInitialDryWeight",
            "parameters.states.Mass.dryWeightFractionRNA",
            "parameters.states.MetabolicReaction.meanInitialGrowthRate",
            "parameters.states.Time.cellCycleLength",
            "parameters.states.RNAPolymerase.stateExpectations",
            "parameters.processes.Transcription.rnaPolymeraseElongationRate",
            # ---- State_Mass dump (cell mass aggregates per compartment) ----
            "states.State_Mass.dump.cell",
            "states.State_Mass.dump.cellDry",
            "states.State_Mass.dump.rnaWt",
            "states.State_Mass.dump.cellInitialDryWeight",
            "states.State_Mass.dump.dryWeightFractionRNA",
            # ---- State_MetabolicReaction dump (Karr's stored runtime values) ----
            "states.State_MetabolicReaction.dump.fluxs",
            "states.State_MetabolicReaction.dump.growth",
            "states.State_MetabolicReaction.dump.growth0",
            "states.State_MetabolicReaction.dump.doublingTime",
            "states.State_MetabolicReaction.dump.meanInitialGrowthRate",
            # ---- Top-level metabolism block (FBA matrices & metadata) ----
            "metabolism.reactionStoichiometryMatrix",
            "metabolism.reactionWholeCellModelIDs",
            "metabolism.reactionNames",
            "metabolism.reactionTypes",
            "metabolism.substrateWholeCellModelIDs",
            "metabolism.substrateNames",
            "metabolism.substrateMolecularWeights",
            "metabolism.enzymeWholeCellModelIDs",
            "metabolism.enzymeMolecularWeights",
            "metabolism.fbaReactionStoichiometryMatrix",
            "metabolism.fbaRightHandSide",
            "metabolism.fbaReactionBounds",
            "metabolism.fbaEnzymeBounds",
            "metabolism.fbaObjective",
            "metabolism.fbaReactionCatalysisMatrix",
            "metabolism.fbaReactionIndexs_metabolicConversion",
            "metabolism.fbaReactionIndexs_metaboliteExternalExchange",
            "metabolism.fbaReactionIndexs_metaboliteInternalExchange",
            "metabolism.fbaReactionIndexs_metaboliteInternalLimitedExchange",
            "metabolism.fbaReactionIndexs_metaboliteInternalUnlimitedExchange",
            "metabolism.fbaReactionIndexs_biomassProduction",
            "metabolism.fbaReactionIndexs_biomassExchange",
            "metabolism.fbaSubstrateIndexs_substrates",
            "metabolism.fbaSubstrateIndexs_metaboliteInternalExchangeConstraints",
            "metabolism.fbaSubstrateIndexs_biomass",
            "metabolism.reactionIndexs_fba",
            "metabolism.substrateIndexs_fba",
            # ---- Process_Transcription (m2 v1 fitted constants) ----
            "processes.Process_Transcription.fittedConstants.transcriptionUnitBindingProbabilities",
            "processes.Process_Transcription.parameters.rnaPolymeraseElongationRate",
        ],
        "consumer": "karr_native_ingest_m1.py + karr_native_ingest_m2.py",
    },
    # KB: small whitelist of gene/TU/parameters fields used by ingestion.
    "knowledgeBase_targeted": {
        "struct_arrays": {
            "knowledgeBase.genes": {
                "scalars": [
                    "wholeCellModelID", "name", "symbol", "type", "essential",
                    "startCoordinate", "endCoordinate", "direction",
                    "halfLife", "expression", "synthesisRate",
                ],
            },
            "knowledgeBase.transcriptionUnits": {
                "scalars": [
                    "wholeCellModelID", "name", "startCoordinate", "endCoordinate",
                    "direction",
                ],
            },
            "knowledgeBase.parameters": {
                "scalars": [
                    "wholeCellModelID", "name", "defaultValue", "units",
                    "experimentallyConstrained",
                ],
            },
        },
        "scalars": ["knowledgeBase.translationTable", "knowledgeBase.taxonomy"],
        "consumer": "karr_native_ingest_m2.py + others",
    },
    # ---- m2 v2 (RNA polymerase mechanics) — flat .mat, take all fields ----
    "transcription_v2_targeted": {
        "fields": [
            "rnap_properties", "rnap_activelyTranscribingIndex",
            "rnap_specificallyBoundIndex", "rnap_nonSpecificallyBoundIndex",
            "rnap_freeIndex", "rnap_activelyTranscribingValue",
            "rnap_specificallyBoundValue", "rnap_nonSpecificallyBoundValue",
            "rnap_freeValue", "rnap_notExistValue", "rnap_stateValues",
            "rnap_stateExpectations", "rnap_states", "rnap_positionStrands",
            "rnap_transcriptionFactorBindingProbFoldChange",
            "rnap_supercoilingBindingProbFoldChange", "rnap_stateOccupancies",
            "rnap_nActive", "rnap_nSpecificallyBound", "rnap_nNonSpecificallyBound",
            "rnap_nFree", "rnap_dryWeight", "rnap_verbosity", "rnap_seed",
            "rnap_states_vec",
            "transcript_properties", "tr_transcriptionUnitLengths",
            "tr_transcriptionUnitFivePrimeCoordinates", "tr_transcriptionUnitDirections",
            "pt_enzymes", "pt_boundEnzymes", "pt_enzymeWholeCellModelIDs",
            "pt_enzymeIndexs_rnaPolymerase", "pt_enzymeIndexs_rnaPolymeraseHoloenzyme",
            "pt_rnaPolymerases_nActive", "pt_rnaPolymerases_nSpecificallyBound",
            "pt_rnaPolymerases_nNonSpecificallyBound", "pt_rnaPolymerases_nFree",
            "pt_rnaPolymerases_states", "pt_rnaPolymerases_stateExpectations",
            "pt_rnaPolymerases_activelyTranscribingValue",
            "pt_rnaPolymerases_specificallyBoundValue",
            "pt_rnaPolymerases_nonSpecificallyBoundValue",
            "pt_rnaPolymerases_freeValue",
            "pt_tr_transcriptionUnitLengths", "pt_rnaPolymeraseElongationRate",
            "kb_tu_wholeCellModelIDs", "kb_tu_lengths", "kb_tu_geneWcmIDs",
            "kb_geneWholeCellModelIDs_full",
        ],
        "consumer": "karr_native_ingest_m2v2.py",
    },
    # ---- m3 v2 (ribosome mechanics) — flat .mat, take all fields ----
    "translation_v2_targeted": {
        "fields": [
            "rib_properties", "rib_activeIndex", "rib_notExistIndex",
            "rib_stalledIndex", "rib_activeValue", "rib_notExistValue",
            "rib_stalledValue", "rib_states", "rib_boundMRNAs", "rib_mRNAPositions",
            "rib_tmRNAPositions", "rib_stateOccupancies", "rib_nActive",
            "rib_nNotExist", "rib_nStalled", "rib_nMRNAsBound", "rib_dryWeight",
            "rib_verbosity", "rib_seed", "rib_states_vec",
            "pt_ribosomeElongationRate", "pt_enzymeWholeCellModelIDs",
            "pt_enzymes", "pt_boundEnzymes", "pt_mRNAs", "pt_freeTRNAs",
            "pt_aminoacylatedTRNAs", "pt_polypeptide_monomerLengths",
            "pt_substrateWholeCellModelIDs", "pt_substrateIndexs_gtp",
            "pt_substrateIndexs_water",
            "rna_matureIndexs", "rna_processedIndexs", "rna_nascentIndexs",
            "rna_counts", "rna_lengths", "poly_monomerLengths",
        ],
        "consumer": "karr_native_ingest_m3v2.py",
    },
    # ---- HDF5 v7.3 metabolism_dynamics — top-level flat datasets ----
    "metabolism_dynamics": {
        "format": "hdf5_v73",  # marker; processed via h5py path below
        "fields": [
            "snapshot_substrates", "snapshot_enzymes", "snapshot_cell_dry_mass",
            "step_size_sec",
            "substrate_indexs_fba", "substrate_indexs_external_exch",
            "substrate_indexs_internal_lim",
            "compartment_indexs_extracellular", "compartment_indexs_cytosol",
            "compartment_indexs_membrane",
            "fba_rxn_idx_metab_conv", "fba_rxn_idx_external_exch",
            "fba_rxn_idx_internal_exch", "fba_rxn_idx_internal_lim_exch",
            "fba_rxn_idx_internal_unlim_exch", "fba_rxn_idx_biomass_production",
            "fba_rxn_idx_biomass_exchange",
            "bounds_dynamic_no_protein", "bounds_dynamic_with_protein",
        ],
        "consumer": "karr_native_ingest_m1_dynamics.py",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(node, dotted_path: str):
    """Walk a dotted path under a mat_struct (matlab.mio5_params.mat_struct)."""
    cur = node
    for part in dotted_path.split("."):
        cur = getattr(cur, part)
    return cur


def _to_serializable(value):
    """Convert a leaf to either an ndarray (for npz) or a JSON-safe object."""
    if isinstance(value, np.ndarray):
        if value.dtype == object and value.size > 0 and isinstance(value.flat[0], (str, bytes, np.str_)):
            return [str(x) for x in value.flat], "string_list"
        if value.dtype == object:
            # Mixed object array; coerce each element via tolist.
            try:
                return [_to_serializable(x)[0] for x in value.flat], "object_list"
            except Exception:
                return value.tolist(), "object_list"
        return value, "ndarray"
    if isinstance(value, (str, np.str_)):
        return str(value), "string"
    if isinstance(value, (np.generic,)):
        return value.item(), "scalar"
    if isinstance(value, (int, float, bool)):
        return value, "scalar"
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace"), "string"
    return repr(value), "repr"


def _sha256_array(a: np.ndarray) -> str:
    if not isinstance(a, np.ndarray):
        a = np.asarray(a)
    return hashlib.sha256(a.tobytes()).hexdigest()[:16]


def _flatten_struct_array(arr, scalar_fields, nested_specs=None):
    """Walk a struct array, return {field: list-of-values} (nested handled separately)."""
    nested_specs = nested_specs or {}
    cols = {f: [] for f in scalar_fields}
    nested_out = {nf: [] for nf in nested_specs}  # list of per-element nested dicts
    for elem in np.atleast_1d(arr):
        for f in scalar_fields:
            try:
                v = getattr(elem, f)
            except AttributeError:
                v = None
            cols[f].append(v)
        for nf, nf_scalars in nested_specs.items():
            try:
                nested_arr = getattr(elem, nf)
            except AttributeError:
                nested_out[nf].append(None)
                continue
            sub_cols = {s: [] for s in nf_scalars}
            for sub in np.atleast_1d(nested_arr):
                for s in nf_scalars:
                    try:
                        sub_cols[s].append(getattr(sub, s))
                    except AttributeError:
                        sub_cols[s].append(None)
            nested_out[nf].append(sub_cols)
    return cols, nested_out


def _coerce_column(values, name: str):
    """Try to convert a list of values to a homogeneous ndarray; fall back to list."""
    if all(isinstance(v, str) for v in values):
        return np.array(values, dtype=object), "string_list"
    if all(v is None or isinstance(v, str) for v in values):
        return np.array([("" if v is None else v) for v in values], dtype=object), "string_list"
    try:
        arr = np.array(values)
        if arr.dtype == object:
            # Heterogeneous; keep as list-in-JSON.
            return values, "object_list"
        return arr, "ndarray"
    except Exception:
        return values, "object_list"


# ---------------------------------------------------------------------------
# Main extraction loop
# ---------------------------------------------------------------------------

def main() -> int:
    if not SRC.exists():
        print(f"ERROR: source dir {SRC} not found. Run MATLAB extraction first.", file=sys.stderr)
        return 1

    npz_payload: dict[str, np.ndarray] = {}
    strings_payload: dict[str, object] = {}
    manifest = {
        "schema_version": "karr_archive__v1",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dir_relative": str(SRC.relative_to(ROOT)),
        "files": {},
    }

    for basename, spec in ARCHIVE_SPEC.items():
        mat_path = SRC / f"{basename}.mat"
        if not mat_path.exists():
            print(f"WARN: {mat_path.name} missing, skipping")
            continue
        print(f"[archive] {mat_path.name}")
        if spec.get("format") == "hdf5_v73":
            if h5py is None:
                print("  ERROR: h5py not installed; skipping HDF5 file")
                continue
            file_manifest: dict[str, dict] = {}
            with h5py.File(str(mat_path), "r") as f:
                for fpath in spec.get("fields", []):
                    if fpath not in f:
                        print(f"  miss: {fpath}")
                        continue
                    arr = np.array(f[fpath])
                    key = f"{basename}__{fpath}"
                    npz_payload[key] = arr
                    file_manifest[fpath] = {
                        "source_path": fpath, "kind": "ndarray",
                        "dtype": str(arr.dtype), "shape": list(arr.shape),
                        "sha256_16": _sha256_array(arr),
                        "note": "hdf5_v73 raw shape; consumers may need .T to restore column-major orientation",
                    }
            manifest["files"][basename] = {
                "consumer": spec.get("consumer", "?"),
                "format": "hdf5_v73",
                "fields": file_manifest,
            }
            print(f"  -> {len(file_manifest)} field groups extracted (h5py)")
            continue
        raw = loadmat(str(mat_path), struct_as_record=False, squeeze_me=True)
        root = raw["data"]
        file_manifest = {}

        for fpath in spec.get("fields", []):
            try:
                val = _resolve(root, fpath)
            except AttributeError as e:
                print(f"  miss: {fpath}  ({e})")
                continue
            payload, kind = _to_serializable(val)
            key = f"{basename}__{fpath.replace('.', '__')}"
            entry = {
                "source_path": fpath, "kind": kind,
            }
            if kind == "ndarray":
                npz_payload[key] = payload
                entry["dtype"] = str(payload.dtype)
                entry["shape"] = list(payload.shape)
                entry["sha256_16"] = _sha256_array(payload)
            else:
                strings_payload[key] = payload
                entry["repr_len"] = len(payload) if hasattr(payload, "__len__") else 1
            file_manifest[fpath] = entry

        for sa_path, sa_spec in spec.get("struct_arrays", {}).items():
            try:
                arr = _resolve(root, sa_path)
            except AttributeError as e:
                print(f"  miss struct_array: {sa_path}  ({e})")
                continue
            cols, nested = _flatten_struct_array(
                arr,
                sa_spec.get("scalars", []),
                sa_spec.get("nested_struct_arrays", {}),
            )
            sa_entry = {"length": int(np.atleast_1d(arr).size), "columns": {}, "nested": {}}
            for col_name, col_vals in cols.items():
                arr_out, kind = _coerce_column(col_vals, col_name)
                key = f"{basename}__{sa_path.replace('.', '__')}__{col_name}"
                col_entry = {"kind": kind}
                if kind == "ndarray":
                    npz_payload[key] = arr_out
                    col_entry["dtype"] = str(arr_out.dtype)
                    col_entry["shape"] = list(arr_out.shape)
                    col_entry["sha256_16"] = _sha256_array(arr_out)
                else:
                    strings_payload[key] = arr_out if isinstance(arr_out, list) else list(arr_out)
                    col_entry["length"] = len(arr_out)
                sa_entry["columns"][col_name] = col_entry

            for nf, per_elem_dicts in nested.items():
                # Concatenate sub-columns across all parents, plus an offsets array.
                sub_cols_all: dict[str, list] = {}
                offsets = [0]
                for d in per_elem_dicts:
                    if d is None:
                        offsets.append(offsets[-1])
                        continue
                    n = max((len(v) for v in d.values()), default=0)
                    for s, vs in d.items():
                        sub_cols_all.setdefault(s, []).extend(vs)
                    offsets.append(offsets[-1] + n)
                offsets_key = f"{basename}__{sa_path.replace('.', '__')}__{nf}__offsets"
                npz_payload[offsets_key] = np.asarray(offsets, dtype=np.int64)
                nested_entry = {
                    "offsets_key": offsets_key,
                    "length": offsets[-1],
                    "columns": {},
                }
                for s, vs in sub_cols_all.items():
                    arr_out, kind = _coerce_column(vs, s)
                    key = f"{basename}__{sa_path.replace('.', '__')}__{nf}__{s}"
                    col_entry = {"kind": kind}
                    if kind == "ndarray":
                        npz_payload[key] = arr_out
                        col_entry["dtype"] = str(arr_out.dtype)
                        col_entry["shape"] = list(arr_out.shape)
                        col_entry["sha256_16"] = _sha256_array(arr_out)
                    else:
                        strings_payload[key] = arr_out if isinstance(arr_out, list) else list(arr_out)
                        col_entry["length"] = len(arr_out)
                    nested_entry["columns"][s] = col_entry
                sa_entry["nested"][nf] = nested_entry
            file_manifest[sa_path] = sa_entry

        for sc in spec.get("scalars", []):
            try:
                val = _resolve(root, sc)
            except AttributeError as e:
                print(f"  miss scalar: {sc}  ({e})")
                continue
            payload, kind = _to_serializable(val)
            key = f"{basename}__{sc.replace('.', '__')}"
            if kind == "ndarray":
                npz_payload[key] = payload
                file_manifest[sc] = {
                    "kind": "ndarray", "dtype": str(payload.dtype),
                    "shape": list(payload.shape), "sha256_16": _sha256_array(payload),
                }
            else:
                strings_payload[key] = payload
                file_manifest[sc] = {"kind": kind}

        manifest["files"][basename] = {
            "consumer": spec.get("consumer", "?"),
            "fields": file_manifest,
        }
        print(f"  -> {len(file_manifest)} field groups extracted")

    # Write outputs
    npz_path = DST / "karr_archive.npz"
    strings_path = DST / "karr_archive_strings.json"
    manifest_path = DST / "karr_archive_manifest.json"

    np.savez_compressed(npz_path, **npz_payload)
    with open(strings_path, "w") as f:
        json.dump(strings_payload, f, indent=2, default=str)
    # Compute file-level checksum.
    npz_sha = hashlib.sha256(npz_path.read_bytes()).hexdigest()
    strings_sha = hashlib.sha256(strings_path.read_bytes()).hexdigest()
    manifest["artifacts"] = {
        "karr_archive.npz": {"size_bytes": npz_path.stat().st_size, "sha256": npz_sha,
                              "n_arrays": len(npz_payload)},
        "karr_archive_strings.json": {"size_bytes": strings_path.stat().st_size,
                                       "sha256": strings_sha, "n_keys": len(strings_payload)},
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    print()
    print(f"Wrote {npz_path}  ({npz_path.stat().st_size/1024:.1f} KB, {len(npz_payload)} arrays)")
    print(f"Wrote {strings_path}  ({strings_path.stat().st_size/1024:.1f} KB, {len(strings_payload)} keys)")
    print(f"Wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
