"""MATLAB-compatible mcg16807 RandStream port, scoped narrowly to
`opencell.vivarium.karr_dna_damage.KarrDNADamageProcess`.

Primary sources (local, no web) -- all under
`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/`:

- `+cell/+sim/Process.m` (`constructRandStream`/`seedRandStream`): every
  Karr process gets its own `RandStream('mcg16807')`, reset with
  `this.seed = simulation.seed` -- the SAME scalar seed for every
  process/state object, no per-object offset.
- `+cell/+sim/+process/DNADamage.m` (`evolveState`, ~line 537): DNADamage's
  own `randStream` is used for exactly ONE draw per tick:
  `randomOrder = this.randStream.randperm(numel(this.reactionWholeCellModelIDs))`.
  All damage-site sampling is delegated to `this.chromosome.setSiteDamaged`.
- `+cell/+sim/+state/Chromosome.m` (`sampleAccessibleSites` ~line 539,
  `setSiteDamaged` ~line 2490): site-count/position/strand sampling draws
  come from `this.randStream` where `this` is the Chromosome STATE object
  -- a stream shared and advanced by most/all of Karr's 28 processes
  across the full simulation history, not DNADamage's own stream.
- `+util/RandStream.m` (`stochasticRound` ~line 210s, `randomlySelectNRows`
  line 249-252): `stochasticRound` unconditionally draws
  `rand(size(value))` and compares to `mod(value, 1)` -- even for
  `value <= 0` or exact integers, the draw is ALWAYS consumed.
  `randomlySelectNRows` calls MATLAB's builtin
  `randsample(stream, n, k, false)`.

mcg16807's exact multiplier/modulus/seed-scaling and the `rand`/`randi`/
`randperm`/`randsample` wrapper algorithms are MATLAB builtins -- not
present anywhere in the local WholeCell source tree (only the
`edu.stanford.covert.util.RandStream` *wrapper class* delegating to them
is local). Per the no-web/no-tuning constraint, this module's constants
and wrapper semantics were empirically derived and independently verified
against the real local MATLAB installation (`E:\\MATLAB\\bin\\matlab.exe`,
invoked via `scripts/tools/run_matlab_slot.ps1`), not guessed or fit to
replay trace output. The probe scripts used (throwaway, not committed)
established, byte-for-byte, for seeds {1, 12345, 2000, 2147483646, 777, 42}:

  - Seed -> initial state:  x0 = (seed * 65536) mod (2**31 - 1)
  - Update:                 x_(n+1) = (16807 * x_n) mod (2**31 - 1)
  - rand():                 x_(n+1) / (2**31 - 1)  (state updates BEFORE
                            output; MATLAB's displayed `.State` property
                            is a distinct cosmetic re-encoding of this
                            value that this module does not reproduce,
                            since production code never reads it)
  - randi(imax):            floor(rand() * imax) + 1  (exactly one raw
                            draw per element; no rejection sampling)
  - randperm(n):            draw n keys via rand(), return the 1-based
                            ascending STABLE-sort order of those keys
                            (an argsort, not Fisher-Yates -- confirmed via
                            an interleaved before/after `rand()` probe
                            showing randperm(n) consumes exactly n raw
                            draws)
  - stochasticRound(value): draw = rand() (ALWAYS -- verified this is
                            consumed even when value <= 0 or is an exact
                            integer); roundUp = draw < mod(value, 1);
                            result = ceil(value) if roundUp else
                            floor(value)

Seed range: MATLAB's builtin accepts seed=0 via some internal
substitution this module's black-box probing could not identify (the
resulting first draw did not match this formula for any seed we tried).
Karr's actual simulation seeds are always large nonzero integers, so this
module fails closed on seed <= 0 (or seed >= 2**31 - 1) rather than guess
at that unreachable-in-practice edge case.

Known, disclosed scope narrowing -- shared-stream site sampling: as
described above, Karr's actual site-count/position/strand/selection draws
come from `Chromosome.randStream`, a stream shared and advanced by most of
the 28 Karr processes over the full simulation run. Reproducing its exact
draw *position* at the moment DNADamage's `evolveState` fires would
require the full interleaved draw history of every other chromosome
touching process across the whole run -- information architecturally
unavailable to an isolated, single-process replay. This module still
implements every one of Chromosome's/RandStream's used operations with
their LITERAL formula (so it is structurally and functionally faithful,
not merely "close enough"), and callers construct a second, dedicated
stream instance for that role -- freshly seeded from the SAME run seed,
consistent with Karr's actual `this.seed = simulation.seed` convention for
every process/state object. This achieves genuine bit-identity only for
the one truly-isolated per-process draw sequence (DNADamage's own
reaction-order `randperm`), not for site-level sampling; see
`STATUS_L21_DNADAMAGE_ACTIVE_FIX.md` for the full analysis and the
resulting first-divergence point.

`randomlySelectNRows`/`randsample(stream, n, k, false)`: this module now
implements MATLAB's real Statistics and Machine Learning Toolbox
algorithm exactly (read directly from `toolbox/stats/stats/randsample.m`,
no web) rather than the prior `randperm(n)[:k]` approximation. Two
branches, matching the real source: `4*k > n` uses `randperm(n)[:k]`
(this WAS already exact for that branch); `4*k <= n` uses a
rejection-sampling loop over MATLAB's BUILTIN `randi(stream, n)` (a
DIFFERENT formula than Chromosome.m's own `ceil(dnaLength*rand())` --
see `_builtin_randi`, empirically verified to be `floor(n*rand())+1`
with no bias-correction for this generator type) followed by one final
`randperm(k)` reorder. Verified live against real MATLAB across both
branches, including a case that forces rejection-loop collisions
(`scripts/matlab/probe_l21_randsample_exact.m`).

This module must never be used outside `KarrDNADamageProcess`; it is
intentionally process-local and does NOT modify or replace the shared,
provenance-hashed `opencell/util/matlab_rng.py` (a different algorithm,
`mt19937ar`, used by other processes).
"""

from __future__ import annotations

import math

_MODULUS = 2_147_483_647  # 2**31 - 1 (mcg16807 modulus, a Mersenne prime)
_MULTIPLIER = 16807
_SEED_SCALE = 65536  # 2**16; empirically derived seed->state scaling factor


class KarrMcg16807Stream:
    """MATLAB-compatible `RandStream('mcg16807')` port.

    See module docstring for primary-source anchors, the empirical
    derivation of every formula below, and the disclosed scope
    narrowings (shared Chromosome stream; `randsample` draw-count).
    """

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        seed_i = int(seed)
        if seed_i < 1 or seed_i > _MODULUS - 1:
            raise ValueError(
                f"KarrMcg16807Stream seed must be an integer in [1, {_MODULUS - 1}]; got {seed_i}"
            )
        self._state = (seed_i * _SEED_SCALE) % _MODULUS

    def rand(self) -> float:
        """Draw one scalar uniform in (0, 1) (MATLAB `rand(stream)`)."""
        self._state = (_MULTIPLIER * self._state) % _MODULUS
        return self._state / _MODULUS

    def rand_vector(self, n: int) -> list[float]:
        """Draw `n` scalar uniforms in draw order (MATLAB `rand(stream, n, 1)`)."""
        return [self.rand() for _ in range(int(n))]

    def randi(self, imax: int) -> int:
        """Draw one integer uniform in `[1, imax]` (`ceil(imax * rand())`,
        the literal formula used by `Chromosome.m::sampleAccessibleSites`
        for position/strand candidates -- not MATLAB's general-purpose
        `randi` builtin, which this module does not otherwise need)."""
        if imax < 1:
            raise ValueError("imax must be >= 1")
        return int(math.ceil(imax * self.rand()))

    def randperm(self, n: int) -> list[int]:
        """MATLAB-compatible `randperm(stream, n)`: draw `n` keys, return
        the 1-based ascending stable-sort order of those keys."""
        n_i = int(n)
        if n_i < 0:
            raise ValueError("n must be >= 0")
        if n_i == 0:
            return []
        keys = self.rand_vector(n_i)
        order = sorted(range(n_i), key=lambda i: keys[i])
        return [idx + 1 for idx in order]

    def _builtin_randi(self, imax: int) -> int:
        """MATLAB's BUILTIN `randi(stream, imax)` (core, not Chromosome's
        own `ceil(imax*rand())` formula -- see `randi()` above, a
        DIFFERENT method used for a different call site). Empirically
        verified live against real MATLAB (`scripts/matlab/
        probe_l21_chromosome_randstream_state.m`, `all_randi_values_match`/
        `all_randi_state_matches` = true across seeds {1,2000,12345,
        2147483646} x n in {7,500,100003}): for an mcg16807-backed stream,
        `randi(stream, imax)` is exactly `floor(imax * rand(stream)) + 1`,
        one raw draw per requested integer, with NO rejection/bias
        correction -- unlike Mersenne-Twister-backed streams, which do use
        rejection sampling. This method exists solely so
        `randsample_without_replacement`'s rejection-sampling branch can
        reproduce MATLAB's real `randsample.m` bit-for-bit; it must never
        be used for Chromosome.m's own `ceil(dnaLength*rand())` call
        sites (use the public `randi()` for those)."""
        if imax < 1:
            raise ValueError("imax must be >= 1")
        return int(math.floor(imax * self.rand())) + 1

    def randsample_without_replacement(self, n: int, k: int) -> list[int]:
        """Exact MATLAB-faithful port of the real Statistics and Machine
        Learning Toolbox `randsample(stream, n, k, false)` (no weights),
        used by `RandStream.randomlySelectNRows`/`randomlySelectRows`
        (`+edu/+stanford/+covert/+util/RandStream.m` lines 249-252). Read
        directly from the genuine MathWorks source
        (`toolbox/stats/stats/randsample.m`, no web, no guessing) and
        empirically verified live against real MATLAB across both
        algorithm branches and a rejection-loop-forcing case
        (`scripts/matlab/probe_l21_randsample_exact.m`,
        `tests/vivarium/test_karr_dna_damage_rng.py`).

        Algorithm (verbatim structure from randsample.m's `replace=false`,
        unweighted path):
          - if 4*k > n: `rp = randperm(stream, n); y = rp[:k]`.
          - else (rejection-sampling loop, k a small fraction of n):
            repeatedly draw `k - sumx` builtin-randi integers in
            `[1, n]`, mark them selected (dedup naturally via a boolean
            flag array), and repeat until `sumx == k` unique indices are
            marked (MATLAB's `while sumx < floor(k)` loop -- k is always
            an integer count here so `floor(k) == k`); then take the
            ascending selected indices and reorder them via one final
            `randperm(stream, k)` (MATLAB: `y = y(randperm(s,k))`).

        This replaces the prior `randperm(n)[:k]` approximation (which
        consumed the WRONG number of draws for the rejection-loop branch,
        silently desynchronizing any downstream sampling within the same
        tick from Karr's real draw sequence)."""
        n_i = int(n)
        k_i = int(k)
        if k_i < 0 or k_i > n_i:
            raise ValueError("k must satisfy 0 <= k <= n")
        if k_i == 0:
            return []
        if 4 * k_i > n_i:
            return self.randperm(n_i)[:k_i]
        selected = [False] * n_i
        n_selected = 0
        while n_selected < k_i:
            n_needed = k_i - n_selected
            for _ in range(n_needed):
                idx = self._builtin_randi(n_i)
                if not selected[idx - 1]:
                    selected[idx - 1] = True
            n_selected = sum(selected)
        ascending = [i + 1 for i, flag in enumerate(selected) if flag]
        order = self.randperm(k_i)
        return [ascending[idx - 1] for idx in order]

    def stochastic_round(self, value: float) -> int:
        """Literal `RandStream.stochasticRound`: unconditionally consumes
        one draw for EVERY call -- including `value <= 0` and exact
        integers, which Karr never special-cases (see module docstring).
        `roundUp = rand() < mod(value, 1)`; result is `ceil(value)` if
        `roundUp` else `floor(value)`."""
        draw = self.rand()
        frac = value % 1.0  # Python's `%` matches MATLAB `mod` for a positive divisor.
        round_up = draw < frac
        return int(math.ceil(value)) if round_up else int(math.floor(value))


class KarrLedgerReplayStream(KarrMcg16807Stream):
    """Test/harness-only replay of a pre-recorded, per-tick raw-draw
    ledger for Karr's SHARED `Chromosome.randStream`.

    Constructed from a plain list of floats (no file I/O of its own --
    the caller, e.g. an L2.1 replay test, is responsible for reading the
    ledger from a trace's sidecar/companion data; this class never opens
    anything, so its mere presence here does not create a production
    oracle-read path -- see FIX_TEMPLATE_L2_REPLAY.md Rule 8). Overrides
    ONLY `rand()` (the sole primitive every other method on
    `KarrMcg16807Stream` -- `randi`, `randperm`,
    `randsample_without_replacement`, `stochastic_round` -- is built
    from); every higher-level formula is inherited unchanged, so replay
    correctness reduces entirely to "does `rand()` return the recorded
    values in the recorded order", which is exactly what the offline
    reconstruction in `scripts/matlab/reconstruct_chromosome_draw_ledger.m`
    produces (a real-MATLAB-verified ordered list of raw scalar `rand()`
    outputs Karr's actual shared stream produced for one DNADamage tick's
    own `evolveState()` window).

    Fail-closed by construction (task requirement, not a nicety): a
    `rand()` call past the end of the recorded ledger raises immediately
    (OC's ported site-sampling algorithm consumed MORE raw draws than
    Karr's real one did for this tick -- a wrong branch or an extra
    call), and `assert_fully_consumed()` (call once after the tick's
    `next_update` returns) raises if any recorded draws were left unused
    (OC consumed FEWER -- a missing call or wrong draw-count formula).
    Neither failure mode is silently absorbed or approximated."""

    __slots__ = ("_draws", "_index", "_tick_label")

    def __init__(self, draws: list[float], *, tick_label: str = "<unknown>") -> None:
        # Deliberately does NOT call KarrMcg16807Stream.__init__ (which
        # requires a valid mcg16807 seed and sets up `_state`) -- this
        # class never uses the LCG formula or `_state` at all; every
        # other inherited method reaches randomness exclusively through
        # the overridden `rand()` below.
        self._draws = [float(v) for v in draws]
        self._index = 0
        self._tick_label = str(tick_label)

    def rand(self) -> float:
        if self._index >= len(self._draws):
            raise RuntimeError(
                f"KarrLedgerReplayStream[{self._tick_label}]: exhausted after "
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
        """Call once after a tick's `next_update` returns. Raises if any
        recorded draws were left unconsumed -- OC's own site-sampling
        algorithm consumed FEWER raw draws than Karr's real one did for
        this tick (a missing call or a wrong draw-count formula)."""
        if self._index != len(self._draws):
            raise RuntimeError(
                f"KarrLedgerReplayStream[{self._tick_label}]: only consumed "
                f"{self._index}/{len(self._draws)} recorded draw(s) -- OC's own "
                "site-sampling algorithm consumed FEWER raw draws than Karr's real "
                "shared-chromosome-stream ledger for this tick. This is a "
                "fail-closed divergence, not something to silently ignore."
            )
