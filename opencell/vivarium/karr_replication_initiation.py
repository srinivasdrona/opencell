"""Vivarium Process port of Karr's replication initiation gate logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ReplicationInitiation_flat.mat"


def _resolve_fixture_path(path: str | Path) -> Path:
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
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        token = _coerce_scalar(raw)
        out.append(str(token))
    return out


def _parse_index_array(value: object) -> np.ndarray:
    raw = np.asarray(value)
    while raw.dtype == object and raw.size == 1 and isinstance(raw.flat[0], np.ndarray):
        raw = np.asarray(raw.flat[0])
    return np.asarray(raw, dtype=np.int64).reshape(-1)


class KarrReplicationInitiationProcess(Process):
    """Karr Process_ReplicationInitiation (DnaA OriC gating)."""

    name = "karr_replication_initiation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "polymer_max_length": 7,
        "r1234_threshold": 7,
        "r5_threshold": 1,
        "polymerization_rate_scale": 1_000.0,
        "binding_rate_scale": 25_000.0,
        "release_rate_scale": 1_000.0,
        "inactivation_rate_scale": 1.0e16,
        "regen_rate_scale": 1_000.0,
        "membrane_conc": 0.03,
        "r5_binding_boost": 40.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        self._free_dnaa_atp = 0
        self._free_dnaa_adp = 0
        self._bound_atp = np.zeros(self.n_sites, dtype=np.int64)
        self._bound_adp = np.zeros(self.n_sites, dtype=np.int64)
        self._initialized = False

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.substrate_index_atp = int(_coerce_scalar(fx.substrateIndexs_atp)) - 1
        self.substrate_index_adp = int(_coerce_scalar(fx.substrateIndexs_adp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_water = int(_coerce_scalar(fx.substrateIndexs_water)) - 1
        self.substrate_index_h = int(_coerce_scalar(fx.substrateIndexs_hydrogen)) - 1

        self.atp_wid = self.substrate_wids[self.substrate_index_atp]
        self.adp_wid = self.substrate_wids[self.substrate_index_adp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.water_wid = self.substrate_wids[self.substrate_index_water]
        self.hydrogen_wid = self.substrate_wids[self.substrate_index_h]

        self.dnaa_wid = self.enzyme_wids[int(_coerce_scalar(fx.enzymeIndexs_DnaA)) - 1]

        self.kb_atp = float(_coerce_scalar(fx.kb1ATP))
        self.kb_adp = float(_coerce_scalar(fx.kb1ADP))
        self.kd_atp = float(_coerce_scalar(fx.kd1ATP))
        self.kd_adp = float(_coerce_scalar(fx.kd1ADP))
        self.k_regen = float(_coerce_scalar(fx.k_Regen))
        self.k_regen_p4 = float(_coerce_scalar(fx.K_Regen_P4))
        self.k_inact = float(_coerce_scalar(fx.k_inact))
        self.site_cooperativity = float(_coerce_scalar(fx.siteCooperativity))
        self.state_cooperativity = float(_coerce_scalar(fx.stateCooperativity))

        all_start_positions = _parse_index_array(fx.dnaABoxStartPositions)
        self.n_sites = int(all_start_positions.size)

        r12345 = (_parse_index_array(fx.dnaABoxIndexs_R12345) - 1).tolist()
        if len(r12345) != 5:
            raise ValueError(f"Expected 5 OriC sites, found {len(r12345)}")
        self.r12345_indices = [int(idx) for idx in r12345]
        self.r1234_indices = self.r12345_indices[:4]
        self.r5_index = int((_parse_index_array(fx.dnaABoxIndexs_R5) - 1)[0])

        self.oric_site_ids = ["R1", "R2", "R3", "R4", "R5"]
        self.r1234_site_ids = self.oric_site_ids[:4]
        self._oric_index_to_name = {
            self.r12345_indices[0]: "R1",
            self.r12345_indices[1]: "R2",
            self.r12345_indices[2]: "R3",
            self.r12345_indices[3]: "R4",
            self.r12345_indices[4]: "R5",
        }

        self.index_to_site_id: list[str] = []
        for idx in range(self.n_sites):
            if idx in self._oric_index_to_name:
                self.index_to_site_id.append(self._oric_index_to_name[idx])
            else:
                self.index_to_site_id.append(f"DnaA_box_{idx + 1:04d}")
        self.site_id_to_index = {sid: idx for idx, sid in enumerate(self.index_to_site_id)}
        self.all_dnaa_sites = list(self.index_to_site_id)
        self.non_oric_site_ids = [
            site_id for site_id in self.all_dnaa_sites if site_id not in set(self.oric_site_ids)
        ]

    def ports_schema(self) -> dict[str, Any]:
        return {
            "chromosome": {
                "dnaa_complex_count": {
                    site_id: {"_default": 0, "_updater": "accumulate", "_emit": True}
                    for site_id in self.all_dnaa_sites
                },
                "replication_state": {
                    "_default": "idle",
                    "_updater": "set",
                    "_emit": True,
                },
                "supercoiled": {
                    "_default": True,
                    "_updater": "set",
                    "_emit": False,
                },
            },
            "protein": {
                "counts": {
                    self.dnaa_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                }
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "requests": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.water_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_emit": False},
                    self.water_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        chromosome_state = states.get("chromosome", {})
        dnaa_counts_state = chromosome_state.get("dnaa_complex_count", {})
        protein_counts = states["protein"]["counts"]
        dnaa_adp_wid, dnaa_atp_wid = self.enzyme_wids[0], self.enzyme_wids[1]
        free_dnaa_adp = int(max(0.0, float(protein_counts.get(dnaa_adp_wid, 0.0))))
        free_dnaa_atp = int(max(0.0, float(protein_counts.get(dnaa_atp_wid, 0.0))))
        has_enzyme_pools = dnaa_adp_wid in protein_counts or dnaa_atp_wid in protein_counts
        free_dnaa = free_dnaa_adp + free_dnaa_atp if has_enzyme_pools else int(
            max(0.0, float(protein_counts.get(self.dnaa_wid, 0.0)))
        )
        supercoiled = bool(chromosome_state.get("supercoiled", True))
        replication_state = str(chromosome_state.get("replication_state", "idle"))

        site_total_from_state = np.asarray(
            [
                int(max(0.0, float(dnaa_counts_state.get(site_id, 0.0))))
                for site_id in self.all_dnaa_sites
            ],
            dtype=np.int64,
        )
        self._sync_internal_state(free_dnaa=free_dnaa, site_totals=site_total_from_state)
        if has_enzyme_pools:
            self._free_dnaa_adp = free_dnaa_adp
            self._free_dnaa_atp = free_dnaa_atp

        start_free_adp, start_free_atp = int(self._free_dnaa_adp), int(self._free_dnaa_atp)
        start_bound_total = (self._bound_atp + self._bound_adp).copy()

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        available_atp = self._allocated_or_state(allocated_state, self.atp_wid)
        available_water = self._allocated_or_state(allocated_state, self.water_wid)
        substrate_delta: dict[str, int] = {}

        # 1) activateFreeDnaA
        self._activate_free_dnaa(available_atp=available_atp, substrate_delta=substrate_delta)
        # 2) inactivateFreeDnaAATP
        self._inactivate_free_dnaa_atp(
            dt=dt,
            available_water=available_water,
            substrate_delta=substrate_delta,
        )
        # 3-4) OriC polymerization (only if supercoiled)
        if supercoiled:
            self._polymerize_dnaa_atp(dt=dt)
            self._polymerize_dnaa_adp(dt=dt)
        # 5-6) stochastic binding to free boxes
        self._bind_dnaa_atp(dt=dt)
        self._bind_dnaa_adp(dt=dt)
        # 7-8) stochastic uniform release
        self._release_dnaa_atp(dt=dt)
        self._release_dnaa_adp(dt=dt)
        # 9) ADP reactivation via membrane regeneration
        self._reactivate_free_dnaa_adp(dt=dt)

        update: dict[str, Any] = {}

        bound_total = self._bound_atp + self._bound_adp
        chrom_delta = bound_total - start_bound_total
        chrom_updates = {
            site_id: int(chrom_delta[idx])
            for idx, site_id in enumerate(self.all_dnaa_sites)
            if chrom_delta[idx] != 0
        }
        if chrom_updates:
            update.setdefault("chromosome", {})
            update["chromosome"]["dnaa_complex_count"] = chrom_updates

        free_total = int(self._free_dnaa_atp + self._free_dnaa_adp)
        free_delta = free_total - start_free_atp - start_free_adp
        if free_delta != 0 and not has_enzyme_pools:
            update.setdefault("protein", {})
            update["protein"] = {"counts": {self.dnaa_wid: float(free_delta)}}
        if has_enzyme_pools:
            adp_delta = float(self._free_dnaa_adp - start_free_adp)
            atp_delta = float(self._free_dnaa_atp - start_free_atp)
            if adp_delta != 0.0 or atp_delta != 0.0:
                counts = update.setdefault("protein", {}).setdefault("counts", {})
                if adp_delta != 0.0:
                    counts[dnaa_adp_wid] = adp_delta
                if atp_delta != 0.0:
                    counts[dnaa_atp_wid] = atp_delta

        if replication_state == "idle" and self._check_initiation_trigger():
            update.setdefault("chromosome", {})
            update["chromosome"]["replication_state"] = "initiating"

        substrate_updates = {
            wid: float(delta) for wid, delta in substrate_delta.items() if int(delta) != 0
        }
        if substrate_updates:
            update["substrates"] = substrate_updates

        update["requests"] = {
            self.name: {
                self.atp_wid: float(max(0, self._free_dnaa_adp)),
                self.water_wid: float(max(0, self._free_dnaa_atp)),
            }
        }
        return update

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _sync_internal_state(self, free_dnaa: int, site_totals: np.ndarray) -> None:
        if not self._initialized:
            self._bound_atp = np.maximum(site_totals.astype(np.int64), 0)
            self._bound_adp = np.zeros(self.n_sites, dtype=np.int64)
            self._free_dnaa_atp = 0
            self._free_dnaa_adp = max(0, int(free_dnaa))
            self._initialized = True
            return

        current_totals = self._bound_atp + self._bound_adp
        target_totals = np.maximum(site_totals.astype(np.int64), 0)
        delta = target_totals - current_totals

        add_mask = delta > 0
        if np.any(add_mask):
            self._bound_atp[add_mask] += delta[add_mask]

        remove_mask = delta < 0
        if np.any(remove_mask):
            to_remove = -delta[remove_mask]
            adp_avail = self._bound_adp[remove_mask]
            from_adp = np.minimum(adp_avail, to_remove)
            self._bound_adp[remove_mask] -= from_adp
            remaining = to_remove - from_adp
            self._bound_atp[remove_mask] = np.maximum(
                0,
                self._bound_atp[remove_mask] - remaining,
            )

        current_free = int(self._free_dnaa_atp + self._free_dnaa_adp)
        target_free = max(0, int(free_dnaa))
        if target_free > current_free:
            self._free_dnaa_adp += target_free - current_free
        elif target_free < current_free:
            excess = current_free - target_free
            from_adp = min(self._free_dnaa_adp, excess)
            self._free_dnaa_adp -= from_adp
            excess -= from_adp
            self._free_dnaa_atp = max(0, self._free_dnaa_atp - excess)

    def _activate_free_dnaa(self, available_atp: float, substrate_delta: dict[str, int]) -> None:
        atp_pool = max(0, int(np.floor(available_atp)))
        n_events = min(self._free_dnaa_adp, atp_pool)
        if n_events <= 0:
            return
        self._free_dnaa_adp -= n_events
        self._free_dnaa_atp += n_events
        substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0) - n_events

    def _inactivate_free_dnaa_atp(
        self,
        dt: float,
        available_water: float,
        substrate_delta: dict[str, int],
    ) -> None:
        if self._free_dnaa_atp <= 0:
            return
        hydrolysis_p = self._event_probability(
            rate=self.k_inact / float(self.parameters["inactivation_rate_scale"]),
            dt=dt,
        )
        if hydrolysis_p <= 0.0:
            return

        n_events = int(self._rng.binomial(self._free_dnaa_atp, hydrolysis_p))
        if n_events <= 0:
            return
        n_events = min(n_events, max(0, int(np.floor(available_water))))
        if n_events <= 0:
            return

        self._free_dnaa_atp -= n_events
        self._free_dnaa_adp += n_events

        substrate_delta[self.adp_wid] = substrate_delta.get(self.adp_wid, 0) + n_events
        substrate_delta[self.pi_wid] = substrate_delta.get(self.pi_wid, 0) + n_events
        substrate_delta[self.water_wid] = substrate_delta.get(self.water_wid, 0) - n_events
        substrate_delta[self.hydrogen_wid] = substrate_delta.get(self.hydrogen_wid, 0) + n_events

    def _polymerize_dnaa_atp(self, dt: float) -> None:
        max_polymer = int(self.parameters["polymer_max_length"])
        for idx in self.r1234_indices:
            if self._free_dnaa_atp <= 0:
                return
            if int(self._bound_atp[idx] + self._bound_adp[idx]) >= max_polymer:
                continue
            cooperativity = self._oric_cooperativity(idx)
            rate = (
                self.kb_atp
                * float(self._free_dnaa_atp)
                * cooperativity
                / float(self.parameters["polymerization_rate_scale"])
            )
            if self._rng.random() < self._event_probability(rate=rate, dt=dt):
                self._bound_atp[idx] += 1
                self._free_dnaa_atp -= 1

        if self._free_dnaa_atp <= 0:
            return
        if self._bound_atp[self.r5_index] >= int(self.parameters["r5_threshold"]):
            return
        if not all(
            self._bound_atp[idx] >= int(self.parameters["r1234_threshold"])
            for idx in self.r1234_indices
        ):
            return

        rate = (
            self.kb_atp
            * float(self._free_dnaa_atp)
            * float(self.parameters["r5_binding_boost"])
            / float(self.parameters["polymerization_rate_scale"])
        )
        if self._rng.random() < self._event_probability(rate=rate, dt=dt):
            self._bound_atp[self.r5_index] += 1
            self._free_dnaa_atp -= 1

    def _polymerize_dnaa_adp(self, dt: float) -> None:
        max_polymer = int(self.parameters["polymer_max_length"])
        for idx in self.r1234_indices:
            if self._free_dnaa_adp <= 0:
                return
            if int(self._bound_atp[idx] + self._bound_adp[idx]) >= max_polymer:
                continue
            cooperativity = self._oric_cooperativity(idx)
            rate = (
                self.kb_adp
                * float(self._free_dnaa_adp)
                * cooperativity
                / float(self.parameters["polymerization_rate_scale"])
            )
            if self._rng.random() < self._event_probability(rate=rate, dt=dt):
                self._bound_adp[idx] += 1
                self._free_dnaa_adp -= 1

    def _bind_dnaa_atp(self, dt: float) -> None:
        if self._free_dnaa_atp <= 0:
            return
        free_sites = np.flatnonzero((self._bound_atp + self._bound_adp) == 0)
        if free_sites.size <= 0:
            return
        n_trials = min(int(free_sites.size), self._free_dnaa_atp)
        bind_p = self._event_probability(
            rate=(
                self.kb_atp
                * float(self._free_dnaa_atp)
                / float(self.parameters["binding_rate_scale"])
            ),
            dt=dt,
        )
        if bind_p <= 0.0:
            return
        n_events = int(self._rng.binomial(n_trials, bind_p))
        if n_events <= 0:
            return
        n_events = min(n_events, self._free_dnaa_atp, int(free_sites.size))
        chosen = self._rng.choice(free_sites, size=n_events, replace=False)
        self._bound_atp[chosen] += 1
        self._free_dnaa_atp -= n_events

    def _bind_dnaa_adp(self, dt: float) -> None:
        if self._free_dnaa_adp <= 0:
            return
        free_sites = np.flatnonzero((self._bound_atp + self._bound_adp) == 0)
        if free_sites.size <= 0:
            return
        n_trials = min(int(free_sites.size), self._free_dnaa_adp)
        bind_p = self._event_probability(
            rate=(
                self.kb_adp
                * float(self._free_dnaa_adp)
                / float(self.parameters["binding_rate_scale"])
            ),
            dt=dt,
        )
        if bind_p <= 0.0:
            return
        n_events = int(self._rng.binomial(n_trials, bind_p))
        if n_events <= 0:
            return
        n_events = min(n_events, self._free_dnaa_adp, int(free_sites.size))
        chosen = self._rng.choice(free_sites, size=n_events, replace=False)
        self._bound_adp[chosen] += 1
        self._free_dnaa_adp -= n_events

    def _release_dnaa_atp(self, dt: float) -> None:
        if not np.any(self._bound_atp > 0):
            return
        release_p = self._event_probability(
            rate=self.kd_atp / float(self.parameters["release_rate_scale"]),
            dt=dt,
        )
        if release_p <= 0.0:
            return

        min_r1234 = int(np.min(self._bound_atp[self.r1234_indices]))
        for idx in np.flatnonzero(self._bound_atp > 0):
            if idx in self.r1234_indices and min_r1234 > 0 and self._bound_atp[idx] <= min_r1234:
                continue
            bound = int(self._bound_atp[idx])
            n_release = int(self._rng.binomial(bound, release_p))
            if n_release <= 0:
                continue
            self._bound_atp[idx] -= n_release
            self._free_dnaa_atp += n_release

    def _release_dnaa_adp(self, dt: float) -> None:
        if not np.any(self._bound_adp > 0):
            return
        release_p = self._event_probability(
            rate=self.kd_adp / float(self.parameters["release_rate_scale"]),
            dt=dt,
        )
        if release_p <= 0.0:
            return
        for idx in np.flatnonzero(self._bound_adp > 0):
            bound = int(self._bound_adp[idx])
            n_release = int(self._rng.binomial(bound, release_p))
            if n_release <= 0:
                continue
            self._bound_adp[idx] -= n_release
            self._free_dnaa_adp += n_release

    def _reactivate_free_dnaa_adp(self, dt: float) -> None:
        if self._free_dnaa_adp <= 0:
            return
        membrane_conc = float(self.parameters["membrane_conc"])
        regen_rate = (self.k_regen * membrane_conc) / (self.k_regen_p4 + membrane_conc)
        target = (
            float(self._free_dnaa_adp)
            * regen_rate
            * dt
            / float(self.parameters["regen_rate_scale"])
        )
        n_events = min(self._free_dnaa_adp, max(0, int(np.floor(target))))
        if n_events <= 0:
            return
        self._free_dnaa_adp -= n_events
        self._free_dnaa_atp += n_events

    def _oric_cooperativity(self, idx: int) -> float:
        del idx
        occupied_other = np.count_nonzero(self._bound_atp[self.r1234_indices] > 0)
        coop = 1.0 + self.state_cooperativity * (float(occupied_other) / len(self.r1234_indices))
        return max(1.0, coop)

    def _check_initiation_trigger(self) -> bool:
        threshold_r1234 = int(self.parameters["r1234_threshold"])
        threshold_r5 = int(self.parameters["r5_threshold"])
        r1234_ready = all(self._bound_atp[idx] >= threshold_r1234 for idx in self.r1234_indices)
        r5_ready = self._bound_atp[self.r5_index] >= threshold_r5
        return bool(r1234_ready and r5_ready)

    def _event_probability(self, rate: float, dt: float) -> float:
        if rate <= 0.0 or dt <= 0.0:
            return 0.0
        return float(np.clip(1.0 - np.exp(-rate * dt), a_min=0.0, a_max=1.0))


__all__ = ["KarrReplicationInitiationProcess"]
