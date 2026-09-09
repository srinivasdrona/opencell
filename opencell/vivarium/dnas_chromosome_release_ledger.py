"""Loader and replay RNG for the DNASupercoiling chromosome-owned release RNG ledger.

The ledger captures the exact ``chromosome.randStream`` state immediately
before and after each tick's live MATLAB DNASupercoiling ``evolveState()``
call (see ``scripts/matlab/l22_dnas_chromosome_release_rng_ledger.m``), plus
the exact sequence of uniform draws consumed in between. Those draws are
recovered by a formula-free "replay-forward" reconstruction: a throwaway
MATLAB ``RandStream`` (never the live production stream) is seeded to the
captured before-state and stepped one draw at a time until its state matches
the captured after-state exactly. This needs no knowledge of MATLAB's
internal ``mcg16807`` advance formula, only the (empirically proven) fact
that ``RandStream.State`` alone fully determines all subsequent draws.

This is an input oracle: it supplies the exact random numbers MATLAB's
chromosome-owned release stream produced for a specific seed/tick, not any
biological decision or outcome, and it is scoped to DNASupercoiling's own
release consumption of ``chromosome.randStream`` only -- it does not
simulate, replay, or otherwise touch any of the other 27 WholeCell
processes.

Known, UNRESOLVED exhaustion pattern (previously mischaracterized as an
allowed "population-saturation boundary", now rejected): a full-corpus scan
(``tmp/scan_crash_risk.py``) found 476/20000 seed/tick combinations
(18/200 seeds) where the release candidate count Python computes from the
tick-start ``states_before`` chromosome snapshot (``matching.size``, equal
to the scalar ``boundEnzymes[gyrase]`` oracle value) exceeds the ledger's
recorded draw count for that tick -- always by exactly 1, and always
exactly when the bound count is at that seed's gyrase population cap (all
molecules bound, zero free). A prior revision of this module (commit
``cb3889e``) treated this as a structural precision limit of a tick-start
single-process snapshot and papered over it with a counted fallback draw
from the process's own RNG. That fallback was rejected (commit reverting
it: see git log) because a per-tick candidate-count mismatch between two
traces of the *same* deterministic MATLAB run is evidence of a real,
first-order source/state divergence -- not a property of "saturation" that
is safe to paper over. ``ChromosomeReleaseReplayRng`` fails loudly
(``RuntimeError``) on ANY exhaustion, including this pattern, with no
fallback. The correct next step is root-causing the mismatch itself (why
does OC's tick-start snapshot imply 50 release candidates when MATLAB's own
release call only consumed 49 draws?) via a narrow, seed/tick-scoped
Karr-vs-OC ledger of the exact release call inputs -- see
``scripts/l22_dnas_release_call_ledger.py`` (or equivalent per-tick probe)
and ``STATUS_L22_DNAS_SEPT2.md`` for the investigation in progress.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

_DEFAULT_LEDGER_DIR = "data/l22_dnas_rare_event/chromosome_release_rng_ledger"


def default_ledger_path(seed: int) -> Path:
    """Return the conventional per-seed ledger path (may not exist)."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / _DEFAULT_LEDGER_DIR / f"seed_{int(seed):03d}.json"


def _scalar_state_value(raw: object) -> float:
    if isinstance(raw, list):
        if not raw:
            raise ValueError("randStream state values array is empty")
        return float(raw[0])
    return float(raw)  # type: ignore[arg-type]


def _tick_hash(*, seed: int, tick: int, state_before: float, state_after: float, draws: list[float]) -> str:
    payload = json.dumps(
        {
            "seed": int(seed),
            "tick": int(tick),
            "state_before": float(state_before),
            "state_after": float(state_after),
            "draws": [float(d) for d in draws],
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ChromosomeReleaseLedger:
    """Per-seed, per-tick chromosome-owned release RNG draw ledger."""

    def __init__(self, *, seed: int, ticks: dict[int, np.ndarray], hashes: dict[int, str]) -> None:
        self.seed = int(seed)
        self._ticks = ticks
        self._hashes = hashes

    @classmethod
    def load(cls, path: str | Path) -> ChromosomeReleaseLedger:
        path = Path(path)
        raw = json.loads(path.read_text())
        seed = int(raw["seed"])
        ticks: dict[int, np.ndarray] = {}
        hashes: dict[int, str] = {}
        for entry in raw["ticks"]:
            tick = int(entry["tick_zero_based"])
            if not bool(entry.get("chromosome_release_draws_reconstructed_ok", False)):
                raise ValueError(
                    f"Ledger {path} tick {tick}: chromosome release draw reconstruction "
                    "did not converge (chromosome_release_draws_reconstructed_ok=False); "
                    "refusing to use an unproven reconstruction."
                )
            draws_raw = entry.get("chromosome_release_draws")
            if draws_raw is None:
                draws = np.zeros(0, dtype=np.float64)
            elif isinstance(draws_raw, (int, float)):
                draws = np.asarray([float(draws_raw)], dtype=np.float64)
            else:
                draws = np.asarray(draws_raw, dtype=np.float64).reshape(-1)
            state_before = _scalar_state_value(entry["chromosome_state_before"]["values"])
            state_after = _scalar_state_value(entry["chromosome_state_after"]["values"])
            ticks[tick] = draws
            hashes[tick] = _tick_hash(
                seed=seed,
                tick=tick,
                state_before=state_before,
                state_after=state_after,
                draws=draws.tolist(),
            )
        return cls(seed=seed, ticks=ticks, hashes=hashes)

    def has_tick(self, tick: int) -> bool:
        return int(tick) in self._ticks

    def draws_for_tick(self, tick: int) -> np.ndarray:
        try:
            return self._ticks[int(tick)]
        except KeyError as exc:
            raise KeyError(
                f"Chromosome release RNG ledger (seed={self.seed}) has no entry for tick {tick}"
            ) from exc

    def hash_for_tick(self, tick: int) -> str:
        return self._hashes[int(tick)]

    @property
    def n_ticks(self) -> int:
        return len(self._ticks)


class ChromosomeReleaseReplayRng:
    """Dispenses exactly the recorded MATLAB chromosome-release draws, in order.

    This is NOT a random number generator: it replays a fixed, pre-recorded
    sequence of uniform values captured from live MATLAB execution for a
    single tick. It fails loudly if asked for more draws than were recorded,
    rather than silently falling back to an independently generated value.
    """

    def __init__(self, draws: np.ndarray) -> None:
        self._draws = np.asarray(draws, dtype=np.float64).reshape(-1)
        self._pos = 0

    def remaining(self) -> int:
        """Number of recorded draws not yet consumed for this tick."""
        return len(self._draws) - self._pos

    def random(self, size: int | None = None) -> np.ndarray | float:
        n = 1 if size is None else int(size)
        end = self._pos + n
        if end > len(self._draws):
            raise RuntimeError(
                "Chromosome release RNG replay exhausted: requested "
                f"{n} draw(s) at position {self._pos}, only {len(self._draws)} recorded for this tick."
            )
        out = self._draws[self._pos : end]
        self._pos = end
        if size is None:
            return float(out[0])
        return out.copy()
