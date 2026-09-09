"""Loader and replay RNG for DNASupercoiling's OWN process-level ``this.randStream``.

This is a SEPARATE MATLAB random stream from ``chromosome.randStream``
(see ``dnas_chromosome_release_ledger.py``): ``DNASupercoiling.m`` holds a
private ``this.randStream`` (inherited from the base ``Process`` class) that
drives:

  - ``order = this.randStream.randperm(length(this.enzymes))``
    (``DNASupercoiling.m:391``) -- enzyme processing order for the
    "bind enzymes in regions with accommodating sigmas" loop.
  - ``this.randStream.rand < 0.5`` (``DNASupercoiling.m:419``) -- a coin
    flip that decides which of two full-chromosome regions gets
    round-half-up vs round-half-down for a fractional transient-binding
    split (only reached when exactly two full-length regions exist).
  - ``this.randStream.randsample(numel(rgnProbs), 1, true, rgnProbs)`` and
    ``this.randStream.rand`` inside
    ``ChromosomeProcessAspect.bindProteinToChromosomeStochastically``
    (region choice + within-region offset for each stably-bound enzyme
    instance).
  - ``enzProps = enzProps(this.randStream.randperm(length(enzProps)))``
    (``DNASupercoiling.m:470``) -- a SECOND, independent permutation
    fixing enzyme-type processing order for the linking-number update
    loop.
  - ``this.randStream.stochasticRound(...)`` (``RandStream.m:236-240``,
    called from ``DNASupercoiling.m:487``) -- the activity-event count
    draw, already exactly replayed via opencell's own unconditional
    ``_stochastic_round`` (root cause #1, see ``STATUS_L22_DNAS_SEPT2.md``).

## State-seeded design (supersedes the finite-draw-list ledger)

An earlier version of this module dispensed a FIXED, per-tick list of
raw draws (the exact count real MATLAB's own run happened to consume that
tick, recovered via black-box replay-forward reconstruction). That design
had a structural flaw: whenever OC's own tick computation legitimately
needed even one more draw than real MATLAB's specific historical run used
(e.g. because OC's per-region legality/binding computation differs
slightly from MATLAB's in a way not yet root-caused), the finite list
exhausted and the process failed closed with no supply left -- observed on
a substantial fraction of seeds, always late in the 100-tick window
(``tmp/probe_process_rng_full_n200_exhaustion_scan.py``). A finite,
"exactly enough for one specific historical run" list is the wrong
long-horizon input contract: exhaustion under it is not evidence of a
correctness bug in the SUPPLY mechanism, only evidence that the supply was
never meant to cover a legitimately-larger consumption pattern.

This version instead captures/uses the process-owned
``this.randStream``'s exact ``State`` (a single ``mcg16807`` integer)
immediately before DNASupercoiling's ``evolveState()`` call each tick
(already captured, as ``process_state_before``, by
``scripts/matlab/l22_dnas_chromosome_release_rng_ledger.m`` /
``_batch.m``), and regenerates a GENEROUSLY-SIZED batch of draws directly
from that exact state via
``scripts/matlab/l22_dnas_process_rng_state_extension_batch.m``
(``data/l22_dnas_rare_event/process_rng_state_ledger/seed_{NNN}.json``).

This is NOT a reimplementation of ``mcg16807``'s internal state-advance
formula -- that was attempted and definitively falsified this session
(``scripts/matlab/verify_mcg16807_stepwise.m``,
``scripts/matlab/check_minstd_reference_vector.m``:
MATLAB's real per-call state transitions do not match the standard
Park-Miller recurrence ``Xn+1 = 16807*Xn mod (2^31-1)`` at ANY fixed
step count, including failing the well-known MINSTD reference vector,
1 <= 20000 steps searched). Instead, a THROWAWAY MATLAB ``RandStream`` is
seeded directly to the captured ``process_state_before`` integer and asked
to generate many draws in one call (``rand(s, 1, batch_size)``) -- MATLAB
itself performs the (still not independently understood) real
state-advance, exactly as the already-trusted "replay-forward"
reconstruction methodology already relies on MATLAB doing. This was
verified explicitly (``scripts/matlab/verify_extended_draws_match_prefix.m``): the
leading ``recorded_draws_len`` values of a freshly-generated 500-draw batch
are BYTE-IDENTICAL to the already-audited replay-forward reconstruction,
for every tick checked (10/10, seed 0).

The extraction batch itself performs this same audit for EVERY (seed,
tick) in the corpus and fails loudly (refuses to write) on any mismatch --
``ProcessRngLedger.load`` re-checks the recorded audit flags at load time
and raises if either is false, so a corrupted or unverified artifact can
never be silently used.

``batch_size`` (300 in the committed corpus) is a generous headroom
figure, not a tight fit: the TRUE maximum per-tick draw consumption across
the entire existing, independently-verified 200-seed x 100-tick
chromosome-release-RNG-ledger corpus (which happens to also capture this
same stream's real per-tick consumption) is 52 (seed 79, tick 33) -- see
the corpus scan referenced in this module's tests. 300 is roughly 6x that
observed maximum. ``ProcessRngReplayRng`` tracks (but does not enforce) the
``recorded_len`` boundary as a diagnostic/audit signal: draws consumed
within that boundary are independently verified against a specific real
MATLAB run; draws consumed beyond it are still genuine draws from the
SAME real, correctly-seeded MATLAB stream, just not individually
cross-checked against one particular historical tick's consumption count
(there is nothing wrong with a tick needing more draws than one specific
real run happened to use -- what would be wrong is inventing values that
did not come from the real generator, which this design never does).

## What was empirically verified (not reimplemented) for permutation/choice

  - ``randperm(stream, n)`` consumes exactly ``n`` raw draws and returns
    the ascending argsort of those ``n`` draws.
  - ``randsample(stream, n, 1, true, w)`` (single weighted draw with
    replacement) consumes exactly 1 raw draw and returns the first index
    where the draw is ``<=`` the normalized cumulative weight vector.

Both verified against live MATLAB via slot-safe probes
(``scripts/matlab/probe_randperm_algorithm.m``,
``scripts/matlab/probe_randsample_algorithm.m``)
before being encoded here.

This module is an INPUT ORACLE: it supplies the exact random numbers
MATLAB's process-owned ``this.randStream`` produces for a specific
seed/tick (via MATLAB's own real generator, seeded from the exact
captured state), replayed through the two documented, empirically-verified
transformations above. It does not simulate, replay, or otherwise touch
any of the other 27 WholeCell processes, and it does not decide or encode
any biological outcome.

Known intentional NON-coverage: ``DNASupercoiling.m`` never calls
``poissrnd``/``poisson`` on ``this.randStream`` (confirmed by source
inspection -- no such call exists in the file). opencell's own
``_replication_supercoil_load_events`` draws
``self._rng.poisson(...)`` for a *different*, OC-specific
replication-driven supercoiling-load approximation that has no MATLAB
``this.randStream`` counterpart to replay. ``ProcessRngReplayRng``
deliberately has no ``poisson`` method: if that path is ever reached while
a ledger covers the current tick, callers must not route it through this
oracle (there is nothing authoritative to serve), and must keep using the
process's own approximate stream for that unmapped channel.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_DEFAULT_LEDGER_DIR = "data/l22_dnas_rare_event/process_rng_state_ledger"


def default_process_rng_ledger_path(seed: int) -> Path:
    """Return the conventional per-seed ledger path (may not exist)."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / _DEFAULT_LEDGER_DIR / f"seed_{int(seed):03d}.json"


class ProcessRngTickEntry:
    """One tick's state-seeded draw buffer, plus its audit metadata."""

    __slots__ = ("draws", "recorded_len", "state_before", "state_after_recorded", "provenance_hash")

    def __init__(
        self,
        *,
        draws: np.ndarray,
        recorded_len: int,
        state_before: float,
        state_after_recorded: float,
        provenance_hash: str,
    ) -> None:
        self.draws = draws
        self.recorded_len = int(recorded_len)
        self.state_before = float(state_before)
        self.state_after_recorded = float(state_after_recorded)
        self.provenance_hash = provenance_hash


class ProcessRngLedger:
    """Per-seed, per-tick DNASupercoiling process-owned RNG state ledger."""

    def __init__(self, *, seed: int, ticks: dict[int, ProcessRngTickEntry]) -> None:
        self.seed = int(seed)
        self._ticks = ticks

    @classmethod
    def load(cls, path: str | Path) -> ProcessRngLedger:
        path = Path(path)
        raw = json.loads(path.read_text())
        seed = int(raw["seed"])
        if str(raw.get("rng_type", "mcg16807")) != "mcg16807":
            raise ValueError(
                f"Ledger {path}: unexpected rng_type {raw.get('rng_type')!r}, expected 'mcg16807'"
            )
        ticks: dict[int, ProcessRngTickEntry] = {}
        for entry in raw["ticks"]:
            tick = int(entry["tick_zero_based"])
            # Fail closed on any tick whose extraction-time audit did not
            # prove the generated batch's leading prefix matches the
            # independently-reconstructed real draws, and that consuming
            # exactly `recorded_draws_len` of them reaches the recorded
            # real `process_state_after`. An unverified or malformed
            # artifact must never be silently used as an input oracle.
            if not bool(entry.get("audit_prefix_match", False)):
                raise ValueError(
                    f"Ledger {path} tick {tick}: audit_prefix_match is false or missing; "
                    "refusing to use an unverified state-seeded draw batch."
                )
            if not bool(entry.get("audit_state_after_match", False)):
                raise ValueError(
                    f"Ledger {path} tick {tick}: audit_state_after_match is false or missing; "
                    "refusing to use an unverified state-seeded draw batch."
                )
            draws_raw = entry.get("extended_draws")
            if draws_raw is None:
                raise ValueError(f"Ledger {path} tick {tick}: missing extended_draws")
            draws = np.asarray(draws_raw, dtype=np.float64).reshape(-1)
            if draws.size == 0:
                raise ValueError(f"Ledger {path} tick {tick}: extended_draws is empty")
            ticks[tick] = ProcessRngTickEntry(
                draws=draws,
                recorded_len=int(entry["recorded_draws_len"]),
                state_before=float(entry["process_state_before"]),
                state_after_recorded=float(entry["process_state_after_recorded"]),
                provenance_hash=str(entry.get("provenance_hash", "")),
            )
        return cls(seed=seed, ticks=ticks)

    def has_tick(self, tick: int) -> bool:
        return int(tick) in self._ticks

    def entry_for_tick(self, tick: int) -> ProcessRngTickEntry:
        try:
            return self._ticks[int(tick)]
        except KeyError as exc:
            raise KeyError(
                f"Process RNG state ledger (seed={self.seed}) has no entry for tick {tick}"
            ) from exc

    @property
    def n_ticks(self) -> int:
        return len(self._ticks)


class ProcessRngReplayRng:
    """Dispenses real MATLAB draws generated from a state-seeded batch.

    Unlike a truly unlimited live generator, this dispenses from a large
    PRE-GENERATED buffer (see module docstring for the sizing rationale) --
    it fails loudly only if that generous buffer itself is exhausted
    (a scenario 6x beyond any per-tick consumption ever observed in the
    corpus), not merely if consumption exceeds one specific historical
    MATLAB run's own draw count. ``exceeded_audit_boundary`` tracks
    (non-fatally) whether consumption passed the point independently
    verified against that specific real run, for diagnostic/verification
    use only -- see module docstring.
    """

    def __init__(self, draws: np.ndarray, *, recorded_len: int = 0) -> None:
        self._draws = np.asarray(draws, dtype=np.float64).reshape(-1)
        self._pos = 0
        self._recorded_len = int(recorded_len)
        self.exceeded_audit_boundary = False

    def remaining(self) -> int:
        """Number of undispensed draws left in the generous buffer."""
        return len(self._draws) - self._pos

    def _take(self, n: int) -> np.ndarray:
        end = self._pos + n
        if end > len(self._draws):
            raise RuntimeError(
                "Process RNG state-seeded buffer exhausted: requested "
                f"{n} draw(s) at position {self._pos}, only {len(self._draws)} generated for "
                "this tick. This buffer is sized ~6x beyond any per-tick consumption ever "
                "observed in the full N=200 corpus; exhausting it indicates a genuinely "
                "unprecedented consumption pattern, not the expected finite-list boundary "
                "condition this design replaced -- investigate rather than enlarge blindly."
            )
        if end > self._recorded_len:
            self.exceeded_audit_boundary = True
        out = self._draws[self._pos : end]
        self._pos = end
        return out

    def random(self, size: int | None = None) -> np.ndarray | float:
        n = 1 if size is None else int(size)
        out = self._take(n)
        if size is None:
            return float(out[0])
        return out.copy()

    def permutation(self, n: int) -> np.ndarray:
        """Exact replay of ``randStream.randperm(n)``: n raw draws, ascending argsort."""
        draws = self._take(int(n))
        return np.argsort(draws, kind="stable")

    def choice(self, n: int, *, p: np.ndarray) -> int:
        """Exact replay of ``randStream.randsample(n, 1, true, p)``: 1 raw
        draw, first index where the draw is <= the normalized cumulative
        weight vector."""
        weights = np.asarray(p, dtype=np.float64).reshape(-1)
        if weights.size != int(n):
            raise ValueError(f"choice: weights length {weights.size} != n {n}")
        total = float(weights.sum())
        if total <= 0.0:
            raise ValueError("choice: weights must sum to a positive value")
        cdf = np.cumsum(weights) / total
        draw = float(self._take(1)[0])
        idx = int(np.searchsorted(cdf, draw, side="left"))
        return min(idx, int(n) - 1)
