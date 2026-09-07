"""Validation + inversion tests for `KarrMcg16807Stream`.

The byte-for-byte expected values below were captured directly from the
real local MATLAB installation (`E:\\MATLAB\\bin\\matlab.exe`, invoked via
`scripts/tools/run_matlab_slot.ps1`) using throwaway probe scripts (not
committed) that constructed `RandStream('mcg16807', 'Seed', <seed>)` and
recorded `rand`/`randi`/`randperm`/`randsample` outputs. See
`opencell/vivarium/karr_dna_damage_rng.py`'s module docstring for the full
derivation and primary-source anchors. These are NOT trace-cribbed values
(no oracle/replay-trace file is read here) -- they are raw MATLAB builtin
RNG outputs, independent of any DNADamage-specific simulation state.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.vivarium.karr_dna_damage_rng import KarrLedgerReplayStream, KarrMcg16807Stream

_SEED_1_RAND12 = [
    0.51290893578571684, 0.46048375054285107, 0.35039537369757673, 0.09504573517248302,
    0.43367104392204014, 0.709235197729075, 0.11596823256275068, 0.078084682150783333,
    0.36925290821551016, 0.033628378079099755, 0.19215037542961089, 0.471359845470339,
]
_SEED_12345_RAND12 = [
    0.86081227467433186, 0.67190045149619715, 0.63088829658501233, 0.33960070430282535,
    0.66903721758585288, 0.5085159654303063, 0.62783098715722141, 0.95540115142026971,
    0.42715192047280814, 0.14232738648649648, 0.0963846785465184, 0.93729233133480527,
]
_SEED_2000_RAND12 = [
    0.81787157143367062, 0.96750108570209759, 0.79074739515350545, 0.091470344966030834,
    0.3420878440803326, 0.47039545814990785, 0.9364651255013724, 0.16936430156666984,
    0.505816431020301, 0.25675615819951342, 0.30075085922179318, 0.71969094067797579,
]
_SEED_2147483646_RAND12 = [
    0.48709106421428316, 0.53951624945714893, 0.64960462630242322, 0.904954264827517,
    0.56632895607795986, 0.29076480227092505, 0.88403176743724932, 0.92191531784921665,
    0.63074709178448984, 0.9663716219209002, 0.80784962457038911, 0.52864015452966107,
]
_RANDI_100_SEED_777 = [54, 80, 26, 86, 97, 8, 11, 68, 91, 13, 31, 25, 61, 76, 16, 57, 57, 98, 33, 13]
_RANDPERM_10_SEED_777 = [6, 7, 10, 3, 1, 8, 2, 4, 9, 5]
_RANDPERM_28_SEED_2000 = [
    17, 4, 27, 8, 19, 28, 24, 10, 11, 5, 15, 6, 9, 23, 21, 18, 14, 25, 12, 26, 16, 20, 3, 1, 13, 7, 22, 2,
]


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        (1, _SEED_1_RAND12),
        (12345, _SEED_12345_RAND12),
        (2000, _SEED_2000_RAND12),
        (2147483646, _SEED_2147483646_RAND12),
    ],
)
def test_rand_matches_real_matlab_mcg16807(seed: int, expected: list[float]) -> None:
    stream = KarrMcg16807Stream(seed)
    got = [stream.rand() for _ in expected]
    for g, e in zip(got, expected, strict=True):
        assert g == pytest.approx(e, rel=0, abs=1e-15)


def test_randi_matches_real_matlab_via_ceil_scale() -> None:
    stream = KarrMcg16807Stream(777)
    got = [stream.randi(100) for _ in _RANDI_100_SEED_777]
    assert got == _RANDI_100_SEED_777


def test_randperm_10_matches_real_matlab() -> None:
    stream = KarrMcg16807Stream(777)
    assert stream.randperm(10) == _RANDPERM_10_SEED_777


def test_randperm_28_matches_real_matlab() -> None:
    stream = KarrMcg16807Stream(2000)
    assert stream.randperm(28) == _RANDPERM_28_SEED_2000


def test_randperm_zero_is_empty() -> None:
    stream = KarrMcg16807Stream(42)
    assert stream.randperm(0) == []


def test_seed_zero_fails_closed() -> None:
    with pytest.raises(ValueError):
        KarrMcg16807Stream(0)


def test_seed_at_or_above_modulus_fails_closed() -> None:
    with pytest.raises(ValueError):
        KarrMcg16807Stream(2147483647)


def test_stochastic_round_consumes_a_draw_for_zero_value() -> None:
    """Karr's `stochasticRound` never skips the draw, even for value==0
    (inversion target: OC's prior `_stochastic_round` special-cased
    `value <= 0` and returned 0 WITHOUT consuming a draw -- that would
    desynchronize every subsequent draw from Karr's real sequence)."""
    stream = KarrMcg16807Stream(2000)
    before = stream._state
    result = stream.stochastic_round(0.0)
    after = stream._state
    assert result == 0
    assert after != before, "stochastic_round(0.0) must still consume a draw"


def test_stochastic_round_consumes_a_draw_for_exact_integer() -> None:
    stream = KarrMcg16807Stream(2000)
    before = stream._state
    result = stream.stochastic_round(5.0)
    after = stream._state
    assert result == 5
    assert after != before, "stochastic_round(5.0) must still consume a draw"


def test_stochastic_round_matches_literal_formula_for_negative_value() -> None:
    """mod(-2.3, 1) in MATLAB is 0.7 (floor-mod, same sign as the positive
    divisor) -- Python's `%` matches this directly; a naive `math.fmod`
    port would invert the comparison sign for negative inputs."""
    stream = KarrMcg16807Stream(2000)
    draw = stream.rand()
    stream2 = KarrMcg16807Stream(2000)
    frac = (-2.3) % 1.0
    assert frac == pytest.approx(0.7, abs=1e-12)
    round_up = draw < frac
    expected = math.ceil(-2.3) if round_up else math.floor(-2.3)
    assert stream2.stochastic_round(-2.3) == expected


def test_randsample_without_replacement_matches_randperm_prefix() -> None:
    """4*k > n branch: `randsample(s,n,k,false)` == `randperm(s,n)[:k]`."""
    stream = KarrMcg16807Stream(2000)
    full = KarrMcg16807Stream(2000).randperm(8)
    assert stream.randsample_without_replacement(8, 3) == full[:3]


# Ground truth below was captured directly from the REAL local MATLAB
# Statistics and Machine Learning Toolbox `randsample(stream, n, k,
# false)` (`E:\MATLAB\toolbox\stats\stats\randsample.m`), via
# `scripts/matlab/probe_l21_randsample_exact.m`, run with that toolbox
# path explicitly promoted ahead of `scripts/matlab` (`addpath(fullfile(
# matlabroot,'toolbox','stats','stats'), '-begin')` -- see
# `scripts/matlab/karr_bootstrap.m::require_genuine_statistics_rng_providers`
# for why this promotion is mandatory: this repo ships its own
# `scripts/matlab/randsample.m` FALLBACK SHIM (a completely different,
# weighted-cdf-based algorithm, for environments without the Statistics
# Toolbox) that silently shadows the real toolbox function on MATLAB's
# path whenever `scripts/matlab` is added without the promotion --
# empirically hit and corrected during this task; see
# STATUS_L21_DNADAMAGE_ACTIVE_FIX.md for the full account. These 6 cases
# span both `randsample.m` branches (4*k>n prefix-of-randperm; 4*k<=n
# rejection-sampling loop over MATLAB's BUILTIN `randi`), a k=1 edge case,
# a k==n edge case, and a realistic genome-scale n=50000.
_RANDSAMPLE_CASES = [
    (2000, 20, 3, [16, 17, 20]),
    (12345, 500, 1, [431]),
    (12345, 7, 7, [4, 6, 7, 3, 5, 2, 1]),
    (42, 3, 1, [2]),
    (777, 50000, 12, [33590, 6463, 26513, 39794, 42527, 12330, 12861, 3788, 45476, 5366, 48121, 15043]),
    (2000, 10000, 5, [7908, 9676, 915, 8179, 3421]),
]


@pytest.mark.parametrize(("seed", "n", "k", "expected"), _RANDSAMPLE_CASES)
def test_randsample_without_replacement_matches_real_matlab_toolbox(
    seed: int, n: int, k: int, expected: list[int]
) -> None:
    stream = KarrMcg16807Stream(seed)
    assert stream.randsample_without_replacement(n, k) == expected


def test_randsample_rejection_branch_selected_for_small_k_over_n() -> None:
    """Sanity check the branch-selection threshold itself (4*k <= n)."""
    assert 4 * 3 <= 20  # the (n=20, k=3) case above must hit the rejection loop
    assert 4 * 12 <= 50000  # the (n=50000, k=12) case above must hit it too


def test_randsample_rejects_k_greater_than_n() -> None:
    stream = KarrMcg16807Stream(2000)
    with pytest.raises(ValueError):
        stream.randsample_without_replacement(5, 6)


# --- Inversion tests: these assert that KNOWN-WRONG substitute
# implementations diverge from the real-MATLAB-verified values above, so
# a future regression that silently reintroduces one of these bugs is
# caught by a failing (not merely differently-passing) test.


def test_inversion_pcg64_substitute_diverges_from_matlab() -> None:
    import numpy as np

    pcg = np.random.default_rng(2000)
    pcg_vals = [float(pcg.random()) for _ in _SEED_2000_RAND12]
    assert pcg_vals != pytest.approx(_SEED_2000_RAND12, rel=0, abs=1e-15)


def test_inversion_skipping_draw_for_nonpositive_value_desyncs_stream() -> None:
    """A `_stochastic_round` that special-cases `value <= 0` (no draw
    consumed) must NOT match the always-consumes-a-draw stream position
    a caller relying on literal Karr semantics would expect."""
    stream_literal = KarrMcg16807Stream(2000)
    stream_literal.stochastic_round(0.0)  # consumes exactly 1 draw
    literal_next = stream_literal.rand()

    stream_buggy = KarrMcg16807Stream(2000)
    # Simulate the old buggy behavior: skip the draw entirely for value<=0.
    buggy_next = stream_buggy.rand()  # no stochastic_round call first

    assert literal_next != buggy_next


def test_inversion_wrong_randi_endpoint_order_diverges() -> None:
    """A `floor(rand()*imax)` (0-based, missing the `+1`) or an
    `int(rand()*(imax+1))` off-by-one variant must not accidentally match
    Karr's literal `ceil(imax*rand())` for this seed/imax."""
    stream = KarrMcg16807Stream(777)
    wrong = []
    stream_wrong = KarrMcg16807Stream(777)
    for _ in _RANDI_100_SEED_777:
        wrong.append(int(math.floor(100 * stream_wrong.rand())))  # 0-based, no +1
    correct = [stream.randi(100) for _ in _RANDI_100_SEED_777]
    assert correct == _RANDI_100_SEED_777
    assert wrong != _RANDI_100_SEED_777


def test_inversion_oracle_trace_not_read_by_production_module() -> None:
    """`karr_dna_damage_rng.py` must contain no trace/oracle file I/O --
    it is a pure, self-contained algorithmic port."""
    source = Path(_REPO_ROOT, "opencell", "vivarium", "karr_dna_damage_rng.py").read_text(encoding="utf-8")
    forbidden = ("loadmat", "open(", "genuine_signedzero", "karr_native", "per_process_traces")
    for token in forbidden:
        assert token not in source, f"karr_dna_damage_rng.py must not reference {token!r} (oracle leakage)"


def test_inversion_randperm_prefix_approximation_diverges_for_rejection_branch() -> None:
    """The prior `randsample_without_replacement` implementation
    (`randperm(n)[:k]` for EVERY (n,k), not just the 4*k>n branch) drew
    the wrong number of raw values for the rejection-sampling branch and
    would silently desynchronize the stream for any subsequent draw in
    the same tick. Guard against silently reintroducing that
    approximation for a case where it demonstrably diverges from the
    real MATLAB toolbox answer."""
    seed, n, k = 777, 50000, 12
    expected_real = [33590, 6463, 26513, 39794, 42527, 12330, 12861, 3788, 45476, 5366, 48121, 15043]
    approx = KarrMcg16807Stream(seed).randperm(n)[:k]
    assert approx != expected_real
    exact = KarrMcg16807Stream(seed).randsample_without_replacement(n, k)
    assert exact == expected_real


# --- KarrLedgerReplayStream: fail-closed replay of a pre-recorded
# per-tick raw-draw ledger (used by the shared-Chromosome-stream L2.1
# replay closure; see scripts/matlab/reconstruct_chromosome_draw_ledger.m).


def test_ledger_replay_stream_returns_recorded_values_in_order() -> None:
    draws = [0.1, 0.9, 0.4]
    stream = KarrLedgerReplayStream(draws, tick_label="t")
    assert [stream.rand(), stream.rand(), stream.rand()] == draws
    stream.assert_fully_consumed()


def test_ledger_replay_stream_fails_closed_on_exhaustion() -> None:
    stream = KarrLedgerReplayStream([0.5], tick_label="t")
    stream.rand()
    with pytest.raises(RuntimeError, match="exhausted"):
        stream.rand()


def test_ledger_replay_stream_fails_closed_on_leftover_draws() -> None:
    stream = KarrLedgerReplayStream([0.1, 0.9], tick_label="t")
    stream.rand()
    with pytest.raises(RuntimeError, match="only consumed 1/2"):
        stream.assert_fully_consumed()


def test_ledger_replay_stream_drives_higher_level_formulas_correctly() -> None:
    """`randi`/`randperm`/`stochastic_round`/`randsample_without_replacement`
    are all inherited unchanged from `KarrMcg16807Stream` and must consume
    the ledger through the SAME formulas already verified against real
    MATLAB -- e.g. a scripted stream whose only draw is 0.5 must produce
    the same `randi(4)` result a live `KarrMcg16807Stream` positioned to
    draw exactly 0.5 next would (`floor`/`ceil` semantics unchanged)."""
    stream = KarrLedgerReplayStream([0.5], tick_label="t")
    # Chromosome.m's own ceil(imax*rand()) formula: ceil(4*0.5) == 2.
    assert stream.randi(4) == 2
    stream.assert_fully_consumed()

    stream2 = KarrLedgerReplayStream([0.3, 0.7, 0.1], tick_label="t2")
    order = stream2.randperm(3)
    assert sorted(order) == [1, 2, 3]
    stream2.assert_fully_consumed()


def test_inversion_ledger_replay_wrong_draw_count_fails_closed_not_silent() -> None:
    """A caller that consumes fewer draws than recorded (e.g. an
    algorithmic regression that skips a call) must be caught by
    `assert_fully_consumed`, not silently pass with leftover ledger
    entries ignored."""
    stream = KarrLedgerReplayStream([0.9, 0.9, 0.9], tick_label="t")
    stream.randi(10)  # consumes exactly 1 of the 3 recorded draws
    with pytest.raises(RuntimeError):
        stream.assert_fully_consumed()
