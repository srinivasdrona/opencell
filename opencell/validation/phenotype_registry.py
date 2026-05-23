"""Phase E.2 phenotype registry definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

Bucket = Literal[
    "opencell-tooling",
    "validation-and-organism-scaling",
    "karr-known-incomplete",
    "biology-beyond-Karr",
]

Trajectory = dict[str, Any]
Extractor = Callable[[Trajectory], float | bool | None]

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
    comparator: Literal["relative", "ratio_band", "threshold_max", "bool"] = "relative"


def _extractor_unimplemented(_trajectory: Trajectory) -> None:
    return None


def _tol(bucket: Bucket, override: float | None = None) -> float:
    return BUCKET_DEFAULT_REL_TOL[bucket] if override is None else float(override)


PHENOTYPES: dict[str, PhenotypeDef] = {
    "KP01": PhenotypeDef(
        id="KP01",
        label="Growth rate (g/s)",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr 2012 Fig 3a",
        rel_tol=_tol("opencell-tooling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP02": PhenotypeDef(
        id="KP02",
        label="Doubling time (s)",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr 2012 Fig 3a",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP03": PhenotypeDef(
        id="KP03",
        label="Flux-oracle agreement",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: m1 oracle fixture",
        rel_tol=_tol("opencell-tooling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP04": PhenotypeDef(
        id="KP04",
        label="Glucose uptake (PTS)",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr supplement table S6",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP05": PhenotypeDef(
        id="KP05",
        label="Total mRNA abundance",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr supplement table S3",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP06": PhenotypeDef(
        id="KP06",
        label="Total protein abundance",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr supplement table S3",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP07": PhenotypeDef(
        id="KP07",
        label="mRNA short-horizon stability",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="Qualitative stability metric",
        rel_tol=_tol("opencell-tooling", 0.30),
        comparator="threshold_max",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP08": PhenotypeDef(
        id="KP08",
        label="Protein short-horizon stability",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="Qualitative stability metric",
        rel_tol=_tol("opencell-tooling", 0.10),
        comparator="threshold_max",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP09": PhenotypeDef(
        id="KP09",
        label="Amino-acid pool stability",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="Qualitative stability metric",
        rel_tol=_tol("opencell-tooling", 0.10),
        comparator="threshold_max",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP10": PhenotypeDef(
        id="KP10",
        label="Cell dry mass (g) at division",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr 2012 Fig 3b",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP11": PhenotypeDef(
        id="KP11",
        label="Replication initiation timing (s)",
        bucket="karr-known-incomplete",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr 2012 Fig 3c",
        rel_tol=_tol("karr-known-incomplete"),
        comparator="ratio_band",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP12": PhenotypeDef(
        id="KP12",
        label="Replication duration (s)",
        bucket="karr-known-incomplete",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr 2012 Fig 3c",
        rel_tol=_tol("karr-known-incomplete"),
        comparator="ratio_band",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP13": PhenotypeDef(
        id="KP13",
        label="Cytokinesis duration (s)",
        bucket="karr-known-incomplete",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr 2012 Fig 3c",
        rel_tol=_tol("karr-known-incomplete"),
        comparator="ratio_band",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP14": PhenotypeDef(
        id="KP14",
        label="dNTP vs replication coupling",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=0.5,
        karr_citation="Qualitative expected positive coupling",
        rel_tol=_tol("opencell-tooling"),
        comparator="threshold_max",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP15": PhenotypeDef(
        id="KP15",
        label="DNA-binding occupancy dynamics",
        bucket="biology-beyond-Karr",
        extractor=_extractor_unimplemented,
        karr_value=True,
        karr_citation="Qualitative occupancy presence",
        rel_tol=_tol("biology-beyond-Karr"),
        comparator="bool",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP16": PhenotypeDef(
        id="KP16",
        label="DNA content doubling",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=2.0,
        karr_citation="Expected chromosome mass doubling over cycle",
        rel_tol=_tol("opencell-tooling", 0.10),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP17": PhenotypeDef(
        id="KP17",
        label="DNA mass fraction",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr supplement table S4",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP18": PhenotypeDef(
        id="KP18",
        label="RNA mass fraction",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr supplement table S4",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP19": PhenotypeDef(
        id="KP19",
        label="Protein mass fraction",
        bucket="validation-and-organism-scaling",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr supplement table S4",
        rel_tol=_tol("validation-and-organism-scaling"),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP20": PhenotypeDef(
        id="KP20",
        label="Metabolite concentration profile",
        bucket="karr-known-incomplete",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="TODO: Karr supplement table S5",
        rel_tol=_tol("karr-known-incomplete", 1.0),
        comparator="threshold_max",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP21": PhenotypeDef(
        id="KP21",
        label="ATP/GTP production-use balance",
        bucket="opencell-tooling",
        extractor=_extractor_unimplemented,
        karr_value=0.0,
        karr_citation="Expected near-zero production-use discrepancy",
        rel_tol=_tol("opencell-tooling", 0.05),
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP22": PhenotypeDef(
        id="KP22",
        label="Energy discrepancy phenotype",
        bucket="karr-known-incomplete",
        extractor=_extractor_unimplemented,
        karr_value=True,
        karr_citation="Qualitative energy discrepancy detector",
        rel_tol=_tol("karr-known-incomplete"),
        comparator="bool",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP23": PhenotypeDef(
        id="KP23",
        label="Burst-like protein synthesis stats",
        bucket="biology-beyond-Karr",
        extractor=_extractor_unimplemented,
        karr_value=True,
        karr_citation="Qualitative computability check",
        rel_tol=_tol("biology-beyond-Karr"),
        comparator="bool",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP24": PhenotypeDef(
        id="KP24",
        label="mRNA/protein distribution shape",
        bucket="biology-beyond-Karr",
        extractor=_extractor_unimplemented,
        karr_value=True,
        karr_citation="Qualitative distribution-shape availability",
        rel_tol=_tol("biology-beyond-Karr"),
        comparator="bool",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP25": PhenotypeDef(
        id="KP25",
        label="Gene essentiality accuracy",
        bucket="biology-beyond-Karr",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="Requires multi-run KO sweep",
        rel_tol=_tol("biology-beyond-Karr"),
        comparator="bool",
        notes="Blocked in v1 by design.",
        disposition_todo_id="E2-V1_1-KP25-KO-SWEEP",
    ),
    "KP26": PhenotypeDef(
        id="KP26",
        label="Single-gene disruption phenotype class",
        bucket="biology-beyond-Karr",
        extractor=_extractor_unimplemented,
        karr_value=None,
        karr_citation="Requires multi-run KO sweep",
        rel_tol=_tol("biology-beyond-Karr"),
        comparator="bool",
        notes="Blocked in v1 by design.",
        disposition_todo_id="E2-V1_1-KP26-KO-CLASS",
    ),
    "KP27": PhenotypeDef(
        id="KP27",
        label="Host adhesion competence",
        bucket="biology-beyond-Karr",
        extractor=_extractor_unimplemented,
        karr_value=True,
        karr_citation="Qualitative host interaction output",
        rel_tol=_tol("biology-beyond-Karr"),
        comparator="bool",
        notes="Extractor wired in checkpoint 3.",
    ),
    "KP28": PhenotypeDef(
        id="KP28",
        label="Host immune activation cascade",
        bucket="biology-beyond-Karr",
        extractor=_extractor_unimplemented,
        karr_value=True,
        karr_citation="Qualitative host interaction output",
        rel_tol=_tol("biology-beyond-Karr"),
        comparator="bool",
        notes="Extractor wired in checkpoint 3.",
    ),
}


__all__ = [
    "BUCKET_DEFAULT_REL_TOL",
    "Bucket",
    "Extractor",
    "PHENOTYPES",
    "PhenotypeDef",
    "Trajectory",
]
