# MATLAB RNG Shim Notes

## Scope
This note documents the `MatlabRandStream` shim in `opencell/util/matlab_rng.py` and its golden tests in `tests/util/test_matlab_rng.py`.

## Key Compatibility Decisions
- Generator: `mt19937ar` only.
- Seed behavior: MATLAB seed `0` maps to MT init seed `5489` (matches published MATLAB seed-0 startup stream behavior).
- `rand`: shared MT stream with MATLAB-compatible 53-bit float conversion.
- `randn`: MATLAB-style Ziggurat implementation ported from an open C++ reference implementation (`py_matlab_randn`) and validated against published MATLAB seed-22 values.
- `randi`: implemented as `floor(imax * rand) + 1` on the same stream.
- `randperm`: implemented via sorting stream uniforms, which matches published startup sequences (`[6 3 7 8 5 1 2 4 9 10]` and subsequent calls).
- State serialization: full MT state (`625` uint32 words) round-trips via `get_state`/`set_state`.

## Sources
- https://www.mathworks.com/help/matlab/ref/rng.html
- https://www.mathworks.com/help/matlab/ref/randstream.html
- https://walkingrandomly.com/?p=5479
- https://walkingrandomly.com/?p=5480
- https://github.com/jonasrauber/randn-matlab-python
- https://github.com/KrepakVitaly/py_matlab_randn
- https://blogs.mathworks.com/matlab/2022/06/07/6-3-7-8-5-1-2-4-9-10-or-a-story-of-surprise-about-randomness/
- https://groups.google.com/g/comp.soft-sys.matlab/c/FojUKhI8om4

## Known Gaps
- Some vectors are still tagged in tests as TODO-primary-source where only secondary sources are available (`randn(seed=0)` and `randperm(100,5)`).
- randperm enzyme-loop ports landed in `karr_dna_supercoiling` for MATLAB `DNASupercoiling.m` line-391 and line-470 replay alignment.
