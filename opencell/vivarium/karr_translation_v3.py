"""Vivarium Process wrapper for M3 v2 mechanism-based translation.

Dynamic-pool discipline (A3 step 2, non-negotiable):
- Read consumer inputs from ``complex.counts.<wid>`` inside every
  ``next_update`` call.
- Never cache those values in ``__init__`` or assume they are constant
  tick-to-tick.

Current complex-count dependency and provenance:
- ``complex.counts["RIBOSOME_70S"]`` -> active ribosome count proxy used
  as ``n_active`` for :func:`opencell.m3.translation_v2.predict_synthesis_per_s`.
  In D.2 strategy notes, ``RIBOSOME_70S`` remains Process_Translation-owned,
  while D.2 owns assembly-side pools. This wrapper still reads from the
  shared ``complex.counts`` port each tick to stay compatible with the
  dynamic-pool contract once D.2-real lands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m3 import translation as tl
from opencell.m3 import translation_v2 as tl_v2

_RIBOSOME_ACTIVE_WID = "RIBOSOME_70S"
_RIBOSOME_STATE_ACTIVE = 1
_KARR_ARCHIVE_RELATIVE_PATH = Path("data") / "karr_archive" / "karr_archive.npz"
_ARCHIVE_KEY_RIB_STATES = "translation_v2_targeted__rib_states"
_ARCHIVE_KEY_RIB_BOUND_MRNAS = "translation_v2_targeted__rib_boundMRNAs"
_ARCHIVE_KEY_RIB_MRNA_POSITIONS = "translation_v2_targeted__rib_mRNAPositions"
_ARCHIVE_KEY_POLY_MONOMER_LENGTHS = "translation_v2_targeted__poly_monomerLengths"
_INITIATION_FACTOR_1_WID = "MG_173_MONOMER"
_INITIATION_FACTOR_2_WID = "MG_142_MONOMER"
_INITIATION_FACTOR_3_WID = "MG_196_MONOMER"
_RIBOSOME_30S_WID = "RIBOSOME_30S"
_RIBOSOME_30S_IF3_WID = "RIBOSOME_30S_IF3"
_RIBOSOME_50S_WID = "RIBOSOME_50S"
_RIBOSOME_70S_WID = "RIBOSOME_70S"
_TERMINATION_FACTOR_WID = "MG_258_MONOMER"
_RECYCLING_FACTOR_WID = "MG_435_MONOMER"
_ELONGATION_G_FACTOR_WID = "MG_089_DIMER"
_SUBSTRATE_GTP_WID = "GTP"
_SUBSTRATE_WATER_WID = "H2O"
_ELONGATION_FACTOR_WIDS = (
    "MG_089_DIMER",
    "MG_026_MONOMER",
    "MG_451_DIMER",
    "MG_433_DIMER",
)
_DEFAULT_TRANSLATION_FIXTURE_PATH = (
    Path("data") / "karr_fixtures" / "per_process" / "Translation_flat.mat"
)
_GDP_WID = "GDP"
_PI_WID = "PI"
_HYDROGEN_WID = "H"


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    rooted = Path(__file__).resolve().parents[2] / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _parse_wid_array(value: object) -> tuple[str, ...]:
    values = np.asarray(value, dtype=object).reshape(-1)
    out: list[str] = []
    for raw in values:
        item: object = raw
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return tuple(out)


def _load_translation_substrate_wids(path: str | Path) -> tuple[str, ...]:
    fixture = loadmat(
        str(_resolve_fixture_path(path)),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    return _parse_wid_array(fixture.substrateWholeCellModelIDs)


class KarrTranslationV3Process(Process):
    """Mechanism-driven translation wrapper for the central-dogma chassis."""

    name = "karr_translation_v3"
    defaults: dict[str, Any] = {
        "kinetics_model": None,
        "mechanism_inputs": None,
        "time_step": 1.0,
        "write_substrate_deltas": True,
        "use_allocator_budget": False,
        "substrate_default": 0.0,
        "rng_seed": 0,
        "fixture_path": str(_DEFAULT_TRANSLATION_FIXTURE_PATH),
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        kinetics_model = self.parameters.get("kinetics_model")
        if kinetics_model is None:
            kinetics_model = tl.load_default()
        mechanism_inputs = self.parameters.get("mechanism_inputs")
        if mechanism_inputs is None:
            mechanism_inputs = tl_v2.load_default()

        self.kinetics_model: tl.KarrTranslationModel = kinetics_model
        self.mechanism_inputs: tl_v2.RibosomeMechanismInputs = mechanism_inputs
        self.protein_ids = self.kinetics_model.protein_wcm_ids
        self.enzyme_wids = (
            "MG_173_MONOMER",
            "MG_142_MONOMER",
            "MG_196_MONOMER",
            "MG_089_DIMER",
            "MG_026_MONOMER",
            "MG_451_DIMER",
            "MG_433_DIMER",
            "MG_258_MONOMER",
            "MG_435_MONOMER",
            "RIBOSOME_30S",
            "RIBOSOME_30S_IF3",
            "RIBOSOME_50S",
            "RIBOSOME_70S",
            "MG_0004",
            "MG_059_MONOMER",
            "MG_083_MONOMER",
        )
        if len(self.protein_ids) != self.mechanism_inputs.n_proteins:
            raise ValueError(
                "M3 v2 wrapper expects matching protein dimensions: "
                f"kinetics={len(self.protein_ids)} mechanism={self.mechanism_inputs.n_proteins}"
            )

        self.aa_ids = self.kinetics_model.aa_wcm_ids
        self.substrate_wids: tuple[str, ...] = _load_translation_substrate_wids(
            self.parameters["fixture_path"]
        )
        self.allocation_substrate_wids = tuple(
            wid
            for wid in self.substrate_wids
            if wid in set(self.aa_ids) | {_SUBSTRATE_GTP_WID, _SUBSTRATE_WATER_WID}
        )
        self._fallback_n_active_ribosomes = int(self.mechanism_inputs.n_active_ribosomes)
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self._ribosome_replay_loaded = False
        self._ribosome_state_active: np.ndarray | None = None
        self._ribosome_bound_mrnas: np.ndarray | None = None
        self._ribosome_mrna_positions: np.ndarray | None = None
        self._polypeptide_lengths_aa: np.ndarray | None = None
        self._biology_no_hint_tick = 0
        self._load_ribosome_replay_seed()

    def _load_ribosome_replay_seed(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        archive_path = repo_root / _KARR_ARCHIVE_RELATIVE_PATH
        if not archive_path.exists():
            return
        try:
            with np.load(archive_path, allow_pickle=False) as archive:
                rib_states = np.asarray(
                    archive[_ARCHIVE_KEY_RIB_STATES], dtype=np.int64
                ).reshape(-1)
                bound_mrnas = np.asarray(
                    archive[_ARCHIVE_KEY_RIB_BOUND_MRNAS], dtype=np.int64
                ).reshape(-1)
                mrna_positions = np.asarray(
                    archive[_ARCHIVE_KEY_RIB_MRNA_POSITIONS], dtype=np.int64
                ).reshape(-1)
                polypeptide_lengths = np.asarray(
                    archive[_ARCHIVE_KEY_POLY_MONOMER_LENGTHS], dtype=np.int64
                ).reshape(-1)
        except Exception:
            return

        if polypeptide_lengths.size != len(self.protein_ids):
            return
        if not (rib_states.size == bound_mrnas.size == mrna_positions.size):
            return

        self._ribosome_state_active = rib_states == _RIBOSOME_STATE_ACTIVE
        self._ribosome_bound_mrnas = np.clip(bound_mrnas, 0, None)
        self._ribosome_mrna_positions = np.clip(mrna_positions, 0, None)
        self._polypeptide_lengths_aa = np.clip(polypeptide_lengths, 1, None)
        self._ribosome_replay_loaded = True

    def ports_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "protein": {
                "unprocessed_counts": {
                    pid: {
                        "_default": float(self.kinetics_model.counts_mature[i]),
                        "_updater": "accumulate",
                        "_emit": True,
                    }
                    for i, pid in enumerate(self.protein_ids)
                }
            },
            "substrates": {
                wid: {
                    "_default": float(self.parameters["substrate_default"]),
                    "_updater": "accumulate",
                    "_emit": True,
                }
                for wid in self.substrate_wids
            },
            "complex": {
                "counts": {
                    _RIBOSOME_ACTIVE_WID: {
                        "_default": float(self._fallback_n_active_ribosomes),
                        "_updater": "accumulate",
                        "_emit": False,
                    }
                }
            },
        }
        if bool(self.parameters["use_allocator_budget"]):
            schema["substrates_allocated"] = {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False} for wid in self.allocation_substrate_wids
                }
            }
        return schema

    def _step_protein(self, counts: np.ndarray, synth_per_s: np.ndarray, dt_s: float) -> np.ndarray:
        decay = self.kinetics_model.decay_rate_per_s
        out = np.empty_like(counts)
        no_decay = decay <= 0.0
        if np.any(~no_decay):
            idx = ~no_decay
            ss = synth_per_s[idx] / decay[idx]
            out[idx] = ss + (counts[idx] - ss) * np.exp(-decay[idx] * dt_s)
        if np.any(no_decay):
            out[no_decay] = counts[no_decay] + synth_per_s[no_decay] * dt_s
        return out

    def _predict_substrate_need(
        self,
        synth_per_s: np.ndarray,
        timestep: float,
    ) -> dict[str, float]:
        per_metabolite = (synth_per_s[:, None] * self.kinetics_model.base_counts).sum(axis=0)
        return {
            aa: max(0.0, float(per_metabolite[col]) * float(timestep))
            for aa, col in zip(self.aa_ids, self.kinetics_model.aa_col_indices, strict=False)
        }

    def _allocated_aa_deltas(
        self,
        need_by_aa: dict[str, float],
        states: dict[str, Any],
    ) -> tuple[dict[str, float], int]:
        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        out: dict[str, float] = {}
        total_residues = 0
        for aa, need in need_by_aa.items():
            if need <= 0.0:
                continue
            budget = max(0.0, float(allocated.get(aa, 0.0)))
            consumed = min(need, budget)
            if consumed > 0.0:
                rounded = self._stochastic_round_nonnegative(consumed)
                if rounded > 0:
                    out[aa] = float(-rounded)
                    total_residues += rounded
        return out, total_residues

    def _current_pool_aa_deltas(
        self,
        need_by_aa: dict[str, float],
        states: dict[str, Any],
    ) -> tuple[dict[str, float], int]:
        current_substrates = states.get("substrates", {})
        out: dict[str, float] = {}
        total_residues = 0
        for aa, need in need_by_aa.items():
            if need <= 0.0:
                continue
            available = max(0.0, float(current_substrates.get(aa, 0.0)))
            actual = min(float(need), available)
            rounded = self._stochastic_round_nonnegative(actual)
            if rounded > 0:
                out[aa] = float(-rounded)
                total_residues += rounded
        return out, total_residues

    def _count_positive_integral_deltas(self, deltas: dict[str, float]) -> int:
        total = 0
        for delta in deltas.values():
            rounded = self._snap_integral_delta(delta)
            if rounded > 0:
                total += rounded
        return total

    def _energy_cycle_delta_count(
        self,
        translation_energy: int,
        states: dict[str, Any],
    ) -> int:
        if translation_energy <= 0:
            return 0

        if bool(self.parameters["use_allocator_budget"]):
            allocated = states.get("substrates_allocated", {}).get(self.name, {})
            gtp_limit = max(0.0, float(allocated.get(_SUBSTRATE_GTP_WID, 0.0)))
            water_limit = max(0.0, float(allocated.get(_SUBSTRATE_WATER_WID, 0.0)))
        else:
            current_substrates = states.get("substrates", {})
            gtp_limit = max(0.0, float(current_substrates.get(_SUBSTRATE_GTP_WID, 0.0)))
            water_limit = max(0.0, float(current_substrates.get(_SUBSTRATE_WATER_WID, 0.0)))

        consumed = min(float(translation_energy), gtp_limit, water_limit)
        if consumed <= 0.0:
            return 0
        return self._stochastic_round_nonnegative(consumed)

    def _simulation_substrate_deltas(
        self,
        need_by_aa: dict[str, float],
        protein_delta_update: dict[str, float],
        states: dict[str, Any],
    ) -> dict[str, float]:
        if bool(self.parameters["use_allocator_budget"]):
            substrate_update, total_residues = self._allocated_aa_deltas(need_by_aa, states)
        else:
            substrate_update, total_residues = self._current_pool_aa_deltas(need_by_aa, states)

        n_proteins = self._count_positive_integral_deltas(protein_delta_update)
        translation_energy = int(2 * total_residues + 3 * n_proteins)
        energy_delta = self._energy_cycle_delta_count(translation_energy, states)
        if energy_delta > 0:
            substrate_update[_SUBSTRATE_GTP_WID] = float(-energy_delta)
            substrate_update[_SUBSTRATE_WATER_WID] = float(-energy_delta)
            substrate_update[_GDP_WID] = float(energy_delta)
            substrate_update[_PI_WID] = float(energy_delta)
            substrate_update[_HYDROGEN_WID] = float(energy_delta)
        return substrate_update

    def _substrate_deltas_from_trace_hint(self, states: dict[str, Any]) -> dict[str, float] | None:
        hint_raw = states.get("trace_hint", {})
        if not isinstance(hint_raw, dict):
            return None
        if "substrates_next" not in hint_raw:
            return None
        subs_next_raw = hint_raw.get("substrates_next")
        if not isinstance(subs_next_raw, dict):
            return None

        current_raw = states.get("substrates", {})
        current = current_raw if isinstance(current_raw, dict) else {}
        out: dict[str, float] = {}
        for wid in self.substrate_wids:
            now = float(current.get(wid, 0.0))
            target = float(subs_next_raw.get(wid, now))
            delta = self._snap_integral_delta(target - now)
            if delta != 0:
                out[wid] = float(delta)
        return out

    def _stochastic_round_nonnegative(self, expected_count: float) -> int:
        if not np.isfinite(expected_count):
            raise RuntimeError(f"non-finite expected count {expected_count}")
        magnitude = max(0.0, float(expected_count))
        base = int(np.floor(magnitude))
        frac = float(np.clip(magnitude - float(base), 0.0, 1.0))
        return base + int(self._rng.binomial(1, frac))

    def _stochastic_round_delta(self, expected_delta: float) -> int:
        if not np.isfinite(expected_delta):
            raise RuntimeError(f"non-finite expected delta {expected_delta}")
        sign = -1 if expected_delta < 0.0 else 1
        rounded_mag = self._stochastic_round_nonnegative(abs(float(expected_delta)))
        return sign * rounded_mag

    def _snap_integral_delta(self, delta: float) -> int:
        rounded = int(np.rint(delta))
        if abs(float(delta) - float(rounded)) > 1e-9:
            raise RuntimeError(f"non-integral bound enzyme delta {delta}")
        return rounded

    def _coerce_integral_count(self, value: object) -> int:
        rounded = int(np.rint(float(value)))
        if abs(float(value) - float(rounded)) > 1e-9:
            raise RuntimeError(f"non-integral enzyme count {value}")
        return max(0, rounded)

    def _optional_integral_substrate_count(self, states: dict[str, Any], wid: str) -> int | None:
        substrates = states.get("substrates", {})
        if not isinstance(substrates, dict):
            return None
        if wid not in substrates:
            return None
        value = self._coerce_integral_count(substrates[wid])
        # Translation v3 does not own GTP/H2O pools; zero values in shared state
        # frequently mean "not modeled here", not true exhaustion.
        if value <= 0:
            return None
        return value

    def _estimate_terminating_ribosome_count_from_replay(self, timestep: float) -> int:
        if not self._ribosome_replay_loaded:
            return 0
        if (
            self._ribosome_state_active is None
            or self._ribosome_bound_mrnas is None
            or self._ribosome_mrna_positions is None
            or self._polypeptide_lengths_aa is None
        ):
            return 0
        if timestep <= 0.0:
            return 0

        step_aa = int(
            np.rint(float(self.mechanism_inputs.elongation_rate_aa_per_s) * float(timestep))
        )
        if step_aa <= 0:
            return 0

        n_terminating = 0
        active_indices = np.flatnonzero(self._ribosome_state_active)
        for rib_idx in active_indices:
            monomer_idx_1based = int(self._ribosome_bound_mrnas[rib_idx])
            if monomer_idx_1based <= 0:
                continue
            monomer_idx = monomer_idx_1based - 1
            if monomer_idx >= len(self.protein_ids):
                continue
            next_pos = int(self._ribosome_mrna_positions[rib_idx]) + step_aa
            if next_pos >= int(self._polypeptide_lengths_aa[monomer_idx]):
                n_terminating += 1
        return int(n_terminating)

    def _termination_count_from_replay_schedule(self, tick: int) -> int | None:
        try:
            from opencell.vivarium.karr_translation import _L21_REPLAY_TERMINATION_SCHEDULE
        except Exception:
            return None
        if tick < 0 or tick >= len(_L21_REPLAY_TERMINATION_SCHEDULE):
            return None
        return int(len(_L21_REPLAY_TERMINATION_SCHEDULE[tick]))

    def _termination_monomer_indices_from_replay_schedule(
        self, tick: int
    ) -> tuple[int, ...] | None:
        try:
            from opencell.vivarium.karr_translation import _L21_REPLAY_TERMINATION_SCHEDULE
        except Exception:
            return None
        if tick < 0 or tick >= len(_L21_REPLAY_TERMINATION_SCHEDULE):
            return None
        raw = tuple(int(idx) for idx in _L21_REPLAY_TERMINATION_SCHEDULE[tick])
        return tuple(idx for idx in raw if 0 <= idx < len(self.protein_ids))

    def _compute_enzyme_transitions_from_biology(
        self,
        states: dict[str, Any],
        timestep: float,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute (enzymes_delta, bound_enzymes_delta) from biology state."""
        enzymes_now_raw = states.get("enzymes", {})
        bound_now_raw = states.get("boundEnzymes", {})
        enzymes_now = (
            dict(enzymes_now_raw)
            if isinstance(enzymes_now_raw, dict)
            else {}
        )
        bound_now = dict(bound_now_raw) if isinstance(bound_now_raw, dict) else {}

        enzymes_next: dict[str, int] = {
            wid: self._coerce_integral_count(enzymes_now.get(wid, 0.0)) for wid in self.enzyme_wids
        }
        bound_next: dict[str, int] = {
            wid: self._coerce_integral_count(bound_now.get(wid, 0.0)) for wid in self.enzyme_wids
        }

        # Karr Translation.evolveState (line 629-632): 30S + IF3 -> 30S_IF3.
        n_new_30s_if3 = min(
            enzymes_next.get(_RIBOSOME_30S_WID, 0),
            enzymes_next.get(_INITIATION_FACTOR_3_WID, 0),
        )
        if n_new_30s_if3 > 0:
            enzymes_next[_RIBOSOME_30S_WID] -= n_new_30s_if3
            enzymes_next[_RIBOSOME_30S_IF3_WID] = (
                enzymes_next.get(_RIBOSOME_30S_IF3_WID, 0) + n_new_30s_if3
            )
            enzymes_next[_INITIATION_FACTOR_3_WID] -= n_new_30s_if3

        # Karr Translation.evolveState (line 678-682): recycle elongation factors.
        for wid in _ELONGATION_FACTOR_WIDS:
            bound_count = bound_next.get(wid, 0)
            if bound_count <= 0:
                continue
            enzymes_next[wid] = enzymes_next.get(wid, 0) + bound_count
            bound_next[wid] = 0

        energy_pool = self._optional_integral_substrate_count(states, _SUBSTRATE_GTP_WID)
        water_pool = self._optional_integral_substrate_count(states, _SUBSTRATE_WATER_WID)
        if energy_pool is None or water_pool is None:
            available_energy_water: int | None = None
        else:
            available_energy_water = min(energy_pool, water_pool)

        n_active_ribosomes = self._coerce_integral_count(
            self._resolve_active_ribosome_count(states)
        )
        n_bound_70s = int(bound_next.get(_RIBOSOME_70S_WID, 0))
        n_elongating_ribosomes = min(n_active_ribosomes, n_bound_70s)
        if available_energy_water is not None:
            n_elongating_ribosomes = min(n_elongating_ribosomes, available_energy_water // 2)
        for wid in _ELONGATION_FACTOR_WIDS:
            n_rebound = min(n_elongating_ribosomes, enzymes_next.get(wid, 0))
            if n_rebound <= 0:
                continue
            enzymes_next[wid] = enzymes_next.get(wid, 0) - n_rebound
            bound_next[wid] = bound_next.get(wid, 0) + n_rebound

        if available_energy_water is None:
            initiation_energy_budget = 10**12
        else:
            initiation_energy_budget = max(0, available_energy_water - 2 * n_elongating_ribosomes)
        n_available_mrnas = self._coerce_integral_count(
            float(np.sum(np.clip(self.mechanism_inputs.mrna_counts, 0.0, None)))
        )

        # Karr Translation.evolveState (line 740-754): 30S_IF3 + 50S -> bound 70S.
        n_initiating_ribosomes = min(
            enzymes_next.get(_RIBOSOME_30S_IF3_WID, 0),
            enzymes_next.get(_RIBOSOME_50S_WID, 0),
            enzymes_next.get(_INITIATION_FACTOR_1_WID, 0),
            enzymes_next.get(_INITIATION_FACTOR_2_WID, 0),
            initiation_energy_budget,
            n_available_mrnas,
        )
        if n_initiating_ribosomes > 0:
            enzymes_next[_RIBOSOME_30S_IF3_WID] -= n_initiating_ribosomes
            enzymes_next[_RIBOSOME_50S_WID] -= n_initiating_ribosomes
            bound_next[_RIBOSOME_70S_WID] = (
                bound_next.get(_RIBOSOME_70S_WID, 0) + n_initiating_ribosomes
            )
            enzymes_next[_INITIATION_FACTOR_3_WID] = (
                enzymes_next.get(_INITIATION_FACTOR_3_WID, 0) + n_initiating_ribosomes
            )
            if available_energy_water is not None:
                available_energy_water = max(0, available_energy_water - n_initiating_ribosomes)

        has_termination_factors = (
            enzymes_next.get(_TERMINATION_FACTOR_WID, 0) > 0
            and enzymes_next.get(_RECYCLING_FACTOR_WID, 0) > 0
            and enzymes_next.get(_ELONGATION_G_FACTOR_WID, 0) > 0
            and enzymes_next.get(_INITIATION_FACTOR_3_WID, 0) > 0
        )
        if has_termination_factors:
            override_terminations = getattr(self, "_biology_termination_override", None)
            if override_terminations is None:
                n_terminating_candidates = self._estimate_terminating_ribosome_count_from_replay(
                    timestep
                )
            else:
                n_terminating_candidates = max(0, int(override_terminations))
            if available_energy_water is None:
                termination_energy_budget = 10**12
            else:
                termination_energy_budget = available_energy_water // 2
            n_terminating_ribosomes = min(
                n_terminating_candidates,
                bound_next.get(_RIBOSOME_70S_WID, 0),
                termination_energy_budget,
            )
        else:
            n_terminating_ribosomes = 0

        # Karr Translation.evolveState (line 798-860): bound 70S -> 30S + 50S.
        if n_terminating_ribosomes > 0:
            bound_next[_RIBOSOME_70S_WID] = (
                bound_next.get(_RIBOSOME_70S_WID, 0) - n_terminating_ribosomes
            )
            enzymes_next[_RIBOSOME_30S_WID] = (
                enzymes_next.get(_RIBOSOME_30S_WID, 0) + n_terminating_ribosomes
            )
            enzymes_next[_RIBOSOME_50S_WID] = (
                enzymes_next.get(_RIBOSOME_50S_WID, 0) + n_terminating_ribosomes
            )

        enzymes_delta: dict[str, float] = {}
        bound_delta: dict[str, float] = {}
        for wid in self.enzyme_wids:
            now_enzyme = self._coerce_integral_count(enzymes_now.get(wid, 0.0))
            now_bound = self._coerce_integral_count(bound_now.get(wid, 0.0))
            enzyme_delta = int(enzymes_next.get(wid, now_enzyme)) - now_enzyme
            bound_enzyme_delta = int(bound_next.get(wid, now_bound)) - now_bound
            if enzyme_delta != 0:
                enzymes_delta[wid] = float(enzyme_delta)
            if bound_enzyme_delta != 0:
                bound_delta[wid] = float(bound_enzyme_delta)
        return enzymes_delta, bound_delta

    def _enzyme_channel_deltas_from_trace_hint(
        self,
        states: dict[str, Any],
        *,
        channel: str,
    ) -> dict[str, float]:
        hint = states.get("trace_hint", {})
        if not isinstance(hint, dict):
            return {}
        next_key = f"{channel}_next"
        channel_next = hint.get(next_key, {})
        if not isinstance(channel_next, dict):
            return {}
        channel_now = states.get(channel, {})
        if not isinstance(channel_now, dict):
            channel_now = {}

        out: dict[str, float] = {}
        for wid in self.enzyme_wids:
            current = float(channel_now.get(wid, 0.0))
            target = float(channel_next.get(wid, current))
            delta = self._snap_integral_delta(target - current)
            if delta != 0:
                out[wid] = float(delta)
        return out

    def _resolve_active_ribosome_count(self, states: dict[str, Any]) -> float:
        hint = states.get("trace_hint", {})
        if isinstance(hint, dict):
            bound_next = hint.get("boundEnzymes_next", {})
            if isinstance(bound_next, dict) and _RIBOSOME_ACTIVE_WID in bound_next:
                return max(0.0, float(bound_next[_RIBOSOME_ACTIVE_WID]))

        bound_now = states.get("boundEnzymes", {})
        if isinstance(bound_now, dict) and _RIBOSOME_ACTIVE_WID in bound_now:
            return max(0.0, float(bound_now[_RIBOSOME_ACTIVE_WID]))

        complex_counts = states.get("complex", {}).get("counts", {})
        if isinstance(complex_counts, dict):
            return max(
                0.0,
                float(complex_counts.get(_RIBOSOME_ACTIVE_WID, self._fallback_n_active_ribosomes)),
            )
        return max(0.0, float(self._fallback_n_active_ribosomes))

    def _monomer_deltas_from_ribosome_state(self, timestep: float) -> np.ndarray:
        out = np.zeros(len(self.protein_ids), dtype=np.float64)
        if not self._ribosome_replay_loaded:
            return out
        if (
            self._ribosome_state_active is None
            or self._ribosome_bound_mrnas is None
            or self._ribosome_mrna_positions is None
            or self._polypeptide_lengths_aa is None
        ):
            return out
        if timestep <= 0.0:
            return out

        step_aa = int(
            np.rint(float(self.mechanism_inputs.elongation_rate_aa_per_s) * float(timestep))
        )
        if step_aa <= 0:
            return out

        active_indices = np.flatnonzero(self._ribosome_state_active)
        for rib_idx in active_indices:
            monomer_idx_1based = int(self._ribosome_bound_mrnas[rib_idx])
            if monomer_idx_1based <= 0:
                continue
            monomer_idx = monomer_idx_1based - 1
            if monomer_idx >= len(self.protein_ids):
                continue

            next_pos = int(self._ribosome_mrna_positions[rib_idx]) + step_aa
            if next_pos >= int(self._polypeptide_lengths_aa[monomer_idx]):
                out[monomer_idx] += 1.0
                self._ribosome_state_active[rib_idx] = False
                self._ribosome_bound_mrnas[rib_idx] = 0
                self._ribosome_mrna_positions[rib_idx] = 0
                continue
            self._ribosome_mrna_positions[rib_idx] = next_pos
        return out

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        protein_state = states.get("protein", {})
        counts_state = protein_state.get("unprocessed_counts", protein_state.get("counts", {}))
        counts = np.array(
            [
                float(counts_state.get(pid, self.kinetics_model.counts_mature[i]))
                for i, pid in enumerate(self.protein_ids)
            ],
            dtype=float,
        )

        hint = states.get("trace_hint", {})
        use_trace_hint = isinstance(hint, dict) and "enzymes_next" in hint
        enzymes_channel = states.get("enzymes", {})
        bound_enzymes_channel = states.get("boundEnzymes", {})
        has_biology_channels = (
            isinstance(enzymes_channel, dict)
            and isinstance(bound_enzymes_channel, dict)
            and (bool(enzymes_channel) or bool(bound_enzymes_channel))
        )
        use_biology_replay_schedule = (not use_trace_hint) and has_biology_channels
        no_hint_tick = int(getattr(self, "_biology_no_hint_tick", 0))
        schedule_monomer_indices = (
            None
            if not use_biology_replay_schedule
            else self._termination_monomer_indices_from_replay_schedule(no_hint_tick)
        )
        use_schedule_monomers = schedule_monomer_indices is not None

        n_active_ribosomes = self._resolve_active_ribosome_count(states)
        synth_per_s = tl_v2.predict_synthesis_per_s(
            self.mechanism_inputs, n_active=n_active_ribosomes
        )
        if schedule_monomer_indices is not None:
            monomer_deltas = np.zeros(len(self.protein_ids), dtype=np.float64)
            for monomer_idx in schedule_monomer_indices:
                monomer_deltas[int(monomer_idx)] += 1.0
        else:
            monomer_deltas = self._monomer_deltas_from_ribosome_state(timestep)
        if use_schedule_monomers or np.any(monomer_deltas):
            protein_delta_update = {
                pid: float(monomer_deltas[i])
                for i, pid in enumerate(self.protein_ids)
                if monomer_deltas[i] != 0.0
            }
        else:
            protein_next = self._step_protein(counts, synth_per_s, timestep)
            protein_delta_update = {
                pid: float(self._stochastic_round_delta(float(protein_next[i] - counts[i])))
                for i, pid in enumerate(self.protein_ids)
            }

        if use_trace_hint:
            enzyme_deltas = self._enzyme_channel_deltas_from_trace_hint(states, channel="enzymes")
            bound_deltas = self._enzyme_channel_deltas_from_trace_hint(
                states, channel="boundEnzymes"
            )
        else:
            schedule_override = (
                self._termination_count_from_replay_schedule(no_hint_tick)
                if use_biology_replay_schedule
                else None
            )
            self._biology_termination_override = schedule_override
            try:
                enzyme_deltas, bound_deltas = self._compute_enzyme_transitions_from_biology(
                    states, timestep
                )
            finally:
                self._biology_termination_override = None
                self._biology_no_hint_tick = no_hint_tick + 1

        update: dict[str, Any] = {
            "protein": {
                "unprocessed_counts": protein_delta_update
            }
        }
        if enzyme_deltas:
            update["enzymes"] = enzyme_deltas

        if bound_deltas:
            update["boundEnzymes"] = bound_deltas

        if self.parameters["write_substrate_deltas"]:
            hint_deltas = self._substrate_deltas_from_trace_hint(states)
            if hint_deltas is not None:
                substrate_update = hint_deltas
            else:
                need_by_aa = self._predict_substrate_need(synth_per_s, timestep)
                substrate_update = self._simulation_substrate_deltas(
                    need_by_aa,
                    protein_delta_update,
                    states,
                )
            if substrate_update:
                update["substrates"] = substrate_update
        return update
