"""Octave-based functional regression tests for
`scripts/matlab/mnrnd.m` (legacy-mnrnd compatibility shim -- Canary D
tick-25361 fix).

This file NEVER runs `extract_per_process_traces_v2.m`, `karr_bootstrap`,
or any simulation/bootstrap/extraction code -- it only exercises
`scripts/matlab/mnrnd.m` in isolation, which has zero Karr/simulation
dependencies of its own (it is a standalone RNG compatibility shim, see
that file's own docstring). All tests here are skipped cleanly (never
fail) when Octave is unavailable on PATH, matching
`test_extract_per_process_traces_v2_static.py`'s
`test_real_parse_only_probe_via_octave` skip convention -- this project's
canonical execution environment is WSL, where Octave is installed.

`mnrnd.m` deliberately avoids `histcounts`/`histc` (see its docstring):
`histcounts` does not exist in Octave (verified -- not part of Octave
core or the Octave-Forge `statistics` package), so this shim's bin-
counting loop uses only `rand`/`cumsum`/`sum`/comparison, which IS
identical between MATLAB and Octave -- meaning this Octave-based test
suite is a genuine functional regression test of the exact code that will
run under real MATLAB too, not merely a parse-only probe.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MNRND_PATH = REPO_ROOT / "scripts" / "matlab" / "mnrnd.m"

# The single Octave script every test below runs (once per test, via a
# `--eval` prelude selecting which check to run) -- kept as one shared
# probe body so every check exercises the exact same `addpath` bootstrap
# and error-classification helper, rather than duplicating that
# boilerplate per test.
_PRELUDE = "addpath('{matlab_dir}');\n".format(matlab_dir=(REPO_ROOT / "scripts" / "matlab").as_posix())


def _octave_executable() -> str | None:
    for name in ("octave-cli", "octave"):
        path = shutil.which(name)
        if path:
            return path
    return None


pytestmark = pytest.mark.skipif(
    _octave_executable() is None,
    reason="octave-cli not available on PATH; mnrnd shim functional regression skipped",
)


def _run_octave(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    """Write `_PRELUDE + body` to a scratch .m script and run it with
    Octave, returning the completed process (never raises on nonzero
    exit -- callers assert on `.returncode`/`.stdout`/`.stderr`
    themselves, matching `test_real_parse_only_probe_via_octave`'s style).
    """
    octave = _octave_executable()
    assert octave is not None  # narrowed by module-level skipif
    script_path = tmp_path / "probe.m"
    script_path.write_text(_PRELUDE + body, encoding="utf-8")
    return subprocess.run(
        [octave, "--no-gui", str(script_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_mnrnd_file_exists():
    assert MNRND_PATH.is_file(), f"missing {MNRND_PATH}"


def test_duplicate_edge_zero_probability_categories_no_longer_crash(tmp_path):
    """Canary D root-cause reproduction: a sparse probability vector with
    zero-probability categories (p = [0.5 0 0.3 0 0.2]) used to build
    edges = [0 0.5 0.5 0.8 0.8 1] -- duplicate, non-strictly-increasing
    values -- which is exactly the class of defect that crashed
    ProteinProcessingII.m:394 at tick 25361. The fixed shim must draw
    successfully, keep zero-probability categories at count 0, and the
    resulting counts must sum to exactly n."""
    result = _run_octave(
        tmp_path,
        """
p = [0.5 0 0.3 0 0.2];
counts = mnrnd(1000, p);
assert(isequal(size(counts), size(p)));
assert(counts(2) == 0);
assert(counts(4) == 0);
assert(sum(counts) == 1000);
disp('OK_DUPLICATE_EDGE');
""",
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "OK_DUPLICATE_EDGE" in result.stdout


def test_row_and_column_p_are_equivalent_under_identical_rng_state(tmp_path):
    """Orientation must never affect the draw: p(:)' normalizes a column
    to a row with identical values/order, so an identical RNG state must
    produce byte-identical counts regardless of whether p was supplied as
    a row or a column -- and the output must always be a row (Karr's own
    call sites apply their own trailing transpose)."""
    result = _run_octave(
        tmp_path,
        """
rand('state', 42);
c_row = mnrnd(500, [0.2 0.3 0.5]);
rand('state', 42);
c_col = mnrnd(500, [0.2; 0.3; 0.5]);
assert(isequal(c_row, c_col));
assert(isequal(size(c_row), [1 3]));
disp('OK_ROW_COLUMN_EQUIVALENT');
""",
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "OK_ROW_COLUMN_EQUIVALENT" in result.stdout


def test_deterministic_given_identical_rng_state(tmp_path):
    """Same pre-call RNG state must produce the same draw -- no hidden
    reseed or extra randomness source inside the shim."""
    result = _run_octave(
        tmp_path,
        """
rand('state', 7);
a = mnrnd(200, [0.1 0.2 0.7]);
rand('state', 7);
b = mnrnd(200, [0.1 0.2 0.7]);
assert(isequal(a, b));
disp('OK_DETERMINISTIC');
""",
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "OK_DETERMINISTIC" in result.stdout


def test_consumes_exactly_n_uniforms_from_active_stream(tmp_path):
    """Post-call RNG state must match a direct `rand(n, 1)` call with the
    same pre-call state exactly -- the shim must draw exactly n uniforms,
    no more, no fewer, and never reseed/reset the stream itself."""
    result = _run_octave(
        tmp_path,
        """
rand('state', 11);
mnrnd(300, [0.3 0.7]);
after_mnrnd = rand();
rand('state', 11);
rand(300, 1);
after_direct = rand();
assert(after_mnrnd == after_direct);
disp('OK_RNG_CONSUMPTION');
""",
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "OK_RNG_CONSUMPTION" in result.stdout


def test_n_zero_returns_correctly_shaped_zeros_without_drawing_even_for_zero_sum_p(tmp_path):
    """n == 0 is a degenerate-but-harmless 'zero draws requested' case:
    it must return correctly-shaped all-zero counts WITHOUT erroring, even
    when sum(p) == 0 (which would otherwise be a fail-closed error for any
    n > 0)."""
    result = _run_octave(
        tmp_path,
        """
z = mnrnd(0, [0 0 0]);
assert(isequal(z, [0 0 0]));
disp('OK_N_ZERO');
""",
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "OK_N_ZERO" in result.stdout


@pytest.mark.parametrize(
    ("label", "call", "expected_error_id_prefix"),
    [
        ("matrix_p", "mnrnd(10, [0.5 0.5; 0.5 0.5])", "mnrnd:InvalidP"),
        ("empty_p", "mnrnd(10, [])", "mnrnd:InvalidP"),
        ("nan_p", "mnrnd(10, [0.5 NaN 0.5])", "mnrnd:NonFiniteP"),
        ("inf_p", "mnrnd(10, [0.5 Inf 0.5])", "mnrnd:NonFiniteP"),
        ("negative_p", "mnrnd(10, [0.5 -0.1 0.6])", "mnrnd:NegativeP"),
        ("zero_sum_p_with_positive_n", "mnrnd(10, [0 0 0])", "mnrnd:ZeroProbabilityMass"),
        ("nan_n", "mnrnd(NaN, [0.5 0.5])", "mnrnd:InvalidN"),
        ("negative_n", "mnrnd(-5, [0.5 0.5])", "mnrnd:InvalidN"),
        ("non_integer_n", "mnrnd(2.5, [0.5 0.5])", "mnrnd:InvalidN"),
        ("non_scalar_n", "mnrnd([1 2], [0.5 0.5])", "mnrnd:UnsupportedN"),
        ("too_few_inputs", "mnrnd(10)", "mnrnd:NotEnoughInputs"),
    ],
)
def test_fails_closed_never_silently_clamps(tmp_path, label, call, expected_error_id_prefix):
    """Every unsupported/invalid input FAILS CLOSED (errors with a
    specific, checkable error identifier) -- it is never silently
    clamped, coerced, or reinterpreted into a plausible-looking (but
    fabricated) answer."""
    result = _run_octave(
        tmp_path,
        f"""
try
    {call};
    disp('UNEXPECTED_SUCCESS');
catch err
    printf('CAUGHT:%s\\n', err.identifier);
end
""",
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "UNEXPECTED_SUCCESS" not in result.stdout, f"{label} did not fail closed"
    assert f"CAUGHT:{expected_error_id_prefix}" in result.stdout, (
        f"{label}: expected error id prefix {expected_error_id_prefix!r}, got stdout: {result.stdout!r}"
    )
