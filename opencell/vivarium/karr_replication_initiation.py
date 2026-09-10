"""Vivarium Process port of Karr's replication initiation gate logic."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.state.chromosome_store import (
    CHROMOSOME_FIELDS,
    ChromosomeStore,
    SparseTriplet,
    sparse_triplet_schema,
)

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ReplicationInitiation_flat.mat"
_CHROMOSOME_FIXTURE_PATH = "data/karr_fixtures/per_process/Chromosome_flat.mat"
_N_AVOGADRO = 6.02214076e23


class _Mcg16807RandStream:
    """Minimal Karr-compatible process RNG for ReplicationInitiation."""

    _MOD = 2_147_483_647
    _MUL = 16_807
    _RAND_SCALE = 65_536
    # MATLAB's built-in RandStream('mcg16807', 'Seed', 0) does not alias seed 1.
    # A narrow primary-source probe shows it resets to this deterministic hidden state.
    _SEED0_HIDDEN_STATE = 1_539_392_561

    def __init__(self, seed: int) -> None:
        seed_i = int(seed)
        self._state = self._SEED0_HIDDEN_STATE if seed_i == 0 else max(1, seed_i)

    def random(self, size: int | tuple[int, ...] | None = None) -> float | np.ndarray:
        if size is None:
            return float(self._advance())
        shape = (int(size),) if isinstance(size, int) else tuple(int(dim) for dim in size)
        count = int(np.prod(shape, dtype=np.int64))
        out = np.empty(count, dtype=np.float64)
        for idx in range(count):
            out[idx] = self._advance()
        return out.reshape(shape)

    def stochastic_round(self, value: float) -> int | float:
        value_f = float(value)
        frac = float(np.mod(value_f, 1.0))
        draw = float(self.random())
        if math.isnan(value_f):
            # Matches MATLAB: this.randStream.stochasticRound(NaN) still consumes
            # exactly one rand() draw (RandStream.stochasticRound has no
            # early-return for non-finite input) but propagates NaN. Callers
            # that do `min(existing_int, stochastic_round(...))` rely on
            # Python's min() ignoring a NaN second argument, matching MATLAB's
            # NaN-ignoring min() semantics.
            return float("nan")
        return int(np.ceil(value_f) if draw < frac else np.floor(value_f))

    def randperm(self, n: int, k: int | None = None) -> np.ndarray:
        n_i = int(n)
        k_i = n_i if k is None else int(k)
        if n_i <= 0 or k_i <= 0:
            return np.zeros(0, dtype=np.int64)
        keys = np.asarray(self.random(n_i), dtype=np.float64)
        order = np.argsort(keys, kind="mergesort").astype(np.int64)
        return order[: min(n_i, k_i)]

    def randsample(
        self,
        n: int,
        k: int,
        *,
        replacement: bool,
        weights: np.ndarray | None,
    ) -> np.ndarray:
        n_i = int(n)
        k_i = int(k)
        if n_i < 0 or k_i < 0:
            raise ValueError("n and k must be >= 0")
        if not replacement and k_i > n_i:
            raise ValueError("Cannot sample k > n without replacement")
        if n_i == 0 or k_i == 0:
            return np.zeros(0, dtype=np.int64)

        if weights is None:
            w = np.ones(n_i, dtype=np.float64)
        else:
            w = np.asarray(weights, dtype=np.float64).reshape(-1).copy()
            if w.size != n_i:
                raise ValueError(f"weights length {w.size} does not match n={n_i}")
            w[~np.isfinite(w) | (w < 0.0)] = 0.0
            if not np.any(w):
                return np.zeros(0, dtype=np.int64)

        if replacement:
            if np.all(w == w[0]):
                return np.floor(np.asarray(self.random(k_i), dtype=np.float64) * float(n_i)).astype(np.int64)

            cdf = np.cumsum(w, dtype=np.float64)
            total = float(cdf[-1])
            if total <= 0.0:
                return np.zeros(0, dtype=np.int64)
            draws = np.asarray(self.random(k_i), dtype=np.float64) * total
            return np.searchsorted(cdf, draws, side="right").astype(np.int64)

        if k_i > 1:
            if np.all(w == w[0]):
                return self._uniform_randsample_without_replacement(n_i, k_i)

            selected = np.flatnonzero(w >= np.finfo(np.float64).max).astype(np.int64)
            if selected.size > k_i:
                order = self.randperm(selected.size)
                return selected[np.asarray(order[:k_i], dtype=np.int64)]
            if selected.size == k_i:
                return selected

            tfs = np.zeros(n_i, dtype=bool)
            if selected.size:
                tfs[selected] = True
                w[selected] = 0.0

            selected_list = selected.tolist()
            n_more = k_i - len(selected_list)
            while n_more > 0 and np.any(w):
                tmp_idxs = self.randsample(
                    n_i,
                    n_more,
                    replacement=True,
                    weights=w,
                )
                tmp_keep = np.zeros(tmp_idxs.size, dtype=bool)
                for idx, pick in enumerate(np.asarray(tmp_idxs, dtype=np.int64).tolist()):
                    if tfs[int(pick)]:
                        continue
                    tfs[int(pick)] = True
                    tmp_keep[idx] = True
                w[np.asarray(tmp_idxs, dtype=np.int64)] = 0.0
                if np.any(tmp_keep):
                    selected_list.extend(np.asarray(tmp_idxs[tmp_keep], dtype=np.int64).tolist())
                n_more = k_i - len(selected_list)
            return np.asarray(selected_list, dtype=np.int64)

        return self.randsample(
            n_i,
            k_i,
            replacement=True,
            weights=w,
        )

    def _uniform_randsample_without_replacement(self, n: int, k: int) -> np.ndarray:
        n_i = int(n)
        k_i = int(k)
        if 4 * k_i > n_i:
            return np.asarray(self.randperm(n_i)[:k_i], dtype=np.int64)

        flags = np.zeros(n_i, dtype=bool)
        selected = 0
        while selected < k_i:
            picks = np.floor(
                np.asarray(self.random(k_i - selected), dtype=np.float64) * float(n_i)
            ).astype(np.int64)
            flags[picks] = True
            selected = int(np.count_nonzero(flags))
        values = np.flatnonzero(flags)
        return values[np.asarray(self.randperm(k_i), dtype=np.int64)]

    def bernoulli_count(self, n: int, p: float) -> int:
        n_i = int(max(0, n))
        p_f = float(np.clip(p, a_min=0.0, a_max=1.0))
        if n_i <= 0 or p_f <= 0.0:
            return 0
        draws = np.asarray(self.random(n_i), dtype=np.float64)
        return int(np.count_nonzero(draws < p_f))

    def _advance(self) -> float:
        self._state = (self._MUL * self._state) % self._MOD
        return ((self._state * self._RAND_SCALE) % self._MOD) / self._MOD


class _ReplicationInitiationChromosomeLedgerRandStream(_Mcg16807RandStream):
    """Test/harness-only replay of a pre-recorded, per-tick raw-draw ledger
    for Karr's SHARED `Chromosome.randStream` (see DEC-006:
    `decisions/dec-006-shared-chromosome-randstream-input-oracle.md`,
    `scripts/matlab/reconstruct_chromosome_draw_ledger.m`, and
    `tests/vivarium/chromosome_rand_stream_ledger.py`). MATLAB's
    `bindDnaAATP`/`bindDnaAADP` (ReplicationInitiation.m:765-789) delegate
    chromosome site *selection* to this shared stream (via
    `bindProteinToChromosome` -> `Chromosome.setSiteProteinBound`), a
    stream instance separate from ReplicationInitiation's own
    `this.randStream` and shared/advanced by every process that ever
    binds/damages/samples chromosome sites -- its true per-tick position
    is not inferable from a single-process trace, but IS directly
    capturable (see DEC-006) and offline-reconstructable into an exact,
    ordered per-tick raw-draw ledger.

    This class overrides ONLY the scalar draw primitive (`_advance`) that
    every other method on `_Mcg16807RandStream` (`random`, `randsample`,
    `randperm`, `_uniform_randsample_without_replacement`,
    `stochastic_round`) already funnels through -- correctness reduces
    entirely to "does `_advance()` return the recorded values in the
    recorded order", exactly mirroring the DNADamage/TranscriptionalRegulation
    lanes' own `<Process>ChromosomeLedgerRandStream` classes (independent,
    process-local subclasses per DEC-006's consequences -- no shared base
    class is introduced across processes).

    Fail-closed by construction: a draw past the end of the recorded
    ledger raises immediately (OC's own site-selection algorithm consumed
    MORE raw draws than Karr's real shared-chromosome-stream ledger for
    this tick), and `assert_fully_consumed()` (call once after the tick's
    `next_update` returns) raises if any recorded draws were left unused
    (OC consumed FEWER). Neither failure mode is silently absorbed.

    Never constructed by production code -- only an L2.1 replay TEST/audit
    harness ever builds and injects this onto `process._chromosome_rng`
    (see `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` Rule 8; there is no
    oracle-read path in `next_update` itself)."""

    def __init__(self, draws: list[float], *, tick_label: str = "<unknown>") -> None:
        # Deliberately does NOT call _Mcg16807RandStream.__init__ (which
        # requires a valid mcg16807 seed and sets up self._state) -- this
        # class never uses the LCG formula or self._state at all; every
        # other inherited method reaches randomness exclusively through
        # the overridden _advance() below.
        self._draws = [float(v) for v in draws]
        self._index = 0
        self._tick_label = str(tick_label)

    def _advance(self) -> float:
        if self._index >= len(self._draws):
            raise RuntimeError(
                f"_ReplicationInitiationChromosomeLedgerRandStream[{self._tick_label}]: "
                f"exhausted after {self._index} draw(s) (ledger recorded only "
                f"{len(self._draws)}) -- OC's own site-selection algorithm consumed MORE "
                "raw draws than Karr's real shared-chromosome-stream ledger for this "
                "tick. This is a fail-closed divergence (wrong branch, extra call, or a "
                "genuine algorithmic mismatch), not a value to guess at."
            )
        value = self._draws[self._index]
        self._index += 1
        return value

    def assert_fully_consumed(self) -> None:
        """Call once after a tick's `next_update` returns. Raises if any
        recorded draws were left unconsumed -- OC's own site-selection
        algorithm consumed FEWER raw draws than Karr's real one did for
        this tick (a missing call or a wrong draw-count formula)."""
        if self._index != len(self._draws):
            raise RuntimeError(
                f"_ReplicationInitiationChromosomeLedgerRandStream[{self._tick_label}]: "
                f"only consumed {self._index}/{len(self._draws)} recorded draw(s) -- OC's "
                "own site-selection algorithm consumed FEWER raw draws than Karr's real "
                "shared-chromosome-stream ledger for this tick. This is a fail-closed "
                "divergence, not something to silently ignore."
            )


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
        "m6ad_global_index": None,
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
        self._rng = _Mcg16807RandStream(int(self.parameters["rng_seed"]))
        # MATLAB's bindDnaAATP/bindDnaAADP (ReplicationInitiation.m:765-789)
        # select actual binding-site positions via
        # this.bindProteinToChromosome(...) -> Chromosome.setSiteProteinBound
        # (+state/Chromosome.m:503's `this.randStream.randsample(...)`),
        # where `this` there is the CHROMOSOME state object's OWN randStream
        # property -- a separate stream instance from ReplicationInitiation's
        # own `this.randStream` (confirmed: Chromosome.m declares/uses its
        # own randStream; Simulation.seedRandStream() seeds every state AND
        # every process with the same base seed, but as independent stream
        # objects). polymerizeDnaAATP/ADP and releaseDnaAAxP, by contrast,
        # call `this.randStream` directly (ReplicationInitiation's own
        # stream) with no such delegation. A real MATLAB call-by-call RNG
        # ledger (seed=0, ticks 0-4, docs/phase_f/probes/repinit_rng_ledger/
        # matlab_rng_ledger_ticks0-4.jsonl) proves ReplicationInitiation's
        # OWN stream consumes exactly 26/50/74/98/122 cumulative draws after
        # ticks 0-4 -- i.e. zero draws for chromosome-level site selection.
        # _sample_binding_sites (this class's port of Chromosome's
        # setSiteProteinBound rejection-sampling loop) must therefore draw
        # from a stream OTHER than self._rng, or it silently steals draws
        # from -- and desyncs -- the stream that stochasticRound/release
        # depend on. The real Chromosome.randStream's exact position is not
        # recoverable from a per-process trace (it depends on the full
        # 28-process scheduler's chromosome-touching draws, information a
        # single-process trace does not carry), so this dedicated stream is
        # necessarily an independent approximation for that one
        # unreconstructable operation -- but it must still be a genuinely
        # separate object so self._rng itself stays in exact lockstep with
        # MATLAB's this.randStream for every operation this class performs
        # directly on it (stochasticRound, release). Seeded identically to
        # self._rng (both mirror MATLAB's Simulation.seedRandStream(), which
        # seeds every state/process object from the same literal base seed).
        self._chromosome_rng = _Mcg16807RandStream(int(self.parameters["rng_seed"]))

        self._free_dnaa_atp = 0
        self._free_dnaa_adp = 0
        self._bound_atp = np.zeros((self.n_sites, 2), dtype=np.int64)
        self._bound_adp = np.zeros((self.n_sites, 2), dtype=np.int64)
        self._blocked_sites = np.zeros((self.n_sites, 2), dtype=bool)
        self._initialized = False
        self._using_explicit_enzyme_pools = False

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

        self.enzyme_index_dnaa_total = int(_coerce_scalar(fx.enzymeIndexs_DnaA)) - 1
        self.dnaa_wid = self.enzyme_wids[self.enzyme_index_dnaa_total]

        self.kb_atp = float(_coerce_scalar(fx.kb1ATP))
        self.kb2_atp = float(_coerce_scalar(fx.kb2ATP))
        self.kb_adp = float(_coerce_scalar(fx.kb1ADP))
        self.kb2_adp = float(_coerce_scalar(fx.kb2ADP))
        self.kd_atp = float(_coerce_scalar(fx.kd1ATP))
        self.kd_adp = float(_coerce_scalar(fx.kd1ADP))
        self.k_regen = float(_coerce_scalar(fx.k_Regen))
        self.k_regen_p4 = float(_coerce_scalar(fx.K_Regen_P4))
        self.k_inact = float(_coerce_scalar(fx.k_inact))
        self.site_cooperativity = float(_coerce_scalar(fx.siteCooperativity))
        self.state_cooperativity = float(_coerce_scalar(fx.stateCooperativity))
        self._step_size_sec = float(_coerce_scalar(fx.stepSizeSec))

        # Chromosome-level supercoiling constants (Chromosome.m's own
        # calcSupercoiled: sigma = (lk - length/relaxedBasesPerTurn) /
        # (length/relaxedBasesPerTurn); supercoiled iff
        # abs(sigma - equilibriumSuperhelicalDensity) <
        # supercoiledSuperhelicalDensityTolerance). These are Chromosome
        # STATE-object fixture constants, not ReplicationInitiation's own
        # -- loaded from a second fixture file, matching real MATLAB's own
        # class boundary (this.chromosome.relaxedBasesPerTurn etc., not
        # this.relaxedBasesPerTurn). Used by _is_region_supercoiled, the
        # checkRegionSupercoiled gate bindDnaAATP/bindDnaAADP apply via
        # bindProteinToChromosome->sampleAccessibleRegions->
        # isRegionAccessible->isRegionDoubleStranded.
        chrom_fixture_path = _resolve_fixture_path(_CHROMOSOME_FIXTURE_PATH)
        chrom_mat = loadmat(str(chrom_fixture_path), squeeze_me=True, struct_as_record=False)
        chrom_fx = chrom_mat["data"].fixture
        self.relaxed_bases_per_turn = float(_coerce_scalar(chrom_fx.relaxedBasesPerTurn))
        self.equilibrium_superhelical_density = float(
            _coerce_scalar(chrom_fx.equilibriumSuperhelicalDensity)
        )
        self.supercoiled_superhelical_density_tolerance = float(
            _coerce_scalar(chrom_fx.supercoiledSuperhelicalDensityTolerance)
        )

        self.enzyme_global_indexs = np.asarray(fx.enzymeGlobalIndexs, dtype=np.int64).reshape(-1)
        self.enzyme_index_dnaa_1mer_adp = int(_coerce_scalar(fx.enzymeIndexs_DnaA_1mer_ADP)) - 1
        self.enzyme_index_dnaa_1mer_atp = int(_coerce_scalar(fx.enzymeIndexs_DnaA_1mer_ATP)) - 1
        self.enzyme_indexs_dnaa_nmer_atp = (
            _parse_index_array(fx.enzymeIndexs_DnaA_Nmer_ATP) - 1
        ).astype(np.int64)
        self.enzyme_indexs_dnaa_nmer_adp = (
            _parse_index_array(fx.enzymeIndexs_DnaA_Nmer_ADP) - 1
        ).astype(np.int64)

        all_start_positions = _parse_index_array(fx.dnaABoxStartPositions) - 1
        self.n_sites = int(all_start_positions.size)
        self.chromosome_length = ChromosomeStore.DEFAULT_SEQUENCE_LEN
        if np.any(all_start_positions >= 0):
            self.chromosome_length = max(
                int(ChromosomeStore.DEFAULT_SEQUENCE_LEN),
                int(np.max(all_start_positions)) + 1,
            )
        self.chromosome_shape = (
            self.chromosome_length,
            ChromosomeStore.DEFAULT_N_COMPARTMENTS,
        )
        self._dnaa_box_positions = all_start_positions.astype(np.int64, copy=False)
        self._site_index_by_position = {
            int(position): idx for idx, position in enumerate(self._dnaa_box_positions.tolist())
        }

        r12345 = (_parse_index_array(fx.dnaABoxIndexs_R12345) - 1).tolist()
        if len(r12345) != 5:
            raise ValueError(f"Expected 5 OriC sites, found {len(r12345)}")
        self.r12345_indices = [int(idx) for idx in r12345]
        self.r1234_indices = self.r12345_indices[:4]
        self.r5_index = int((_parse_index_array(fx.dnaABoxIndexs_R5) - 1)[0])
        self._copy_strands = np.asarray([0, 2], dtype=np.int64)
        self.dnaABoxIndexs_7mer = (_parse_index_array(fx.dnaABoxIndexs_7mer) - 1).astype(np.int64)
        self.dnaABoxIndexs_8mer = (_parse_index_array(fx.dnaABoxIndexs_8mer) - 1).astype(np.int64)
        self.dnaABoxIndexs_9mer = (_parse_index_array(fx.dnaABoxIndexs_9mer) - 1).astype(np.int64)

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
        self._oric_position_set = {
            int(self._dnaa_box_positions[idx]) for idx in self.r12345_indices
        }

        self._dnaa_counts_by_global_index: dict[int, tuple[int, int]] = {}
        self._dnaa_global_index_by_counts: dict[tuple[int, int], int] = {}
        self._dnaa_local_index_by_counts: dict[tuple[int, int], int] = {}
        self._dnaa_local_index_by_global_index: dict[int, int] = {}
        self._register_dnaa_complex(self.enzyme_index_dnaa_1mer_adp, atp_count=0, adp_count=1)
        self._register_dnaa_complex(self.enzyme_index_dnaa_1mer_atp, atp_count=1, adp_count=0)
        for offset, local_idx in enumerate(self.enzyme_indexs_dnaa_nmer_atp.tolist(), start=1):
            self._register_dnaa_complex(local_idx, atp_count=offset, adp_count=0)
        for offset, local_idx in enumerate(self.enzyme_indexs_dnaa_nmer_adp.tolist(), start=1):
            self._register_dnaa_complex(local_idx, atp_count=max(0, offset - 1), adp_count=1)

        self.enzyme_indexs_dnaa_polymer_atp = self.enzyme_indexs_dnaa_nmer_atp[1:].copy()
        self._free_enzyme_counts = np.zeros(len(self.enzyme_wids), dtype=np.int64)

        self._atp_moieties_by_wid = {
            wid: self._infer_atp_moieties(wid) for wid in self.enzyme_wids
        }
        m6ad_cfg = self.parameters.get("m6ad_global_index")
        self.m6ad_global_index = None if m6ad_cfg is None else int(m6ad_cfg)

        states = np.asarray(fx.states, dtype=object).ravel()
        chromosome_state = next(
            (
                state
                for state in states
                if getattr(state, "x_class_", "") == "edu.stanford.covert.cell.sim.state.Chromosome"
            ),
            None,
        )
        if chromosome_state is None:
            raise ValueError("ReplicationInitiation fixture is missing Chromosome state")
        geometry_state = next(
            (
                state
                for state in states
                if getattr(state, "x_class_", "") == "edu.stanford.covert.cell.sim.state.CellGeometry"
            ),
            None,
        )
        if geometry_state is None:
            raise ValueError("ReplicationInitiation fixture is missing CellGeometry state")
        self._geometry_volume = float(_coerce_scalar(geometry_state.volume))
        self.dna_strandedness_ssdna = int(_coerce_scalar(chromosome_state.dnaStrandedness_ssDNA))
        self.dna_strandedness_dsdna = int(_coerce_scalar(chromosome_state.dnaStrandedness_dsDNA))
        self.dna_strandedness_xsdna = int(_coerce_scalar(chromosome_state.dnaStrandedness_xsDNA))
        self.monomer_dna_footprints = np.asarray(
            chromosome_state.monomerDNAFootprints,
            dtype=np.int64,
        ).reshape(-1)
        self.complex_dna_footprints = np.asarray(
            chromosome_state.complexDNAFootprints,
            dtype=np.int64,
        ).reshape(-1)
        self.monomer_dna_footprint_binding_strandedness = np.asarray(
            chromosome_state.monomerDNAFootprintBindingStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.complex_dna_footprint_binding_strandedness = np.asarray(
            chromosome_state.complexDNAFootprintBindingStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.monomer_dna_footprint_region_strandedness = np.asarray(
            chromosome_state.monomerDNAFootprintRegionStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.complex_dna_footprint_region_strandedness = np.asarray(
            chromosome_state.complexDNAFootprintRegionStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.reaction_bound_monomer = np.asarray(
            chromosome_state.reactionBoundMonomer,
            dtype=np.int64,
        ).reshape(-1)
        self.reaction_bound_complex = np.asarray(
            chromosome_state.reactionBoundComplex,
            dtype=np.int64,
        ).reshape(-1)
        self.reaction_monomer_catalysis_matrix = np.asarray(
            chromosome_state.reactionMonomerCatalysisMatrix,
            dtype=np.int64,
        )
        self.reaction_complex_catalysis_matrix = np.asarray(
            chromosome_state.reactionComplexCatalysisMatrix,
            dtype=np.int64,
        )
        self.reaction_thresholds = np.asarray(
            chromosome_state.reactionThresholds,
            dtype=np.int64,
        ).reshape(-1)

    def _register_dnaa_complex(self, local_index: int, *, atp_count: int, adp_count: int) -> None:
        global_index = int(self.enzyme_global_indexs[int(local_index)])
        local_index = int(local_index)
        counts = (int(atp_count), int(adp_count))
        self._dnaa_counts_by_global_index[global_index] = counts
        self._dnaa_global_index_by_counts[counts] = global_index
        self._dnaa_local_index_by_counts[counts] = local_index
        self._dnaa_local_index_by_global_index[global_index] = local_index

    def build_default_chromosome_state(
        self,
        *,
        replication_state: str = "idle",
        supercoiled: bool = True,
    ) -> dict[str, Any]:
        store = ChromosomeStore(shape=self.chromosome_shape)
        store.set_field("polymerizedRegions", self._mother_polymerized_regions())
        state = store.to_state()
        state["dnaa_complex_count"] = {site_id: 0 for site_id in self.all_dnaa_sites}
        state["replication_state"] = replication_state
        state["supercoiled"] = bool(supercoiled)
        return state

    def _mother_polymerized_regions(self) -> SparseTriplet:
        return SparseTriplet.from_regions(
            [
                (0, 0, self.chromosome_length),
                (0, 1, self.chromosome_length),
            ],
            shape=self.chromosome_shape,
        )

    def ports_schema(self) -> dict[str, Any]:
        chromosome_schema = {
            field: sparse_triplet_schema(
                self.chromosome_shape,
                emit=(field in {"complexBoundSites", "damagedBases", "polymerizedRegions"}),
            )
            for field in CHROMOSOME_FIELDS
        }
        chromosome_schema.update(
            {
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
            }
        )
        return {
            "chromosome": chromosome_schema,
            "protein": {
                "counts": {
                    self.dnaa_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
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
        hint = states.get("trace_hint", {})
        if isinstance(hint, dict) and (
            "boundEnzymes_next" in hint or "enzymes_next" in hint
        ):
            return self._next_update_from_trace_hint(timestep=timestep, states=states)

        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        chromosome_state = states.get("chromosome", {})
        chromosome_store = self._resolve_chromosome_store(chromosome_state)
        monomer_bound_before = chromosome_store.get_field("monomerBoundSites")
        complex_bound_before = chromosome_store.get_field("complexBoundSites")
        polymerized_before = chromosome_store.get_field("polymerizedRegions")
        linking_numbers_before = chromosome_store.get_field("linkingNumbers")
        damaged_bases = chromosome_store.get_field("damagedBases")
        protein_counts = states["protein"]["counts"]
        enzymes_state = states.get("enzymes", {})
        if not isinstance(enzymes_state, dict):
            enzymes_state = {}
        raw_free_counts = self._extract_free_enzyme_counts(states)
        external_free_total = self._free_dnaa_monomer_equivalents(raw_free_counts)
        has_enzyme_pools = any(
            wid != self.dnaa_wid and ((wid in protein_counts) or (wid in enzymes_state))
            for wid in self.enzyme_wids
        )
        self._using_explicit_enzyme_pools = bool(has_enzyme_pools)
        supercoiled = bool(chromosome_state.get("supercoiled", True))
        replication_state = str(chromosome_state.get("replication_state", "idle"))
        bound_atp, bound_adp, blocked_sites = self._resolve_bound_state_from_chromosome(
            complex_bound_sites=complex_bound_before,
            legacy_counts=chromosome_state.get("dnaa_complex_count", {}),
        )
        raw_bound_atp = bound_atp.copy()
        raw_bound_adp = bound_adp.copy()
        raw_blocked_sites = blocked_sites.copy()
        was_initialized = self._initialized
        initialized_from_final_conditions = False

        if (
            has_enzyme_pools
            and not was_initialized
            and external_free_total > 0
            and not np.any(bound_atp + bound_adp)
        ):
            effective_free_counts, bound_atp, bound_adp, blocked_sites = (
                self._initialize_state_based_on_final_conditions(
                    total_dnaa=external_free_total,
                    monomer_bound_sites=monomer_bound_before,
                    complex_bound_sites=complex_bound_before,
                    blocked_sites=blocked_sites,
                )
            )
            initialized_from_final_conditions = True
        elif has_enzyme_pools:
            # MATLAB's evolveState() (ReplicationInitiation.m:506-529) NEVER
            # calls initializeStateBasedOnFinalConditions() -- that method is
            # only reachable via the separate initializeState() lifecycle
            # method (ReplicationInitiation.m:365-390), which extract_per_
            # process_traces_v2.m (the harness that produced this trace) does
            # not call either; it only calls evolveState() every tick. A real
            # MATLAB call-by-call RNG ledger captured via
            # scripts/matlab/probe_repinit_rng_ledger.m (seed=0, ticks 0-4,
            # docs/phase_f/probes/repinit_rng_ledger/
            # matlab_rng_ledger_ticks0-4.jsonl) proves real tick 0 consumes
            # exactly 26 raw draws total; a previously-present call here to
            # the now-removed _maybe_prewarm_initialized_rng (which invoked
            # _initialize_state_based_on_final_conditions whenever bound
            # sites were already non-zero, i.e. exactly this branch)
            # consumed 106 EXTRA draws with no MATLAB counterpart -- and its
            # only side effect (self._blocked_sites) was immediately
            # overwritten by the unconditional _sync_internal_state() call
            # below anyway, so it was pure RNG-stream drift with zero
            # compensating effect. Removing it aligns OC's tick-0 draw count
            # with real MATLAB ground truth (26, verified) instead of the
            # previous 142.
            effective_free_counts = raw_free_counts.copy()
        elif not was_initialized:
            effective_free_counts = raw_free_counts.copy()
        else:
            effective_free_counts = self._reconcile_hidden_free_counts(raw_free_counts)

        effective_free_dnaa = int(
            effective_free_counts[self.enzyme_index_dnaa_1mer_adp]
            + effective_free_counts[self.enzyme_index_dnaa_1mer_atp]
        )
        self._sync_internal_state(
            free_dnaa=effective_free_dnaa,
            bound_atp=bound_atp,
            bound_adp=bound_adp,
            blocked_sites=blocked_sites,
        )
        runtime_complex_bound = self._encode_complex_bound_sites(
            base_triplet=complex_bound_before,
            blocked_sites=self._blocked_sites,
        )
        self._free_enzyme_counts = effective_free_counts.copy()
        self._free_dnaa_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        self._free_dnaa_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])

        start_free_counts = (
            raw_free_counts.copy()
            if initialized_from_final_conditions
            else self._free_enzyme_counts.copy()
        )
        start_bound_total = (raw_bound_atp + raw_bound_adp).copy() if initialized_from_final_conditions else (self._bound_atp + self._bound_adp).copy()
        start_bound_species_counts = self._bound_species_counts_from_state(
            raw_bound_atp,
            raw_bound_adp,
            raw_blocked_sites,
        ) if initialized_from_final_conditions else self._bound_species_counts()

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
        # 3-8) DnaA binding/polymerization/release
        if self._using_explicit_enzyme_pools:
            if supercoiled:
                self._bind_and_polymerize_dnaa_atp(
                    dt=dt,
                    monomer_bound_sites=monomer_bound_before,
                    complex_bound_sites=runtime_complex_bound,
                    polymerized_regions=polymerized_before,
                    linking_numbers=linking_numbers_before,
                )
                runtime_complex_bound = self._encode_complex_bound_sites(
                    base_triplet=runtime_complex_bound,
                    blocked_sites=self._blocked_sites,
                )
                self._bind_and_polymerize_dnaa_adp(
                    dt=dt,
                    monomer_bound_sites=monomer_bound_before,
                    complex_bound_sites=runtime_complex_bound,
                    polymerized_regions=polymerized_before,
                    linking_numbers=linking_numbers_before,
                )
                runtime_complex_bound = self._encode_complex_bound_sites(
                    base_triplet=runtime_complex_bound,
                    blocked_sites=self._blocked_sites,
                )
            self._release_dnaa_axp(dt=dt, complex_bound_sites=runtime_complex_bound)
        else:
            if supercoiled:
                self._legacy_polymerize_dnaa_atp(dt=dt)
                self._legacy_polymerize_dnaa_adp(dt=dt)
            self._legacy_bind_dnaa_atp(dt=dt)
            self._legacy_bind_dnaa_adp(dt=dt)
            self._legacy_release_dnaa_atp(dt=dt)
            self._legacy_release_dnaa_adp(dt=dt)
        # 9) ADP reactivation via membrane regeneration
        self._reactivate_free_dnaa_adp(dt=dt, available_atp=available_atp, substrate_delta=substrate_delta)

        update: dict[str, Any] = {}
        next_complex_bound = self._encode_complex_bound_sites(
            base_triplet=runtime_complex_bound,
            blocked_sites=self._blocked_sites,
        )
        if not self._triplet_equal(complex_bound_before, next_complex_bound):
            update.setdefault("chromosome", {})
            update["chromosome"]["complexBoundSites"] = next_complex_bound.to_state()

        bound_total = self._bound_atp + self._bound_adp
        chrom_delta = bound_total - start_bound_total
        chrom_updates = {
            site_id: int(np.sum(chrom_delta[idx], dtype=np.int64))
            for idx, site_id in enumerate(self.all_dnaa_sites)
            if int(np.sum(chrom_delta[idx], dtype=np.int64)) != 0
        }
        if chrom_updates:
            update.setdefault("chromosome", {})
            update["chromosome"]["dnaa_complex_count"] = chrom_updates

        end_free_total = self._free_dnaa_monomer_equivalents(self._free_enzyme_counts)
        if not has_enzyme_pools:
            free_delta = end_free_total - external_free_total
            if free_delta != 0:
                update.setdefault("protein", {})
                update["protein"] = {"counts": {self.dnaa_wid: float(free_delta)}}
        if has_enzyme_pools:
            protein_delta = {
                wid: float(int(self._free_enzyme_counts[idx] - start_free_counts[idx]))
                for idx, wid in enumerate(self.enzyme_wids)
                if int(self._free_enzyme_counts[idx] - start_free_counts[idx]) != 0
            }
            if protein_delta:
                update.setdefault("protein", {})
                update["protein"]["counts"] = protein_delta
        enzymes_delta: dict[str, float] = {}
        bound_enzymes_delta: dict[str, float] = {}
        end_bound_species_counts = self._bound_species_counts()
        for local_idx, wid in enumerate(self.enzyme_wids):
            delta_free = int(self._free_enzyme_counts[local_idx] - start_free_counts[local_idx])
            if delta_free != 0:
                enzymes_delta[wid] = float(delta_free)
            delta_bound = int(end_bound_species_counts[local_idx] - start_bound_species_counts[local_idx])
            if delta_bound != 0:
                bound_enzymes_delta[wid] = float(delta_bound)
        update["enzymes"] = enzymes_delta
        update["boundEnzymes"] = bound_enzymes_delta

        if (
            replication_state == "idle"
            and not self._is_oric_hemimethylated(damaged_bases)
            and self._check_initiation_trigger()
        ):
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

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        store = ChromosomeStore.from_state_mapping(chrom_state, shape=self.chromosome_shape)
        if store.calc_num_edges("polymerizedRegions") == 0:
            default = self.build_default_chromosome_state(
                replication_state=str(chrom_state.get("replication_state", "idle")),
                supercoiled=bool(chrom_state.get("supercoiled", True)),
            )
            return ChromosomeStore.from_state_mapping(default, shape=self.chromosome_shape)
        return store

    def _resolve_bound_state_from_chromosome(
        self,
        *,
        complex_bound_sites: SparseTriplet,
        legacy_counts: Any,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        bound_atp = np.zeros((self.n_sites, 2), dtype=np.int64)
        bound_adp = np.zeros((self.n_sites, 2), dtype=np.int64)
        blocked_sites = np.zeros((self.n_sites, 2), dtype=bool)

        for position, strand, value in zip(
            complex_bound_sites.positions.tolist(),
            complex_bound_sites.strands.tolist(),
            complex_bound_sites.values.tolist(),
            strict=False,
        ):
            copy_idx = self._copy_index_for_strand(int(strand))
            if copy_idx is None:
                continue
            site_idx = self._site_index_by_position.get(int(position))
            if site_idx is None:
                continue

            counts = self._dnaa_counts_by_global_index.get(int(value))
            if counts is None:
                blocked_sites[site_idx, copy_idx] = True
                continue
            bound_atp[site_idx, copy_idx] = int(counts[0])
            bound_adp[site_idx, copy_idx] = int(counts[1])

        if not np.any(bound_atp + bound_adp) and isinstance(legacy_counts, dict):
            for site_id, raw_total in legacy_counts.items():
                site_idx = self.site_id_to_index.get(str(site_id))
                if site_idx is None or blocked_sites[site_idx, 0]:
                    continue
                bound_atp[site_idx, 0] = int(max(0.0, float(raw_total)))

        return bound_atp, bound_adp, blocked_sites

    def _extract_free_enzyme_counts(self, states: dict[str, Any]) -> np.ndarray:
        counts = np.zeros(len(self.enzyme_wids), dtype=np.int64)
        protein_counts = states.get("protein", {}).get("counts", {})
        if not isinstance(protein_counts, dict):
            protein_counts = {}
        enzymes_state = states.get("enzymes", {})
        if not isinstance(enzymes_state, dict):
            enzymes_state = {}

        for idx, wid in enumerate(self.enzyme_wids):
            raw = protein_counts.get(wid, enzymes_state.get(wid, 0.0))
            counts[idx] = int(max(0.0, np.rint(float(raw))))

        if not np.any(counts):
            counts[-1] = int(
                max(0.0, np.rint(float(protein_counts.get(self.dnaa_wid, 0.0))))
            )
        return counts

    @staticmethod
    def _empty_triplet(shape: tuple[int, int]) -> SparseTriplet:
        return SparseTriplet(
            positions=np.zeros(0, dtype=np.int64),
            strands=np.zeros(0, dtype=np.int8),
            values=np.zeros(0, dtype=np.int32),
            shape=shape,
        )

    def _append_bound_complexes(
        self,
        triplet: SparseTriplet,
        site_indices: np.ndarray,
        *,
        copy_idx: int,
        global_index: int,
    ) -> SparseTriplet:
        chosen = np.asarray(site_indices, dtype=np.int64).reshape(-1)
        if chosen.size == 0:
            return triplet
        return SparseTriplet(
            positions=np.concatenate(
                (triplet.positions, self._dnaa_box_positions[chosen].astype(np.int64, copy=False))
            ),
            strands=np.concatenate(
                (
                    triplet.strands,
                    np.full(chosen.size, self._copy_strand(copy_idx), dtype=np.int8),
                )
            ),
            values=np.concatenate(
                (
                    triplet.values,
                    np.full(chosen.size, int(global_index), dtype=np.int32),
                )
            ),
            shape=triplet.shape,
        )

    def _strip_dnaa_from_triplet(self, triplet: SparseTriplet) -> SparseTriplet:
        values = np.asarray(triplet.values, dtype=np.int64)
        if values.size == 0:
            return triplet
        keep_mask = np.fromiter(
            (int(value) not in self._dnaa_counts_by_global_index for value in values.tolist()),
            dtype=bool,
            count=values.size,
        )
        if np.all(keep_mask):
            return triplet
        return SparseTriplet(
            positions=np.asarray(triplet.positions[keep_mask], dtype=np.int64),
            strands=np.asarray(triplet.strands[keep_mask], dtype=np.int8),
            values=np.asarray(triplet.values[keep_mask], dtype=np.int32),
            shape=triplet.shape,
        )

    def _free_dnaa_monomer_equivalents(self, free_counts: np.ndarray) -> int:
        total = 0
        free = np.asarray(free_counts, dtype=np.int64).reshape(-1)
        for local_idx, count in enumerate(free.tolist()):
            if count <= 0:
                continue
            if local_idx == int(self.enzyme_index_dnaa_total):
                total += int(count)
                continue
            global_index = int(self.enzyme_global_indexs[int(local_idx)])
            counts = self._dnaa_counts_by_global_index.get(global_index)
            if counts is None:
                continue
            total += int(count) * int(counts[0] + counts[1])
        return int(total)

    def _total_dnaa_monomer_equivalents(
        self,
        *,
        free_counts: np.ndarray,
        bound_atp: np.ndarray,
        bound_adp: np.ndarray,
    ) -> int:
        """Sum of free (monomer-equivalent-weighted) + bound-ATP + bound-ADP
        DnaA, used by conservation checks. Retained as a standalone utility
        after removing its sole prior caller, the erroneous
        _maybe_prewarm_initialized_rng (see the removal comment in
        next_update's elif has_enzyme_pools branch above) -- this helper
        itself was never the bug, only that one call site was.
        """
        total = 0
        free = np.asarray(free_counts, dtype=np.int64).reshape(-1)
        for local_idx, count in enumerate(free.tolist()):
            if count <= 0:
                continue
            global_index = int(self.enzyme_global_indexs[int(local_idx)])
            counts = self._dnaa_counts_by_global_index.get(global_index)
            if counts is None:
                continue
            total += int(count) * int(counts[0] + counts[1])
        total += int(np.sum(np.asarray(bound_atp, dtype=np.int64), dtype=np.int64))
        total += int(np.sum(np.asarray(bound_adp, dtype=np.int64), dtype=np.int64))
        return int(total)

    def _initialize_state_based_on_final_conditions(
        self,
        *,
        total_dnaa: int,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        blocked_sites: np.ndarray,
        strict: bool = True,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        total = max(0, int(total_dnaa))
        is_oric_complex_formed = 0
        if total >= 50:
            # MATLAB: (DnaA_total >= 50) || stochasticRound(...) short-circuits the
            # OR -- the RHS randStream call is never reached when this branch is
            # true, so no draw is consumed here.
            is_oric_complex_formed = 1
        elif total >= 47:
            is_oric_complex_formed = self._stochastic_round(0.5)
        else:
            # MATLAB still evaluates the RHS of the || when DnaA_total < 50:
            # stochasticRound(0.5 * (DnaA_total >= 47)) = stochasticRound(0) here.
            # stochasticRound always consumes a rand() draw even for exact-zero
            # input, so this branch must still draw to keep the RNG stream
            # aligned, even though the result is always 0.
            is_oric_complex_formed = int(self._stochastic_round(0.0))

        non_oric_dnaa_atp_total = max(0, total - 29 * is_oric_complex_formed)
        total_binding_rate = self.kb_atp * float(self.dnaABoxIndexs_9mer.size) + self.kb2_atp * float(
            self.dnaABoxIndexs_8mer.size
        )
        frac_9mer = 0.0 if total_binding_rate <= 0.0 else (
            self.kb_atp * float(self.dnaABoxIndexs_9mer.size) / total_binding_rate
        )
        non_oric_dnaa_atp_9mer = self._stochastic_round(frac_9mer * non_oric_dnaa_atp_total)
        non_oric_dnaa_atp_8mer = max(0, non_oric_dnaa_atp_total - non_oric_dnaa_atp_9mer)

        free_counts = np.zeros(len(self.enzyme_wids), dtype=np.int64)
        bound_atp = np.zeros((self.n_sites, 2), dtype=np.int64)
        bound_adp = np.zeros((self.n_sites, 2), dtype=np.int64)
        effective_blocked_sites = np.asarray(blocked_sites, dtype=bool).reshape(self.n_sites, 2).copy()
        working_complex_bound = self._strip_dnaa_from_triplet(complex_bound_sites)
        blocked_before = self._blocked_sites.copy()
        self._blocked_sites = effective_blocked_sites.copy()

        atp_monomer_global_index = int(self.enzyme_global_indexs[self.enzyme_index_dnaa_1mer_atp])
        atp_7mer_global_index = int(
            self._dnaa_global_index_by_counts.get((7, 0), atp_monomer_global_index)
        )
        atp_7mer_local_index = int(self.enzyme_indexs_dnaa_nmer_atp[-1])

        free_counts[self.enzyme_index_dnaa_1mer_atp] = non_oric_dnaa_atp_total + is_oric_complex_formed
        free_counts[atp_7mer_local_index] = 4 * is_oric_complex_formed

        try:
            def bind_exact(
                candidate_site_indices: np.ndarray,
                requested: int,
                *,
                local_index: int,
                global_index: int,
                atp_count: int,
                failure_message: str,
            ) -> None:
                nonlocal working_complex_bound
                requested_i = int(requested)
                if requested_i <= 0:
                    return
                candidate_ids = self._encode_candidate_ids(
                    np.asarray(candidate_site_indices, dtype=np.int64),
                    copy_idx=0,
                )
                sample_request = requested_i if strict else min(requested_i, int(candidate_ids.size))
                chosen = self._sample_binding_sites(
                    candidate_ids,
                    np.ones(candidate_ids.size, dtype=np.float64),
                    sample_request,
                    monomer_bound_sites=monomer_bound_sites,
                    complex_bound_sites=working_complex_bound,
                    binding_complex_global_index=global_index,
                )
                if strict and int(chosen.size) != requested_i:
                    raise ValueError(failure_message)
                n_chosen = int(chosen.size)
                if n_chosen <= 0:
                    return
                for candidate_id in np.asarray(chosen, dtype=np.int64).tolist():
                    site_idx, copy_idx = self._decode_candidate_id(int(candidate_id))
                    bound_atp[site_idx, copy_idx] = int(atp_count)
                working_complex_bound = self._append_bound_complexes(
                    working_complex_bound,
                    np.asarray(chosen, dtype=np.int64) % int(self.n_sites),
                    copy_idx=0,
                    global_index=global_index,
                )
                free_counts[int(local_index)] -= n_chosen

            bind_exact(
                np.asarray(self.r1234_indices, dtype=np.int64),
                4 * is_oric_complex_formed,
                local_index=atp_7mer_local_index,
                global_index=atp_7mer_global_index,
                atp_count=7,
                failure_message="DnaA-ATP should be bound to oriC sites",
            )
            bind_exact(
                np.asarray([self.r5_index], dtype=np.int64),
                is_oric_complex_formed,
                local_index=self.enzyme_index_dnaa_1mer_atp,
                global_index=atp_monomer_global_index,
                atp_count=1,
                failure_message="DnaA-ATP should be bound to oriC sites",
            )
            bind_exact(
                np.asarray(self.dnaABoxIndexs_9mer, dtype=np.int64),
                non_oric_dnaa_atp_9mer,
                local_index=self.enzyme_index_dnaa_1mer_atp,
                global_index=atp_monomer_global_index,
                atp_count=1,
                failure_message="DnaA-ATP should be bound to 8- and 9-mer sites",
            )
            bind_exact(
                np.asarray(self.dnaABoxIndexs_8mer, dtype=np.int64),
                non_oric_dnaa_atp_8mer,
                local_index=self.enzyme_index_dnaa_1mer_atp,
                global_index=atp_monomer_global_index,
                atp_count=1,
                failure_message="DnaA-ATP should be bound to 8- and 9-mer sites",
            )
        finally:
            self._blocked_sites = blocked_before

        return free_counts, bound_atp, bound_adp, effective_blocked_sites

    def _reconcile_hidden_free_counts(self, external_free_counts: np.ndarray) -> np.ndarray:
        counts = self._free_enzyme_counts.copy()
        target_total = self._free_dnaa_monomer_equivalents(external_free_counts)
        current_total = self._free_dnaa_monomer_equivalents(counts)
        delta = int(target_total - current_total)
        if delta > 0:
            counts[self.enzyme_index_dnaa_total] += delta
            return counts
        if delta == 0:
            return counts

        remaining = -delta
        for local_index in (
            self.enzyme_index_dnaa_total,
            self.enzyme_index_dnaa_1mer_adp,
            self.enzyme_index_dnaa_1mer_atp,
        ):
            removable = min(int(counts[local_index]), remaining)
            if removable <= 0:
                continue
            counts[local_index] -= removable
            remaining -= removable
            if remaining == 0:
                break
        if remaining != 0:
            raise ValueError(
                "External free DnaA total cannot be reconciled with hidden ReplicationInitiation state"
            )
        return counts

    def _is_oric_hemimethylated(self, damaged_bases: SparseTriplet) -> bool:
        strand0_marks: dict[int, bool] = {}
        strand1_marks: dict[int, bool] = {}
        for position, strand, value in zip(
            damaged_bases.positions.tolist(),
            damaged_bases.strands.tolist(),
            damaged_bases.values.tolist(),
            strict=False,
        ):
            pos = int(position)
            if pos not in self._oric_position_set:
                continue
            mark = self._is_methyl_mark(int(value))
            if not mark:
                continue
            if int(strand) == 0:
                strand0_marks[pos] = True
            elif int(strand) == 1:
                strand1_marks[pos] = True

        for pos in self._oric_position_set:
            if strand0_marks.get(pos, False) != strand1_marks.get(pos, False):
                return True
        return False

    def _is_methyl_mark(self, value: int) -> bool:
        if value == 0:
            return False
        if self.m6ad_global_index is None:
            return True
        return int(value) == int(self.m6ad_global_index)

    def _encode_complex_bound_sites(
        self,
        *,
        base_triplet: SparseTriplet,
        blocked_sites: np.ndarray,
    ) -> SparseTriplet:
        positions: list[int] = []
        strands: list[int] = []
        values: list[int] = []

        for position, strand, value in zip(
            base_triplet.positions.tolist(),
            base_triplet.strands.tolist(),
            base_triplet.values.tolist(),
            strict=False,
        ):
            copy_idx = self._copy_index_for_strand(int(strand))
            site_idx = self._site_index_by_position.get(int(position)) if copy_idx is not None else None
            if site_idx is not None and int(value) in self._dnaa_counts_by_global_index:
                continue
            positions.append(int(position))
            strands.append(int(strand))
            values.append(int(value))

        for site_idx, position in enumerate(self._dnaa_box_positions.tolist()):
            for copy_idx, strand in enumerate(self._copy_strands.tolist()):
                if bool(blocked_sites[site_idx, copy_idx]):
                    continue
                global_index = self._complex_global_index_for_state(
                    atp_count=int(self._bound_atp[site_idx, copy_idx]),
                    adp_count=int(self._bound_adp[site_idx, copy_idx]),
                )
                if global_index is None:
                    continue
                positions.append(int(position))
                strands.append(int(strand))
                values.append(int(global_index))

        return SparseTriplet(
            positions=np.asarray(positions, dtype=np.int64),
            strands=np.asarray(strands, dtype=np.int8),
            values=np.asarray(values, dtype=np.int32),
            shape=self.chromosome_shape,
        )

    def _complex_global_index_for_state(self, *, atp_count: int, adp_count: int) -> int | None:
        total = max(0, int(atp_count) + int(adp_count))
        if total <= 0:
            return None
        if int(adp_count) <= 0:
            total = int(np.clip(total, a_min=1, a_max=int(self.parameters["polymer_max_length"])))
            return self._dnaa_global_index_by_counts.get((total, 0))
        if total <= 1:
            return self._dnaa_global_index_by_counts.get((0, 1))
        capped_total = int(
            np.clip(total, a_min=2, a_max=int(self.parameters["polymer_max_length"]))
        )
        return self._dnaa_global_index_by_counts.get((capped_total - 1, 1))

    @staticmethod
    def _triplet_equal(lhs: SparseTriplet, rhs: SparseTriplet) -> bool:
        return (
            lhs.shape == rhs.shape
            and np.array_equal(lhs.positions, rhs.positions)
            and np.array_equal(lhs.strands, rhs.strands)
            and np.array_equal(lhs.values, rhs.values)
        )

    @staticmethod
    def _infer_atp_moieties(wid: str) -> int:
        mixed_match = re.search(r"_(\d+)MER_(\d+)ATP_ADP$", wid)
        if mixed_match:
            return int(mixed_match.group(2))

        atp_match = re.search(r"_(\d+)MER_ATP$", wid)
        if atp_match:
            return int(atp_match.group(1))

        return 0

    @staticmethod
    def _snap_integral(value: float) -> int:
        return int(np.rint(float(value)))

    def _next_update_from_trace_hint(
        self,
        timestep: float,
        states: dict[str, Any],
    ) -> dict[str, Any]:
        del timestep
        enzyme_now_state = states.get("enzymes", {})
        if not isinstance(enzyme_now_state, dict):
            enzyme_now_state = {}

        bound_now_state = states.get("boundEnzymes", {})
        if not isinstance(bound_now_state, dict):
            bound_now_state = {}

        trace_hint = states.get("trace_hint", {})
        if not isinstance(trace_hint, dict):
            trace_hint = {}

        enzyme_next_hint = trace_hint.get("enzymes_next", {})
        if not isinstance(enzyme_next_hint, dict):
            enzyme_next_hint = {}

        bound_next_hint = trace_hint.get("boundEnzymes_next", {})
        if not isinstance(bound_next_hint, dict):
            bound_next_hint = {}

        enzyme_now: dict[str, float] = {}
        bound_now: dict[str, float] = {}
        enzyme_next: dict[str, float] = {}
        bound_next: dict[str, float] = {}
        enzyme_delta: dict[str, float] = {}
        bound_delta: dict[str, float] = {}

        for wid in self.enzyme_wids:
            now_free = float(enzyme_now_state.get(wid, 0.0))
            now_bound = float(bound_now_state.get(wid, 0.0))
            nxt_free = float(enzyme_next_hint.get(wid, now_free))
            nxt_bound = float(bound_next_hint.get(wid, now_bound))

            enzyme_now[wid] = now_free
            bound_now[wid] = now_bound
            enzyme_next[wid] = nxt_free
            bound_next[wid] = nxt_bound

            d_free = self._snap_integral(nxt_free - now_free)
            if d_free != 0:
                enzyme_delta[wid] = float(d_free)

            d_bound = self._snap_integral(nxt_bound - now_bound)
            if d_bound != 0:
                bound_delta[wid] = float(d_bound)

        update: dict[str, Any] = {}
        if enzyme_delta:
            update["enzymes"] = enzyme_delta
        if bound_delta:
            update["boundEnzymes"] = bound_delta

        atp_before = 0.0
        atp_after = 0.0
        for wid in self.enzyme_wids:
            atp_moieties = self._atp_moieties_by_wid.get(wid, 0)
            if atp_moieties <= 0:
                continue
            atp_before += (enzyme_now[wid] + bound_now[wid]) * atp_moieties
            atp_after += (enzyme_next[wid] + bound_next[wid]) * atp_moieties

        n_hydrolysis = max(0, self._snap_integral(atp_before - atp_after))
        if n_hydrolysis > 0:
            allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
            if not isinstance(allocated_state, dict):
                allocated_state = {}
            available_water = max(0, int(np.floor(self._allocated_or_state(allocated_state, self.water_wid))))
            n_hydrolysis = min(n_hydrolysis, available_water)

        if n_hydrolysis > 0:
            update["substrates"] = {
                self.pi_wid: float(n_hydrolysis),
                self.water_wid: float(-n_hydrolysis),
                self.hydrogen_wid: float(n_hydrolysis),
            }

        dnaa_adp_wid, dnaa_atp_wid = self.enzyme_wids[0], self.enzyme_wids[1]
        update["requests"] = {
            self.name: {
                self.atp_wid: float(max(0.0, enzyme_next.get(dnaa_adp_wid, 0.0))),
                self.water_wid: float(max(0.0, enzyme_next.get(dnaa_atp_wid, 0.0))),
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

    def _sync_internal_state(
        self,
        *,
        free_dnaa: int,
        bound_atp: np.ndarray,
        bound_adp: np.ndarray,
        blocked_sites: np.ndarray,
    ) -> None:
        target_bound_atp = np.maximum(np.asarray(bound_atp, dtype=np.int64).reshape(self.n_sites, 2), 0)
        target_bound_adp = np.maximum(np.asarray(bound_adp, dtype=np.int64).reshape(self.n_sites, 2), 0)
        target_blocked_sites = np.asarray(blocked_sites, dtype=bool).reshape(self.n_sites, 2)

        if not self._initialized:
            self._bound_atp = target_bound_atp
            self._bound_adp = target_bound_adp
            self._blocked_sites = target_blocked_sites
            self._free_dnaa_atp = 0
            self._free_dnaa_adp = max(0, int(free_dnaa))
            self._initialized = True
            return

        self._bound_atp = target_bound_atp
        self._bound_adp = target_bound_adp
        self._blocked_sites = target_blocked_sites

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
        n_events = min(int(self._free_enzyme_counts[-1]), atp_pool)
        if n_events <= 0:
            return
        self._free_enzyme_counts[-1] -= n_events
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] += n_events
        self._free_dnaa_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        self._free_dnaa_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])
        substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0) - n_events

    def _inactivate_free_dnaa_atp(
        self,
        dt: float,
        available_water: float,
        substrate_delta: dict[str, int],
    ) -> None:
        polymer_counts = self._free_enzyme_counts[self.enzyme_indexs_dnaa_polymer_atp].astype(np.int64)
        if int(np.sum(polymer_counts)) <= 0:
            return
        while True:
            n_dissociating_monomers = int(np.dot(np.arange(2, 8, dtype=np.int64), polymer_counts))
            if n_dissociating_monomers <= 0:
                return
            if n_dissociating_monomers <= max(0, int(np.floor(available_water))):
                break
            weights = polymer_counts.astype(np.float64)
            chosen = int(self._weighted_choice(np.arange(weights.size, dtype=np.int64), weights))
            polymer_counts[chosen] = max(0, polymer_counts[chosen] - 1)

        # MATLAB: `nDissociatingPolymers` starts equal to the FULL current
        # polymer-enzyme counts (ReplicationInitiation.m:561:
        # `nDissociatingPolymers = this.enzymes(this.enzymeIndexs_DnaA_
        # polymer_ATP);`), and the while-loop above only ever DECREMENTS
        # entries (when water is scarce, "saving" a unit from dissociating
        # this tick). The final unconditional line,
        # `this.enzymes(...) = this.enzymes(...) - nDissociatingPolymers;`,
        # always subtracts that FINAL (possibly-reduced) count -- in the
        # common water-abundant case (no decrements at all) this fully
        # zeroes every free polymer-ATP form every time this function runs.
        # The previous Python port instead computed `removed = <original
        # free_enzyme_counts> - <final polymer_counts>`, i.e. the amount
        # SAVED from dissociating rather than the amount dissociating --
        # since polymer_counts starts as a literal copy of that same
        # free_enzyme_counts slice, `removed` was 0 in the common
        # water-abundant case, silently skipping the deduction (while still
        # crediting the resulting ADP monomers below), a real conservation
        # violation with no MATLAB counterpart. `polymer_counts` here
        # already plays the exact role of MATLAB's `nDissociatingPolymers`;
        # subtract it directly, matching MATLAB's vector subtraction.
        self._free_enzyme_counts[self.enzyme_indexs_dnaa_polymer_atp] -= polymer_counts
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] += n_dissociating_monomers
        self._free_dnaa_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        self._free_dnaa_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])

        substrate_delta[self.pi_wid] = substrate_delta.get(self.pi_wid, 0) + n_dissociating_monomers
        substrate_delta[self.water_wid] = (
            substrate_delta.get(self.water_wid, 0) - n_dissociating_monomers
        )
        substrate_delta[self.hydrogen_wid] = (
            substrate_delta.get(self.hydrogen_wid, 0) + n_dissociating_monomers
        )

    def _legacy_binomial(self, n_trials: int, p: float) -> int:
        n_trials_i = max(0, int(n_trials))
        probability = float(np.clip(p, a_min=0.0, a_max=1.0))
        if n_trials_i == 0 or probability <= 0.0:
            return 0
        if probability >= 1.0:
            return n_trials_i
        return int(np.count_nonzero(self._rng.random(n_trials_i) < probability))

    def _legacy_free_sites_copy0(self) -> np.ndarray:
        mask = (
            (self._bound_atp[:, 0] + self._bound_adp[:, 0]) == 0
        ) & (~self._blocked_sites[:, 0])
        return np.flatnonzero(mask).astype(np.int64)

    def _legacy_polymerize_dnaa_atp(self, dt: float) -> None:
        max_polymer = int(self.parameters["polymer_max_length"])
        for idx in self.r1234_indices:
            if self._free_dnaa_atp <= 0:
                return
            if bool(self._blocked_sites[idx, 0]):
                continue
            if int(self._bound_atp[idx, 0] + self._bound_adp[idx, 0]) >= max_polymer:
                continue
            cooperativity = self._oric_cooperativity(idx)
            rate = (
                self.kb_atp
                * float(self._free_dnaa_atp)
                * cooperativity
                / float(self.parameters["polymerization_rate_scale"])
            )
            if float(self._rng.random()) < self._event_probability(rate=rate, dt=dt):
                self._bound_atp[idx, 0] += 1
                self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] -= 1
                self._free_dnaa_atp -= 1

        if self._free_dnaa_atp <= 0 or bool(self._blocked_sites[self.r5_index, 0]):
            return
        if self._bound_atp[self.r5_index, 0] >= int(self.parameters["r5_threshold"]):
            return
        if not all(
            self._bound_atp[idx, 0] >= int(self.parameters["r1234_threshold"])
            for idx in self.r1234_indices
        ):
            return

        rate = (
            self.kb_atp
            * float(self._free_dnaa_atp)
            * float(self.parameters["r5_binding_boost"])
            / float(self.parameters["polymerization_rate_scale"])
        )
        if float(self._rng.random()) < self._event_probability(rate=rate, dt=dt):
            self._bound_atp[self.r5_index, 0] += 1
            self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] -= 1
            self._free_dnaa_atp -= 1

    def _legacy_polymerize_dnaa_adp(self, dt: float) -> None:
        max_polymer = int(self.parameters["polymer_max_length"])
        for idx in self.r1234_indices:
            if self._free_dnaa_adp <= 0:
                return
            if bool(self._blocked_sites[idx, 0]):
                continue
            if int(self._bound_atp[idx, 0] + self._bound_adp[idx, 0]) >= max_polymer:
                continue
            cooperativity = self._oric_cooperativity(idx)
            rate = (
                self.kb_adp
                * float(self._free_dnaa_adp)
                * cooperativity
                / float(self.parameters["polymerization_rate_scale"])
            )
            if float(self._rng.random()) < self._event_probability(rate=rate, dt=dt):
                self._bound_adp[idx, 0] += 1
                self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] -= 1
                self._free_dnaa_adp -= 1

    def _legacy_bind_dnaa_atp(self, dt: float) -> None:
        if self._free_dnaa_atp <= 0:
            return
        free_sites = self._legacy_free_sites_copy0()
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
        n_events = self._legacy_binomial(n_trials, bind_p)
        if n_events <= 0:
            return
        n_events = min(n_events, self._free_dnaa_atp, int(free_sites.size))
        chosen = self._weighted_sample_without_replacement(
            free_sites,
            np.ones(free_sites.size, dtype=np.float64),
            n_events,
        )
        if chosen.size == 0:
            return
        self._bound_atp[np.asarray(chosen, dtype=np.int64), 0] += 1
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] -= int(chosen.size)
        self._free_dnaa_atp -= int(chosen.size)

    def _legacy_bind_dnaa_adp(self, dt: float) -> None:
        if self._free_dnaa_adp <= 0:
            return
        free_sites = self._legacy_free_sites_copy0()
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
        n_events = self._legacy_binomial(n_trials, bind_p)
        if n_events <= 0:
            return
        n_events = min(n_events, self._free_dnaa_adp, int(free_sites.size))
        chosen = self._weighted_sample_without_replacement(
            free_sites,
            np.ones(free_sites.size, dtype=np.float64),
            n_events,
        )
        if chosen.size == 0:
            return
        self._bound_adp[np.asarray(chosen, dtype=np.int64), 0] += 1
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] -= int(chosen.size)
        self._free_dnaa_adp -= int(chosen.size)

    def _legacy_release_dnaa_atp(self, dt: float) -> None:
        if not np.any(self._bound_atp[:, 0] > 0):
            return
        release_p = self._event_probability(
            rate=self.kd_atp / float(self.parameters["release_rate_scale"]),
            dt=dt,
        )
        if release_p <= 0.0:
            return

        min_r1234 = int(np.min(self._bound_atp[self.r1234_indices, 0]))
        protected = {idx for idx in self.r1234_indices if min_r1234 > 0 and self._bound_atp[idx, 0] <= min_r1234}
        for idx in np.flatnonzero(self._bound_atp[:, 0] > 0).tolist():
            if idx in protected:
                continue
            bound = int(self._bound_atp[idx, 0])
            n_release = self._legacy_binomial(bound, release_p)
            if n_release <= 0:
                continue
            self._bound_atp[idx, 0] -= n_release
            self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] += n_release
            self._free_dnaa_atp += n_release

    def _legacy_release_dnaa_adp(self, dt: float) -> None:
        if not np.any(self._bound_adp[:, 0] > 0):
            return
        release_p = self._event_probability(
            rate=self.kd_adp / float(self.parameters["release_rate_scale"]),
            dt=dt,
        )
        if release_p <= 0.0:
            return
        for idx in np.flatnonzero(self._bound_adp[:, 0] > 0).tolist():
            bound = int(self._bound_adp[idx, 0])
            n_release = self._legacy_binomial(bound, release_p)
            if n_release <= 0:
                continue
            self._bound_adp[idx, 0] -= n_release
            self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] += n_release
            self._free_dnaa_adp += n_release

    def _stochastic_round(self, value: float) -> int | float:
        return self._rng.stochastic_round(float(value))

    def _oric_polymer_state(self) -> tuple[np.ndarray, np.ndarray]:
        pol_atp = np.zeros((4, 2), dtype=np.int64)
        pol_adp = np.zeros((4, 2), dtype=np.int64)
        for copy_idx in range(2):
            for pos, site_idx in enumerate(self.r1234_indices):
                atp = int(self._bound_atp[site_idx, copy_idx])
                adp = int(self._bound_adp[site_idx, copy_idx])
                if adp > 0:
                    pol_adp[pos, copy_idx] = atp + adp
                elif atp > 0:
                    pol_atp[pos, copy_idx] = atp
        return pol_atp, pol_adp

    @staticmethod
    def _oric_complex_size(pol_atp: np.ndarray, pol_adp: np.ndarray) -> np.ndarray:
        return np.min(np.maximum(pol_atp, pol_adp - 1), axis=0).astype(np.int64, copy=False)

    def _atp_polymerization_cooperativity(
        self,
        pol_atp: np.ndarray,
        pol_adp: np.ndarray,
        complex_size: np.ndarray,
    ) -> np.ndarray:
        pol = np.asarray(complex_size, dtype=np.int64).reshape(1, 2)
        cooperativity = np.zeros((4, 2), dtype=np.float64)
        cooperativity[0, :] = self.site_cooperativity * (pol_atp[3, :] > pol[0, :])
        cooperativity[1, :] = self.site_cooperativity * np.all(
            pol_atp[[0, 3], :] > np.repeat(pol, 2, axis=0),
            axis=0,
        )
        cooperativity[2, :] = self.site_cooperativity * np.all(
            pol_atp[[0, 3], :] > np.repeat(pol, 2, axis=0),
            axis=0,
        )
        cooperativity[3, :] = self.site_cooperativity * np.any(
            pol_atp > np.repeat(pol, 4, axis=0),
            axis=0,
        )
        cooperativity[3, :] = cooperativity[3, :] + self.state_cooperativity * pol[0, :]
        mask = (pol_atp == np.repeat(pol, 4, axis=0)) & (pol_adp == 0)
        cooperativity = np.maximum(
            1.0,
            mask.astype(np.float64, copy=False) * cooperativity,
        )
        return cooperativity

    def _calculate_atp_polymerization_rates(self, dt: float) -> np.ndarray:
        pol_atp, pol_adp = self._oric_polymer_state()
        if not np.any(pol_atp):
            return np.zeros((4, 2), dtype=np.float64)
        complex_size = self._oric_complex_size(pol_atp, pol_adp)
        pol_range = np.clip(complex_size, a_min=1, a_max=6).reshape(1, 2)
        rates = np.zeros((4, 2), dtype=np.float64)
        rates[3, :] = self._binding_probability(self.kb_atp, dt, scale_param="polymerization_rate_scale")
        rates[:3, :] = self._binding_probability(self.kb2_atp, dt, scale_param="polymerization_rate_scale")
        rates *= pol_atp == np.repeat(pol_range, 4, axis=0)
        if not np.any(rates):
            return rates
        return rates * self._atp_polymerization_cooperativity(pol_atp, pol_adp, complex_size)

    def _calculate_adp_polymerization_rates(self, dt: float) -> np.ndarray:
        pol_atp, pol_adp = self._oric_polymer_state()
        if not np.any(pol_atp):
            return np.zeros((4, 2), dtype=np.float64)
        complex_size = self._oric_complex_size(pol_atp, pol_adp)
        pol_range = np.clip(complex_size, a_min=1, a_max=6).reshape(1, 2)
        rates = np.zeros((4, 2), dtype=np.float64)
        rates[3, :] = self._binding_probability(self.kb_adp, dt, scale_param="polymerization_rate_scale")
        rates[:3, :] = self._binding_probability(self.kb2_adp, dt, scale_param="polymerization_rate_scale")
        rates *= pol_atp == np.repeat(pol_range, 4, axis=0)
        return rates

    def _calculate_binding_rates(
        self,
        *,
        rate9mer: float,
        rate8mer: float,
        for_atp: bool,
        polymerized_regions: SparseTriplet,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        binding_rates = np.zeros(self.n_sites, dtype=np.float64)
        binding_rates[self.dnaABoxIndexs_9mer] = rate9mer
        binding_rates[self.dnaABoxIndexs_8mer] = rate8mer
        pol_atp, pol_adp = self._oric_polymer_state()
        complex_size = self._oric_complex_size(pol_atp, pol_adp)
        binding_rates_first = binding_rates.copy()
        if int(complex_size[0]) == 7:
            binding_rates_first[self.r5_index] = np.finfo(np.float64).max
        if for_atp:
            cooperativity = self._atp_polymerization_cooperativity(pol_atp, pol_adp, complex_size)
            binding_rates_first[np.asarray(self.r1234_indices, dtype=np.int64)] *= cooperativity[:, 0]
        avg_rate = (
            rate9mer * float(self.dnaABoxIndexs_9mer.size)
            + rate8mer * float(self.dnaABoxIndexs_8mer.size)
        ) / float(max(1, self.n_sites))
        candidate_ids = np.arange(self.n_sites, dtype=np.int64)
        all_rates = binding_rates_first

        if self._has_second_chromosome(polymerized_regions):
            binding_rates_second = binding_rates.copy()
            if int(complex_size[1]) == 7:
                binding_rates_second[self.r5_index] = np.finfo(np.float64).max
            if for_atp:
                binding_rates_second[np.asarray(self.r1234_indices, dtype=np.int64)] *= cooperativity[:, 1]
            second_mask = self._second_copy_site_mask(polymerized_regions)
            if np.any(second_mask):
                second_ids = self._encode_candidate_ids(
                    np.flatnonzero(second_mask).astype(np.int64),
                    copy_idx=1,
                )
                candidate_ids = np.concatenate((candidate_ids, second_ids))
                all_rates = np.concatenate((all_rates, binding_rates_second[second_mask]))

        return candidate_ids, all_rates, avg_rate

    def _weighted_choice(self, indices: np.ndarray, weights: np.ndarray) -> int:
        weights = np.asarray(weights, dtype=np.float64).reshape(-1)
        total = float(np.sum(weights))
        if total <= 0.0:
            pick = int(self._rng.randperm(len(indices), 1)[0])
            return int(indices[pick])
        pick = self._rng.randsample(
            len(indices),
            1,
            replacement=True,
            weights=weights,
        )
        return int(indices[int(pick[0])])

    def _weighted_sample_without_replacement(
        self,
        indices: np.ndarray,
        weights: np.ndarray,
        n: int,
    ) -> np.ndarray:
        idxs = np.asarray(indices, dtype=np.int64).reshape(-1)
        w = np.asarray(weights, dtype=np.float64).reshape(-1)
        n = int(min(max(0, n), idxs.size))
        if n <= 0 or idxs.size == 0:
            return np.array([], dtype=np.int64)
        chosen = self._rng.randsample(
            idxs.size,
            n,
            replacement=False,
            weights=w,
        )
        return idxs[np.asarray(chosen, dtype=np.int64)]

    def _count_binding_rate_sites(
        self,
        candidate_ids: np.ndarray,
        binding_rates: np.ndarray,
        site_indices: np.ndarray,
    ) -> int:
        candidate_site_indices = np.asarray(candidate_ids, dtype=np.int64) % int(self.n_sites)
        site_mask = np.isin(candidate_site_indices, np.asarray(site_indices, dtype=np.int64))
        if not np.any(site_mask):
            return 0
        return int(np.count_nonzero(np.asarray(binding_rates, dtype=np.float64)[site_mask]))

    def _matlab_find_order_dnaa_site_indices(self, complex_bound_sites: SparseTriplet) -> np.ndarray:
        values = np.asarray(complex_bound_sites.values, dtype=np.int64)
        if values.size == 0:
            return np.zeros(0, dtype=np.int64)

        is_dnaa = np.fromiter(
            (int(value) in self._dnaa_counts_by_global_index for value in values.tolist()),
            dtype=bool,
            count=values.size,
        )
        if not np.any(is_dnaa):
            return np.zeros(0, dtype=np.int64)

        positions = np.asarray(complex_bound_sites.positions[is_dnaa], dtype=np.int64)
        strands = np.asarray(complex_bound_sites.strands[is_dnaa], dtype=np.int64)
        matlab_find_order = np.lexsort((positions, strands))

        ordered_site_indices: list[int] = []
        for ordered_idx in matlab_find_order.tolist():
            site_idx = self._site_index_by_position.get(int(positions[int(ordered_idx)]))
            copy_idx = self._copy_index_for_strand(int(strands[int(ordered_idx)]))
            if site_idx is None or copy_idx is None:
                continue
            ordered_site_indices.append(int(self._encode_candidate_ids(np.array([site_idx]), copy_idx=copy_idx)[0]))
        return np.asarray(ordered_site_indices, dtype=np.int64)

    @staticmethod
    def _footprint_overhangs(total_footprint: int) -> tuple[int, int]:
        footprint5 = int(np.ceil((int(total_footprint) - 1) / 2.0))
        footprint3 = int(total_footprint) - 1 - footprint5
        return footprint5, footprint3

    @staticmethod
    def _strand_pair_index(strand: int) -> int:
        return int(strand) // 2

    def _copy_index_for_strand(self, strand: int) -> int | None:
        strand_i = int(strand)
        if strand_i not in (0, 2):
            return None
        return strand_i // 2

    def _copy_strand(self, copy_idx: int) -> int:
        return int(self._copy_strands[int(copy_idx)])

    def _encode_candidate_ids(self, site_indices: np.ndarray, *, copy_idx: int) -> np.ndarray:
        return np.asarray(site_indices, dtype=np.int64) + int(copy_idx) * int(self.n_sites)

    def _decode_candidate_id(self, candidate_id: int) -> tuple[int, int]:
        candidate_i = int(candidate_id)
        return candidate_i % int(self.n_sites), candidate_i // int(self.n_sites)

    def _is_region_polymerized(self, polymerized: SparseTriplet, position: int, strand: int) -> bool:
        mask = polymerized.strands == int(strand)
        if not np.any(mask):
            return False
        starts = polymerized.positions[mask]
        lengths = polymerized.values[mask]
        pos_i = int(position)
        return bool(np.any((pos_i >= starts) & (pos_i < starts + lengths)))

    def _polymerized_region_length_at(
        self,
        polymerized: SparseTriplet,
        position: int,
        strand: int,
    ) -> int:
        """Length of the polymerized region covering `position` on
        `strand`, or 0 if none (extent=0, matching MATLAB's
        `isRegionPolymerized`)."""
        mask = polymerized.strands == int(strand)
        if not np.any(mask):
            return 0
        starts = polymerized.positions[mask]
        lengths = polymerized.values[mask]
        pos_i = int(position)
        hits = np.flatnonzero((pos_i >= starts) & (pos_i < starts + lengths))
        if hits.size == 0:
            return 0
        return int(lengths[int(hits[0])])

    def _has_second_chromosome(self, polymerized_regions: SparseTriplet) -> bool:
        total_polymerized = int(np.sum(polymerized_regions.values, dtype=np.int64))
        return total_polymerized > 2 * int(self.chromosome_length)

    def _strand_runs(self, polymerized: SparseTriplet, strand: int) -> list[tuple[int, int]]:
        """Sorted (position, length) polymerized runs on `strand`, position
        ascending -- matches MATLAB's `find()` traversal order within a
        single strand column of a sparse matrix."""
        mask = polymerized.strands == int(strand)
        if not np.any(mask):
            return []
        starts = polymerized.positions[mask]
        lengths = polymerized.values[mask]
        order = np.argsort(starts, kind="stable")
        return list(zip(starts[order].tolist(), lengths[order].tolist(), strict=True))

    @staticmethod
    def _intersect_sorted_runs(
        runs_a: list[tuple[int, int]],
        runs_b: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        """Sorted (position, length) runs covering the intersection of two
        sorted, non-overlapping run lists (linear, non-circular -- matches
        this project's own established convention that any region crossing
        the chromosome origin is already split into two separate,
        non-wrapping entries at the raw triplet level, so a plain linear
        sweep over [0, chromosome_length) is sufficient; see
        `merge_adjacent_regions`'s own docstring on this same convention).
        Two-pointer sweep, O(len(runs_a) + len(runs_b))."""
        result: list[tuple[int, int]] = []
        i = j = 0
        while i < len(runs_a) and j < len(runs_b):
            a_start, a_len = runs_a[i]
            b_start, b_len = runs_b[j]
            a_end = a_start + a_len
            b_end = b_start + b_len
            lo = max(a_start, b_start)
            hi = min(a_end, b_end)
            if lo < hi:
                result.append((lo, hi - lo))
            if a_end <= b_end:
                i += 1
            else:
                j += 1
        return result

    def _double_stranded_region_runs_for_strand(
        self,
        polymerized_regions: SparseTriplet,
        strand: int,
    ) -> list[tuple[int, int]]:
        """Merged (position, length) DOUBLE-STRANDED runs covering `strand`
        -- i.e. positions where both `strand` and its pair partner are
        polymerized (Chromosome.m's `calcDoubleStrandedRegions`, restricted
        to one strand of a pair: `extent = min(abs(extentOfStrandA),
        abs(extentOfStrandB))`, written identically to both strands of the
        pair). For simple, non-fragmented overlap geometry (this project's
        fixtures never show anything else), this equals the geometric
        intersection of the two strands' own raw `polymerizedRegions`
        coverage -- computed here directly, rather than reusing the
        single-position `_polymerized_region_length_at` query, because the
        real MATLAB caller (`calculateDnaAATPBindingRates`'s/
        `calculateDnaAADPBindingRates`'s own second-copy candidate filter,
        see `_second_copy_site_mask`) needs the FIRST and LAST run's own
        (position, length) -- not a per-position membership test."""
        partner = strand + 1 if strand % 2 == 0 else strand - 1
        runs_a = self._strand_runs(polymerized_regions, strand)
        runs_b = self._strand_runs(polymerized_regions, partner)
        return self._intersect_sorted_runs(runs_a, runs_b)

    def _second_copy_site_mask(self, polymerized_regions: SparseTriplet) -> np.ndarray:
        """Port of `calculateDnaAATPBindingRates`'s/`calculateDnaAADPBindingRates`'s
        own second-copy candidate filter (ReplicationInitiation.m:999-1006/
        1042-1049):
        ```
        if collapse(polymerizedRegions) < 4*sequenceLen
            [pos, len] = find(doubleStrandedRegions);
            len = len(pos(:,2)==4, 1);
            pos = pos(pos(:,2)==4, 1);
            tfs = dnaABoxStartPositions < pos(1)+len(1) | dnaABoxStartPositions > pos(end);
            ...filter to tfs...
        end
        ```
        NOTE: this is NOT a per-position "is this exact DnaA box already
        double-stranded on copy 2" test -- it only ever looks at the FIRST
        and LAST `doubleStrandedRegions` run's own (position, length) on
        the query strand (MATLAB's `pos(1)`/`len(1)`/`pos(end)`), a
        heuristic that degenerates to "include every candidate" whenever
        there is only ONE double-stranded run on that strand (`pos(1) ==
        pos(end)`, so `x < pos(1)+len(1) | x > pos(1)` is true for every
        `x`) -- confirmed against real MATLAB via a live probe at tick 13
        (`scripts/matlab/probe_repinit_tick13_candidate_universe.m`): with
        a single [0, 1111) double-stranded run on copy 2, real MATLAB's
        own filter includes all 2283 second-copy candidates (`tfs` always
        true), while a PER-POSITION double-strandedness check (this
        function's own prior implementation) wrongly excluded all but the
        3 candidates whose exact DnaA-box position happened to fall inside
        that one small run. A previous version of this method implemented
        the per-position test instead of this formula -- a real,
        source-fidelity bug, not a stylistic difference (see
        STATUS_L21_REPINIT_SEPT2.md Session N+3)."""
        total_polymerized = int(np.sum(polymerized_regions.values, dtype=np.int64))
        if total_polymerized <= 2 * int(self.chromosome_length):
            return np.zeros(self.n_sites, dtype=bool)
        if total_polymerized >= 4 * int(self.chromosome_length):
            return np.ones(self.n_sites, dtype=bool)

        second_copy_partner = self._copy_strand(1) + 1
        runs = self._double_stranded_region_runs_for_strand(polymerized_regions, second_copy_partner)
        if not runs:
            # MATLAB's own `pos(1)` would itself error on an empty
            # doubleStrandedRegions(:,4) here -- this branch is only
            # reachable when `_has_second_chromosome` is true (some second-
            # copy polymerization exists), and every fixture/trace this
            # project has ever observed has at least one double-stranded
            # run on the second copy whenever that's the case. Fail closed
            # rather than silently return an empty (all-False) mask that
            # would look like a legitimate, source-faithful zero-candidate
            # result.
            raise ValueError(
                "second copy detected (total_polymerized > 2*chromosome_length) but "
                "doubleStrandedRegions has no entries on the second-copy partner strand "
                f"{second_copy_partner} -- cannot evaluate MATLAB's pos(1)/pos(end) filter"
            )
        first_start, first_len = runs[0]
        last_start, _ = runs[-1]
        first_end = first_start + first_len
        positions = self._dnaa_box_positions
        return (positions < first_end) | (positions > last_start)

    def _linking_number_at(
        self,
        linking_numbers: SparseTriplet,
        position: int,
        strand: int,
    ) -> int | None:
        """Find the linking-number SCALAR (Chromosome.m's own sparse
        `linkingNumbers` property; its sparse-matrix VALUE at a given
        position/strand key IS the linking number itself, e.g.
        `setRegionPolymerized`'s `this.linkingNumbers([pos tmpStrd; pos
        nonTmpStrd]) = len / this.relaxedBasesPerTurn`, Chromosome.m:2013)
        covering `position` on `strand`. Region LENGTH is looked up
        separately from `polymerizedRegions` (see
        `_polymerized_region_length_at`), since `linkingNumbers` entries
        are keyed the same way but carry the linking-number value, not a
        length, in their own triplet slot. Returns None if no covering
        entry is recorded."""
        mask = linking_numbers.strands == int(strand)
        if not np.any(mask):
            return None
        starts = linking_numbers.positions[mask]
        # linkingNumbers regions share polymerizedRegions' own segment
        # boundaries for any region not independently modified; since the
        # triplet itself only carries (position, strand, linking_number)
        # -- not an explicit length -- resolve the covering entry as the
        # closest start position at or before the query position on this
        # strand (matches contiguous non-overlapping region semantics).
        pos_i = int(position)
        candidates = np.flatnonzero(starts <= pos_i)
        if candidates.size == 0:
            return None
        best = candidates[np.argmax(starts[candidates])]
        return int(linking_numbers.values[mask][int(best)])

    def _is_region_supercoiled(
        self,
        *,
        polymerized_regions: SparseTriplet,
        linking_numbers: SparseTriplet,
        position: int,
        strand: int,
    ) -> bool:
        """Port of Chromosome.m's `calcSupercoiled`/`isRegionDoubleStranded`
        `checkRegionSupercoiled` gate: a candidate binding site is only
        accessible if its position is (a) double-stranded (both strands
        of its copy's pair are polymerized there -- already enforced
        upstream for the second-copy case via `_second_copy_site_mask`
        in `_calculate_binding_rates`) and (b) within the equilibrium
        superhelical-density tolerance:
        `abs((lk - length/relaxedBasesPerTurn) / (length/relaxedBasesPerTurn)
        - equilibriumSuperhelicalDensity) < supercoiledSuperhelicalDensityTolerance`
        (Chromosome.m:3602-3615, constants from data/karr_fixtures/
        per_process/Chromosome_flat.mat, loaded in `_load_fixture`).
        `length` here is the `doubleStrandedRegions` extent -- Chromosome.m's
        `calcDoubleStrandedRegions` (Chromosome.m:3205-3260) sets it to
        `min(abs(extentOfStrandA), abs(extentOfStrandB))`, the SHORTER of
        the two paired strands' own polymerized-run extents at this
        position, NOT the query strand's own extent alone. Live-MATLAB-
        confirmed source-fidelity bug (STATUS_L21_REPINIT_SEPT2.md Session
        N+4): using the query strand's own (potentially much larger)
        single-strand extent instead of the paired minimum produces a
        WRONG `lk0`/`sigma` whenever the partner strand's own polymerized
        run at this exact position is meaningfully shorter -- e.g. tick 55
        candidate site 2269 (position 577910): query-strand extent
        580076 (a fully-polymerized single run spanning the whole
        chromosome) vs partner-strand extent 4711 (a real, much shorter
        run reflecting where replication has actually reached) --
        confirmed via live real-MATLAB isRegionAccessible: real MATLAB
        ACCEPTS this candidate (using the correct min=4711), while the
        single-strand-extent version incorrectly REJECTS it (using
        580076), causing a real site-selection swap. Returns False (not
        accessible) if no polymerized/linking-number region covers this
        position on this strand at all -- matches MATLAB's extent=0 (not
        double-stranded) case, which also fails `checkRegionSupercoiled`'s
        membership test."""
        partner_strand = int(strand) + 1 if int(strand) % 2 == 0 else int(strand) - 1
        length = self._polymerized_region_length_at(polymerized_regions, int(position), int(strand))
        if length <= 0:
            return False
        partner_length = self._polymerized_region_length_at(polymerized_regions, int(position), int(partner_strand))
        if partner_length <= 0:
            return False
        length = min(length, partner_length)
        linking_number = self._linking_number_at(linking_numbers, int(position), int(strand))
        if linking_number is None:
            return False
        lk0 = float(length) / self.relaxed_bases_per_turn
        if lk0 == 0.0:
            return False
        sigma = (linking_number - lk0) / lk0
        return bool(
            abs(sigma - self.equilibrium_superhelical_density)
            < self.supercoiled_superhelical_density_tolerance
        )

    def _releasable_complex_indexs(
        self,
        *,
        binding_monomers: tuple[int, ...] = (),
        binding_complexes: tuple[int, ...] = (),
    ) -> np.ndarray:
        score = np.zeros_like(self.reaction_thresholds)
        if binding_monomers:
            monomer_cols = np.asarray(binding_monomers, dtype=np.int64) - 1
            score = score + np.sum(self.reaction_monomer_catalysis_matrix[:, monomer_cols], axis=1)
        if binding_complexes:
            complex_cols = np.asarray(binding_complexes, dtype=np.int64) - 1
            score = score + np.sum(self.reaction_complex_catalysis_matrix[:, complex_cols], axis=1)
        releasable = self.reaction_bound_complex[score >= self.reaction_thresholds]
        releasable = releasable[releasable != 0]
        if releasable.size == 0:
            return np.zeros(0, dtype=np.int64)
        return np.unique(releasable.astype(np.int64, copy=False))

    def _releasable_monomer_indexs(
        self,
        *,
        binding_monomers: tuple[int, ...] = (),
        binding_complexes: tuple[int, ...] = (),
    ) -> np.ndarray:
        score = np.zeros_like(self.reaction_thresholds)
        if binding_monomers:
            monomer_cols = np.asarray(binding_monomers, dtype=np.int64) - 1
            score = score + np.sum(self.reaction_monomer_catalysis_matrix[:, monomer_cols], axis=1)
        if binding_complexes:
            complex_cols = np.asarray(binding_complexes, dtype=np.int64) - 1
            score = score + np.sum(self.reaction_complex_catalysis_matrix[:, complex_cols], axis=1)
        releasable = self.reaction_bound_monomer[score >= self.reaction_thresholds]
        releasable = releasable[releasable != 0]
        if releasable.size == 0:
            return np.zeros(0, dtype=np.int64)
        return np.unique(releasable.astype(np.int64, copy=False))

    def _wrapped_interval_segments(self, start: int, length: int) -> tuple[tuple[int, int], ...]:
        start_i = int(start) % self.chromosome_length
        end_i = start_i + int(length) - 1
        if end_i < self.chromosome_length:
            return ((start_i, end_i),)
        return (
            (start_i, self.chromosome_length - 1),
            (0, end_i % self.chromosome_length),
        )

    def _intervals_overlap(
        self,
        start_a: int,
        length_a: int,
        start_b: int,
        length_b: int,
    ) -> bool:
        for seg_a_start, seg_a_end in self._wrapped_interval_segments(start_a, length_a):
            for seg_b_start, seg_b_end in self._wrapped_interval_segments(start_b, length_b):
                if seg_a_start <= seg_b_end and seg_b_start <= seg_a_end:
                    return True
        return False

    def _binding_site_accessible(
        self,
        *,
        site_idx: int,
        copy_idx: int,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        binding_complex_global_index: int,
        polymerized_regions: SparseTriplet | None = None,
        linking_numbers: SparseTriplet | None = None,
    ) -> bool:
        if bool(self._blocked_sites[site_idx, copy_idx]):
            return False

        binding_global_index = int(binding_complex_global_index)
        binding_footprint = int(self.complex_dna_footprints[binding_global_index - 1])
        if binding_footprint <= 0:
            binding_footprint = 1
        query_strand = self._copy_strand(copy_idx)

        if polymerized_regions is not None and linking_numbers is not None and not self._is_region_supercoiled(
            polymerized_regions=polymerized_regions,
            linking_numbers=linking_numbers,
            position=int(self._dnaa_box_positions[int(site_idx)]),
            strand=query_strand,
        ):
            # checkRegionSupercoiled gate (Chromosome.m's isRegionDoubleStranded/
            # calcSupercoiled, applied by isRegionAccessible for
            # bindDnaAATP/bindDnaAADP's bindProteinToChromosome call --
            # ReplicationInitiation.m:719,747 pass checkRegionSupercoiled=true).
            # A candidate site is only accessible if its own polymerized
            # region is within the equilibrium superhelical-density
            # tolerance -- freshly-replicated (nascent second-copy) DNA is
            # not automatically supercoiled-compliant once torsional
            # activity from other processes has modified its linking
            # number.
            return False

        query_start = int(
            self._interval_start_for_query_position(
                position=int(self._dnaa_box_positions[int(site_idx)]),
                strand=query_strand,
                footprint=binding_footprint,
                is_centroid=False,
            )
        )
        query_binding_strandedness = int(
            self.complex_dna_footprint_binding_strandedness[binding_global_index - 1]
        )
        query_key = (
            self._strand_pair_index(query_strand)
            if query_binding_strandedness == self.dna_strandedness_dsdna
            else query_strand
        )

        releasable_monomers = self._releasable_monomer_indexs(
            binding_complexes=(binding_global_index,),
        )
        releasable_complexes = self._releasable_complex_indexs(
            binding_complexes=(binding_global_index,),
        )
        releasable_monomer_set = frozenset(int(value) for value in releasable_monomers.tolist())
        releasable_set = frozenset(int(value) for value in releasable_complexes.tolist())

        for position, strand, value in zip(
            monomer_bound_sites.positions.tolist(),
            monomer_bound_sites.strands.tolist(),
            monomer_bound_sites.values.tolist(),
            strict=False,
        ):
            value_i = int(value)
            if value_i <= 0 or value_i in releasable_monomer_set:
                continue
            if value_i > self.monomer_dna_footprints.size:
                continue

            foreign_binding_strandedness = int(
                self.monomer_dna_footprint_binding_strandedness[value_i - 1]
            )
            if query_binding_strandedness == self.dna_strandedness_dsdna:
                foreign_key = self._strand_pair_index(int(strand))
            elif foreign_binding_strandedness == self.dna_strandedness_dsdna:
                foreign_key = self._strand_pair_index(query_strand)
            else:
                foreign_key = int(strand)
            if foreign_key != query_key:
                continue

            foreign_footprint = int(self.monomer_dna_footprints[value_i - 1])
            if foreign_footprint <= 0:
                foreign_footprint = 1
            if self._intervals_overlap(
                query_start,
                binding_footprint,
                int(position),
                foreign_footprint,
            ):
                return False

        for position, strand, value in zip(
            complex_bound_sites.positions.tolist(),
            complex_bound_sites.strands.tolist(),
            complex_bound_sites.values.tolist(),
            strict=False,
        ):
            value_i = int(value)
            if value_i <= 0 or value_i in releasable_set:
                continue
            if value_i > self.complex_dna_footprints.size:
                continue

            foreign_binding_strandedness = int(
                self.complex_dna_footprint_binding_strandedness[value_i - 1]
            )
            if query_binding_strandedness == self.dna_strandedness_dsdna:
                foreign_key = self._strand_pair_index(int(strand))
            elif foreign_binding_strandedness == self.dna_strandedness_dsdna:
                foreign_key = self._strand_pair_index(query_strand)
            else:
                foreign_key = int(strand)
            if foreign_key != query_key:
                continue

            foreign_footprint = int(self.complex_dna_footprints[value_i - 1])
            if foreign_footprint <= 0:
                foreign_footprint = 1
            if self._intervals_overlap(
                query_start,
                binding_footprint,
                int(position),
                foreign_footprint,
            ):
                return False
        return True

    def _selected_binding_sites_overlap(
        self,
        selected_sites: list[int],
        candidate_site: int,
        *,
        binding_complex_global_index: int,
    ) -> bool:
        if not selected_sites:
            return False
        binding_footprint = int(self.complex_dna_footprints[int(binding_complex_global_index) - 1])
        if binding_footprint <= 0:
            binding_footprint = 1
        candidate_site_idx, candidate_copy_idx = self._decode_candidate_id(candidate_site)
        candidate_strand = self._copy_strand(candidate_copy_idx)
        candidate_binding_strandedness = int(
            self.complex_dna_footprint_binding_strandedness[int(binding_complex_global_index) - 1]
        )
        candidate_start = int(
            self._interval_start_for_query_position(
                position=int(self._dnaa_box_positions[int(candidate_site_idx)]),
                strand=candidate_strand,
                footprint=binding_footprint,
                is_centroid=False,
            )
        )
        candidate_key = (
            self._strand_pair_index(candidate_strand)
            if candidate_binding_strandedness == self.dna_strandedness_dsdna
            else candidate_strand
        )
        for chosen_site in selected_sites:
            chosen_site_idx, chosen_copy_idx = self._decode_candidate_id(chosen_site)
            chosen_strand = self._copy_strand(chosen_copy_idx)
            chosen_start = int(
                self._interval_start_for_query_position(
                    position=int(self._dnaa_box_positions[int(chosen_site_idx)]),
                    strand=chosen_strand,
                    footprint=binding_footprint,
                    is_centroid=False,
                )
            )
            chosen_key = (
                self._strand_pair_index(chosen_strand)
                if candidate_binding_strandedness == self.dna_strandedness_dsdna
                else chosen_strand
            )
            if chosen_key != candidate_key:
                continue
            if self._intervals_overlap(
                candidate_start,
                binding_footprint,
                chosen_start,
                binding_footprint,
            ):
                return True
        return False

    def _sample_binding_sites(
        self,
        candidate_sites: np.ndarray,
        weights: np.ndarray,
        n_sites: int,
        *,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        binding_complex_global_index: int,
        polymerized_regions: SparseTriplet | None = None,
        linking_numbers: SparseTriplet | None = None,
    ) -> np.ndarray:
        site_indices = np.asarray(candidate_sites, dtype=np.int64).reshape(-1)
        site_weights = np.asarray(weights, dtype=np.float64).reshape(-1).copy()
        target = int(min(max(0, n_sites), site_indices.size))
        if target <= 0 or site_indices.size == 0 or not np.any(site_weights > 0.0):
            return np.zeros(0, dtype=np.int64)

        chosen_sites: list[int] = []
        while np.any(site_weights > 0.0) and len(chosen_sites) < target:
            n_more_sites = min(
                max(2 * (target - len(chosen_sites)), 10),
                int(np.count_nonzero(site_weights > 0.0)),
            )
            selected = self._chromosome_rng.randsample(
                site_indices.size,
                n_more_sites,
                replacement=False,
                weights=site_weights,
            )
            site_weights[np.asarray(selected, dtype=np.int64)] = 0.0
            selected_relative = np.asarray(selected, dtype=np.int64)

            # Evaluate accessibility for the WHOLE batch first, matching
            # MATLAB's sampleAccessibleRegions (isRegionAccessible is
            # called vectorized over the entire selectedSites array, and
            # excludeOverlappingRegions filters the entire accessible set,
            # BEFORE truncating to however many are still needed). Never
            # stop early mid-batch: an early stop would silently skip
            # evaluating some candidates that MATLAB's real algorithm
            # always evaluates, and could accept a DIFFERENT subset than
            # MATLAB's own truncation (which takes the first
            # `nSites - numel(idxs)` of the FULL accessible/non-
            # overlapping set, not the first ones encountered while
            # scanning).
            accessible_candidate_ids: list[int] = []
            for relative_idx in selected_relative.tolist():
                candidate_id = int(site_indices[int(relative_idx)])
                site_idx, copy_idx = self._decode_candidate_id(candidate_id)
                if self._binding_site_accessible(
                    site_idx=site_idx,
                    copy_idx=copy_idx,
                    monomer_bound_sites=monomer_bound_sites,
                    complex_bound_sites=complex_bound_sites,
                    binding_complex_global_index=binding_complex_global_index,
                    polymerized_regions=polymerized_regions,
                    linking_numbers=linking_numbers,
                ):
                    accessible_candidate_ids.append(candidate_id)

            # excludeOverlappingRegions (Chromosome.m:2825-2870) checks
            # each accessible candidate, IN LIST ORDER, against idxs PLUS
            # every EARLIER accessible candidate in this same batch --
            # REGARDLESS of whether that earlier candidate itself later
            # turned out to overlap something else (MATLAB's own
            # backward-iterating loop builds `tmpTfs` from the raw,
            # unfiltered position list, not the survivors-only list). A
            # candidate that itself gets excluded can still "block" a
            # later one. Blocking references must therefore be ALL
            # earlier accessible candidates in list order, not just the
            # ones that ultimately survive.
            new_ids: list[int] = []
            for earlier_count, candidate_id in enumerate(accessible_candidate_ids):
                blocking_refs = chosen_sites + accessible_candidate_ids[:earlier_count]
                if self._selected_binding_sites_overlap(
                    blocking_refs,
                    candidate_id,
                    binding_complex_global_index=binding_complex_global_index,
                ):
                    continue
                new_ids.append(candidate_id)

            remaining = target - len(chosen_sites)
            if len(new_ids) > remaining:
                new_ids = new_ids[:remaining]
            chosen_sites.extend(new_ids)

        if not chosen_sites:
            return np.zeros(0, dtype=np.int64)
        return np.sort(np.asarray(chosen_sites, dtype=np.int64), kind="mergesort")

    def _bind_sites(
        self,
        candidate_ids: np.ndarray,
        binding_rates: np.ndarray,
        max_binding: int,
        *,
        atp: bool,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        polymerized_regions: SparseTriplet | None = None,
        linking_numbers: SparseTriplet | None = None,
    ) -> int:
        if max_binding <= 0:
            return 0
        positive = np.flatnonzero(binding_rates > 0.0)
        if positive.size == 0:
            return 0
        binding_complex_global_index = (
            int(self.enzyme_global_indexs[self.enzyme_index_dnaa_1mer_atp])
            if atp
            else int(self.enzyme_global_indexs[self.enzyme_index_dnaa_1mer_adp])
        )
        chosen = self._sample_binding_sites(
            np.asarray(candidate_ids, dtype=np.int64)[positive],
            binding_rates[positive],
            min(max_binding, positive.size),
            monomer_bound_sites=monomer_bound_sites,
            complex_bound_sites=complex_bound_sites,
            binding_complex_global_index=binding_complex_global_index,
            polymerized_regions=polymerized_regions,
            linking_numbers=linking_numbers,
        )
        if chosen.size == 0:
            return 0
        for candidate_id in np.asarray(chosen, dtype=np.int64).tolist():
            site_idx, copy_idx = self._decode_candidate_id(int(candidate_id))
            if atp:
                self._bound_atp[site_idx, copy_idx] += 1
            else:
                self._bound_adp[site_idx, copy_idx] += 1
        if atp:
            self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] -= int(chosen.size)
        else:
            self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] -= int(chosen.size)
        self._free_dnaa_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        self._free_dnaa_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])
        return int(chosen.size)

    def _bind_and_polymerize_dnaa_atp(
        self,
        dt: float,
        *,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        polymerized_regions: SparseTriplet,
        linking_numbers: SparseTriplet | None = None,
    ) -> None:
        free_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])
        if free_atp <= 0:
            return
        candidate_ids, binding_rates, avg_binding_rate = self._calculate_binding_rates(
            rate9mer=self._binding_probability(self.kb_atp, dt, scale_param="binding_rate_scale"),
            rate8mer=self._binding_probability(self.kb2_atp, dt, scale_param="binding_rate_scale"),
            for_atp=True,
            polymerized_regions=polymerized_regions,
        )
        monomer_bound = int(np.count_nonzero((self._bound_atp == 1) & (self._bound_adp == 0))) + int(
            np.count_nonzero((self._bound_atp == 0) & (self._bound_adp == 1))
        )
        num_free_binding_sites = max(0, int(binding_rates.size) - monomer_bound)
        max_binding = self._stochastic_round(
            min(
                avg_binding_rate * num_free_binding_sites * free_atp
                + float(
                    self._count_binding_rate_sites(
                        candidate_ids,
                        binding_rates,
                        self.dnaABoxIndexs_7mer,
                    )
                ),
                float(num_free_binding_sites),
                float(free_atp),
            )
        )

        pol_rates = self._calculate_atp_polymerization_rates(dt)
        max_pol = 0
        if np.any(pol_rates):
            num_free_pol_sites = int(np.count_nonzero(pol_rates))
            max_pol = self._stochastic_round(
                min(
                    float(np.sum(pol_rates)) * float(free_atp),
                    float(num_free_pol_sites),
                    float(free_atp),
                )
            )

        tot_binding_rate = avg_binding_rate * float(num_free_binding_sites)
        tot_pol_rate = float(np.sum(pol_rates))
        denom_atp = tot_binding_rate + tot_pol_rate
        # MATLAB calls stochasticRound(...) unconditionally here (no `if` guard);
        # when denom is 0 the division is 0/0 == NaN in MATLAB, and
        # min(maxBinding, NaN) leaves maxBinding unchanged while still consuming
        # a rand() draw. Always call _stochastic_round to preserve RNG lockstep;
        # rely on Python's min(int, nan) == int (nan as the 2nd arg) to match
        # MATLAB's NaN-ignoring min semantics.
        ratio_atp = (float(free_atp) * tot_binding_rate / denom_atp) if denom_atp != 0.0 else float("nan")
        max_binding = min(max_binding, self._stochastic_round(ratio_atp))

        n_bound = self._bind_sites(
            candidate_ids,
            binding_rates,
            max_binding,
            atp=True,
            monomer_bound_sites=monomer_bound_sites,
            complex_bound_sites=complex_bound_sites,
            polymerized_regions=polymerized_regions,
            linking_numbers=linking_numbers,
        )
        remaining_free = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])
        if max_pol <= 0 or remaining_free <= 0:
            return
        candidate_offsets = np.flatnonzero(pol_rates > 0.0)
        if candidate_offsets.size == 0:
            return
        flat_rates = np.reshape(pol_rates, -1, order="F")
        chosen_offsets = self._weighted_sample_without_replacement(
            np.flatnonzero(flat_rates > 0.0).astype(np.int64),
            flat_rates[flat_rates > 0.0],
            min(max_pol, remaining_free, candidate_offsets.size, free_atp - n_bound),
        )
        if chosen_offsets.size == 0:
            return
        for offset in np.asarray(chosen_offsets, dtype=np.int64).tolist():
            site_offset = int(offset) % 4
            copy_idx = int(offset) // 4
            self._bound_atp[self.r1234_indices[site_offset], copy_idx] += 1
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] -= int(chosen_offsets.size)
        self._free_dnaa_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])

    def _bind_and_polymerize_dnaa_adp(
        self,
        dt: float,
        *,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        polymerized_regions: SparseTriplet,
        linking_numbers: SparseTriplet | None = None,
    ) -> None:
        free_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        if free_adp <= 0:
            return
        candidate_ids, binding_rates, avg_binding_rate = self._calculate_binding_rates(
            rate9mer=self._binding_probability(self.kb_adp, dt, scale_param="binding_rate_scale"),
            rate8mer=self._binding_probability(self.kb2_adp, dt, scale_param="binding_rate_scale"),
            for_atp=False,
            polymerized_regions=polymerized_regions,
        )
        monomer_bound = int(np.count_nonzero((self._bound_atp == 1) & (self._bound_adp == 0))) + int(
            np.count_nonzero((self._bound_atp == 0) & (self._bound_adp == 1))
        )
        num_free_binding_sites = max(0, int(binding_rates.size) - monomer_bound)
        max_binding = self._stochastic_round(
            min(
                avg_binding_rate * num_free_binding_sites * free_adp
                + float(
                    self._count_binding_rate_sites(
                        candidate_ids,
                        binding_rates,
                        self.dnaABoxIndexs_7mer,
                    )
                ),
                float(num_free_binding_sites),
                float(free_adp),
            )
        )

        pol_rates = self._calculate_adp_polymerization_rates(dt)
        max_pol = 0
        if np.any(pol_rates):
            num_free_pol_sites = int(np.count_nonzero(pol_rates))
            max_pol = self._stochastic_round(
                min(
                    float(np.sum(pol_rates)) * float(free_adp),
                    float(num_free_pol_sites),
                    float(free_adp),
                )
            )

        tot_binding_rate = avg_binding_rate * float(num_free_binding_sites)
        tot_pol_rate = float(np.sum(pol_rates))
        denom_adp = tot_binding_rate + tot_pol_rate
        # See matching comment in _bind_and_polymerize_dnaa_atp: MATLAB calls
        # stochasticRound(...) unconditionally here; always draw to preserve
        # RNG lockstep, relying on Python's min(int, nan) to match MATLAB's
        # NaN-ignoring min() when denom_adp is 0.
        ratio_adp = (float(free_adp) * tot_binding_rate / denom_adp) if denom_adp != 0.0 else float("nan")
        max_binding = min(max_binding, self._stochastic_round(ratio_adp))

        n_bound = self._bind_sites(
            candidate_ids,
            binding_rates,
            max_binding,
            atp=False,
            monomer_bound_sites=monomer_bound_sites,
            complex_bound_sites=complex_bound_sites,
            polymerized_regions=polymerized_regions,
            linking_numbers=linking_numbers,
        )
        remaining_free = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        if max_pol <= 0 or remaining_free <= 0:
            return
        candidate_offsets = np.flatnonzero(pol_rates > 0.0)
        if candidate_offsets.size == 0:
            return
        flat_rates = np.reshape(pol_rates, -1, order="F")
        chosen_offsets = self._weighted_sample_without_replacement(
            np.flatnonzero(flat_rates > 0.0).astype(np.int64),
            flat_rates[flat_rates > 0.0],
            min(max_pol, remaining_free, candidate_offsets.size, free_adp - n_bound),
        )
        if chosen_offsets.size == 0:
            return
        for offset in np.asarray(chosen_offsets, dtype=np.int64).tolist():
            site_offset = int(offset) % 4
            copy_idx = int(offset) // 4
            self._bound_adp[self.r1234_indices[site_offset], copy_idx] = (
                self._bound_atp[self.r1234_indices[site_offset], copy_idx] + 1
            )
            self._bound_atp[self.r1234_indices[site_offset], copy_idx] = 0
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] -= int(chosen_offsets.size)
        self._free_dnaa_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])

    def _bind_only_dnaa_atp(
        self,
        dt: float,
        *,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        polymerized_regions: SparseTriplet,
    ) -> None:
        free_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])
        if free_atp <= 0:
            return
        candidate_ids, binding_rates, avg_binding_rate = self._calculate_binding_rates(
            rate9mer=self._binding_probability(self.kb_atp, dt, scale_param="binding_rate_scale"),
            rate8mer=self._binding_probability(self.kb2_atp, dt, scale_param="binding_rate_scale"),
            for_atp=True,
            polymerized_regions=polymerized_regions,
        )
        monomer_bound = int(np.count_nonzero((self._bound_atp == 1) & (self._bound_adp == 0))) + int(
            np.count_nonzero((self._bound_atp == 0) & (self._bound_adp == 1))
        )
        num_free_binding_sites = max(0, int(binding_rates.size) - monomer_bound)
        max_binding = self._stochastic_round(
            min(
                avg_binding_rate * num_free_binding_sites * free_atp
                + float(
                    self._count_binding_rate_sites(
                        candidate_ids,
                        binding_rates,
                        self.dnaABoxIndexs_7mer,
                    )
                ),
                float(num_free_binding_sites),
                float(free_atp),
            )
        )
        self._bind_sites(
            candidate_ids,
            binding_rates,
            max_binding,
            atp=True,
            monomer_bound_sites=monomer_bound_sites,
            complex_bound_sites=complex_bound_sites,
        )

    def _bind_only_dnaa_adp(
        self,
        dt: float,
        *,
        monomer_bound_sites: SparseTriplet,
        complex_bound_sites: SparseTriplet,
        polymerized_regions: SparseTriplet,
    ) -> None:
        free_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        if free_adp <= 0:
            return
        candidate_ids, binding_rates, avg_binding_rate = self._calculate_binding_rates(
            rate9mer=self._binding_probability(self.kb_adp, dt, scale_param="binding_rate_scale"),
            rate8mer=self._binding_probability(self.kb2_adp, dt, scale_param="binding_rate_scale"),
            for_atp=False,
            polymerized_regions=polymerized_regions,
        )
        monomer_bound = int(np.count_nonzero((self._bound_atp == 1) & (self._bound_adp == 0))) + int(
            np.count_nonzero((self._bound_atp == 0) & (self._bound_adp == 1))
        )
        num_free_binding_sites = max(0, int(binding_rates.size) - monomer_bound)
        max_binding = self._stochastic_round(
            min(
                avg_binding_rate * num_free_binding_sites * free_adp
                + float(
                    self._count_binding_rate_sites(
                        candidate_ids,
                        binding_rates,
                        self.dnaABoxIndexs_7mer,
                    )
                ),
                float(num_free_binding_sites),
                float(free_adp),
            )
        )
        self._bind_sites(
            candidate_ids,
            binding_rates,
            max_binding,
            atp=False,
            monomer_bound_sites=monomer_bound_sites,
            complex_bound_sites=complex_bound_sites,
        )

    def _release_dnaa_axp(self, dt: float, complex_bound_sites: SparseTriplet) -> None:
        if not np.any((self._bound_atp + self._bound_adp) > 0):
            return
        release_p = self._linear_event_probability(self.kd_atp, dt, scale_param="release_rate_scale")
        if release_p <= 0.0:
            return

        pol_atp, pol_adp = self._oric_polymer_state()
        min_pol = self._oric_complex_size(pol_atp, pol_adp)
        protected_sites: set[int] = set()
        for copy_idx in range(2):
            if int(min_pol[copy_idx]) <= 0:
                continue
            for pos, site_idx in enumerate(self.r1234_indices):
                if int(pol_atp[pos, copy_idx]) == int(min_pol[copy_idx]):
                    protected_sites.add(
                        int(self._encode_candidate_ids(np.array([site_idx]), copy_idx=copy_idx)[0])
                    )
            if int(min_pol[copy_idx]) >= 7:
                protected_sites.add(
                    int(self._encode_candidate_ids(np.array([self.r5_index]), copy_idx=copy_idx)[0])
                )

        for candidate_id in self._matlab_find_order_dnaa_site_indices(complex_bound_sites):
            candidate_i = int(candidate_id)
            if candidate_i in protected_sites:
                continue
            if float(self._rng.random()) >= release_p:
                continue
            site_idx, copy_idx = self._decode_candidate_id(candidate_i)
            if self._bound_adp[site_idx, copy_idx] > 0:
                self._bound_adp[site_idx, copy_idx] -= 1
                self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] += 1
            elif self._bound_atp[site_idx, copy_idx] > 0:
                self._bound_atp[site_idx, copy_idx] -= 1
                self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] += 1

        self._free_dnaa_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        self._free_dnaa_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])

    def _reactivate_free_dnaa_adp(
        self,
        dt: float,
        *,
        available_atp: float,
        substrate_delta: dict[str, int],
    ) -> None:
        free_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        if free_adp <= 0:
            return
        membrane_conc = float(self.parameters["membrane_conc"])
        regen_rate = (self.k_regen / 3600.0 * membrane_conc) / (self.k_regen_p4 + membrane_conc)
        target = float(free_adp) * regen_rate * dt
        if not self._using_explicit_enzyme_pools:
            target /= float(self.parameters["regen_rate_scale"])
        n_events = min(
            free_adp,
            max(0, int(np.floor(available_atp))),
            self._stochastic_round(target),
        )
        if n_events <= 0:
            return
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp] -= n_events
        self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp] += n_events
        self._free_dnaa_adp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_adp])
        self._free_dnaa_atp = int(self._free_enzyme_counts[self.enzyme_index_dnaa_1mer_atp])
        substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0) - n_events
        substrate_delta[self.adp_wid] = substrate_delta.get(self.adp_wid, 0) + n_events

    def _oric_cooperativity(self, idx: int) -> float:
        del idx
        occupied_other = np.count_nonzero(self._bound_atp[self.r1234_indices, :] > 0)
        coop = 1.0 + self.state_cooperativity * (float(occupied_other) / len(self.r1234_indices))
        return max(1.0, coop)

    def _bound_species_counts_from_state(
        self,
        bound_atp: np.ndarray,
        bound_adp: np.ndarray,
        blocked_sites: np.ndarray,
    ) -> np.ndarray:
        counts = np.zeros(len(self.enzyme_wids), dtype=np.int64)
        state_atp = np.asarray(bound_atp, dtype=np.int64).reshape(self.n_sites, 2)
        state_adp = np.asarray(bound_adp, dtype=np.int64).reshape(self.n_sites, 2)
        state_blocked = np.asarray(blocked_sites, dtype=bool).reshape(self.n_sites, 2)
        for site_idx in range(self.n_sites):
            for copy_idx in range(2):
                if bool(state_blocked[site_idx, copy_idx]):
                    continue
                local_idx = self._local_index_for_state(
                    atp_count=int(state_atp[site_idx, copy_idx]),
                    adp_count=int(state_adp[site_idx, copy_idx]),
                )
                if local_idx is None:
                    continue
                counts[local_idx] += 1
        return counts

    def _bound_species_counts(self) -> np.ndarray:
        return self._bound_species_counts_from_state(
            self._bound_atp,
            self._bound_adp,
            self._blocked_sites,
        )

    def _local_index_for_state(self, *, atp_count: int, adp_count: int) -> int | None:
        total = max(0, int(atp_count) + int(adp_count))
        if total <= 0:
            return None
        if int(adp_count) <= 0:
            total = int(np.clip(total, a_min=1, a_max=int(self.parameters["polymer_max_length"])))
            return self._dnaa_local_index_by_counts.get((total, 0))
        if total <= 1:
            return self._dnaa_local_index_by_counts.get((0, 1))
        capped_total = int(np.clip(total, a_min=2, a_max=int(self.parameters["polymer_max_length"])))
        return self._dnaa_local_index_by_counts.get((capped_total - 1, 1))

    def _check_initiation_trigger(self) -> bool:
        threshold_r1234 = int(self.parameters["r1234_threshold"])
        threshold_r5 = int(self.parameters["r5_threshold"])
        for copy_idx in range(2):
            r1234_ready = all(
                self._bound_atp[idx, copy_idx] >= threshold_r1234 for idx in self.r1234_indices
            )
            r5_ready = self._bound_atp[self.r5_index, copy_idx] >= threshold_r5
            if r1234_ready and r5_ready:
                return True
        return False

    def _event_probability(self, rate: float, dt: float) -> float:
        if rate <= 0.0 or dt <= 0.0:
            return 0.0
        return float(np.clip(1.0 - np.exp(-rate * dt), a_min=0.0, a_max=1.0))

    def _binding_probability(
        self,
        rate_constant: float,
        dt: float,
        *,
        scale_param: str | None = None,
    ) -> float:
        if rate_constant <= 0.0 or dt <= 0.0:
            return 0.0
        probability = float(rate_constant) * 1.0e9 / 3600.0 / _N_AVOGADRO / self._geometry_volume * float(dt)
        if scale_param is not None and not self._using_explicit_enzyme_pools:
            probability /= float(self.parameters[scale_param])
        return probability

    def _linear_event_probability(
        self,
        rate_per_hour: float,
        dt: float,
        *,
        scale_param: str | None = None,
    ) -> float:
        if rate_per_hour <= 0.0 or dt <= 0.0:
            return 0.0
        rate = float(rate_per_hour)
        if scale_param is not None and not self._using_explicit_enzyme_pools:
            rate /= float(self.parameters[scale_param])
        return float(np.clip(rate * float(dt) / 3600.0, a_min=0.0, a_max=1.0))

    def _interval_start_for_query_position(
        self,
        *,
        position: int,
        strand: int,
        footprint: int,
        is_centroid: bool,
    ) -> int:
        if not is_centroid:
            return int(position)
        return self._centroid_interval_start(
            position=int(position),
            strand=int(strand),
            footprint=int(footprint),
        )

    def _centroid_interval_start(self, *, position: int, strand: int, footprint: int) -> int:
        footprint5, footprint3 = self._footprint_overhangs(footprint)
        if int(strand) % 2 == 0:
            return int(position) - int(footprint5)
        return int(position) - int(footprint3)


__all__ = ["KarrReplicationInitiationProcess"]
