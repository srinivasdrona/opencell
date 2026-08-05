"""Shared helpers for the DNADamage synthetic-mechanism stress profile.

Factored out of ``test_dna_damage_stress_preregistration.py`` so the
mechanism-fidelity canary (``dna_damage_mechanism_canary.py``) can re-derive
the exact same fixture-sourced numbers the preregistration test already
verifies against ``DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json`` -- one source of
truth for "what does the Karr fixture actually say", never two independent
re-derivations that could silently drift apart.

Primary source: ``DNADamage.m::calcExpectedReactionRates`` (rate formula) +
``data/karr_fixtures/per_process/DNADamage_flat.mat`` (per-reaction bounds,
radiation gating, vulnerable-motif composition). See
``docs/phase_f/l2_2_design_a/stress/DNADAMAGE_STRESS_PROFILE_PROPOSAL.md``
for the full non-biological/non-gating disclosure this profile carries.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "stress"
    / "DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json"
)
FIXTURE_PATH = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "DNADamage_flat.mat"


def scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return ""
        out = out.flat[0]
    return out


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def fixture_details() -> dict:
    """Re-derive, straight from the tracked fixture, everything the frozen
    spec's numbers are supposed to match: per-reaction radiation-gated rates
    (``calcExpectedReactionRates`` with the radiation multiplier held at
    exactly 1.0 unit, i.e. the *per-unit* rate a dose gets multiplied into),
    the reaction ids and Karr ``damage_types`` (chromosome field) each
    radiation-gated reaction writes into, and the fixture's declared ploidy.
    """
    fixture = loadmat(FIXTURE_PATH, squeeze_me=True, struct_as_record=False)["data"].fixture
    substrate_wids = [
        str(scalar(value))
        for value in np.asarray(fixture.substrateWholeCellModelIDs, dtype=object).ravel()
    ]
    bounds = np.asarray(fixture.reactionBounds, dtype=np.float64)
    radiation = np.asarray(fixture.reactionRadiation, dtype=np.int64).reshape(-1)
    motifs = np.asarray(fixture.reactionVulnerableMotifs, dtype=object).ravel()
    reaction_ids = [
        str(scalar(value))
        for value in np.asarray(fixture.reactionWholeCellModelIDs, dtype=object).ravel()
    ]
    damage_types = [
        str(scalar(value))
        for value in np.asarray(fixture.reactionDamageTypes, dtype=object).ravel()
    ]

    sequence_len = None
    gc_content = None
    ploidy = None
    for state in np.asarray(fixture.states, dtype=object).ravel():
        if str(getattr(state, "x_class_", "")).endswith("Chromosome"):
            sequence_len = int(state.sequenceLen)
            gc_content = float(state.sequenceGCContent)
            ploidy = float(state.ploidy)
            break
    assert sequence_len is not None and gc_content is not None and ploidy is not None
    assert ploidy == 1.0

    polymerized_nt = 2.0 * sequence_len * ploidy
    composition = {
        "A": (1.0 - gc_content) / 2.0,
        "C": gc_content / 2.0,
        "G": gc_content / 2.0,
        "T": (1.0 - gc_content) / 2.0,
    }
    vulnerable = np.zeros(bounds.shape[0], dtype=np.float64)
    for index, motif in enumerate(motifs):
        motif = scalar(motif)
        if not isinstance(motif, str) or not motif:
            continue
        vulnerable[index] = polymerized_nt * float(np.prod([composition[base] for base in motif]))
    per_unit_rates = vulnerable * bounds[:, 1]

    result: dict[str, dict] = {}
    for wid in ("UVB_radiation", "gamma_radiation"):
        local_index_1b = substrate_wids.index(wid) + 1
        mask = radiation == local_index_1b
        indices = np.flatnonzero(mask)
        result[wid] = {
            "count": int(mask.sum()),
            "sum_rate": float(per_unit_rates[mask].sum()),
            "per_unit_rates": per_unit_rates[mask],
            "reaction_ids": [reaction_ids[index] for index in indices],
            "damage_types": [damage_types[index] for index in indices],
        }
    return {"ploidy": ploidy, "radiation": result}


def per_field_expected_counts(condition_name: str, *, n_seeds: int, m_ticks: int) -> dict[str, float]:
    """Expected pooled damage-site count per Karr chromosome field for
    ``condition_name`` (``"uvb_mechanism"`` or ``"gamma_mechanism"``), at the
    frozen spec's ``injected_radiation_value`` dose, scaled to an
    ``n_seeds`` x ``m_ticks`` window. Splits the condition's single pooled
    expectation (``target_expected_pooled_site_events``, uniform across the
    frozen 50x20 design) proportionally by each radiation-gated reaction's
    own per-unit rate share within its Karr-declared ``damage_types`` field --
    i.e. re-derives the same per-reaction rate array
    ``test_dna_damage_stress_preregistration.py`` already verifies, then
    aggregates by field instead of by reaction id.
    """
    spec = load_spec()
    condition = spec["conditions"][condition_name]
    details = fixture_details()["radiation"][condition["radiation_wid"]]
    dose = float(condition["injected_radiation_value"])
    per_reaction_expected = details["per_unit_rates"] * dose * float(m_ticks) * float(n_seeds)
    out: dict[str, float] = {}
    for field, expected in zip(details["damage_types"], per_reaction_expected.tolist(), strict=True):
        out[field] = out.get(field, 0.0) + float(expected)
    return out
