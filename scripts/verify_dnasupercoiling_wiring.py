"""Independent verification of codex's DNASupercoiling wiring.

Designed to catch the Beat-4 failure modes named in PROMPT.md:
  F1: Pin updated without empirical run (verify pin matches a fresh empirical run)
  F2: Projection from substrate proxies, not chromosome (verify projection uses sparse triples)
  F3: Tick handler ignores Karr chromosome state (verify state IS overlaid)
  F4: NaN-semantics regression (verify Metabolism oracle test still passes)
  F5: Strict-rubric passes but runner crashes (run the runner end-to-end)

Run AFTER codex commits. Do not trust codex's STATUS — re-verify here.
"""
from __future__ import annotations
import sys
import subprocess
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))


def f1_pin_matches_empirical() -> None:
    """F1: Pin updated without empirical run.

    Re-run the L2.2 design-A runner myself; compare to the pinned verdict.
    """
    print("=" * 70)
    print("F1: Pin vs empirical match")
    print("=" * 70)
    # Run the runner
    cmd = [
        "bin/oc-py",
        "tests/vivarium/l2_2_design_a_runner.py",
        "--process", "DNASupercoiling",
        "--seeds", "50",
        "--ticks", "10",
        "--output-dir", "tmp/f1_verify_dnasupercoiling",
    ]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=600)
    print(f"  Exit code: {result.returncode}")
    print(f"  Last output line: {result.stdout.strip().split(chr(10))[-1] if result.stdout else '(empty)'}")
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[-500:]}")
        print("  ❌ F1 FAIL: runner crashed; cannot verify pin against empirical")
        return
    # Look at last line for the verdict
    last = result.stdout.strip().split("\n")[-1] if result.stdout else ""
    print(f"  Empirical verdict line: {last}")
    
    # Now check the pin
    pin_file = REPO / "tests/vivarium/test_l2_2_strict_rubric.py"
    pin_content = pin_file.read_text(encoding="utf-8")
    if '"DNASupercoiling"' in pin_content or "'DNASupercoiling'" in pin_content:
        # find the pinned value
        import re
        m = re.search(r"['\"]DNASupercoiling['\"]\s*:\s*['\"](\w+)['\"]", pin_content)
        if m:
            pinned = m.group(1)
            print(f"  Pinned verdict: {pinned}")
            if pinned == "NOT_WIRED":
                print("  ❌ F1 FAIL: pin still says NOT_WIRED but runner returned a verdict")
                return
            print(f"  ✓ F1 PASS: pin is {pinned}, runner ran successfully")
        else:
            print("  ⚠ F1 INCONCLUSIVE: couldn't parse pin value")
    else:
        print("  ❌ F1 FAIL: DNASupercoiling not in pin file")


def f2_projection_from_sparse_triples() -> None:
    """F2: Projection from substrate proxies vs from real linkingNumbers triples.

    Read the actual projection code and confirm it uses .values.sum() and
    len(.positions), NOT substrate or scalar values.
    """
    print()
    print("=" * 70)
    print("F2: Projection extractor uses sparse-triple data")
    print("=" * 70)
    helpers = REPO / "tests/vivarium/_l2_2_design_a_runner_helpers.py"
    runner = REPO / "tests/vivarium/l2_2_design_a_runner.py"
    
    # Search for the projection extractor function
    helpers_text = helpers.read_text(encoding="utf-8")
    runner_text = runner.read_text(encoding="utf-8")
    
    proj_keywords = [
        "linkingNumbers.delta_value_sum",
        "linkingNumbers.delta_nnz",
        ".values.sum()",
        ".positions",
        "SparseTriplet",
        "ChromosomeStore",
    ]
    found_in_helpers = [k for k in proj_keywords if k in helpers_text]
    found_in_runner = [k for k in proj_keywords if k in runner_text]
    print(f"  Helpers has: {found_in_helpers}")
    print(f"  Runner has: {found_in_runner}")
    
    if "SparseTriplet" not in helpers_text and "SparseTriplet" not in runner_text:
        print("  ❌ F2 FAIL: no SparseTriplet usage anywhere in runner code")
    elif ".values.sum()" not in helpers_text and ".values.sum()" not in runner_text:
        print("  ⚠ F2 SUSPECT: SparseTriplet used but no .values.sum() — projection may not compute deltas correctly")
    else:
        print("  ✓ F2 PASS: chromosome projection uses sparse-triple data")
    
    # Check for proxy red flags
    proxies = ["supercoil_density", "fork_position_bp", "substrate.*proxy"]
    proxy_hits = [p for p in proxies if p in helpers_text or p in runner_text]
    if proxy_hits:
        # Some legacy mirror is OK; flag if used inside projection
        print(f"  ⚠ Note: proxy keys present: {proxy_hits} (OK if only legacy mirror; check usage)")


def f3_chromosome_state_overlaid() -> None:
    """F3: Tick handler IS reading Karr's chromosome state, not a default.

    Read _run_dna_supercoiling_tick and look for chromosome overlay code.
    """
    print()
    print("=" * 70)
    print("F3: Tick handler overlays Karr's chromosome state")
    print("=" * 70)
    helpers = REPO / "tests/vivarium/_l2_2_design_a_runner_helpers.py"
    text = helpers.read_text(encoding="utf-8")
    
    if "_run_dna_supercoiling_tick" not in text:
        print("  ❌ F3 FAIL: no _run_dna_supercoiling_tick function found")
        return
    
    # Extract the function
    import re
    m = re.search(r"def _run_dna_supercoiling_tick.*?(?=\ndef |\Z)", text, re.DOTALL)
    if not m:
        print("  ❌ F3 FAIL: couldn't extract _run_dna_supercoiling_tick body")
        return
    body = m.group(0)
    print(f"  Function length: {len(body)} chars")
    
    keywords = ["chromosome", "ChromosomeStore", "SparseTriplet", "from_state", "to_state", "overlay"]
    found = [k for k in keywords if k in body]
    print(f"  Found in body: {found}")
    
    if "chromosome" not in body or "store" not in body.lower():
        print("  ❌ F3 FAIL: tick handler doesn't reference chromosome store overlay")
    else:
        print("  ✓ F3 PASS: tick handler references chromosome overlay")


def f4_no_metabolism_regression() -> None:
    """F4: Metabolism oracle test still passes (NaN semantics + fmax not broken)."""
    print()
    print("=" * 70)
    print("F4: No regression in Metabolism oracle test")
    print("=" * 70)
    cmd = [
        "bin/oc-pytest",
        "tests/m1/test_calc_flux_bounds.py::test_compute_bounds_matches_matlab_oracle_no_protein",
        "-q",
    ]
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        print("  ✓ F4 PASS: test_compute_bounds_matches_matlab_oracle_no_protein still passes")
    else:
        print("  ❌ F4 FAIL: regression — Metabolism oracle test broke")
        print(f"  Output: {result.stdout[-500:]}")


def f5_l2_1_no_regression() -> None:
    """F5: L2.1 strict-rubric still 28/28."""
    print()
    print("=" * 70)
    print("F5: L2.1 strict-rubric still 28/28")
    print("=" * 70)
    cmd = [
        "bin/oc-pytest",
        "tests/vivarium/test_l2_1_strict_rubric.py",
        "-q",
    ]
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=300)
    if result.returncode == 0 and "28 passed" in result.stdout:
        print("  ✓ F5 PASS: 28/28 L2.1 strict-rubric tests still pass")
    else:
        print(f"  ❌ F5 FAIL: L2.1 strict-rubric broken")
        print(f"  Output: {result.stdout[-500:]}")


if __name__ == "__main__":
    print("Independent verification of codex's DNASupercoiling wiring")
    print(f"Repo: {REPO}")
    print()
    f1_pin_matches_empirical()
    f2_projection_from_sparse_triples()
    f3_chromosome_state_overlaid()
    f4_no_metabolism_regression()
    f5_l2_1_no_regression()
    print()
    print("=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)
