"""TranscriptionalRegulation-only MATLAB ``RandStream('mcg16807')`` shim.

Karr's process base class constructs every process's random stream with the
multiplicative-congruential generator, not Mersenne Twister:

    edu.stanford.covert.cell.sim.Process.m:283
        this.randStream = edu.stanford.covert.util.RandStream('mcg16807');

TranscriptionalRegulation never overrides ``constructRandStream``, so it
inherits this ``mcg16807`` stream like every other Karr process. An earlier
version of this port incorrectly used the shared ``mt19937ar``-based
``MatlabRandStream`` (``opencell/util/matlab_rng.py``) -- that class is a
faithful shim for MATLAB's *default/global* stream (used by a handful of
processes that explicitly construct ``RandStream('mt19937ar', ...)``, e.g.
the Statistics-RNG-provider migration), not for a per-process ``Process``
stream, which is always ``mcg16807``.

This module follows the same isolation precedent already established by
``opencell/util/chromcond_mcg_rand.py`` (ChromosomeCondensation) and
``opencell/vivarium/karr_protein_decay_light.py`` (``_Mcg16807``): each
process that needs an ``mcg16807`` stream gets its own small, self-contained
implementation rather than sharing one general-purpose class. Two reasons to
keep this fully independent rather than importing
``chromcond_mcg_rand.ChromCondMcgRandStream``:

1. ``chromcond_mcg_rand.py``'s own docstring records that its file hash is
   deliberately kept out of any process's provenance dependency set *other
   than* ChromosomeCondensation's; coupling TranscriptionalRegulation to it
   would create exactly the cross-process provenance entanglement that
   module was written to avoid.
2. ``opencell/util/matlab_rng.py`` is a registered L2.2 provenance dependency
   for ProteinTranslocation (``scripts/l22_evidence/schema.py``); this
   process-local module (like ChromCond's) never touches that file, so no
   unrelated process's accepted evidence goes stale because of this fix.

The generator algorithm (Park-Miller multiplicative congruential, modulus
2**31-1, multiplier 16807) is independently verified bit-for-bit against live
MATLAB (``scripts/matlab/probe_txreg_mcg_randsample.m``,
``probe_txreg_real_sample_accessible_regions.m``): every ``rand()``/
``randsample()`` output this class produces matches real MATLAB exactly for
every case tested. **Correction (2026-09-05):** this module's internal
``get_state()``/``set_state()`` ``mcg_state`` value is this class's OWN
representation only -- it is NOT MATLAB's real ``RandStream('mcg16807').State``
encoding. A dedicated live probe
(``scripts/matlab/probe_l21_chromosome_randstream_state.m``, reused verbatim
from the DNADamage shared-RNG lane, ``agent/l21-dnadamage-active-fix-20260903``)
confirms real MATLAB's ``.State`` is directly readable/writable/round-trippable
(``all_reconstruction_ok=true`` across seeds {0, 1, 2000, 12345, 2147483646})
but matches NO simple closed-form encoding this project has derived
(``all_formula_matches=false``) -- so a real MATLAB ``.State`` scalar can
never be injected directly into this class's ``mcg_state``. For that use case
(restoring the genuine, per-tick SHARED ``Chromosome.randStream`` position --
see ``TxRegChromosomeLedgerRandStream`` below and
``STATUS_L21_TXREG_ACTIVE_FIX.md``), Karr's real state is captured as an
opaque scalar by the extractor and reconciled OFFLINE, in MATLAB itself, into
an ordered list of raw ``rand()`` output values
(``scripts/matlab/reconstruct_chromosome_draw_ledger.m``) -- never decoded
into this class's state space. The weighted
``randsample`` here is the literal
``edu.stanford.covert.util.RandStream.randsample(this, n, k, replacement, w)``
algorithm (see ``RandStream.m``): a forced-``k==1``-with-replacement branch,
and a ``k>1`` rejection-sampling loop over repeated with-replacement draws
(``weights(selectedSites) = 0`` after each draw, no early-return on
duplicates). The *batch-size padding* used by
``Chromosome.m::sampleAccessibleRegions`` (``nMoreSites = min(max(2*(nSites-
collected),10), nnz(weights))``) is a separate, process-specific caller
concern and lives in
``opencell/vivarium/karr_transcriptional_regulation.py::_sample_accessible_sites_batched``,
not in this generator shim.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = ["TxRegMcgRandStream", "TxRegChromosomeLedgerRandStream"]


class TxRegMcgRandStream:
    """MATLAB-compatible ``RandStream('mcg16807')`` shim, TranscriptionalRegulation-only."""

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
        ``randsample(s, n, k, true, w)`` weighted-with-replacement branch
        (``E:\\MATLAB\\toolbox\\stats\\stats\\randsample.m``, the exact
        provider ``karr_bootstrap.m`` fails closed on)::

            p = w(:)' / sumw;
            edges = min([0 cumsum(p)], 1);   % protect against round-off
            edges(end) = 1;                  % exact upper edge
            [~, ~, y] = histcounts(rand(s, k, 1), edges);

        Two details matter for bit-exact replay, both previously wrong in
        this shim:
        1. ``w`` is normalized to a probability vector (``p = w/sum(w)``)
           **before** the cumulative sum, and the draw is compared against
           a raw ``rand()`` in ``[0, 1)`` -- NOT against ``rand() * sum(w)``
           compared to an *unnormalized* cumulative sum. These are
           mathematically equivalent in exact arithmetic but not bit-for-bit
           in floating point (dividing-then-summing vs. summing-then-
           multiplying accumulate rounding error differently), which can
           flip the selected bin for a draw landing near a bucket edge.
        2. ``histcounts``' bin semantics: every bin is half-open
           ``[edges(i), edges(i+1))`` **except the last, which is closed on
           both ends** (values exactly equal to the final edge -- always
           forced to ``1.0`` here -- fall in the last bin, not out of
           range).
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


class TxRegChromosomeLedgerRandStream(TxRegMcgRandStream):
    """Test/harness-only replay of a pre-recorded, per-tick raw-draw ledger
    for Karr's SHARED ``Chromosome.randStream``.

    Mirrors ``KarrLedgerReplayStream`` in the DNADamage shared-RNG lane's
    ``opencell/vivarium/karr_dna_damage_rng.py``
    (``agent/l21-dnadamage-active-fix-20260903``) exactly -- same
    construction contract, same fail-closed exhaustion/under-consumption
    checks -- so both lanes' L2.1 replay harnesses share one pattern.

    Constructed from a plain list of floats (never does its own file I/O
    -- the caller, e.g. an L2.1 replay test, is responsible for reading
    the ledger from a trace's sidecar/companion JSON; this class never
    opens anything, so its mere presence here does not create a
    production oracle-read path -- see FIX_TEMPLATE_L2_REPLAY.md Rule 8).
    Overrides ONLY the single scalar-draw primitive (``_mcg_rand_scalar``
    -- every other method on ``TxRegMcgRandStream``: ``rand``, ``randi``,
    ``randperm``, ``randsample``, the weighted-with-replacement helper --
    is built exclusively from repeated calls to it), so replay correctness
    reduces entirely to "does the scalar draw primitive return the
    recorded values in the recorded order", which is exactly what the
    offline reconstruction in
    ``scripts/matlab/reconstruct_chromosome_draw_ledger.m`` produces (a
    real-MATLAB-verified ordered list of raw scalar ``rand()`` outputs
    Karr's actual shared stream produced for one TranscriptionalRegulation
    tick's own ``evolveState()``/``bindTranscriptionFactors()`` window).

    Fail-closed by construction: a draw past the end of the recorded
    ledger raises immediately (OC's ported site-sampling algorithm
    consumed MORE raw draws than Karr's real one did for this tick -- a
    wrong branch or an extra call), and ``assert_fully_consumed()`` (call
    once after the tick's ``next_update`` returns) raises if any recorded
    draws were left unused (OC consumed FEWER -- a missing call or wrong
    draw-count formula). Neither failure mode is silently absorbed,
    approximated, or padded with a fresh/warmup stand-in.
    """

    def __init__(self, draws: list[float], *, tick_label: str = "<unknown>") -> None:
        # Deliberately does NOT call TxRegMcgRandStream.__init__ (which
        # requires a valid mcg16807 seed and sets up `_mcg_state`) -- this
        # class never uses the LCG formula or `_mcg_state` at all; every
        # other inherited method reaches randomness exclusively through
        # the overridden `_mcg_rand_scalar` below.
        self.generator = "chromosome_ledger_replay"
        self._draws = [float(v) for v in draws]
        self._index = 0
        self._tick_label = str(tick_label)

    def _mcg_rand_scalar(self) -> float:
        if self._index >= len(self._draws):
            raise RuntimeError(
                f"TxRegChromosomeLedgerRandStream[{self._tick_label}]: exhausted after "
                f"{self._index} draw(s) (ledger recorded only {len(self._draws)}) -- "
                "OC's own site-sampling algorithm consumed MORE raw draws than Karr's "
                "real shared-chromosome-stream ledger for this tick. This is a "
                "fail-closed divergence (wrong branch, extra call, or a genuine "
                "algorithmic mismatch), not a value to guess at."
            )
        value = self._draws[self._index]
        self._index += 1
        return value

    def assert_fully_consumed(self) -> None:
        """Call once after a tick's ``next_update`` returns. Raises if any
        recorded draws were left unconsumed -- OC's own site-sampling
        algorithm consumed FEWER raw draws than Karr's real one did for
        this tick (a missing call or a wrong draw-count formula)."""
        if self._index != len(self._draws):
            raise RuntimeError(
                f"TxRegChromosomeLedgerRandStream[{self._tick_label}]: only consumed "
                f"{self._index}/{len(self._draws)} recorded draw(s) -- OC's own "
                "site-sampling algorithm consumed FEWER raw draws than Karr's real "
                "shared-chromosome-stream ledger for this tick. This is a "
                "fail-closed divergence, not something to silently ignore."
            )
