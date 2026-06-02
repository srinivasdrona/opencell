"""Vivarium Process for Karr RNADecay (process #13), light replay variant.

Karr-light v2 scope:
- First-order stochastic RNA decay per species.
- Enzyme-gated aminoacylated RNA decay (peptidyl-tRNA hydrolase).
- Water-limited weighted acceptance of proposed RNA decays.
- RNA/substrate stoichiometric deltas from RNADecay fixture.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process"
_RNA_DECAY_FLAT = _FIXTURE_DIR / "RnaDecay_flat.mat"
_RNA_STATE_CLASS = "edu.stanford.covert.cell.sim.state.Rna"
_TRANSCRIPT_STATE_CLASS = "edu.stanford.covert.cell.sim.state.Transcript"
_LN2 = math.log(2.0)


def _load_flat_fixture(path: Path) -> object:  # noqa: ANN401 - matlab struct dynamic
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    rooted = Path(__file__).resolve().parents[2] / candidate
    if rooted.exists():
        return rooted

    return candidate


def _to_str_list(values: object) -> list[str]:
    raw = np.asarray(values, dtype=object).ravel()
    out: list[str] = []
    for value in raw:
        item: object = value
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


def _uniquify_ids(values: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    totals: dict[str, int] = {}
    for value in values:
        totals[value] = totals.get(value, 0) + 1

    out: list[str] = []
    for value in values:
        counts[value] = counts.get(value, 0) + 1
        if totals[value] <= 1:
            out.append(value)
        else:
            out.append(f"{value}__{counts[value]}")
    return out


def _fixture_state_by_class(
    fixture: object,
    class_name: str,
) -> object:  # noqa: ANN401 - matlab struct dynamic
    for state in np.asarray(fixture.states, dtype=object).ravel():
        if getattr(state, "x_class_", "") == class_name:
            return state
    raise ValueError(f"Fixture state not found: {class_name}")


def _normalize_indices(raw_values: object, size: int) -> np.ndarray:
    values = np.asarray(raw_values, dtype=np.int64).reshape(-1)
    if values.size == 0:
        return np.asarray([], dtype=np.int64)
    # Karr MATLAB indices are 1-based in fixtures.
    if np.all(values >= 1):
        values = values - 1
    values = values[(values >= 0) & (values < size)]
    if values.size == 0:
        return np.asarray([], dtype=np.int64)
    return np.unique(values.astype(np.int64))


class RnaDecayLightProcess(Process):
    """Karr RNADecay process #13, light allocation-aware variant."""

    name = "karr_rna_decay"
    defaults: dict[str, Any] = {
        "fixture_path": str(_RNA_DECAY_FLAT),
        "rng_seed": 0,
        "time_step": 1.0,
        # Guard against invalid tiny sentinel values in some fixture half-life slots.
        "min_valid_half_life_s": 1.0e-6,
        "emit_substrate_stoich": True,
        # Fixture-absent fallback parameters.
        "fallback_rna_ids": [],
        "fallback_rna_type_by_wid": {},
        "fallback_half_life_min": {
            "mRNA": 4.5,
            "rRNA": 150.0,
            "sRNA": 89.0,
            "tRNA": 45.0,
        },
        # If False, fallback omits substrate/H2O deltas (documented approximation).
        "fallback_consume_h2o": False,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._rng_seed = int(self.parameters["rng_seed"])
        self._rng = np.random.RandomState(self._rng_seed)

        fixture_path = _resolve_path(self.parameters["fixture_path"])
        if fixture_path.exists():
            self._load_from_fixture(fixture_path)
        else:
            self._load_from_fallback()

        if self.decay_reactions.shape != (len(self.rna_wids), len(self.substrate_wids)):
            raise ValueError(
                "RnaDecay stoichiometry dimension mismatch: "
                f"{self.decay_reactions.shape} vs "
                f"({len(self.rna_wids)}, {len(self.substrate_wids)})"
            )
        self._rng = np.random.RandomState(self._rng_seed)

    def _load_from_fixture(self, fixture_path: Path) -> None:
        fixture = _load_flat_fixture(fixture_path)
        rna_state = _fixture_state_by_class(fixture, _RNA_STATE_CLASS)

        self.rna_wids = _uniquify_ids(_to_str_list(rna_state.wholeCellModelIDs))
        self.substrate_wids = _to_str_list(fixture.substrateWholeCellModelIDs)
        enzyme_wids_raw = getattr(fixture, "enzymeWholeCellModelIDs", None)
        if enzyme_wids_raw is None:
            self.enzyme_wids = []
        else:
            self.enzyme_wids = _to_str_list(enzyme_wids_raw)
        self.water_wid = "H2O"

        half_lives = np.asarray(rna_state.halfLives, dtype=np.float64).reshape(-1)
        if half_lives.size != len(self.rna_wids):
            raise ValueError(
                "RnaDecay half-life vector length mismatch: "
                f"{half_lives.size} vs {len(self.rna_wids)}"
            )

        min_valid_half_life_s = float(self.parameters["min_valid_half_life_s"])
        valid_half_life = np.isfinite(half_lives) & (half_lives > min_valid_half_life_s)
        rates = np.zeros_like(half_lives, dtype=np.float64)
        rates[valid_half_life] = _LN2 / half_lives[valid_half_life]
        self.decay_rates_per_s = rates

        stoich = np.asarray(fixture.decayReactions, dtype=np.int64)
        if stoich.shape == (len(self.substrate_wids), len(self.rna_wids)):
            stoich = stoich.T
        self.decay_reactions = stoich

        water_idx_raw = getattr(fixture, "substrateIndexs_water", None)
        if water_idx_raw is not None:
            self.substrate_index_water = int(water_idx_raw) - 1
        else:
            try:
                self.substrate_index_water = self.substrate_wids.index("H2O")
            except ValueError as exc:
                raise ValueError("H2O index unavailable in RnaDecay fixture") from exc

        hydrogen_idx_raw = getattr(fixture, "substrateIndexs_hydrogen", None)
        if hydrogen_idx_raw is not None:
            self.substrate_index_hydrogen = int(hydrogen_idx_raw) - 1
        else:
            self.substrate_index_hydrogen = (
                self.substrate_wids.index("H") if "H" in self.substrate_wids else -1
            )
        self.substrate_indices_nmps = _normalize_indices(
            getattr(fixture, "substrateIndexs_nmps", np.asarray([], dtype=np.int64)),
            len(self.substrate_wids),
        )

        self.water_need_per_decay = np.clip(
            -self.decay_reactions[:, self.substrate_index_water], a_min=0, a_max=None
        ).astype(np.int64)
        self._fixture_rna_counts = np.asarray(
            getattr(fixture, "RNAs", np.zeros(len(self.rna_wids))),
            dtype=np.int64,
        ).reshape(-1)[: len(self.rna_wids)]
        self._fixture_enzyme_counts = np.asarray(
            getattr(fixture, "enzymes", np.zeros(len(self.enzyme_wids))),
            dtype=np.float64,
        ).reshape(-1)[: len(self.enzyme_wids)]

        self.aminoacylated_indices = _normalize_indices(
            getattr(rna_state, "aminoacylatedIndexs", np.asarray([], dtype=np.int64)),
            len(self.rna_wids),
        )
        ribonuclease_idx_raw = int(getattr(fixture, "enzymeIndexs_ribonucleaseR", 0))
        self.enzyme_index_ribonuclease_r = ribonuclease_idx_raw - 1 if ribonuclease_idx_raw > 0 else -1
        peptidyl_idx_raw = int(getattr(fixture, "enzymeIndexs_peptidylTRNAHydrolase", 0))
        self.enzyme_index_peptidyl_hydrolase = peptidyl_idx_raw - 1 if peptidyl_idx_raw > 0 else -1
        self.peptidyl_trna_hydrolase_specific_rate = float(
            getattr(fixture, "peptidylTRNAHydrolaseSpecificRate", 0.0)
        )
        self.step_size_sec = float(getattr(fixture, "stepSizeSec", 1.0))

        self._fixture_transcription_unit_sequences = self._read_fixture_transcription_unit_sequences(
            fixture=fixture
        )
        self._fixture_aborted_sequences = self._read_fixture_aborted_sequences(fixture=fixture)

    def _load_from_fallback(self) -> None:
        self.rna_wids = _uniquify_ids(
            [str(wid) for wid in self.parameters.get("fallback_rna_ids", [])]
        )
        if not self.rna_wids:
            raise FileNotFoundError(
                "RnaDecay fixture not found and fallback_rna_ids is empty; cannot initialize."
            )
        self.enzyme_wids = []
        self.water_wid = "H2O"

        type_by_wid = {
            str(wid): str(rna_type)
            for wid, rna_type in (self.parameters.get("fallback_rna_type_by_wid") or {}).items()
        }
        half_life_min = {
            str(key): float(val)
            for key, val in (self.parameters.get("fallback_half_life_min") or {}).items()
        }
        default_half_life_min = float(half_life_min.get("mRNA", 4.5))

        half_lives_s = np.asarray(
            [
                60.0 * float(half_life_min.get(type_by_wid.get(wid, "mRNA"), default_half_life_min))
                for wid in self.rna_wids
            ],
            dtype=np.float64,
        )
        self.decay_rates_per_s = _LN2 / half_lives_s

        self.substrate_wids = ["H2O"]
        self.substrate_index_water = 0
        self.substrate_index_hydrogen = -1
        self.substrate_indices_nmps = np.asarray([], dtype=np.int64)
        self.decay_reactions = np.zeros((len(self.rna_wids), 1), dtype=np.int64)
        if bool(self.parameters.get("fallback_consume_h2o", False)):
            self.decay_reactions[:, 0] = -1

        self.water_need_per_decay = np.clip(-self.decay_reactions[:, 0], a_min=0, a_max=None)
        self._fixture_rna_counts = np.zeros(len(self.rna_wids), dtype=np.int64)
        self._fixture_enzyme_counts = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        self.aminoacylated_indices = np.asarray([], dtype=np.int64)
        self.enzyme_index_ribonuclease_r = -1
        self.enzyme_index_peptidyl_hydrolase = -1
        self.peptidyl_trna_hydrolase_specific_rate = 0.0
        self.step_size_sec = 1.0
        self._fixture_transcription_unit_sequences: list[str] = []
        self._fixture_aborted_sequences: list[str] = []

    def ports_schema(self) -> dict[str, Any]:
        return {
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.rna_wids
                }
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "requests": {
                self.name: {
                    self.water_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.water_wid: {"_default": 0.0, "_emit": False},
                }
            },
            "transcripts": {
                "aborted_sequences": {"_default": [], "_updater": "set", "_emit": False},
                "aborted_transcripts": {"_default": [], "_updater": "set", "_emit": False},
                "transcription_unit_sequences": {"_default": [], "_updater": "set", "_emit": False},
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep)
        if dt <= 0.0:
            dt = self.step_size_sec

        enzyme_counts = self._read_enzyme_counts(states=states)
        peptidyl_capacity = self._peptidyl_hydrolase_capacity_with_counts(
            dt=dt,
            enzyme_counts=enzyme_counts,
        )
        ribonuclease_r = self._ribonuclease_r_count(enzyme_counts=enzyme_counts)

        if ribonuclease_r <= 0.0:
            return {
                "requests": {
                    self.name: {
                        self.water_wid: 0.0,
                    }
                }
            }

        rna_counts = np.asarray(
            [
                max(0, int(float(states.get("rna", {}).get("counts", {}).get(wid, 0.0))))
                for wid in self.rna_wids
            ],
            dtype=np.int64,
        )
        if not np.any(rna_counts):
            rna_counts = self._fixture_rna_counts

        substrate_counts = self._read_substrate_counts(states=states)
        aborted_sequences, has_runtime_transcript_state = self._read_aborted_sequences(states=states)
        aborted_substrate_delta = np.zeros(len(self.substrate_wids), dtype=np.int64)
        remaining_aborted_sequences = aborted_sequences
        if aborted_sequences:
            aborted_substrate_delta, remaining_aborted_sequences = self._apply_aborted_decay(
                aborted_sequences=aborted_sequences,
                substrate_counts=substrate_counts,
            )

        decay_rates = np.minimum(1.0e6, self.decay_rates_per_s * dt)
        expected = decay_rates * rna_counts.astype(np.float64)
        sampled_decay = self._sample_poisson_vector(expected)
        sampled_decay = np.minimum(sampled_decay, rna_counts)

        raw_h2o_need = float(np.dot(self.water_need_per_decay, sampled_decay))
        update: dict[str, Any] = {
            "requests": {
                self.name: {
                    self.water_wid: raw_h2o_need,
                }
            }
        }
        if np.any(aborted_substrate_delta != 0):
            update["substrates"] = {
                wid: float(aborted_substrate_delta[i])
                for i, wid in enumerate(self.substrate_wids)
                if aborted_substrate_delta[i] != 0
            }
        if has_runtime_transcript_state:
            update["transcripts"] = {"aborted_sequences": list(remaining_aborted_sequences)}

        if not np.any(sampled_decay > 0):
            return update

        decay_events = sampled_decay.copy()

        # RNADecay.m: aminoacylated RNA decay is additionally constrained by
        # peptidyl-tRNA hydrolase activity.
        if self.aminoacylated_indices.size > 0 and peptidyl_capacity >= 0:
            amino_counts = decay_events[self.aminoacylated_indices].copy()
            amino_kept = np.zeros_like(amino_counts, dtype=np.int64)
            while peptidyl_capacity > 0 and np.any(amino_counts > 0):
                picked = self._draw_weighted_index(amino_counts)
                if picked is None:
                    break
                amino_counts[picked] -= 1
                amino_kept[picked] += 1
                peptidyl_capacity -= 1
            decay_events[self.aminoacylated_indices] = amino_kept

        water_remaining = self._available_water(states=states)
        if self.substrate_index_water >= 0 and self.substrate_index_water < aborted_substrate_delta.size:
            water_remaining += float(aborted_substrate_delta[self.substrate_index_water])
        water_remaining = max(0.0, water_remaining)
        tmp = decay_events.copy()
        kept = np.zeros_like(tmp, dtype=np.int64)
        while np.any(tmp > 0):
            picked = self._draw_weighted_index(tmp)
            if picked is None:
                break
            required = float(self.water_need_per_decay[picked])
            if water_remaining < required:
                break
            water_remaining -= required
            tmp[picked] -= 1
            kept[picked] += 1
        decay_events = kept

        if np.any(decay_events > 0):
            rna_delta = -decay_events
            rna_update = {
                wid: float(rna_delta[i]) for i, wid in enumerate(self.rna_wids) if rna_delta[i] != 0
            }
            if rna_update:
                update["rna"] = {"counts": rna_update}

            if bool(self.parameters.get("emit_substrate_stoich", True)):
                substrate_delta = (decay_events @ self.decay_reactions) + aborted_substrate_delta
                substrate_update = {
                    wid: float(substrate_delta[i])
                    for i, wid in enumerate(self.substrate_wids)
                    if substrate_delta[i] != 0
                }
                if substrate_update:
                    update["substrates"] = substrate_update
        elif np.any(aborted_substrate_delta != 0):
            update["substrates"] = {
                wid: float(aborted_substrate_delta[i])
                for i, wid in enumerate(self.substrate_wids)
                if aborted_substrate_delta[i] != 0
            }

        return update

    def _draw_weighted_index(self, weights: np.ndarray) -> int | None:
        total = int(np.sum(weights))
        if total <= 0:
            return None
        threshold = float(self._rng.rand()) * float(total)
        cumulative = np.cumsum(weights, dtype=np.int64)
        return int(np.searchsorted(cumulative, threshold, side="right"))

    def _sample_poisson_vector(self, lam: np.ndarray) -> np.ndarray:
        lam_vec = np.asarray(lam, dtype=np.float64).reshape(-1)
        out = np.zeros(lam_vec.size, dtype=np.int64)
        for idx in range(lam_vec.size):
            threshold = float(self._rng.rand())
            rate = float(lam_vec[idx])
            if not np.isfinite(rate) or rate <= 0.0:
                continue
            if rate >= 30.0:
                out[idx] = int(self._rng.poisson(rate))
                continue

            p = math.exp(-rate)
            cdf = p
            k = 0
            while threshold > cdf:
                k += 1
                p *= rate / float(k)
                cdf += p
            out[idx] = k

        return out

    def _available_water(self, states: dict[str, Any]) -> float:
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        if isinstance(allocated_state, dict) and self.water_wid in allocated_state:
            return max(0.0, float(allocated_state.get(self.water_wid, 0.0)))
        substrate_state = states.get("substrates", {})
        if isinstance(substrate_state, dict):
            return max(0.0, float(substrate_state.get(self.water_wid, 0.0)))
        return 0.0

    def _peptidyl_hydrolase_capacity(self, *, states: dict[str, Any], dt: float) -> int:
        return self._peptidyl_hydrolase_capacity_with_counts(
            dt=dt,
            enzyme_counts=self._read_enzyme_counts(states=states),
        )

    def _peptidyl_hydrolase_capacity_with_counts(
        self,
        *,
        dt: float,
        enzyme_counts: np.ndarray,
    ) -> int:
        if self.enzyme_index_peptidyl_hydrolase < 0 or not self.enzyme_wids:
            return -1
        if self.enzyme_index_peptidyl_hydrolase >= enzyme_counts.size:
            return -1
        expected = (
            max(0.0, float(enzyme_counts[self.enzyme_index_peptidyl_hydrolase]))
            * max(0.0, self.peptidyl_trna_hydrolase_specific_rate)
            * max(0.0, dt)
        )
        return self._stochastic_round(expected)

    def _ribonuclease_r_count(self, *, enzyme_counts: np.ndarray) -> float:
        if self.enzyme_index_ribonuclease_r < 0 or not self.enzyme_wids:
            return 1.0
        if self.enzyme_index_ribonuclease_r >= enzyme_counts.size:
            return 1.0
        return max(0.0, float(enzyme_counts[self.enzyme_index_ribonuclease_r]))

    def _stochastic_round(self, value: float) -> int:
        if value <= 0.0:
            return 0
        base = int(np.floor(value))
        frac = float(value - base)
        if frac <= 0.0:
            return base
        return base + int(float(self._rng.rand()) < frac)

    def _read_enzyme_counts(self, *, states: dict[str, Any]) -> np.ndarray:
        enzyme_state = states.get("enzymes", {})
        if isinstance(enzyme_state, dict):
            counts = np.asarray(
                [max(0.0, float(enzyme_state.get(wid, 0.0))) for wid in self.enzyme_wids],
                dtype=np.float64,
            )
            if np.any(counts > 0.0) or not self.enzyme_wids:
                return counts

        protein_counts = states.get("protein", {}).get("counts", {})
        complex_counts = states.get("complex", {}).get("counts", {})
        if isinstance(protein_counts, dict) or isinstance(complex_counts, dict):
            out = np.zeros(len(self.enzyme_wids), dtype=np.float64)
            for i, wid in enumerate(self.enzyme_wids):
                value = 0.0
                if isinstance(protein_counts, dict) and wid in protein_counts:
                    value = float(protein_counts.get(wid, 0.0))
                elif isinstance(complex_counts, dict) and wid in complex_counts:
                    value = float(complex_counts.get(wid, 0.0))
                out[i] = max(0.0, value)
            if np.any(out > 0.0):
                return out

        if self._fixture_enzyme_counts.size == len(self.enzyme_wids):
            return np.clip(self._fixture_enzyme_counts.astype(np.float64), a_min=0.0, a_max=None)
        return np.zeros(len(self.enzyme_wids), dtype=np.float64)

    def _read_substrate_counts(self, *, states: dict[str, Any]) -> np.ndarray:
        substrate_state = states.get("substrates", {})
        if isinstance(substrate_state, dict):
            return np.asarray(
                [float(substrate_state.get(wid, 0.0)) for wid in self.substrate_wids],
                dtype=np.float64,
            )
        return np.zeros(len(self.substrate_wids), dtype=np.float64)

    def _read_fixture_transcription_unit_sequences(self, *, fixture: object) -> list[str]:
        transcript_state = self._fixture_transcript_state(fixture=fixture)
        if transcript_state is None:
            return []
        return self._to_sequence_list(getattr(transcript_state, "transcriptionUnitSequences", []))

    def _read_fixture_aborted_sequences(self, *, fixture: object) -> list[str]:
        transcript_state = self._fixture_transcript_state(fixture=fixture)
        if transcript_state is None:
            return []

        aborted_sequences = getattr(transcript_state, "abortedSequences", None)
        if aborted_sequences is not None:
            return self._to_sequence_list(aborted_sequences)

        aborted_transcripts = getattr(transcript_state, "abortedTranscripts", None)
        return self._aborted_transcripts_to_sequences(
            aborted_transcripts=aborted_transcripts,
            transcription_unit_sequences=self._to_sequence_list(
                getattr(transcript_state, "transcriptionUnitSequences", [])
            ),
        )

    def _fixture_transcript_state(self, *, fixture: object) -> object | None:
        for state in np.asarray(getattr(fixture, "states", []), dtype=object).ravel():
            if getattr(state, "x_class_", "") == _TRANSCRIPT_STATE_CLASS:
                return state
        return None

    def _to_sequence_list(self, raw_values: object) -> list[str]:
        raw = np.asarray(raw_values, dtype=object).ravel()
        out: list[str] = []
        for value in raw:
            text = str(value)
            if text and text != "[]":
                out.append(text)
        return out

    def _aborted_transcripts_to_sequences(
        self,
        *,
        aborted_transcripts: object,
        transcription_unit_sequences: list[str],
    ) -> list[str]:
        if aborted_transcripts is None:
            return []
        matrix = np.asarray(aborted_transcripts)
        if matrix.size == 0:
            return []
        matrix = np.atleast_2d(matrix)
        out: list[str] = []
        for row in matrix:
            if row.size < 2:
                continue
            unit_idx = int(row[0]) - 1
            seq_len = int(row[1])
            if unit_idx < 0 or unit_idx >= len(transcription_unit_sequences):
                continue
            sequence = transcription_unit_sequences[unit_idx]
            if seq_len <= 0:
                continue
            out.append(sequence[:seq_len])
        return out

    def _read_aborted_sequences(self, *, states: dict[str, Any]) -> tuple[list[str], bool]:
        transcript_state = states.get("transcripts", {})
        has_runtime_transcript_state = isinstance(transcript_state, dict)
        if isinstance(transcript_state, dict):
            seq_values = transcript_state.get("aborted_sequences", None)
            if seq_values is None:
                seq_values = transcript_state.get("abortedSequences", None)
            if seq_values is not None:
                return self._to_sequence_list(seq_values), has_runtime_transcript_state

            aborted_transcripts = transcript_state.get("aborted_transcripts", None)
            if aborted_transcripts is None:
                aborted_transcripts = transcript_state.get("abortedTranscripts", None)
            if aborted_transcripts is not None:
                unit_sequences = transcript_state.get(
                    "transcription_unit_sequences",
                    self._fixture_transcription_unit_sequences,
                )
                return self._aborted_transcripts_to_sequences(
                    aborted_transcripts=aborted_transcripts,
                    transcription_unit_sequences=self._to_sequence_list(unit_sequences),
                ), has_runtime_transcript_state

        return list(self._fixture_aborted_sequences), has_runtime_transcript_state

    def _apply_aborted_decay(
        self,
        *,
        aborted_sequences: list[str],
        substrate_counts: np.ndarray,
    ) -> tuple[np.ndarray, list[str]]:
        aborted_delta = np.zeros(len(self.substrate_wids), dtype=np.int64)
        remaining_sequences: list[str] = []
        for idx, sequence in enumerate(aborted_sequences):
            substrate_cost = self._aborted_sequence_decay_reaction(sequence=sequence)
            available = substrate_counts + aborted_delta.astype(np.float64)
            if np.any(available < -substrate_cost.astype(np.float64)):
                remaining_sequences.extend(aborted_sequences[idx:])
                break
            aborted_delta += substrate_cost
        return aborted_delta, remaining_sequences

    def _aborted_sequence_decay_reaction(self, *, sequence: str) -> np.ndarray:
        value = np.zeros(len(self.substrate_wids), dtype=np.int64)
        if self.substrate_indices_nmps.size >= 4:
            sequence_upper = sequence.upper()
            base_counts = (
                sequence_upper.count("A"),
                sequence_upper.count("C"),
                sequence_upper.count("G"),
                sequence_upper.count("U"),
            )
            for base_idx, count in zip(self.substrate_indices_nmps[:4], base_counts, strict=False):
                value[int(base_idx)] = int(count)

        hydrolysis = max(0, len(sequence) - 1)
        if 0 <= self.substrate_index_water < value.size:
            value[self.substrate_index_water] -= hydrolysis
        if 0 <= self.substrate_index_hydrogen < value.size:
            value[self.substrate_index_hydrogen] += hydrolysis
        return value


__all__ = ["RnaDecayLightProcess"]
