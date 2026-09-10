"""Sparse-triple chromosome state helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
CHROMOSOME_HIDDEN_STATE_KEY = "_hidden_chromosome_state"
CHROMOSOME_HIDDEN_SPARSE_FIELDS: tuple[str, ...] = (
    "damagedSites",
    "singleStrandedRegions",
    "doubleStrandedRegions",
    "supercoils",
    "superhelicalDensity",
    "supercoiled",
)
CHROMOSOME_HIDDEN_SCALAR_FIELDS: tuple[str, ...] = (
    "validated",
    "validated_damaged",
    "validated_polymerizedRegions",
    "validated_linkingNumbers",
    "validated_singleStrandedRegions",
    "validated_doubleStrandedRegions",
    "validated_supercoils",
    "validated_superhelicalDensity",
    "validated_supercoiled",
    "validated_damagedSites",
    "validated_damagedSites_shifted_incm6AD",
    "validated_damagedSites_nonRedundant",
    "validated_damagedSites_excm6AD",
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

_DNA_STRANDEDNESS_SSDNA = 1
_DNA_STRANDEDNESS_DSDNA = 2


def _coerce_shape(shape: tuple[int, int] | list[int] | np.ndarray) -> tuple[int, int]:
    values = tuple(int(x) for x in np.asarray(shape, dtype=np.int64).reshape(-1)[:2])
    if len(values) != 2:
        raise ValueError(f"Chromosome sparse triple shape must have 2 dimensions, got {shape!r}")
    if values[0] <= 0 or values[1] <= 0:
        raise ValueError(f"Chromosome sparse triple shape must be positive, got {values!r}")
    return values


def _copy_array(value: np.ndarray, *, dtype: Any) -> np.ndarray:
    return np.asarray(value, dtype=dtype).reshape(-1).copy()


def _coerce_vector(value: Any, *, dtype: Any, name: str, size: int | None = None) -> np.ndarray:
    out = np.asarray(value, dtype=dtype).reshape(-1).copy()
    if size is not None and out.size != size:
        raise ValueError(f"{name} must have {size} entries, got {out.size}")
    return out


def _split_wrapping_interval(start: int, length: int, sequence_len: int) -> list[tuple[int, int]]:
    if length <= 0:
        return []
    norm_start = int(start) % int(sequence_len)
    norm_length = int(length)
    if norm_length >= int(sequence_len):
        return [(0, int(sequence_len) - 1)]
    end = norm_start + norm_length - 1
    if end < int(sequence_len):
        return [(norm_start, end)]
    return [
        (norm_start, int(sequence_len) - 1),
        (0, int(end % int(sequence_len))),
    ]


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


def _copy_hidden_scalar(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        arr = np.asarray(value).copy()
        if arr.size == 1:
            return arr.reshape(-1)[0].item()
        return arr
    if isinstance(value, np.generic):
        return value.item()
    return value


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
    def empty(cls, rows: int, cols: int) -> SparseTriplet:
        return cls(
            positions=np.array([], dtype=np.int64),
            strands=np.array([], dtype=np.int8),
            values=np.array([], dtype=np.int32),
            shape=(int(rows), int(cols)),
        )

    @classmethod
    def from_state(
        cls,
        payload: Mapping[str, Any] | SparseTriplet | None,
        *,
        shape: tuple[int, int] | None = None,
    ) -> SparseTriplet:
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
    def from_hdf5_group(cls, group: h5py.Group) -> SparseTriplet:
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
    ) -> SparseTriplet:
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

    def copy(self) -> SparseTriplet:
        return SparseTriplet(
            positions=self.positions.copy(),
            strands=self.strands.copy(),
            values=self.values.copy(),
            shape=self.shape,
        )

    def calc_num_edges(self) -> int:
        return int(self.values.size)

    def circular_normalize(self) -> SparseTriplet:
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


@dataclass(frozen=True)
class AuxiliarySparseField:
    """Read-only sparse payload for trace-only chromosome caches."""

    positions: np.ndarray
    strands: np.ndarray
    values: np.ndarray
    shape: tuple[int, int]

    def __post_init__(self) -> None:
        shape = _coerce_shape(self.shape)
        positions = _copy_array(self.positions, dtype=np.int64)
        strands = _copy_array(self.strands, dtype=np.int64)
        values = np.asarray(self.values).reshape(-1).copy()

        if not (positions.size == strands.size == values.size):
            raise ValueError(
                "Auxiliary sparse arrays must have equal lengths: "
                f"positions={positions.size}, strands={strands.size}, values={values.size}"
            )
        if positions.size:
            positions = np.mod(positions, shape[0])
            if np.any((strands < 0) | (strands >= shape[1])):
                raise ValueError(
                    f"Auxiliary sparse strands must fall in [0, {shape[1]}), "
                    f"got {strands.tolist()}"
                )
            order = np.lexsort((strands, positions))
            positions = positions[order]
            strands = strands[order]
            values = values[order]

        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "strands", strands.astype(np.int8, copy=False))
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "shape", shape)

    @classmethod
    def empty(cls, rows: int, cols: int) -> AuxiliarySparseField:
        return cls(
            positions=np.array([], dtype=np.int64),
            strands=np.array([], dtype=np.int8),
            values=np.array([], dtype=np.float64),
            shape=(int(rows), int(cols)),
        )

    @classmethod
    def from_state(
        cls,
        payload: Mapping[str, Any] | AuxiliarySparseField | None,
        *,
        shape: tuple[int, int] | None = None,
    ) -> AuxiliarySparseField:
        if isinstance(payload, AuxiliarySparseField):
            return payload.copy()
        if payload is None:
            if shape is None:
                raise ValueError("shape is required when building an empty AuxiliarySparseField")
            return cls.empty(*shape)
        if not isinstance(payload, Mapping):
            raise TypeError(f"Unsupported auxiliary sparse payload: {type(payload)!r}")
        payload_shape = payload.get("shape", shape)
        if payload_shape is None:
            raise ValueError("Auxiliary sparse payload missing required shape")
        return cls(
            positions=np.asarray(payload.get("positions", []), dtype=np.int64),
            strands=np.asarray(payload.get("strands", []), dtype=np.int64),
            values=np.asarray(payload.get("values", [])),
            shape=_coerce_shape(payload_shape),
        )

    @classmethod
    def from_hdf5_group(cls, group: h5py.Group) -> AuxiliarySparseField:
        error = _read_matlab_dataset(group["error"])
        if isinstance(error, str) and error:
            raise ValueError(f"MATLAB serializer reported auxiliary sparse-field error: {error}")
        shape = _coerce_shape(_read_matlab_dataset(group["shape"]))
        positions = np.asarray(_read_matlab_dataset(group["positions"]), dtype=np.int64)
        strands = np.asarray(_read_matlab_dataset(group["strands"]), dtype=np.int64)
        values = np.asarray(_read_matlab_dataset(group["values"]))
        if positions.size:
            positions = positions - 1
        if strands.size:
            strands = strands - 1
        return cls(positions=positions, strands=strands, values=values, shape=shape)

    def copy(self) -> AuxiliarySparseField:
        return AuxiliarySparseField(
            positions=self.positions.copy(),
            strands=self.strands.copy(),
            values=self.values.copy(),
            shape=self.shape,
        )

    def calc_num_edges(self) -> int:
        return int(self.values.size)

    def to_state(self) -> dict[str, Any]:
        return {
            "positions": self.positions.copy(),
            "strands": self.strands.copy(),
            "values": self.values.copy(),
            "shape": self.shape,
        }

    def to_regions(self) -> list[tuple[int, int, Any]]:
        return [
            (int(position), int(strand), value)
            for position, strand, value in zip(
                self.positions.tolist(),
                self.strands.tolist(),
                self.values.tolist(),
                strict=False,
            )
        ]


@dataclass(frozen=True)
class ProteinBindingSideEffect:
    molecule_kind: str
    global_index: int
    mature_delta: int
    bound_delta: int


@dataclass(frozen=True)
class ChromosomeBindingResult:
    n_bound: int
    released_monomers: np.ndarray
    released_complexes: np.ndarray
    side_effects: tuple[ProteinBindingSideEffect, ...]


def merge_adjacent_regions(triplet: SparseTriplet) -> SparseTriplet:
    """Merge touching same-strand run-length regions into one entry.

    Matches Karr's ``Chromosome.mergeAdjacentRegions`` /
    ``mergeOwnAdjacentRegions`` invariant (``Chromosome.m:~2536-2567``),
    applied to run-length ``polymerizedRegions``-style fields (each entry
    is the half-open interval ``[position, position + value)`` on a given
    strand):

    - Two entries on the same strand whose intervals exactly touch
      (``end_i == start_{i+1}``) are collapsed into a single entry
      spanning both.
    - Two entries on the same strand whose intervals actually overlap
      (``end_i > start_{i+1}``) indicate corrupt state and raise
      ``ValueError``, mirroring Karr's own fatal
      ``'polymerizedRegions is corrupt'`` check -- overlap must never be
      silently resolved.
    - A region is never treated as wrapping past ``shape[0]``: Karr's own
      ``CircularSparseMat`` representation always splits any region that
      crosses the chromosome origin into two separate entries (confirmed
      directly against the real seed-0 oracle trace, where an
      origin-centered bubble on strand 4 is stored as two entries
      straddling position 0, never as one entry whose length exceeds the
      remaining distance to ``shape[0]``). A ``position + value`` that
      exceeds ``shape[0]`` is therefore itself invalid input and is
      rejected the same way as an overlap, not silently reinterpreted as
      a wrap.

    Not applicable to point-source fields such as ``complexBoundSites``
    or ``strandBreaks``, whose ``value`` is not a run length.
    """
    row_count, col_count = triplet.shape
    positions = triplet.positions
    strands = triplet.strands
    values = triplet.values

    out_positions: list[int] = []
    out_strands: list[int] = []
    out_values: list[int] = []

    for strand in range(col_count):
        mask = strands == strand
        if not np.any(mask):
            continue
        strand_positions = positions[mask]
        strand_values = values[mask]

        if np.any(strand_values <= 0):
            raise ValueError(
                "polymerizedRegions is corrupt: non-positive region length on strand "
                f"{strand}: {strand_values.tolist()!r}"
            )
        overflow = strand_positions + strand_values > row_count
        if np.any(overflow):
            raise ValueError(
                "polymerizedRegions is corrupt: region exceeds chromosome length on strand "
                f"{strand} (shape[0]={row_count}): "
                f"{list(zip(strand_positions[overflow].tolist(), strand_values[overflow].tolist(), strict=True))!r}"
            )

        order = np.argsort(strand_positions, kind="stable")
        starts = strand_positions[order].tolist()
        lengths = strand_values[order].tolist()

        merged_starts: list[int] = []
        merged_lengths: list[int] = []
        for start, length in zip(starts, lengths, strict=True):
            if merged_starts:
                prior_end = merged_starts[-1] + merged_lengths[-1]
                if start < prior_end:
                    raise ValueError(
                        "polymerizedRegions is corrupt: overlapping regions on strand "
                        f"{strand} (prior end {prior_end}, next start {start})"
                    )
                if start == prior_end:
                    merged_lengths[-1] += length
                    continue
            merged_starts.append(start)
            merged_lengths.append(length)

        out_positions.extend(merged_starts)
        out_strands.extend([strand] * len(merged_starts))
        out_values.extend(merged_lengths)

    return SparseTriplet(
        positions=np.asarray(out_positions, dtype=np.int64),
        strands=np.asarray(out_strands, dtype=np.int64),
        values=np.asarray(out_values, dtype=np.int64),
        shape=triplet.shape,
    )


class ChromosomeStore:
    """Sparse-triple chromosome state for the 11 Karr chromosome fields.

    Defaults are M. genitalium-specific (Karr 2012). For other organisms,
    pass explicit `shape` to __init__. See `opencell/m_gen_constants.py`.
    """

    # Defaults are sourced from m_gen_constants to keep biology-specific
    # values centralized. Generic primitives accept these as parameters.
    from opencell.m_gen_constants import (
        GENOME_LENGTH_BP as _GENOME_LENGTH_BP,
    )
    from opencell.m_gen_constants import (
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
        hidden_sparse_fields: Mapping[str, AuxiliarySparseField] | None = None,
        hidden_scalar_fields: Mapping[str, Any] | None = None,
    ) -> None:
        self.shape = _coerce_shape(shape)
        empty = SparseTriplet.empty(*self.shape)
        self._fields: dict[str, SparseTriplet] = {name: empty.copy() for name in self.FIELDS}
        if fields is not None:
            for name, triplet in fields.items():
                self.set_field(name, triplet)
        self._hidden_sparse_fields: dict[str, AuxiliarySparseField] = {}
        if hidden_sparse_fields is not None:
            for name, field in hidden_sparse_fields.items():
                self.set_hidden_sparse_field(name, field)
        self._hidden_scalar_fields: dict[str, Any] = {}
        if hidden_scalar_fields is not None:
            for name, value in hidden_scalar_fields.items():
                self.set_hidden_scalar(name, value)

    def copy(self) -> ChromosomeStore:
        return ChromosomeStore(
            shape=self.shape,
            fields=self._fields,
            hidden_sparse_fields=self._hidden_sparse_fields,
            hidden_scalar_fields=self._hidden_scalar_fields,
        )

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

    def has_hidden_sparse_field(self, name: str) -> bool:
        return name in self._hidden_sparse_fields

    def get_hidden_sparse_field(self, name: str) -> AuxiliarySparseField:
        if name not in self._hidden_sparse_fields:
            raise KeyError(f"Unknown hidden chromosome sparse field: {name}")
        return self._hidden_sparse_fields[name].copy()

    def set_hidden_sparse_field(
        self,
        name: str,
        field: AuxiliarySparseField | Mapping[str, Any],
    ) -> None:
        if name not in CHROMOSOME_HIDDEN_SPARSE_FIELDS:
            raise KeyError(f"Unknown hidden chromosome sparse field: {name}")
        value = AuxiliarySparseField.from_state(field, shape=self.shape)
        if value.shape != self.shape:
            raise ValueError(
                f"Hidden sparse field {name} shape mismatch: store={self.shape!r}, "
                f"field={value.shape!r}"
            )
        self._hidden_sparse_fields[name] = value

    def has_hidden_scalar(self, name: str) -> bool:
        return name in self._hidden_scalar_fields

    def get_hidden_scalar(self, name: str) -> Any:
        if name not in self._hidden_scalar_fields:
            raise KeyError(f"Unknown hidden chromosome scalar field: {name}")
        return _copy_hidden_scalar(self._hidden_scalar_fields[name])

    def set_hidden_scalar(self, name: str, value: Any) -> None:
        if name not in CHROMOSOME_HIDDEN_SCALAR_FIELDS:
            raise KeyError(f"Unknown hidden chromosome scalar field: {name}")
        self._hidden_scalar_fields[name] = _copy_hidden_scalar(value)

    def _overlapping_bound_site_mask(
        self,
        *,
        triplet: SparseTriplet,
        footprints: np.ndarray,
        site_binding_strandedness: np.ndarray,
        query_positions: np.ndarray,
        query_strands: np.ndarray,
        query_lengths: np.ndarray,
        binding_both_strands: bool,
        region_both_strands: bool,
    ) -> np.ndarray:
        if triplet.positions.size == 0 or query_positions.size == 0:
            return np.zeros(triplet.positions.size, dtype=bool)

        query_segments: list[tuple[int, int, int]] = []
        for position, strand, length in zip(
            query_positions.tolist(),
            query_strands.tolist(),
            query_lengths.tolist(),
            strict=False,
        ):
            if int(length) <= 0:
                continue
            norm_strand = int(strand) // 2 if binding_both_strands else int(strand)
            for start, end in _split_wrapping_interval(int(position), int(length), self.shape[0]):
                query_segments.append((norm_strand, int(start), int(end)))
        if not query_segments:
            return np.zeros(triplet.positions.size, dtype=bool)

        candidate_segments: list[tuple[int, int, int, int]] = []
        for idx, (position, strand, footprint, strandedness) in enumerate(
            zip(
                triplet.positions.tolist(),
                triplet.strands.tolist(),
                footprints.tolist(),
                site_binding_strandedness.tolist(),
                strict=False,
            )
        ):
            if int(footprint) <= 0:
                continue
            candidate_strands: list[int]
            if binding_both_strands:
                candidate_strands = [int(strand) // 2]
            elif region_both_strands and int(strandedness) == _DNA_STRANDEDNESS_DSDNA:
                pair_start = 2 * (int(strand) // 2)
                candidate_strands = [pair_start, pair_start + 1]
            else:
                candidate_strands = [int(strand)]
            for candidate_strand in candidate_strands:
                for start, end in _split_wrapping_interval(int(position), int(footprint), self.shape[0]):
                    candidate_segments.append((idx, candidate_strand, int(start), int(end)))

        overlapping = np.zeros(triplet.positions.size, dtype=bool)
        for query_strand, query_start, query_end in query_segments:
            for idx, candidate_strand, candidate_start, candidate_end in candidate_segments:
                if candidate_strand != query_strand:
                    continue
                if candidate_start <= query_end and candidate_end >= query_start:
                    overlapping[idx] = True
        return overlapping

    def _set_region_bound_sites_unbound(
        self,
        *,
        field_name: str,
        query_positions: np.ndarray,
        query_strands: np.ndarray,
        query_lengths: np.ndarray,
        main_effect_indices: np.ndarray,
        footprints: np.ndarray,
        binding_strandedness: np.ndarray,
        binding_both_strands: bool,
        region_both_strands: bool,
    ) -> tuple[np.ndarray, tuple[ProteinBindingSideEffect, ...]]:
        triplet = self.get_field(field_name)
        released = np.zeros(main_effect_indices.size, dtype=np.int64)
        if triplet.positions.size == 0:
            return released, ()

        overlap = self._overlapping_bound_site_mask(
            triplet=triplet,
            footprints=footprints[triplet.values.astype(np.int64, copy=False) - 1],
            site_binding_strandedness=binding_strandedness[
                triplet.values.astype(np.int64, copy=False) - 1
            ],
            query_positions=query_positions,
            query_strands=query_strands,
            query_lengths=query_lengths,
            binding_both_strands=binding_both_strands,
            region_both_strands=region_both_strands,
        )
        if not np.any(overlap):
            return released, ()

        side_effects: list[ProteinBindingSideEffect] = []
        overlap_values = triplet.values[overlap].astype(np.int64, copy=False)
        unique_values, counts = np.unique(overlap_values, return_counts=True)
        for global_index, count in zip(unique_values.tolist(), counts.tolist(), strict=False):
            match = np.flatnonzero(main_effect_indices == int(global_index))
            if match.size:
                released[match] += int(count)
                continue
            side_effects.append(
                ProteinBindingSideEffect(
                    molecule_kind="monomer" if field_name == "monomerBoundSites" else "complex",
                    global_index=int(global_index),
                    mature_delta=int(count),
                    bound_delta=-int(count),
                )
            )

        self.set_field(
            field_name,
            SparseTriplet(
                positions=triplet.positions[~overlap],
                strands=triplet.strands[~overlap],
                values=triplet.values[~overlap],
                shape=triplet.shape,
            ),
        )
        return released, tuple(side_effects)

    def set_region_protein_unbound(
        self,
        *,
        positions: np.ndarray | list[int],
        strands: np.ndarray | list[int],
        lengths: np.ndarray | list[int],
        main_effect_monomer_indices: np.ndarray | list[int] = (),
        main_effect_complex_indices: np.ndarray | list[int] = (),
        binding_both_strands: bool,
        region_both_strands: bool,
        monomer_footprints: np.ndarray,
        complex_footprints: np.ndarray,
        monomer_binding_strandedness: np.ndarray,
        complex_binding_strandedness: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, tuple[ProteinBindingSideEffect, ...]]:
        query_positions = _coerce_vector(positions, dtype=np.int64, name="positions")
        query_strands = _coerce_vector(strands, dtype=np.int64, name="strands", size=query_positions.size)
        query_lengths = _coerce_vector(lengths, dtype=np.int64, name="lengths", size=query_positions.size)
        main_monomers = _coerce_vector(
            main_effect_monomer_indices,
            dtype=np.int64,
            name="main_effect_monomer_indices",
        )
        main_complexes = _coerce_vector(
            main_effect_complex_indices,
            dtype=np.int64,
            name="main_effect_complex_indices",
        )

        released_monomers, monomer_side_effects = self._set_region_bound_sites_unbound(
            field_name="monomerBoundSites",
            query_positions=query_positions,
            query_strands=query_strands,
            query_lengths=query_lengths,
            main_effect_indices=main_monomers,
            footprints=_coerce_vector(
                monomer_footprints,
                dtype=np.int64,
                name="monomer_footprints",
            ),
            binding_strandedness=_coerce_vector(
                monomer_binding_strandedness,
                dtype=np.int64,
                name="monomer_binding_strandedness",
            ),
            binding_both_strands=binding_both_strands,
            region_both_strands=region_both_strands,
        )
        released_complexes, complex_side_effects = self._set_region_bound_sites_unbound(
            field_name="complexBoundSites",
            query_positions=query_positions,
            query_strands=query_strands,
            query_lengths=query_lengths,
            main_effect_indices=main_complexes,
            footprints=_coerce_vector(
                complex_footprints,
                dtype=np.int64,
                name="complex_footprints",
            ),
            binding_strandedness=_coerce_vector(
                complex_binding_strandedness,
                dtype=np.int64,
                name="complex_binding_strandedness",
            ),
            binding_both_strands=binding_both_strands,
            region_both_strands=region_both_strands,
        )
        return (
            released_monomers,
            released_complexes,
            monomer_side_effects + complex_side_effects,
        )

    def set_site_protein_bound(
        self,
        *,
        positions: np.ndarray | list[int],
        strands: np.ndarray | list[int],
        field_name: str,
        binding_global_index: int,
        binding_footprint: int,
        binding_both_strands: bool,
        region_both_strands: bool,
        lengths: np.ndarray | list[int] | None = None,
        main_effect_monomer_indices: np.ndarray | list[int] = (),
        main_effect_complex_indices: np.ndarray | list[int] = (),
        monomer_footprints: np.ndarray,
        complex_footprints: np.ndarray,
        monomer_binding_strandedness: np.ndarray,
        complex_binding_strandedness: np.ndarray,
    ) -> ChromosomeBindingResult:
        if field_name not in ("monomerBoundSites", "complexBoundSites"):
            raise ValueError(f"Unsupported point-bound field: {field_name}")

        bind_positions = _coerce_vector(positions, dtype=np.int64, name="positions")
        bind_strands = _coerce_vector(strands, dtype=np.int64, name="strands", size=bind_positions.size)
        bind_lengths = (
            np.ones(bind_positions.size, dtype=np.int64)
            if lengths is None
            else _coerce_vector(lengths, dtype=np.int64, name="lengths", size=bind_positions.size)
        )
        if bind_positions.size == 0:
            return ChromosomeBindingResult(
                n_bound=0,
                released_monomers=np.zeros(
                    _coerce_vector(
                        main_effect_monomer_indices,
                        dtype=np.int64,
                        name="main_effect_monomer_indices",
                    ).size,
                    dtype=np.int64,
                ),
                released_complexes=np.zeros(
                    _coerce_vector(
                        main_effect_complex_indices,
                        dtype=np.int64,
                        name="main_effect_complex_indices",
                    ).size,
                    dtype=np.int64,
                ),
                side_effects=(),
            )
        if int(binding_footprint) <= 0:
            raise ValueError(f"binding_footprint must be positive, got {binding_footprint!r}")

        release_positions = np.mod(bind_positions + np.minimum(0, bind_lengths + 1), self.shape[0])
        release_lengths = int(binding_footprint) + np.abs(bind_lengths) - 1
        released_monomers, released_complexes, side_effects = self.set_region_protein_unbound(
            positions=release_positions,
            strands=bind_strands,
            lengths=release_lengths,
            main_effect_monomer_indices=main_effect_monomer_indices,
            main_effect_complex_indices=main_effect_complex_indices,
            binding_both_strands=binding_both_strands,
            region_both_strands=region_both_strands,
            monomer_footprints=monomer_footprints,
            complex_footprints=complex_footprints,
            monomer_binding_strandedness=monomer_binding_strandedness,
            complex_binding_strandedness=complex_binding_strandedness,
        )

        triplet = self.get_field(field_name)
        chosen_pairs = set(
            zip(
                np.mod(bind_positions, self.shape[0]).tolist(),
                bind_strands.tolist(),
                strict=False,
            )
        )
        keep_mask = np.asarray(
            [
                (int(position), int(strand)) not in chosen_pairs
                for position, strand in zip(
                    triplet.positions.tolist(),
                    triplet.strands.tolist(),
                    strict=False,
                )
            ],
            dtype=bool,
        )
        self.set_field(
            field_name,
            SparseTriplet(
                positions=np.concatenate(
                    (
                        triplet.positions[keep_mask].astype(np.int64, copy=False),
                        np.mod(bind_positions, self.shape[0]),
                    )
                ),
                strands=np.concatenate(
                    (
                        triplet.strands[keep_mask].astype(np.int64, copy=False),
                        bind_strands.astype(np.int64, copy=False),
                    )
                ),
                values=np.concatenate(
                    (
                        triplet.values[keep_mask].astype(np.int64, copy=False),
                        np.full(bind_positions.size, int(binding_global_index), dtype=np.int64),
                    )
                ),
                shape=triplet.shape,
            ),
        )

        if field_name == "monomerBoundSites":
            main_effects = _coerce_vector(
                main_effect_monomer_indices,
                dtype=np.int64,
                name="main_effect_monomer_indices",
            )
            match = np.flatnonzero(main_effects == int(binding_global_index))
            if match.size:
                released_monomers[match] -= int(bind_positions.size)
        else:
            main_effects = _coerce_vector(
                main_effect_complex_indices,
                dtype=np.int64,
                name="main_effect_complex_indices",
            )
            match = np.flatnonzero(main_effects == int(binding_global_index))
            if match.size:
                released_complexes[match] -= int(bind_positions.size)

        return ChromosomeBindingResult(
            n_bound=int(bind_positions.size),
            released_monomers=released_monomers,
            released_complexes=released_complexes,
            side_effects=side_effects,
        )

    def to_state(self) -> dict[str, Any]:
        state = {name: triplet.to_state() for name, triplet in self._fields.items()}
        hidden: dict[str, Any] = {}
        for name, field in self._hidden_sparse_fields.items():
            hidden[name] = field.to_state()
        for name, value in self._hidden_scalar_fields.items():
            hidden[name] = _copy_hidden_scalar(value)
        if hidden:
            state[CHROMOSOME_HIDDEN_STATE_KEY] = hidden
        return state

    @classmethod
    def from_state_mapping(
        cls,
        payload: Mapping[str, Any] | None,
        *,
        shape: tuple[int, int] = (DEFAULT_SEQUENCE_LEN, DEFAULT_N_COMPARTMENTS),
    ) -> ChromosomeStore:
        store = cls(shape=shape)
        if not isinstance(payload, Mapping):
            return store
        for name in cls.FIELDS:
            node = payload.get(name)
            if isinstance(node, Mapping):
                store.set_field(name, node)
        hidden_payload = payload.get(CHROMOSOME_HIDDEN_STATE_KEY)
        hidden_mapping = hidden_payload if isinstance(hidden_payload, Mapping) else {}
        for name in CHROMOSOME_HIDDEN_SPARSE_FIELDS:
            node = hidden_mapping.get(name)
            if node is None and name != "supercoiled":
                node = payload.get(name)
            if isinstance(node, Mapping):
                store.set_hidden_sparse_field(name, node)
        for name in CHROMOSOME_HIDDEN_SCALAR_FIELDS:
            node = hidden_mapping.get(name)
            if node is None and name in payload:
                node = payload.get(name)
            if node is not None:
                store.set_hidden_scalar(name, node)
        return store

    @classmethod
    def from_hdf5_group(cls, group: h5py.Group) -> ChromosomeStore:
        sequence_len = int(np.asarray(group["sequenceLen"][()]).reshape(-1)[0])
        n_compartments = int(np.asarray(group["nCompartments"][()]).reshape(-1)[0])
        store = cls(shape=(sequence_len, n_compartments))
        for field_name in cls.FIELDS:
            if field_name in group:
                store.set_field(field_name, SparseTriplet.from_hdf5_group(group[field_name]))
        for field_name in CHROMOSOME_HIDDEN_SPARSE_FIELDS:
            if field_name in group and isinstance(group[field_name], h5py.Group):
                store.set_hidden_sparse_field(
                    field_name,
                    AuxiliarySparseField.from_hdf5_group(group[field_name]),
                )
        for field_name in CHROMOSOME_HIDDEN_SCALAR_FIELDS:
            if field_name in group and isinstance(group[field_name], h5py.Dataset):
                store.set_hidden_scalar(field_name, _read_matlab_dataset(group[field_name]))
        return store

    @classmethod
    def from_trace_tick(
        cls,
        path: str | Path,
        *,
        tick: int = 0,
        group_name: str = "states_before",
    ) -> ChromosomeStore:
        with h5py.File(Path(path), "r") as handle:
            dataset = handle[f"{group_name}/chromosome"]
            ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
            return cls.from_hdf5_group(handle[ref])


__all__ = [
    "CHROMOSOME_FIELDS",
    "CHROMOSOME_HIDDEN_SCALAR_FIELDS",
    "CHROMOSOME_HIDDEN_SPARSE_FIELDS",
    "CHROMOSOME_HIDDEN_STATE_KEY",
    "AuxiliarySparseField",
    "ChromosomeBindingResult",
    "ChromosomeStore",
    "ProteinBindingSideEffect",
    "SparseTriplet",
    "merge_adjacent_regions",
    "sparse_triplet_schema",
]
