"""Vivarium Process port of Karr Cytokinesis.

Faithful port scope:
- Implements Karr's five ordered FtsZ ring phases from ``Cytokinesis.m``.
- Tracks edge-wise ring state plus explicit pinched-diameter geometry.
- Conserves FtsZ subunits across polymer and monomer pools.

Compatibility notes:
- Preserves legacy ``cell.division_progress`` and ``cell.division_complete``
  outputs for existing chassis consumers.
- Keeps the legacy ``requests.karr_cytokinesis.GTP`` key present, but the
  faithful Karr port requests and consumes water for hydrolysis rather than
  soluble GTP.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/Cytokinesis_flat.mat"
_DEFAULT_FTSZ_RING_FIXTURE_PATH = "data/karr_fixtures/per_process/FtsZRing.json"
_DEFAULT_GEOMETRY_FIXTURE_PATH = "data/karr_fixtures/per_process/CellGeometry.json"


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    main_repo = repo_root.parents[1] / "opencell"
    sibling = main_repo / candidate
    if sibling.exists():
        return sibling

    raise FileNotFoundError(f"Path not found: {path}")


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
        out.append(str(_coerce_scalar(raw)))
    return out


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(numeric):
        return float(default)
    return float(numeric)


def _safe_count(value: object) -> int:
    numeric = _safe_float(value, default=0.0)
    rounded = float(np.rint(numeric))
    if abs(numeric - rounded) <= 1.0e-9:
        return max(0, int(rounded))
    return max(0, int(math.floor(numeric)))


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, np.integer)):
        return bool(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            return bool(default)
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "t", "1", "yes"}:
            return True
        if lowered in {"false", "f", "0", "no"}:
            return False
    return bool(value)


def _delta_dict(wids: list[str], before: np.ndarray, after: np.ndarray) -> dict[str, float]:
    delta = after.astype(np.int64) - before.astype(np.int64)
    out: dict[str, float] = {}
    for idx, wid in enumerate(wids):
        step = int(delta[idx])
        if step != 0:
            out[wid] = float(step)
    return out


class KarrCytokinesisProcess(Process):
    """Faithful port of Karr ``Process_Cytokinesis.evolveState``."""

    name = "karr_cytokinesis"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "ftsz_ring_fixture_path": _DEFAULT_FTSZ_RING_FIXTURE_PATH,
        "geometry_fixture_path": _DEFAULT_GEOMETRY_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "gtp_wid": "GTP",
        "min_segregation_progress": 1.0,
        "gating_tolerance": 1.0e-9,
        # Canonical FtsZRing.m constant; override in tests if needed.
        "filament_length_nm": 40.0,
        "rate_filament_binding_membrane": None,
        "rate_filament_dissociation": None,
        "rate_ftsz_gtp_hydrolysis": None,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._load_state_fixtures(
            ftsz_ring_path=self.parameters["ftsz_ring_fixture_path"],
            geometry_path=self.parameters["geometry_fixture_path"],
        )
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        binding_override = self.parameters.get("rate_filament_binding_membrane")
        dissociation_override = self.parameters.get("rate_filament_dissociation")
        hydrolysis_override = self.parameters.get("rate_ftsz_gtp_hydrolysis")

        if binding_override is not None:
            self.rate_filament_binding_membrane = float(binding_override)
        if dissociation_override is not None:
            self.rate_filament_dissociation = float(dissociation_override)
        if hydrolysis_override is not None:
            self.rate_ftsz_gtp_hydrolysis = float(hydrolysis_override)

        self.gtp_wid = str(self.parameters["gtp_wid"])
        self.min_segregation_progress = float(self.parameters["min_segregation_progress"])
        self.gating_tolerance = float(self.parameters["gating_tolerance"])
        self.default_filament_length_nm = float(self.parameters["filament_length_nm"])

        self._substrate_wids = list(self.fixture_substrate_wids)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.fixture_substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.fixture_enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.rate_filament_binding_membrane = float(_coerce_scalar(fx.rateFilamentBindingMembrane))
        self.rate_filament_dissociation = float(_coerce_scalar(fx.rateFilamentDissociation))
        self.rate_ftsz_gtp_hydrolysis = float(_coerce_scalar(fx.rateFtsZGtpHydrolysis))

        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_water = int(_coerce_scalar(fx.substrateIndexs_water)) - 1
        self.substrate_index_hydrogen = int(_coerce_scalar(fx.substrateIndexs_hydrogen)) - 1

        self.enzyme_index_ftsz_gtp_polymer = int(_coerce_scalar(fx.enzymeIndexs_ftsZ_GTP_polymer)) - 1
        self.enzyme_index_ftsz_gdp_polymer = int(_coerce_scalar(fx.enzymeIndexs_ftsZ_GDP_polymer)) - 1
        self.enzyme_index_ftsz_gdp = int(_coerce_scalar(fx.enzymeIndexs_ftsZ_GDP)) - 1
        self.enzyme_index_ftsz_gtp = int(_coerce_scalar(fx.enzymeIndexs_ftsZ_GTP)) - 1

        self.pi_wid = self.fixture_substrate_wids[self.substrate_index_pi]
        self.water_wid = self.fixture_substrate_wids[self.substrate_index_water]
        self.hydrogen_wid = self.fixture_substrate_wids[self.substrate_index_hydrogen]

    def _load_state_fixtures(self, *, ftsz_ring_path: str | Path, geometry_path: str | Path) -> None:
        ftsz_ring_payload = json.loads(_resolve_path(ftsz_ring_path).read_text())
        geometry_payload = json.loads(_resolve_path(geometry_path).read_text())

        ftsz_scalars = ftsz_ring_payload.get("scalars", {})
        geometry_scalars = geometry_payload.get("scalars", {})

        self.num_ftsz_subunits_per_filament = _safe_count(
            ftsz_scalars.get("fixture/numFtsZSubunitsPerFilament", 9)
        )
        self.initial_num_edges_one_straight = _safe_count(
            ftsz_scalars.get("fixture/numEdgesOneStraight", 0)
        )
        self.initial_num_edges_two_straight = _safe_count(
            ftsz_scalars.get("fixture/numEdgesTwoStraight", 0)
        )
        self.initial_num_edges_two_bent = _safe_count(
            ftsz_scalars.get("fixture/numEdgesTwoBent", 0)
        )
        self.initial_num_residual_bent = _safe_count(
            ftsz_scalars.get("fixture/numResidualBent", 0)
        )

        self.initial_width = _safe_float(geometry_scalars.get("fixture/width", 0.0))
        self.initial_pinched_diameter = _safe_float(
            geometry_scalars.get("fixture/pinchedDiameter", self.initial_width)
        )

    def ports_schema(self) -> dict[str, Any]:
        initial_edges = self.calc_num_edges(
            pinched_diameter=self.initial_pinched_diameter,
            filament_length_nm=self.default_filament_length_nm,
        )
        return {
            "cell": {
                "ftsz_ring_complete": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
                "division_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "division_complete": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "chromosome": {
                "segregation_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "segregated": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "geometry": {
                "width": {
                    "_default": self.initial_width,
                    "_updater": "set",
                    "_emit": False,
                },
                "pinchedDiameter": {
                    "_default": self.initial_pinched_diameter,
                    "_updater": "set",
                    "_emit": True,
                },
                "pinched": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "ftsZRing": {
                "numEdges": {
                    "_default": initial_edges,
                    "_updater": "set",
                    "_emit": True,
                },
                "numEdgesOneStraight": {
                    "_default": self.initial_num_edges_one_straight,
                    "_updater": "set",
                    "_emit": True,
                },
                "numEdgesTwoStraight": {
                    "_default": self.initial_num_edges_two_straight,
                    "_updater": "set",
                    "_emit": True,
                },
                "numEdgesTwoBent": {
                    "_default": self.initial_num_edges_two_bent,
                    "_updater": "set",
                    "_emit": True,
                },
                "numResidualBent": {
                    "_default": self.initial_num_residual_bent,
                    "_updater": "set",
                    "_emit": True,
                },
                "numFtsZSubunitsPerFilament": {
                    "_default": self.num_ftsz_subunits_per_filament,
                    "_updater": "set",
                    "_emit": False,
                },
                "filamentLengthInNm": {
                    "_default": self.default_filament_length_nm,
                    "_updater": "set",
                    "_emit": False,
                },
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self._substrate_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.fixture_enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.fixture_enzyme_wids
            },
            "requests": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.water_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_emit": False},
                    self.water_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        _ = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        cell_state = states.get("cell", {})
        chromosome_state = states.get("chromosome", {})
        geometry = self._geometry_state(states.get("geometry", {}), cell_state)
        ring = self._ring_state(states.get("ftsZRing", {}), geometry)

        current_enzymes = self._counts_from_state(states.get("enzymes", {}))
        current_bound = self._counts_from_state(states.get("boundEnzymes", {}))
        next_enzymes = current_enzymes.copy()
        next_bound = current_bound.copy()

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        water_allocated = self._allocated_count(allocated_state, self.water_wid)
        water_requested = self._water_request(ring, geometry, chromosome_state)

        substrate_delta = {wid: 0.0 for wid in self.fixture_substrate_wids}
        segregated = self._segregated(chromosome_state)

        if segregated:
            self._phase_bind_first_and_second_straight(ring, geometry, next_enzymes, next_bound)
            self._phase_unbind_residual_bent(ring, geometry, next_enzymes, next_bound)
            self._phase_hydrolyze_and_bend(
                ring=ring,
                geometry=geometry,
                enzymes=next_enzymes,
                bound=next_bound,
                substrate_delta=substrate_delta,
                water_available=water_allocated,
            )
            self._phase_dissociate_first_bent(ring, next_enzymes, next_bound)

        next_progress = self._division_progress(geometry["pinchedDiameter"])
        current_progress = self._current_division_progress(cell_state, geometry["pinchedDiameter"])
        progress_delta = next_progress - current_progress

        update: dict[str, Any] = {
            "requests": {
                self.name: {
                    self.gtp_wid: 0.0,
                    self.water_wid: float(water_requested),
                }
            },
            "geometry": {
                "width": float(geometry["width"]),
                "pinchedDiameter": float(geometry["pinchedDiameter"]),
                "pinched": bool(geometry["pinched"]),
            },
            "ftsZRing": {
                "numEdges": int(ring["numEdges"]),
                "numEdgesOneStraight": int(ring["numEdgesOneStraight"]),
                "numEdgesTwoStraight": int(ring["numEdgesTwoStraight"]),
                "numEdgesTwoBent": int(ring["numEdgesTwoBent"]),
                "numResidualBent": int(ring["numResidualBent"]),
                "numFtsZSubunitsPerFilament": int(ring["numFtsZSubunitsPerFilament"]),
                "filamentLengthInNm": float(ring["filamentLengthInNm"]),
            },
            "cell": {
                "division_complete": bool(geometry["pinched"]),
            },
        }

        if abs(progress_delta) > 1.0e-12:
            update["cell"]["division_progress"] = float(progress_delta)

        enzyme_delta = _delta_dict(self.fixture_enzyme_wids, current_enzymes, next_enzymes)
        if enzyme_delta:
            update["enzymes"] = enzyme_delta

        bound_delta = _delta_dict(self.fixture_enzyme_wids, current_bound, next_bound)
        if bound_delta:
            update["boundEnzymes"] = bound_delta

        substrate_delta = {
            wid: float(delta) for wid, delta in substrate_delta.items() if abs(float(delta)) > 0.0
        }
        if substrate_delta:
            update["substrates"] = substrate_delta

        return update

    def _geometry_state(
        self,
        geometry_state: dict[str, Any],
        cell_state: dict[str, Any],
    ) -> dict[str, Any]:
        width = _safe_float(geometry_state.get("width", self.initial_width), default=self.initial_width)

        if geometry_state:
            pinched_diameter = _safe_float(
                geometry_state.get("pinchedDiameter", self.initial_pinched_diameter),
                default=self.initial_pinched_diameter,
            )
        else:
            progress = self._current_division_progress(cell_state, self.initial_pinched_diameter)
            pinched_diameter = max(0.0, self.initial_pinched_diameter * (1.0 - progress))

        pinched = _safe_bool(
            geometry_state.get("pinched", pinched_diameter <= 0.0),
            default=pinched_diameter <= 0.0,
        )
        if pinched or pinched_diameter <= 0.0:
            pinched_diameter = 0.0
            pinched = True

        return {
            "width": width,
            "pinchedDiameter": pinched_diameter,
            "pinched": pinched,
        }

    def _ring_state(self, ring_state: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
        filament_length_nm = _safe_float(
            ring_state.get("filamentLengthInNm", self.default_filament_length_nm),
            default=self.default_filament_length_nm,
        )
        num_edges = 0
        if not geometry["pinched"]:
            num_edges = self.calc_num_edges(
                pinched_diameter=float(geometry["pinchedDiameter"]),
                filament_length_nm=filament_length_nm,
            )

        return {
            "numEdges": int(num_edges),
            "numEdgesOneStraight": _safe_count(ring_state.get("numEdgesOneStraight", 0)),
            "numEdgesTwoStraight": _safe_count(ring_state.get("numEdgesTwoStraight", 0)),
            "numEdgesTwoBent": _safe_count(ring_state.get("numEdgesTwoBent", 0)),
            "numResidualBent": _safe_count(ring_state.get("numResidualBent", 0)),
            "numFtsZSubunitsPerFilament": _safe_count(
                ring_state.get("numFtsZSubunitsPerFilament", self.num_ftsz_subunits_per_filament)
            ),
            "filamentLengthInNm": filament_length_nm,
        }

    def _counts_from_state(self, state: dict[str, Any]) -> np.ndarray:
        counts = np.zeros(len(self.fixture_enzyme_wids), dtype=np.int64)
        if not isinstance(state, dict):
            return counts
        for idx, wid in enumerate(self.fixture_enzyme_wids):
            counts[idx] = _safe_count(state.get(wid, 0.0))
        return counts

    def _allocated_count(self, allocated_state: dict[str, Any], wid: str) -> int:
        if not isinstance(allocated_state, dict):
            return 0
        return _safe_count(allocated_state.get(wid, 0.0))

    def _segregated(self, chromosome_state: dict[str, Any]) -> bool:
        if "segregated" in chromosome_state:
            return _safe_bool(chromosome_state.get("segregated", False), default=False)
        segregation_progress = _safe_float(chromosome_state.get("segregation_progress", 0.0))
        return segregation_progress + self.gating_tolerance >= self.min_segregation_progress

    def _water_request(
        self,
        ring: dict[str, Any],
        geometry: dict[str, Any],
        chromosome_state: dict[str, Any],
    ) -> int:
        if not self._segregated(chromosome_state) or geometry["pinched"] or ring["numEdges"] <= 0:
            return 0
        potential_hydrolysis_edges = 0
        if ring["numEdgesTwoBent"] == 0:
            potential_hydrolysis_edges = ring["numEdges"]
        elif (
            ring["numEdgesTwoBent"] + ring["numEdgesTwoStraight"] == ring["numEdges"]
            and ring["numEdgesTwoStraight"] > 0
            and ring["numResidualBent"] == 0
        ):
            potential_hydrolysis_edges = ring["numEdgesTwoStraight"]

        return 2 * ring["numFtsZSubunitsPerFilament"] * max(0, potential_hydrolysis_edges)

    def _phase_bind_first_and_second_straight(
        self,
        ring: dict[str, Any],
        geometry: dict[str, Any],
        enzymes: np.ndarray,
        bound: np.ndarray,
    ) -> None:
        if ring["numEdgesTwoBent"] != 0 or geometry["pinched"]:
            return

        for _ in range(2):
            empty_edges = ring["numEdges"] - ring["numEdgesOneStraight"] - ring["numEdgesTwoStraight"]
            for _ in range(max(0, empty_edges)):
                if (
                    self._rng.random() <= self.rate_filament_binding_membrane
                    and enzymes[self.enzyme_index_ftsz_gtp_polymer] >= 1
                ):
                    enzymes[self.enzyme_index_ftsz_gtp_polymer] -= 1
                    bound[self.enzyme_index_ftsz_gtp_polymer] += 1
                    ring["numEdgesOneStraight"] += 1

        for _ in range(max(0, ring["numEdgesOneStraight"])):
            if (
                self._rng.random() <= self.rate_filament_binding_membrane
                and enzymes[self.enzyme_index_ftsz_gtp_polymer] >= 1
            ):
                enzymes[self.enzyme_index_ftsz_gtp_polymer] -= 1
                bound[self.enzyme_index_ftsz_gtp_polymer] += 1
                ring["numEdgesOneStraight"] -= 1
                ring["numEdgesTwoStraight"] += 1

    def _phase_unbind_residual_bent(
        self,
        ring: dict[str, Any],
        geometry: dict[str, Any],
        enzymes: np.ndarray,
        bound: np.ndarray,
    ) -> None:
        if not (
            ring["numEdgesOneStraight"] + ring["numEdgesTwoStraight"] == ring["numEdges"]
            or geometry["pinched"]
        ):
            return

        for _ in range(max(0, ring["numResidualBent"])):
            if self._rng.random() <= self.rate_filament_dissociation:
                ring["numResidualBent"] -= 1
                bound[self.enzyme_index_ftsz_gdp_polymer] -= 1
                enzymes[self.enzyme_index_ftsz_gdp] += ring["numFtsZSubunitsPerFilament"]

    def _phase_hydrolyze_and_bend(
        self,
        *,
        ring: dict[str, Any],
        geometry: dict[str, Any],
        enzymes: np.ndarray,
        bound: np.ndarray,
        substrate_delta: dict[str, float],
        water_available: int,
    ) -> None:
        if not (
            ring["numEdgesTwoBent"] + ring["numEdgesTwoStraight"] == ring["numEdges"]
            and ring["numEdgesTwoStraight"] > 0
            and ring["numResidualBent"] == 0
        ):
            return

        hydrolysis_cost = 2 * ring["numFtsZSubunitsPerFilament"]
        for _ in range(max(0, ring["numEdgesTwoStraight"])):
            if self._rng.random() <= self.rate_ftsz_gtp_hydrolysis and water_available >= hydrolysis_cost:
                ring["numEdgesTwoStraight"] -= 1
                ring["numEdgesTwoBent"] += 1
                water_available -= hydrolysis_cost
                substrate_delta[self.water_wid] -= float(hydrolysis_cost)
                substrate_delta[self.pi_wid] += float(hydrolysis_cost)
                substrate_delta[self.hydrogen_wid] += float(hydrolysis_cost)
                bound[self.enzyme_index_ftsz_gtp_polymer] -= 2
                bound[self.enzyme_index_ftsz_gdp_polymer] += 2

        if ring["numEdgesTwoStraight"] == 0 and not geometry["pinched"]:
            geometry["pinchedDiameter"] = self.calc_next_pinched_diameter(
                pinched_diameter=float(geometry["pinchedDiameter"]),
                filament_length_nm=float(ring["filamentLengthInNm"]),
            )
            geometry["pinched"] = geometry["pinchedDiameter"] <= 0.0
            ring["numEdges"] = (
                0
                if geometry["pinched"]
                else self.calc_num_edges(
                    pinched_diameter=float(geometry["pinchedDiameter"]),
                    filament_length_nm=float(ring["filamentLengthInNm"]),
                )
            )

    def _phase_dissociate_first_bent(
        self,
        ring: dict[str, Any],
        enzymes: np.ndarray,
        bound: np.ndarray,
    ) -> None:
        if ring["numEdgesTwoStraight"] != 0:
            return

        for _ in range(max(0, ring["numEdgesTwoBent"])):
            if self._rng.random() <= self.rate_filament_dissociation:
                ring["numEdgesTwoBent"] -= 1
                ring["numResidualBent"] += 1
                bound[self.enzyme_index_ftsz_gdp_polymer] -= 1
                enzymes[self.enzyme_index_ftsz_gdp] += ring["numFtsZSubunitsPerFilament"]

    def _current_division_progress(self, cell_state: dict[str, Any], pinched_diameter: float) -> float:
        raw_progress = _safe_float(cell_state.get("division_progress", float("nan")), default=float("nan"))
        if math.isfinite(raw_progress):
            return self._clamp01(raw_progress)
        return self._division_progress(pinched_diameter)

    def _division_progress(self, pinched_diameter: float) -> float:
        if self.initial_pinched_diameter <= 0.0:
            return 1.0 if pinched_diameter <= 0.0 else 0.0
        progress = 1.0 - (_safe_float(pinched_diameter) / self.initial_pinched_diameter)
        return self._clamp01(progress)

    @staticmethod
    def _clamp01(value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return float(min(1.0, max(0.0, value)))

    @staticmethod
    def calc_num_edges(pinched_diameter: float, filament_length_nm: float) -> int:
        if pinched_diameter <= 0.0 or filament_length_nm <= 0.0:
            return 0
        filament_m = filament_length_nm * 1.0e-9
        ratio = filament_m / pinched_diameter
        if ratio >= 1.0:
            return 2
        ratio = max(0.0, min(1.0, ratio))
        return int(math.floor(math.pi / math.asin(ratio)))

    @classmethod
    def calc_next_pinched_diameter(cls, pinched_diameter: float, filament_length_nm: float) -> float:
        if pinched_diameter <= 0.0:
            return 0.0
        num_edges = cls.calc_num_edges(pinched_diameter=pinched_diameter, filament_length_nm=filament_length_nm)
        if num_edges <= 0:
            return 0.0

        filament_m = filament_length_nm * 1.0e-9
        floored_diameter = filament_m / math.sin(math.pi / num_edges)
        new_diameter = filament_m * num_edges / math.pi
        result = new_diameter + (pinched_diameter - floored_diameter)
        if result <= filament_m:
            return 0.0
        return float(result)

    @classmethod
    def calc_required_pinching_cycles(cls, pinched_diameter: float, filament_length_nm: float) -> int:
        if pinched_diameter <= 0.0:
            return 0

        cycles = 0
        current = float(pinched_diameter)
        while current > 0.0:
            current = cls.calc_next_pinched_diameter(
                pinched_diameter=current,
                filament_length_nm=filament_length_nm,
            )
            cycles += 1
            if cycles > 100_000:
                raise RuntimeError("calc_required_pinching_cycles did not converge")
        return cycles


__all__ = ["KarrCytokinesisProcess"]
