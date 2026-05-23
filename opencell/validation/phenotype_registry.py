"""Phase E.2 phenotype registry definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from opencell.validation import phenotype_extractors as ex
from opencell.validation.karr_reference_values import KARR_REFERENCE_VALUES

Bucket = Literal[
    "opencell-tooling",
    "validation-and-organism-scaling",
    "karr-known-incomplete",
    "biology-beyond-Karr",
]

Trajectory = dict[str, Any]
Extractor = Callable[[Trajectory], float | bool | None]

Comparator = Literal["relative", "ratio_band", "threshold_max", "threshold_min", "bool"]

BUCKET_DEFAULT_REL_TOL: dict[Bucket, float] = {
    "opencell-tooling": 0.001,
    "validation-and-organism-scaling": 0.30,
    "karr-known-incomplete": 1.5,
    "biology-beyond-Karr": 0.0,
}


@dataclass(frozen=True)
class PhenotypeDef:
    """Definition for one KP item in the E.2 scorecard."""

    id: str
    label: str
    bucket: Bucket
    extractor: Extractor
    karr_value: float | bool | None
    karr_citation: str
    rel_tol: float
    notes: str = ""
    disposition_todo_id: str | None = None
    comparator: Comparator = "relative"


def _tol(bucket: Bucket, override: float | None = None) -> float:
    return BUCKET_DEFAULT_REL_TOL[bucket] if override is None else float(override)


def _extractor_for_kp(kp_id: str) -> Extractor:
    fn_name = f"extract_{kp_id.lower()}"
    fn = getattr(ex, fn_name, None)
    if fn is None:
        raise KeyError(f"Extractor not found for {kp_id}: {fn_name}")
    return fn


_SPECS: tuple[dict[str, Any], ...] = (
    {"id": "KP01", "label": "Growth rate (g/s)", "bucket": "opencell-tooling"},
    {"id": "KP02", "label": "Doubling time (s)", "bucket": "validation-and-organism-scaling"},
    {
        "id": "KP03",
        "label": "Flux-oracle agreement",
        "bucket": "opencell-tooling",
        "comparator": "threshold_max",
        "rel_tol": 1.0,
        "disposition_todo_id": "E2-V1_1-KP03-FLUX-ORACLE",
        "notes": "Needs metabolic flux stream + oracle fixture in emitter schema v1.1.",
    },
    {
        "id": "KP04",
        "label": "Glucose uptake (PTS)",
        "bucket": "validation-and-organism-scaling",
        "disposition_todo_id": "E2-V1_1-KP04-TX_GLCPTS",
        "notes": "Needs TX_GLCPTS flux in emitted trajectory.",
    },
    {"id": "KP05", "label": "Total mRNA abundance", "bucket": "validation-and-organism-scaling"},
    {"id": "KP06", "label": "Total protein abundance", "bucket": "validation-and-organism-scaling"},
    {
        "id": "KP07",
        "label": "mRNA short-horizon stability",
        "bucket": "opencell-tooling",
        "comparator": "threshold_max",
        "rel_tol": 0.30,
    },
    {
        "id": "KP08",
        "label": "Protein short-horizon stability",
        "bucket": "opencell-tooling",
        "comparator": "threshold_max",
        "rel_tol": 0.10,
    },
    {
        "id": "KP09",
        "label": "Amino-acid pool stability",
        "bucket": "opencell-tooling",
        "comparator": "threshold_max",
        "rel_tol": 0.10,
    },
    {"id": "KP10", "label": "Cell dry mass (g) at division", "bucket": "validation-and-organism-scaling"},
    {
        "id": "KP11",
        "label": "Replication initiation timing (s)",
        "bucket": "karr-known-incomplete",
        "comparator": "ratio_band",
    },
    {
        "id": "KP12",
        "label": "Replication duration (s)",
        "bucket": "karr-known-incomplete",
        "comparator": "ratio_band",
    },
    {
        "id": "KP13",
        "label": "Cytokinesis duration (s)",
        "bucket": "karr-known-incomplete",
        "comparator": "ratio_band",
        "disposition_todo_id": "E2-V1_1-KP13-CYTOKINESIS-TRACE",
        "notes": "Legacy fixtures may miss cytokinesis timestamp observables.",
    },
    {
        "id": "KP14",
        "label": "dNTP vs replication coupling",
        "bucket": "opencell-tooling",
        "comparator": "threshold_min",
        "rel_tol": 0.5,
    },
    {
        "id": "KP15",
        "label": "DNA-binding occupancy dynamics",
        "bucket": "biology-beyond-Karr",
        "comparator": "bool",
        "disposition_todo_id": "E2-V1_1-KP15-DNA-OCCUPANCY",
        "notes": "Needs chromosome.complex_bound_sites trajectory.",
    },
    {
        "id": "KP16",
        "label": "DNA content doubling",
        "bucket": "opencell-tooling",
        "rel_tol": 0.10,
    },
    {
        "id": "KP17",
        "label": "DNA mass fraction",
        "bucket": "validation-and-organism-scaling",
        "disposition_todo_id": "E2-V1_1-KP17-DNA-MASS",
        "notes": "Legacy fixtures may miss phenotype_observables.dna_mass_g emission.",
    },
    {
        "id": "KP18",
        "label": "RNA mass fraction",
        "bucket": "validation-and-organism-scaling",
        "disposition_todo_id": "E2-V1_1-KP18-RNA-MASS",
        "notes": "Needs explicit RNA mass and total mass trajectories.",
    },
    {
        "id": "KP19",
        "label": "Protein mass fraction",
        "bucket": "validation-and-organism-scaling",
        "disposition_todo_id": "E2-V1_1-KP19-PROTEIN-MASS",
        "notes": "Needs explicit protein mass and total mass trajectories.",
    },
    {
        "id": "KP20",
        "label": "Metabolite concentration profile",
        "bucket": "karr-known-incomplete",
        "comparator": "threshold_max",
        "rel_tol": 1.0,
        "disposition_todo_id": "E2-V1_1-KP20-METABOLITE-PROFILE",
        "notes": "Legacy fixtures may miss phenotype_observables.metabolite_pools.",
    },
    {
        "id": "KP21",
        "label": "ATP/GTP production-use balance",
        "bucket": "opencell-tooling",
        "rel_tol": 0.05,
        "disposition_todo_id": "E2-V1_1-KP21-ENERGY-LEDGER",
        "notes": "Needs production/use ledger in trajectory output.",
    },
    {
        "id": "KP22",
        "label": "Energy discrepancy phenotype",
        "bucket": "karr-known-incomplete",
        "comparator": "bool",
    },
    {
        "id": "KP23",
        "label": "Burst-like protein synthesis stats",
        "bucket": "biology-beyond-Karr",
        "comparator": "bool",
    },
    {
        "id": "KP24",
        "label": "mRNA/protein distribution shape",
        "bucket": "biology-beyond-Karr",
        "comparator": "bool",
    },
    {
        "id": "KP25",
        "label": "Gene essentiality accuracy",
        "bucket": "biology-beyond-Karr",
        "comparator": "bool",
        "disposition_todo_id": "E2-V1_1-KP25-KO-SWEEP",
        "notes": "Deferred by design: multi-run KO sweep required.",
    },
    {
        "id": "KP26",
        "label": "Single-gene disruption phenotype class",
        "bucket": "biology-beyond-Karr",
        "comparator": "bool",
        "disposition_todo_id": "E2-V1_1-KP26-KO-CLASS",
        "notes": "Deferred by design: multi-run KO sweep required.",
    },
    {
        "id": "KP27",
        "label": "Host adhesion competence",
        "bucket": "biology-beyond-Karr",
        "comparator": "bool",
        "disposition_todo_id": "E2-V1_1-KP27-HOST-ADHESION",
        "notes": "Needs host.is_bacterium_adherent trajectory emission.",
    },
    {
        "id": "KP28",
        "label": "Host immune activation cascade",
        "bucket": "biology-beyond-Karr",
        "comparator": "bool",
        "disposition_todo_id": "E2-V1_1-KP28-HOST-IMMUNE-CASCADE",
        "notes": "Needs host immune activation booleans in trajectory output.",
    },
)


def _build_registry() -> dict[str, PhenotypeDef]:
    out: dict[str, PhenotypeDef] = {}
    for spec in _SPECS:
        kp_id = spec["id"]
        ref = KARR_REFERENCE_VALUES[kp_id]
        bucket = spec["bucket"]
        out[kp_id] = PhenotypeDef(
            id=kp_id,
            label=spec["label"],
            bucket=bucket,
            extractor=_extractor_for_kp(kp_id),
            karr_value=ref.value,
            karr_citation=ref.citation,
            rel_tol=_tol(bucket, spec.get("rel_tol")),
            notes=spec.get("notes", ""),
            disposition_todo_id=spec.get("disposition_todo_id"),
            comparator=spec.get("comparator", "relative"),
        )
    return out


PHENOTYPES: dict[str, PhenotypeDef] = _build_registry()


__all__ = [
    "BUCKET_DEFAULT_REL_TOL",
    "Bucket",
    "Comparator",
    "Extractor",
    "PHENOTYPES",
    "PhenotypeDef",
    "Trajectory",
]
