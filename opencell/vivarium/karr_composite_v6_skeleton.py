"""Skeleton builder for the 28-process Karr chassis_v6.

Design-only placeholder.

The real implementation is intentionally deferred until:
  - `pc-final` lands `build_karr_chassis_v5` (27-process baseline)
  - `pd-t1` lands `HostInteraction`
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vivarium.core.engine import Engine


CHASSIS_V6_EXPECTED_PROCESS_KEYS: tuple[str, ...] = (
    "karr_m1",
    "karr_replication_initiation",
    "karr_replication",
    "karr_dna_damage",
    "karr_dna_repair",
    "karr_dna_supercoiling",
    "karr_chromosome_condensation",
    "karr_chromosome_segregation",
    "karr_transcription_v3",
    "karr_transcriptional_regulation",
    "karr_rna_processing",
    "karr_rna_modification",
    "karr_rna_decay",
    "karr_trna_aminoacylation",
    "karr_translation_v3",
    "karr_protein_processing_i",
    "karr_protein_processing_ii",
    "karr_protein_modification",
    "karr_protein_folding",
    "karr_protein_activation",
    "karr_protein_decay_light",
    "karr_protein_translocation",
    "karr_d2_real",
    "karr_ribosome_assembly",
    "karr_ftsz_polymerization",
    "karr_cytokinesis",
    "karr_terminal_organelle_assembly",
    "karr_host_interaction",
)


def build_karr_chassis_v6(
    *,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
    dynamic_bounds: bool = False,
    enable_pool_replenishment: bool = False,
    host_adhesion_gates_division: bool = False,
    extra_options: dict[str, Any] | None = None,
) -> "Engine":
    """Build the complete 28-process Karr chassis (skeleton only).

    Design notes:
    - v6 = v5 + HostInteraction (`karr_host_interaction`)
    - HostInteraction reads terminal-organelle + protein state and writes host flags.
    - CellCycleCoordinator host-adhesion gating is optional and OFF by default.
    - Validation emit contract should include scorecard observables used by
      `opencell/validation/karr_trajectory.py` and `trajectory_compare.py`.
    """
    raise NotImplementedError(
        "Skeleton only: waits on pc-final chassis_v5 and pd-t1 HostInteraction implementation."
    )


__all__ = [
    "CHASSIS_V6_EXPECTED_PROCESS_KEYS",
    "build_karr_chassis_v6",
]
