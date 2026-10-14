"""Unified, state-owned MATLAB ``RandStream('mcg16807')`` shim for the
production shared chromosome-state RNG stream (DC-2/DC-4, dec-007).

Karr's `Chromosome` state object (`Chromosome < CellState`) owns exactly one
shared `randStream`, advanced by every chromosome-binding process's
accessibility/commit/release draws in a tick. OpenCell approximated this with
two independently-seeded, byte-identical per-process stand-in shims --
``opencell.util.txreg_mcg_rand.TxRegMcgRandStream`` and
``opencell.util.chromcond_mcg_rand.ChromCondMcgRandStream``. Probe P1
(``docs/design/shared_chromosome_state_subsystem.md`` SLOT 10/19) proves the
two shims are numerically equivalent (``rand``/``randi``/``randperm``/
``randsample``/``get_state``/``set_state``) across seeds
``{0, 1, 42, 123456789}`` -- so this class folds that proven-identical
arithmetic into ONE class, owned by ``opencell.state.chromosome_store
.ChromosomeStore`` (DC-2), rather than perpetuating two copies of one
generator.

This module intentionally does NOT subclass or import either existing
per-process shim: dec-006's provenance-hash isolation for the ChromCond and
TxReg per-process LEDGER replay subclasses (`chromcond_mcg_rand.py`,
`txreg_mcg_rand.py`) is preserved untouched, and this new production class
has no dependency on either file (DC-4's "Rejected" clause: keep the ledger
subclasses in their current files, fold only the generator arithmetic).

Algorithm notes (identical to ``TxRegMcgRandStream``/``ChromCondMcgRandStream``,
see those modules' docstrings for the full live-MATLAB verification history):
Park-Miller multiplicative-congruential generator (modulus ``2**31-1``,
multiplier ``16807``); the exposed ``State`` is a 16-bit half-word swap of the
raw Lehmer state, conditionally XORed with ``0x80008000`` when the pre-swap
low half-word's sign bit is set. Weighted ``randsample`` is the literal
MathWorks Statistics Toolbox ``randsample(s, n, k, replacement, w)`` algorithm
(probability-normalized cumulative edges + ``histcounts``-style half-open
binning), matching ``TxRegMcgRandStream``'s already-live-MATLAB-verified
implementation bit-for-bit (not ``ChromCondMcgRandStream``'s pre-normalization
cumsum/threshold variant -- Probe P1 proves the two are numerically
equivalent for every case exercised, so unifying on either is behavior
preserving).
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = ["ChromosomeStateRandStream"]


class ChromosomeStateRandStream:
    """MATLAB-compatible ``RandStream('mcg16807')`` shim owned by the shared
    chromosome state authority (``ChromosomeStore``, DC-2). One instance per
    cell; serialized as ``[seed, mcg_state]`` (see
    ``opencell.state.chromosome_store.CHROMOSOME_RAND_STREAM_KEY``)."""

    _MCG_MOD = 2_147_483_647
    _MCG_MUL = 16_807
    _MCG_HALF_MASK = 0xFFFF
    _MCG_HALF_SIGN = 0x8000
    _MCG_STATE_XOR_MASK = 0x80008000
    _MCG_DEFAULT_STATE = 931_316_785

    def __init__(self, seed: int) -> None:
        self.generator = "mcg16807"
        self._seed = int(seed)
        self._mcg_state = 1
        self._initialize_mcg(self._seed)

    def rand(self, *shape: int) -> np.ndarray:
        normalized = self._normalize_shape(shape)
        if normalized is None:
            return np.asarray(self._mcg_rand_scalar(), dtype=np.float64)
        count = self._shape_product(normalized)
        values = np.fromiter(
            (self._mcg_rand_scalar() for _ in range(count)), dtype=np.float64, count=count
        )
        return values.reshape(normalized, order="F")

    def randi(self, imax: int, *shape: int) -> np.ndarray:
        if int(imax) < 1:
            raise ValueError("imax must be >= 1")
        imax_i = int(imax)
        if imax_i == 1:
            normalized = self._normalize_shape(shape)
            if normalized is None:
                return np.asarray(1, dtype=np.int64)
            return np.ones(normalized, dtype=np.int64)
        samples = self.rand(*shape)
        values = np.floor(samples * imax_i).astype(np.int64) + 1
        return values

    def randperm(self, n: int, k: int | None = None) -> np.ndarray:
        n_i = int(n)
        if n_i < 0:
            raise ValueError("n must be >= 0")
        if k is None:
            k_i = n_i
        else:
            k_i = int(k)
            if k_i < 0 or k_i > n_i:
                raise ValueError("k must satisfy 0 <= k <= n")

        # MATLAB-compatible ordering: rank independent uniforms from this stream.
        keys = self.rand(n_i)
        order = np.argsort(keys, kind="mergesort").astype(np.int64) + 1
        return order[:k_i]

    def randsample(
        self,
        n: int,
        k: int,
        replacement: bool = False,
        w: np.ndarray | list[float] | None = None,
    ) -> np.ndarray:
        """Literal ``edu.stanford.covert.util.RandStream.randsample(this, n, k,
        replacement, w)``: weighted selection of ``k`` 1-based indices in
        ``1..n``. Returns a 1-based ``int64`` array, in selection order (not
        sorted).
        """
        n_i = int(n)
        k_i = int(k)
        if n_i < 0:
            raise ValueError("n must be >= 0")
        if k_i < 0:
            raise ValueError("k must be >= 0")
        replacement_i = bool(replacement)

        if w is None:
            weights = np.ones(n_i, dtype=np.float64)
        else:
            weights = np.asarray(w, dtype=np.float64).reshape(-1)
            if weights.size != n_i:
                raise ValueError("weights must have length n")
            if np.any(weights < 0.0) or not np.all(np.isfinite(weights)):
                raise ValueError("weights must be finite and nonnegative")

        if not replacement_i and k_i > n_i:
            raise ValueError("k must satisfy 0 <= k <= n when sampling without replacement")
        if n_i == 0 or k_i <= 0 or not np.any(weights):
            return np.zeros(0, dtype=np.int64)

        if not replacement_i and k_i > 1:
            if np.all(weights == weights[0]):
                return self.randperm(n_i, k_i)

            integers = np.flatnonzero(weights >= float(np.finfo(np.float64).max)) + 1
            if integers.size > k_i:
                order = self.randperm(int(integers.size))
                return integers[order[:k_i] - 1].astype(np.int64, copy=False)
            if integers.size == k_i:
                return integers.astype(np.int64, copy=False)

            weights = weights.copy()
            weights[integers - 1] = 0.0
            chosen = np.zeros(n_i, dtype=bool)
            chosen[integers - 1] = True
            out = integers.astype(np.int64).tolist()

            while len(out) < k_i and np.any(weights):
                tmp = self.randsample(n_i, k_i - len(out), True, weights)
                accepted: list[int] = []
                for value in tmp.tolist():
                    idx = int(value) - 1
                    if not chosen[idx]:
                        chosen[idx] = True
                        accepted.append(int(value))
                if not accepted:
                    break
                weights[tmp - 1] = 0.0
                out.extend(accepted)
            return np.asarray(out, dtype=np.int64)

        if k_i == 1:
            replacement_i = True
        if not replacement_i:
            return self.randperm(n_i, k_i)
        return self._weighted_randsample_with_replacement(n=n_i, k=k_i, weights=weights)

    def get_state(self) -> dict[str, Any]:
        return {"generator": self.generator, "seed": self._seed, "mcg_state": int(self._mcg_state)}

    def set_state(self, state: dict[str, Any]) -> None:
        generator = state.get("generator")
        if generator != "mcg16807":
            raise ValueError("state generator must be 'mcg16807'")
        self.generator = generator
        self._seed = int(state.get("seed", 0))
        mcg_state = int(state.get("mcg_state", 0))
        if mcg_state <= 0 or mcg_state >= self._MCG_MOD:
            raise ValueError("state['mcg_state'] must be in [1, 2147483646]")
        self._mcg_state = mcg_state

    def _initialize_mcg(self, seed: int) -> None:
        seed_i = int(seed)
        if seed_i <= 0:
            self._mcg_state = self._MCG_DEFAULT_STATE
            return
        else:
            seed_i %= self._MCG_MOD
            if seed_i == 0:
                seed_i = self._MCG_MOD - 1
        self._mcg_state = seed_i

    def _mcg_rand_scalar(self) -> float:
        raw_state = self._decode_mcg_state(self._mcg_state)
        raw_state = (self._MCG_MUL * raw_state) % self._MCG_MOD
        self._mcg_state = self._encode_mcg_state(raw_state)
        return raw_state / self._MCG_MOD

    @classmethod
    def _encode_mcg_state(cls, raw_state: int) -> int:
        raw_i = int(raw_state)
        if raw_i <= 0 or raw_i >= cls._MCG_MOD:
            raise ValueError("raw mcg16807 state must be in [1, 2147483646]")
        lo = raw_i & cls._MCG_HALF_MASK
        hi = (raw_i >> 16) & cls._MCG_HALF_MASK
        encoded = (lo << 16) | hi
        if lo & cls._MCG_HALF_SIGN:
            encoded ^= cls._MCG_STATE_XOR_MASK
        return int(encoded)

    @classmethod
    def _decode_mcg_state(cls, encoded_state: int) -> int:
        encoded_i = int(encoded_state)
        if encoded_i <= 0 or encoded_i >= cls._MCG_MOD:
            raise ValueError("encoded mcg16807 state must be in [1, 2147483646]")
        if encoded_i & cls._MCG_HALF_SIGN:
            encoded_i ^= cls._MCG_STATE_XOR_MASK
        lo = encoded_i & cls._MCG_HALF_MASK
        hi = (encoded_i >> 16) & cls._MCG_HALF_MASK
        raw = (lo << 16) | hi
        if raw <= 0 or raw >= cls._MCG_MOD:
            raise ValueError("decoded mcg16807 state must be in [1, 2147483646]")
        return int(raw)

    def _weighted_randsample_with_replacement(
        self,
        *,
        n: int,
        k: int,
        weights: np.ndarray,
    ) -> np.ndarray:
        """Literal port of the genuine MathWorks Statistics Toolbox
        ``randsample(s, n, k, true, w)`` weighted-with-replacement branch::

            p = w(:)' / sumw;
            edges = min([0 cumsum(p)], 1);   % protect against round-off
            edges(end) = 1;                  % exact upper edge
            [~, ~, y] = histcounts(rand(s, k, 1), edges);

        See ``TxRegMcgRandStream._weighted_randsample_with_replacement`` for
        the full derivation/verification notes (identical algorithm, proven
        numerically equivalent to ``ChromCondMcgRandStream``'s variant by
        Probe P1).
        """
        p = np.asarray(weights, dtype=np.float64) / float(np.sum(weights))
        edges = np.empty(n + 1, dtype=np.float64)
        edges[0] = 0.0
        np.cumsum(p, out=edges[1:])
        np.minimum(edges, 1.0, out=edges)
        edges[-1] = 1.0
        draws = np.empty(k, dtype=np.int64)
        for i in range(k):
            x = float(self.rand())
            idx0 = int(np.searchsorted(edges, x, side="right")) - 1
            if idx0 >= n:
                idx0 = n - 1
            elif idx0 < 0:
                idx0 = 0
            draws[i] = idx0 + 1
        return draws

    @staticmethod
    def _shape_product(shape: tuple[int, ...]) -> int:
        count = 1
        for dim in shape:
            count *= dim
        return count

    @staticmethod
    def _normalize_shape(shape: tuple[int, ...]) -> tuple[int, ...] | None:
        if len(shape) == 0:
            return None
        if len(shape) == 1 and isinstance(shape[0], tuple):
            shape = shape[0]
        normalized = tuple(int(dim) for dim in shape)
        if any(dim < 0 for dim in normalized):
            raise ValueError("shape dimensions must be >= 0")
        return normalized
