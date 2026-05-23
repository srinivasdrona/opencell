"""Karr reference values for Phase E.2 phenotype scorecard."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KarrReferenceValue:
    """Reference value metadata for one KP row."""

    value: float | bool | None
    citation: str
    sourced_by: str
    sourced_at: str
    source_path: str | None = None
    notes: str = ""


_SOURCED_AT = "2026-05-23"
_SOURCED_BY = "codex-pe-2"

# Note: data/m1_sources/karr2012_supplement_01.xls, _02.xls, _03.xlsx are
# currently HTML anti-bot placeholders in this worktree, not usable tables.
KARR_REFERENCE_VALUES: dict[str, KarrReferenceValue] = {
    "KP01": KarrReferenceValue(
        value=2.1192692552000678e-05,
        citation="karr_native_m1 stored_runtime.growth_per_s",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_native_m1.json",
    ),
    "KP02": KarrReferenceValue(
        value=47186.07593378199,
        citation="karr_native_m1 stored_runtime.doublingTime_s",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_native_m1.json",
    ),
    "KP03": KarrReferenceValue(
        value=0.0,
        citation="karr_phenotype_targets p3_fba_oracle_median_log2_ratio target",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_phenotype_targets.json",
    ),
    "KP04": KarrReferenceValue(
        value=2725.0,
        citation="karr_phenotype_targets p4_glucose_uptake_TX_GLCPTS target",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_phenotype_targets.json",
    ),
    "KP05": KarrReferenceValue(
        value=784.0,
        citation="karr_native_m2 counts_mature_summary.total_counts_reference",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_native_m2.json",
    ),
    "KP06": KarrReferenceValue(
        value=16177.0,
        citation="karr_native_m3 scalars.total_mature_counts",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_native_m3.json",
    ),
    "KP07": KarrReferenceValue(
        value=0.10,
        citation="karr_phenotype_targets p7_mrna_stability_over_20s tol_rel",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_phenotype_targets.json",
    ),
    "KP08": KarrReferenceValue(
        value=0.10,
        citation="karr_phenotype_targets p8_protein_stability_over_20s tol_rel",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_phenotype_targets.json",
    ),
    "KP09": KarrReferenceValue(
        value=0.10,
        citation="phase_e2_phenotype_scorecard bucket override for KP09",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
        notes="Design-specified threshold used because Karr SI tables are unavailable locally.",
    ),
    "KP10": KarrReferenceValue(
        value=3.944640855678535e-15,
        citation="karr_native_m1 stored_runtime.cell_dry_total_mass_g",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_native_m1.json",
    ),
    "KP11": KarrReferenceValue(
        value=None,
        citation="TODO: Karr 2012 Fig 3c replication initiation timing",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        notes="No local machine-readable value found.",
    ),
    "KP12": KarrReferenceValue(
        value=None,
        citation="TODO: Karr 2012 Fig 3c replication duration",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        notes="No local machine-readable value found.",
    ),
    "KP13": KarrReferenceValue(
        value=3869.0,
        citation="parameters.states.Time.cytokinesisDuration",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/parameters.json",
    ),
    "KP14": KarrReferenceValue(
        value=0.5,
        citation="phase_e2_phenotype_scorecard qualitative corr threshold (>0.5)",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
    "KP15": KarrReferenceValue(
        value=True,
        citation="phase_e2_phenotype_scorecard qualitative occupancy check",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
    "KP16": KarrReferenceValue(
        value=2.0,
        citation="phase_e2_phenotype_scorecard DNA content doubling target",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
    "KP17": KarrReferenceValue(
        value=0.1688,
        citation="parameters.states.Mass.dryWeightFractionDNA",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/parameters.json",
    ),
    "KP18": KarrReferenceValue(
        value=0.043482143658563135,
        citation="derived: rna_wt_total_g / cell_dry_total_mass_g",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_native_m1.json",
    ),
    "KP19": KarrReferenceValue(
        value=0.27700176880778027,
        citation="derived: p10b_dry_mass_protein_monomer_g / cell_dry_total_mass_g",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="data/karr_fixtures/karr_phenotype_targets.json",
    ),
    "KP20": KarrReferenceValue(
        value=None,
        citation="TODO: Karr supplement table S5 metabolite profile",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        notes="No local machine-readable S5 table found.",
    ),
    "KP21": KarrReferenceValue(
        value=0.0,
        citation="conservation target: production-use discrepancy near zero",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
    "KP22": KarrReferenceValue(
        value=True,
        citation="E1 pre-fix expectation: energy discrepancy phenotype present",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/phase_e/E1_findings_pre_merge.md",
    ),
    "KP23": KarrReferenceValue(
        value=True,
        citation="phase_e2_phenotype_scorecard qualitative computability gate",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
    "KP24": KarrReferenceValue(
        value=True,
        citation="phase_e2_phenotype_scorecard qualitative distribution-shape gate",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
    "KP25": KarrReferenceValue(
        value=None,
        citation="Deferred: requires KO sweep",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
    ),
    "KP26": KarrReferenceValue(
        value=None,
        citation="Deferred: requires KO sweep",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
    ),
    "KP27": KarrReferenceValue(
        value=True,
        citation="phase_e2_phenotype_scorecard qualitative host adhesion flag",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
    "KP28": KarrReferenceValue(
        value=True,
        citation="phase_e2_phenotype_scorecard qualitative host immune cascade flag",
        sourced_by=_SOURCED_BY,
        sourced_at=_SOURCED_AT,
        source_path="docs/design/phase_e2_phenotype_scorecard.md",
    ),
}


__all__ = ["KARR_REFERENCE_VALUES", "KarrReferenceValue"]
