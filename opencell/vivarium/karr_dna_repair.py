"""Karr DNA repair -- Karr-light port of MATLAB +process/DNARepair.m

SCOPE DECLARATION (non-parity)
==============================

This module is a **deliberate scope reduction** of Karr's MATLAB
`DNARepair.m::evolveState`. It is NOT a faithful per-line port.

Karr-light reductions vs `DNARepair.m::evolveState`:

  1. NHEJ-like aggregation. MATLAB models distinct NER/HR/MMR pathways with
     pathway-specific enzymes and substrates; this module collapses them into
     an aggregate "repair" rate.
  2. No per-substep execution ordering. MATLAB orders binding / nicking / patch
     synthesis / ligation per damage site; this module updates all sites in
     one tick.
  3. Missing pathway coverage. MATLAB includes recA-driven HR initiation,
     mismatch repair MutS/MutL; this module omits these branches.
  4. Substrate accounting depth reduced. MATLAB consumes ATP/dNTPs/cofactors for
     each repair event; this module uses an aggregate ATP debit.

Preserved:
  - High-level damage -> repair throughput rate.
  - Damage site count tracking.

OpenCell additions:
  - Silent guards/floors at lines 172, 207, 215, 400, 402 (axis-C ✗; remove or gate).
  - allocation-port indirection.

Audit: Track-P2 (2026-05-26). Karr-light status: declared.

---

Vivarium Process port of Karr DNARepair with Karr-light pathway aggregation.

Karr-light v1 scope:
- Repair queued damage sites by pathway (BER, NER, HR, NHEJ-like fallback).
- Bound repair throughput by fixture-derived enzyme kinetics.
- Consume ATP + dNTP pools via KarrAllocationStep request/allocation contract.

Deferred to v2:
- Full per-base chromosome state transitions across all DNA damage arrays.
- DisA binding dynamics and restriction/modification mechanics.
- Complete small-molecule stoichiometry beyond ATP + dNTP aggregate budgets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.vivarium.chromosome_views import current_damage_sites

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/DNARepair_flat.mat"

_PATHWAYS = ("ber", "ner", "hr", "nhej_like")

_DAMAGE_TYPE_ALIASES: dict[str, str] = {
    "abasic": "abasic_site",
    "abasicsite": "abasic_site",
    "abasic_site": "abasic_site",
    "ap_site": "abasic_site",
    "damagedbase": "damaged_base",
    "damaged_base": "damaged_base",
    "base_damage": "damaged_base",
    "intrastrandcrosslink": "intrastrand_crosslink",
    "intrastrand_crosslink": "intrastrand_crosslink",
    "crosslink": "intrastrand_crosslink",
    "single_strand_break": "single_strand_break",
    "single_strandbreak": "single_strand_break",
    "strand_break": "single_strand_break",
    "ssb": "single_strand_break",
    "double_strand_break": "double_strand_break",
    "double_strandbreak": "double_strand_break",
    "dsb": "double_strand_break",
}


@dataclass(frozen=True)
class _DamageSite:
    site_id: str
    damage_type: str
    payload: dict[str, Any]


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return 0
        out = out.flat[0]
    return out


def _parse_wid_array(value: object) -> list[str]:
    arr = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in arr.ravel():
        out.append(str(_coerce_scalar(raw)))
    return out


def _parse_index_array(value: object) -> np.ndarray:
    raw = np.asarray(value)
    while raw.dtype == object and raw.size == 1 and isinstance(raw.flat[0], np.ndarray):
        raw = np.asarray(raw.flat[0])
    return np.asarray(raw, dtype=np.int64).reshape(-1)


def _normalize_damage_type(raw: object) -> str:
    key = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    key = key.replace("__", "_")
    return _DAMAGE_TYPE_ALIASES.get(key, key)


def _normalize_dntp_split(raw: object | None) -> np.ndarray:
    if raw is None:
        return np.full(4, 0.25, dtype=np.float64)
    arr = np.asarray(raw, dtype=np.float64).reshape(-1)
    if arr.size != 4:
        raise ValueError(f"dntp_split must have exactly 4 entries, got {arr.size}")
    arr = np.clip(arr, a_min=0.0, a_max=None)
    total = float(np.sum(arr))
    if total <= 0.0:
        return np.full(4, 0.25, dtype=np.float64)
    return arr / total


class KarrDNARepairProcess(Process):
    """Karr DNARepair (light) with pathway-level aggregate repair events."""

    name = "karr_dna_repair"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "pathway_rate_scale": 1.0,
        "ber_patch_length_nt": 1.0,
        "nhej_patch_length_nt": 1.0,
        "dntp_split": (0.25, 0.25, 0.25, 0.25),
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)
        self.reaction_wids = _parse_wid_array(fx.reactionWholeCellModelIDs)

        self.reaction_small_molecule_stoich = np.asarray(
            fx.reactionSmallMoleculeStoichiometryMatrix,
            dtype=np.float64,
        )
        self.reaction_catalysis = np.asarray(fx.reactionCatalysisMatrix, dtype=np.float64)
        self.reaction_ub = np.asarray(fx.enzymeBounds, dtype=np.float64)[:, 1]

        if self.reaction_catalysis.shape[0] != len(self.reaction_wids):
            raise ValueError(
                "DNARepair reactionCatalysis row mismatch: "
                f"{self.reaction_catalysis.shape[0]} vs {len(self.reaction_wids)}"
            )
        if self.reaction_catalysis.shape[1] != len(self.enzyme_wids):
            raise ValueError(
                "DNARepair reactionCatalysis column mismatch: "
                f"{self.reaction_catalysis.shape[1]} vs {len(self.enzyme_wids)}"
            )
        if self.reaction_small_molecule_stoich.shape[0] != len(self.substrate_wids):
            raise ValueError(
                "DNARepair stoichiometry substrate mismatch: "
                f"{self.reaction_small_molecule_stoich.shape[0]} vs {len(self.substrate_wids)}"
            )
        if self.reaction_small_molecule_stoich.shape[1] != len(self.reaction_wids):
            raise ValueError(
                "DNARepair stoichiometry reaction mismatch: "
                f"{self.reaction_small_molecule_stoich.shape[1]} vs {len(self.reaction_wids)}"
            )

        self.enzyme_defaults = {
            wid: float(max(0.0, cnt))
            for wid, cnt in zip(
                self.enzyme_wids,
                np.asarray(fx.enzymes, dtype=np.float64).reshape(-1),
                strict=False,
            )
        }

        self.pathway_reaction_indices: dict[str, np.ndarray] = {
            "ber": _parse_index_array(fx.reactionIndexs_BER) - 1,
            "ner": _parse_index_array(fx.reactionIndexs_NER) - 1,
            "hr": _parse_index_array(fx.reactionIndexs_HR_dsbr) - 1,
            # NHEJ-like fallback uses ligation machinery as an aggregate proxy.
            "nhej_like": _parse_index_array(fx.reactionIndexs_ligation) - 1,
        }
        for pathway, rxn_idx in self.pathway_reaction_indices.items():
            if rxn_idx.size == 0:
                raise ValueError(f"DNARepair pathway {pathway} has no mapped reactions")

        if "ATP" not in self.substrate_wids:
            raise ValueError("DNARepair fixture missing ATP substrate")
        self.atp_wid = "ATP"
        self.atp_index = self.substrate_wids.index(self.atp_wid)

        self.dntp_indices = (_parse_index_array(fx.substrateIndexs_dNTPs) - 1).astype(np.int64)
        if self.dntp_indices.size != 4:
            raise ValueError(f"DNARepair expected 4 dNTP indices, got {self.dntp_indices.size}")
        self.dntp_wids = [self.substrate_wids[int(idx)] for idx in self.dntp_indices]

        expected_dntp_wids = {"DATP", "DCTP", "DGTP", "DTTP"}
        if set(self.dntp_wids) != expected_dntp_wids:
            raise ValueError(
                f"DNARepair dNTP WIDs mismatch: expected {expected_dntp_wids}, got {set(self.dntp_wids)}"
            )

        self.ner_patch_length_nt = float(
            max(
                1.0,
                float(_coerce_scalar(fx.NER_UvrABC_IncisionMargin3))
                + float(_coerce_scalar(fx.NER_UvrABC_IncisionMargin5))
                + 1.0,
            )
        )
        self.hr_patch_length_nt = float(max(1.0, float(_coerce_scalar(fx.HR_PolA_ResectionLength))))
        self.ber_patch_length_nt = float(max(1.0, float(self.parameters["ber_patch_length_nt"])))
        self.nhej_patch_length_nt = float(max(1.0, float(self.parameters["nhej_patch_length_nt"])))

        self.pathway_patch_length_nt = {
            "ber": self.ber_patch_length_nt,
            "ner": self.ner_patch_length_nt,
            "hr": self.hr_patch_length_nt,
            "nhej_like": self.nhej_patch_length_nt,
        }
        self.dntp_split = _normalize_dntp_split(self.parameters.get("dntp_split"))

        self.pathway_atp_cost = {
            pathway: self._pathway_atp_cost(pathway) for pathway in _PATHWAYS
        }
        self.tracked_substrates = [self.atp_wid, *self.dntp_wids]
        self.pathway_per_event_substrate_cost = {
            pathway: self._per_event_substrate_cost(pathway) for pathway in _PATHWAYS
        }

    def ports_schema(self) -> dict[str, Any]:
        return {
            "chromosome": {
                "damage_events_cumulative": {"_default": [], "_updater": "accumulate", "_emit": True},
                "repair_events_cumulative": {"_default": [], "_updater": "accumulate", "_emit": True},
                "repair_count": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                "repair_count_by_pathway": {
                    pathway: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for pathway in _PATHWAYS
                },
            },
            "protein": {
                "counts": {
                    wid: {"_default": self.enzyme_defaults.get(wid, 0.0), "_updater": "accumulate"}
                    for wid in self.enzyme_wids
                }
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.tracked_substrates
            },
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self.tracked_substrates
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False}
                    for wid in self.tracked_substrates
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        damage_sites = self._canonical_damage_sites(current_damage_sites(states))

        enzyme_counts = self._enzyme_counts(states)
        desired_repairs, indices_by_pathway = self._desired_repairs(
            damage_sites=damage_sites,
            enzyme_counts=enzyme_counts,
            dt=dt,
        )
        requests = self._substrate_needs_for_repairs(desired_repairs)

        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        substrates = states.get("substrates", {})
        available = {
            wid: self._allocated_or_state(allocated, substrates, wid) for wid in self.tracked_substrates
        }
        actual_repairs = self._bounded_repairs(desired_repairs=desired_repairs, available=available)

        substrate_consumption = self._substrate_needs_for_repairs(actual_repairs)
        consumed_total = int(sum(actual_repairs.values()))

        update: dict[str, Any] = {
            "requests": {self.name: {wid: float(requests[wid]) for wid in self.tracked_substrates}}
        }

        if any(val > 0.0 for val in substrate_consumption.values()):
            update["substrates"] = {
                wid: -float(substrate_consumption[wid])
                for wid in self.tracked_substrates
                if substrate_consumption[wid] > 0.0
            }

        if consumed_total > 0:
            repaired_indices = self._sample_repaired_indices(indices_by_pathway, actual_repairs)
            repair_events = [
                self._repair_event_from_site(damage_sites[idx].payload)
                for idx in sorted(repaired_indices)
            ]
            update["chromosome"] = {
                "repair_events_cumulative": repair_events,
                "repair_count": float(consumed_total),
                "repair_count_by_pathway": {
                    pathway: float(actual_repairs[pathway])
                    for pathway in _PATHWAYS
                    if actual_repairs[pathway] > 0
                },
            }

        return update

    def _canonical_damage_sites(self, raw: object) -> list[_DamageSite]:
        normalized: list[_DamageSite] = []
        if raw is None:
            return normalized

        records: list[object] = []
        if isinstance(raw, dict):
            if "sites" in raw and isinstance(raw["sites"], (list, tuple)):
                records.extend(list(raw["sites"]))
            else:
                for site_id, payload in raw.items():
                    if isinstance(payload, dict):
                        rec = dict(payload)
                        rec.setdefault("site_id", site_id)
                    else:
                        rec = {"site_id": site_id, "damage_type": payload}
                    records.append(rec)
        elif isinstance(raw, (list, tuple)):
            records.extend(list(raw))
        else:
            records.append(raw)

        for idx, rec in enumerate(records):
            payload: dict[str, Any]
            if isinstance(rec, dict):
                payload = dict(rec)
                damage_raw = payload.get("damage_type", payload.get("type", payload.get("kind", "unknown")))
                site_raw = payload.get("site_id", payload.get("id", None))
            elif isinstance(rec, (tuple, list)):
                if len(rec) >= 2:
                    payload = {"position": rec[0], "damage_type": rec[1]}
                elif len(rec) == 1:
                    payload = {"damage_type": rec[0]}
                else:
                    payload = {"damage_type": "unknown"}
                damage_raw = payload["damage_type"]
                site_raw = payload.get("site_id")
            else:
                payload = {"damage_type": rec}
                damage_raw = rec
                site_raw = None

            damage_type = _normalize_damage_type(damage_raw)
            if site_raw is None:
                if "position" in payload:
                    site_id = f"{damage_type}@{payload['position']}"
                else:
                    site_id = f"{damage_type}#{idx:05d}"
            else:
                site_id = str(site_raw)
            payload["damage_type"] = damage_type
            payload["site_id"] = site_id
            payload.setdefault("id", site_id)
            normalized.append(_DamageSite(site_id=site_id, damage_type=damage_type, payload=payload))
        return normalized

    def _repair_event_from_site(self, site: dict[str, Any]) -> dict[str, Any]:
        site_id = str(site.get("id", site.get("site_id", "")))
        if not site_id:
            damage_type = str(site.get("damage_type", site.get("kind", "unknown")))
            if "position" in site:
                site_id = f"{damage_type}@{site['position']}"
            else:
                site_id = damage_type
        event = {
            "id": site_id,
            "site_id": site_id,
            "damage_type": str(site.get("damage_type", site.get("kind", "unknown"))),
        }
        if "position" in site:
            event["position"] = site["position"]
        return event

    def _enzyme_counts(self, states: dict[str, Any]) -> dict[str, float]:
        protein_counts = states.get("protein", {}).get("counts", {})
        out: dict[str, float] = {}
        for wid in self.enzyme_wids:
            if wid in protein_counts:
                out[wid] = float(max(0.0, protein_counts.get(wid, 0.0)))
            else:
                out[wid] = float(max(0.0, self.enzyme_defaults.get(wid, 0.0)))
        return out

    def _pathway_for_damage_type(self, damage_type: str) -> str:
        if damage_type in {"abasic_site", "damaged_base"}:
            return "ber"
        if damage_type in {"intrastrand_crosslink"}:
            return "ner"
        if damage_type in {"double_strand_break"}:
            return "hr"
        if damage_type in {"single_strand_break"}:
            return "nhej_like"
        return "nhej_like"

    def _pathway_capacity_per_s(self, pathway: str, enzyme_counts: dict[str, float]) -> float:
        rxn_indices = self.pathway_reaction_indices[pathway]
        capacities: list[float] = []
        for rxn_idx in rxn_indices:
            ub = float(self.reaction_ub[int(rxn_idx)])
            if not math.isfinite(ub) or ub <= 0.0:
                continue

            catalyst_col = self.reaction_catalysis[int(rxn_idx), :]
            catalyst_indices = np.flatnonzero(np.abs(catalyst_col) > 0.0)
            if catalyst_indices.size <= 0:
                continue

            enzyme_total = 0.0
            for enz_idx in catalyst_indices:
                enz_wid = self.enzyme_wids[int(enz_idx)]
                stoich = abs(float(catalyst_col[int(enz_idx)]))
                enzyme_total += float(max(0.0, enzyme_counts.get(enz_wid, 0.0))) / max(stoich, 1.0)
            if enzyme_total <= 0.0:
                continue
            capacities.append(ub * enzyme_total)

        if not capacities:
            return 0.0
        return float(min(capacities) * float(self.parameters["pathway_rate_scale"]))

    def _desired_repairs(
        self,
        damage_sites: list[_DamageSite],
        enzyme_counts: dict[str, float],
        dt: float,
    ) -> tuple[dict[str, int], dict[str, list[int]]]:
        indices_by_pathway = {pathway: [] for pathway in _PATHWAYS}
        for idx, site in enumerate(damage_sites):
            indices_by_pathway[self._pathway_for_damage_type(site.damage_type)].append(idx)

        desired: dict[str, int] = {pathway: 0 for pathway in _PATHWAYS}
        for pathway in _PATHWAYS:
            lesion_count = len(indices_by_pathway[pathway])
            if lesion_count <= 0:
                continue
            capacity_per_s = self._pathway_capacity_per_s(pathway, enzyme_counts)
            expected = max(0.0, capacity_per_s * float(dt) * float(lesion_count))
            n = int(self._rng.poisson(expected))
            desired[pathway] = int(min(max(0, n), lesion_count))
        return desired, indices_by_pathway

    def _pathway_atp_cost(self, pathway: str) -> float:
        rxn_indices = self.pathway_reaction_indices[pathway]
        atp_row = self.reaction_small_molecule_stoich[self.atp_index, rxn_indices]
        return float(np.sum(np.clip(-atp_row, a_min=0.0, a_max=None)))

    def _per_event_substrate_cost(self, pathway: str) -> dict[str, float]:
        out = {wid: 0.0 for wid in self.tracked_substrates}
        out[self.atp_wid] = float(self.pathway_atp_cost[pathway])

        dntp_total = float(self.pathway_patch_length_nt[pathway])
        for idx, wid in enumerate(self.dntp_wids):
            out[wid] = float(dntp_total * self.dntp_split[idx])
        return out

    def _substrate_needs_for_repairs(self, repairs_by_pathway: dict[str, int]) -> dict[str, float]:
        needs = {wid: 0.0 for wid in self.tracked_substrates}
        for pathway, n in repairs_by_pathway.items():
            if n <= 0:
                continue
            per_event = self.pathway_per_event_substrate_cost[pathway]
            for wid in self.tracked_substrates:
                needs[wid] += float(n) * float(per_event[wid])
        return needs

    def _bounded_repairs(
        self,
        desired_repairs: dict[str, int],
        available: dict[str, float],
    ) -> dict[str, int]:
        if all(n <= 0 for n in desired_repairs.values()):
            return {pathway: 0 for pathway in _PATHWAYS}

        desired_need = self._substrate_needs_for_repairs(desired_repairs)
        scale = 1.0
        for wid, need in desired_need.items():
            if need <= 0.0:
                continue
            have = max(0.0, float(available.get(wid, 0.0)))
            scale = min(scale, have / need)

        actual = {
            pathway: int(max(0, math.floor(float(n) * scale))) for pathway, n in desired_repairs.items()
        }

        consumed = self._substrate_needs_for_repairs(actual)
        remaining = {
            wid: max(0.0, float(available.get(wid, 0.0)) - float(consumed.get(wid, 0.0)))
            for wid in self.tracked_substrates
        }

        progressed = True
        while progressed:
            progressed = False
            for pathway in sorted(_PATHWAYS, key=lambda name: desired_repairs[name], reverse=True):
                if actual[pathway] >= desired_repairs[pathway]:
                    continue
                per_event = self.pathway_per_event_substrate_cost[pathway]
                feasible = all(remaining[wid] + 1e-12 >= per_event[wid] for wid in self.tracked_substrates)
                if not feasible:
                    continue
                actual[pathway] += 1
                for wid in self.tracked_substrates:
                    remaining[wid] = max(0.0, remaining[wid] - per_event[wid])
                progressed = True
        return actual

    def _sample_repaired_indices(
        self,
        indices_by_pathway: dict[str, list[int]],
        repairs_by_pathway: dict[str, int],
    ) -> set[int]:
        repaired: set[int] = set()
        for pathway in _PATHWAYS:
            n = repairs_by_pathway[pathway]
            if n <= 0:
                continue
            candidates = np.asarray(indices_by_pathway[pathway], dtype=np.int64)
            if candidates.size <= 0:
                continue
            n = min(int(n), int(candidates.size))
            chosen = self._rng.choice(candidates, size=n, replace=False)
            repaired.update(int(idx) for idx in np.asarray(chosen, dtype=np.int64).reshape(-1))
        return repaired

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        substrate_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)


__all__ = ["KarrDNARepairProcess"]
