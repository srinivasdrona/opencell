"""Sparse-triple chromosome state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import h5py
import numpy as np

CHROMOSOME_FIELDS: tuple[str, ...] = (
    "polymerizedRegions",
    "linkingNumbers",
    "monomerBoundSites",
    "complexBoundSites",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "damagedBases",
    "intrastrandCrossLinks",
    "strandBreaks",
    "hollidayJunctions",
)

_MATLAB_CLASS_TO_DTYPE: dict[str, Any] = {
    "double": np.float64,
    "single": np.float32,
    "int64": np.int64,
    "int32": np.int32,
    "int16": np.int16,
    "int8": np.int8,
    "uint64": np.uint64,
    "uint32": np.uint32,
    "uint16": np.uint16,
    "uint8": np.uint8,
    "logical": np.bool_,
}


def _coerce_shape(shape: tuple[int, int] | list[int] | np.ndarray) -> tuple[int, int]:
    values = tuple(int(x) for x in np.asarray(shape, dtype=np.int64).reshape(-1)[:2])
    if len(values) != 2:
        raise ValueError(f"Chromosome sparse triple shape must have 2 dimensions, got {shape!r}")
    if values[0] <= 0 or values[1] <= 0:
        raise ValueError(f"Chromosome sparse triple shape must be positive, got {values!r}")
    return values


def _copy_array(value: np.ndarray, *, dtype: Any) -> np.ndarray:
    return np.asarray(value, dtype=dtype).reshape(-1).copy()


def _canonicalize_triplet(
    positions: np.ndarray,
    strands: np.ndarray,
    values: np.ndarray,
    shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    row_count, col_count = shape
    positions = _copy_array(positions, dtype=np.int64)
    strands = _copy_array(strands, dtype=np.int64)
    values = np.asarray(values).reshape(-1).copy()

    if not (positions.size == strands.size == values.size):
        raise ValueError(
            "Sparse triple arrays must have equal lengths: "
            f"positions={positions.size}, strands={strands.size}, values={values.size}"
        )
    if positions.size == 0:
        return (
            np.array([], dtype=np.int64),
            np.array([], dtype=np.int8),
            np.array([], dtype=np.int32),
        )

    positions = np.mod(positions, row_count)
    if np.any((strands < 0) | (strands >= col_count)):
        raise ValueError(
            f"Sparse triple strands must fall in [0, {col_count}), got {strands.tolist()}"
        )

    order = np.lexsort((strands, positions))
    positions = positions[order]
    strands = strands[order]
    values = values[order]

    starts = np.concatenate(
        (
            np.array([0], dtype=np.int64),
            np.flatnonzero((positions[1:] != positions[:-1]) | (strands[1:] != strands[:-1])) + 1,
        )
    )
    reduced_positions = positions[starts]
    reduced_strands = strands[starts]
    reduced_values = np.add.reduceat(values.astype(np.int64, copy=False), starts)

    keep = reduced_values != 0
    return (
        reduced_positions[keep].astype(np.int64, copy=False),
        reduced_strands[keep].astype(np.int8, copy=False),
        reduced_values[keep].astype(np.int32, copy=False),
    )


def _decode_matlab_class(dataset: h5py.Dataset) -> str:
    raw = dataset.attrs.get("MATLAB_class", b"")
    if isinstance(raw, bytes):
        return raw.decode("ascii", errors="ignore")
    return str(raw)


def _read_matlab_dataset(dataset: h5py.Dataset) -> str | np.ndarray:
    matlab_class = _decode_matlab_class(dataset)
    if int(dataset.attrs.get("MATLAB_empty", 0)) == 1:
        if matlab_class == "char":
            return ""
        return np.array([], dtype=_MATLAB_CLASS_TO_DTYPE.get(matlab_class, np.float64))

    raw = np.asarray(dataset[()])
    if matlab_class == "char":
        return "".join(chr(int(x)) for x in raw.reshape(-1) if int(x) != 0)

    dtype = _MATLAB_CLASS_TO_DTYPE.get(matlab_class)
    if dtype is None:
        return raw
    return raw.astype(dtype, copy=False)


def sparse_triplet_schema(
    shape: tuple[int, int],
    *,
    emit: bool = True,
) -> dict[str, dict[str, Any]]:
    """Vivarium schema for a sparse-triple leaf."""

    norm_shape = _coerce_shape(shape)
    return {
        "positions": {
            "_default": np.array([], dtype=np.int64),
            "_updater": "set",
            "_emit": emit,
        },
        "strands": {
            "_default": np.array([], dtype=np.int8),
            "_updater": "set",
            "_emit": emit,
        },
        "values": {
            "_default": np.array([], dtype=np.int32),
            "_updater": "set",
            "_emit": emit,
        },
        "shape": {
            "_default": norm_shape,
            "_updater": "set",
            "_emit": emit,
        },
    }


@dataclass(frozen=True)
class SparseTriplet:
    """Canonical 0-based sparse-triple representation for chromosome fields."""

    positions: np.ndarray
    strands: np.ndarray
    values: np.ndarray
    shape: tuple[int, int]

    def __post_init__(self) -> None:
        shape = _coerce_shape(self.shape)
        positions, strands, values = _canonicalize_triplet(
            self.positions,
            self.strands,
            self.values,
            shape,
        )
        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "strands", strands)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "shape", shape)

    @classmethod
    def empty(cls, rows: int, cols: int) -> "SparseTriplet":
        return cls(
            positions=np.array([], dtype=np.int64),
            strands=np.array([], dtype=np.int8),
            values=np.array([], dtype=np.int32),
            shape=(int(rows), int(cols)),
        )

    @classmethod
    def from_state(
        cls,
        payload: Mapping[str, Any] | "SparseTriplet" | None,
        *,
        shape: tuple[int, int] | None = None,
    ) -> "SparseTriplet":
        if isinstance(payload, SparseTriplet):
            return payload.copy()
        if payload is None:
            if shape is None:
                raise ValueError("shape is required when building an empty SparseTriplet")
            return cls.empty(*shape)
        if not isinstance(payload, Mapping):
            raise TypeError(f"Unsupported sparse triplet payload: {type(payload)!r}")

        payload_shape = payload.get("shape", shape)
        if payload_shape is None:
            raise ValueError("SparseTriplet payload missing required shape")
        return cls(
            positions=np.asarray(payload.get("positions", []), dtype=np.int64),
            strands=np.asarray(payload.get("strands", []), dtype=np.int64),
            values=np.asarray(payload.get("values", []), dtype=np.int64),
            shape=_coerce_shape(payload_shape),
        )

    @classmethod
    def from_hdf5_group(cls, group: h5py.Group) -> "SparseTriplet":
        error = _read_matlab_dataset(group["error"])
        if isinstance(error, str) and error:
            raise ValueError(f"MATLAB serializer reported sparse-field error: {error}")
        shape = _coerce_shape(_read_matlab_dataset(group["shape"]))
        positions = np.asarray(_read_matlab_dataset(group["positions"]), dtype=np.int64)
        strands = np.asarray(_read_matlab_dataset(group["strands"]), dtype=np.int64)
        values = np.asarray(_read_matlab_dataset(group["values"]), dtype=np.int64)
        if positions.size:
            positions = positions - 1
        if strands.size:
            strands = strands - 1
        return cls(positions=positions, strands=strands, values=values, shape=shape)

    @classmethod
    def from_regions(
        cls,
        regions: list[tuple[int, int, int]] | tuple[tuple[int, int, int], ...],
        *,
        shape: tuple[int, int],
    ) -> "SparseTriplet":
        positions: list[int] = []
        strands: list[int] = []
        values: list[int] = []
        for start, strand, length in regions:
            if int(length) == 0:
                continue
            positions.append(int(start))
            strands.append(int(strand))
            values.append(int(length))
        return cls(
            positions=np.asarray(positions, dtype=np.int64),
            strands=np.asarray(strands, dtype=np.int64),
            values=np.asarray(values, dtype=np.int64),
            shape=shape,
        )

    def copy(self) -> "SparseTriplet":
        return SparseTriplet(
            positions=self.positions.copy(),
            strands=self.strands.copy(),
            values=self.values.copy(),
            shape=self.shape,
        )

    def calc_num_edges(self) -> int:
        return int(self.values.size)

    def circular_normalize(self) -> "SparseTriplet":
        return SparseTriplet(
            positions=self.positions,
            strands=self.strands,
            values=self.values,
            shape=self.shape,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "positions": self.positions.copy(),
            "strands": self.strands.copy(),
            "values": self.values.copy(),
            "shape": self.shape,
        }

    def to_regions(self) -> list[tuple[int, int, int]]:
        return [
            (int(position), int(strand), int(value))
            for position, strand, value in zip(
                self.positions.tolist(),
                self.strands.tolist(),
                self.values.tolist(),
                strict=False,
            )
        ]


class ChromosomeStore:
    """Sparse-triple chromosome state for the 11 Karr chromosome fields.

    Defaults are M. genitalium-specific (Karr 2012). For other organisms,
    pass explicit `shape` to __init__. See `opencell/m_gen_constants.py`.
    """

    # Defaults are sourced from m_gen_constants to keep biology-specific
    # values centralized. Generic primitives accept these as parameters.
    from opencell.m_gen_constants import (
        GENOME_LENGTH_BP as _GENOME_LENGTH_BP,
        N_CHROMOSOME_COMPARTMENTS as _N_CHROMOSOME_COMPARTMENTS,
    )
    DEFAULT_SEQUENCE_LEN = _GENOME_LENGTH_BP
    DEFAULT_N_COMPARTMENTS = _N_CHROMOSOME_COMPARTMENTS
    FIELDS = CHROMOSOME_FIELDS

    def __init__(
        self,
        *,
        shape: tuple[int, int] = (DEFAULT_SEQUENCE_LEN, DEFAULT_N_COMPARTMENTS),
        fields: Mapping[str, SparseTriplet] | None = None,
    ) -> None:
        self.shape = _coerce_shape(shape)
        empty = SparseTriplet.empty(*self.shape)
        self._fields: dict[str, SparseTriplet] = {name: empty.copy() for name in self.FIELDS}
        if fields is not None:
            for name, triplet in fields.items():
                self.set_field(name, triplet)

    def copy(self) -> "ChromosomeStore":
        return ChromosomeStore(shape=self.shape, fields=self._fields)

    def calc_num_edges(self, field_name: str) -> int:
        return self.get_field(field_name).calc_num_edges()

    def get_field(self, name: str) -> SparseTriplet:
        if name not in self._fields:
            raise KeyError(f"Unknown chromosome field: {name}")
        return self._fields[name].copy()

    def set_field(self, name: str, triplet: SparseTriplet | Mapping[str, Any]) -> None:
        if name not in self._fields:
            raise KeyError(f"Unknown chromosome field: {name}")
        value = SparseTriplet.from_state(triplet, shape=self.shape)
        if value.shape != self.shape:
            raise ValueError(
                f"Field {name} shape mismatch: store={self.shape!r}, triplet={value.shape!r}"
            )
        self._fields[name] = value.circular_normalize()

    def to_state(self) -> dict[str, Any]:
        return {name: triplet.to_state() for name, triplet in self._fields.items()}

    @classmethod
    def from_state_mapping(
        cls,
        payload: Mapping[str, Any] | None,
        *,
        shape: tuple[int, int] = (DEFAULT_SEQUENCE_LEN, DEFAULT_N_COMPARTMENTS),
    ) -> "ChromosomeStore":
        store = cls(shape=shape)
        if not isinstance(payload, Mapping):
            return store
        for name in cls.FIELDS:
            node = payload.get(name)
            if isinstance(node, Mapping):
                store.set_field(name, node)
        return store

    @classmethod
    def from_hdf5_group(cls, group: h5py.Group) -> "ChromosomeStore":
        sequence_len = int(np.asarray(group["sequenceLen"][()]).reshape(-1)[0])
        n_compartments = int(np.asarray(group["nCompartments"][()]).reshape(-1)[0])
        store = cls(shape=(sequence_len, n_compartments))
        for field_name in cls.FIELDS:
            if field_name in group:
                store.set_field(field_name, SparseTriplet.from_hdf5_group(group[field_name]))
        return store

    @classmethod
    def from_trace_tick(
        cls,
        path: str | Path,
        *,
        tick: int = 0,
        group_name: str = "states_before",
    ) -> "ChromosomeStore":
        with h5py.File(Path(path), "r") as handle:
            dataset = handle[f"{group_name}/chromosome"]
            ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
            return cls.from_hdf5_group(handle[ref])


__all__ = [
    "CHROMOSOME_FIELDS",
    "ChromosomeStore",
    "SparseTriplet",
    "sparse_triplet_schema",
]
