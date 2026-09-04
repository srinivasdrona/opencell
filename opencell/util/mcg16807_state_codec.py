"""Neutral, process-local codec for MATLAB ``RandStream('mcg16807').State``.

Root-cause background (task: L2.1 Cytokinesis exact replay, M5000 seed-36
promotion): the M5000 seed-36 randStream ledger failed at tick=894 because
Karr's real captured ``randStreamState`` entry/exit values (36 ->
1363919953) could not be reached under the *assumed* raw scalar Lehmer
recurrence (``state = 16807*state mod (2**31-1)``) within any reasonable
step count. The raw HDF5 payload itself is genuinely a 1x1 scalar double at
every tick (verified directly against the seed-36 M5000 trace at
ticks 0/893/894/895 -- never a >1-element vector at any tick, so the
extractor's ``double(mod.randStream.state(:))`` capture is NOT the bug).
The actual root cause is representational: live MATLAB's ``RandStream
('mcg16807').State`` getter/setter does NOT expose the raw Lehmer
recurrence value directly -- it exposes a *value-domain* transform of it (a
16-bit half-word swap, conditionally XORed with ``0x80008000`` whenever the
pre-swap low half-word's sign bit is set), independently re-derived here
from a live MATLAB probe rather than merely reused from
``opencell/util/chromcond_mcg_rand.py`` (that module is ChromosomeCondensation-
only by explicit design -- see its own docstring -- so this Cytokinesis-local
codec re-derives and independently re-verifies the same transform against
this task's own seed/trace rather than importing across that process
boundary).

Live-MATLAB verification performed for this task (2026-09-05, this
worktree, ``E:\\MATLAB\\bin\\matlab.exe`` via ``scripts/tools/
run_matlab_slot.ps1``, R2026a-class MATLAB statistics toolbox
``RandStream``):

- ``RandStream('mcg16807','Seed',uint32(36))``: ``class(State)=='double'``,
  ``size(State)==[1 1]`` (confirms the state is genuinely scalar, refuting
  the "reduced from a vector" hypothesis), ``State==36`` immediately after
  construction (the seed is stored as the State's raw bit-pattern
  verbatim -- no encode transform is applied AT SEED TIME, only on
  subsequent draws).
- 60 consecutive ``rand(rs)`` draws were captured (value + resulting
  ``State`` after each draw). Applying ``decode_state`` to the running
  state before each step of the raw ``16807*x mod (2**31-1)`` recurrence,
  then ``encode_state`` on the result, reproduces ALL 60 real MATLAB
  ``State`` values and ALL 60 real MATLAB ``rand()`` output values exactly
  (0 mismatches; see ``tmp/validate_full_sequence.py`` and
  ``tmp/probe_mcg16807_state_live2.m`` in this worktree for the full
  transcript). In particular, draw 49 lands on ``State==1363919953`` --
  exactly Karr's own recorded tick=894 ``randStreamState`` exit value for
  the M5000 seed-36 trace -- and draw 57 (8 further steps) lands on
  ``State==62833153``, exactly Karr's own recorded tick=895 exit value.
- Re-seeding directly with ``RandStream('mcg16807','Seed',
  uint32(1363919953))`` immediately reports ``State==1363919953`` (the raw
  seed value passed through verbatim, matching the "no encode at seed
  time" rule above) and its first draw exactly reproduces the continuing
  stream's draw 50 -- i.e. a captured ``State`` value can be losslessly
  used as a fresh seed to resume the stream, which is exactly the
  save/restore contract this ledger needs.
- Edge cases (``seed=0`` -> ``State==931316785``; ``seed=1`` ->
  ``State==1``) were also independently live-verified and match the
  literature default-state / passthrough constants already used
  elsewhere in this codebase (``chromcond_mcg_rand.py``'s
  ``_MCG_DEFAULT_STATE``) -- reproduced here as ``DEFAULT_STATE_FOR_ZERO_SEED``
  without importing that ChromCond-scoped module.

``parse_captured_state`` intentionally fails loudly (never silently
truncates/coerces) on every anomaly the task asked this codec to guard
against: more than one captured element ("first-word-only" truncation
risk -- MATLAB's real payload is always exactly 1 element for mcg16807,
so >1 elements means either a different generator or a corrupted/legacy
capture, never a value to arbitrarily index into), non-finite values,
non-integer-valued floats, and out-of-range values. There is no separate
"word order" or "dtype/endian" byte-level transform to invert here --
``decode_state``/``encode_state`` themselves ARE the (value-domain, not
byte-level) word-order transform MATLAB's real generator uses, so genuine
word-order confusion is caught by simply applying (or failing to apply)
this transform, not by a second, independent byte-swap step.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

__all__ = [
    "MCG_MOD",
    "DEFAULT_STATE_FOR_ZERO_SEED",
    "decode_state",
    "encode_state",
    "seed_state",
    "parse_captured_state",
]

MCG_MOD = 2_147_483_647
_MCG_MUL = 16_807
_HALF_MASK = 0xFFFF
_HALF_SIGN = 0x8000
_STATE_XOR_MASK = 0x80008000

# Live-verified 2026-09-05: RandStream('mcg16807','Seed',0).State.
DEFAULT_STATE_FOR_ZERO_SEED = 931_316_785


def encode_state(raw_state: int) -> int:
    """Raw Lehmer recurrence value -> MATLAB-exposed ``State`` encoding."""
    raw_i = int(raw_state)
    if raw_i <= 0 or raw_i >= MCG_MOD:
        raise ValueError(f"raw mcg16807 state must be in [1, {MCG_MOD - 1}], got {raw_i}")
    lo = raw_i & _HALF_MASK
    hi = (raw_i >> 16) & _HALF_MASK
    encoded = (lo << 16) | hi
    if lo & _HALF_SIGN:
        encoded ^= _STATE_XOR_MASK
    return int(encoded)


def decode_state(encoded_state: int) -> int:
    """MATLAB-exposed ``State`` encoding -> raw Lehmer recurrence value."""
    encoded_i = int(encoded_state)
    if encoded_i <= 0 or encoded_i >= MCG_MOD:
        raise ValueError(f"encoded mcg16807 state must be in [1, {MCG_MOD - 1}], got {encoded_i}")
    if encoded_i & _HALF_SIGN:
        encoded_i ^= _STATE_XOR_MASK
    lo = encoded_i & _HALF_MASK
    hi = (encoded_i >> 16) & _HALF_MASK
    raw = (lo << 16) | hi
    if raw <= 0 or raw >= MCG_MOD:
        raise ValueError(f"decoded mcg16807 raw state must be in [1, {MCG_MOD - 1}], got {raw}")
    return int(raw)


def seed_state(seed: int) -> int:
    """The ``State`` MATLAB reports immediately after
    ``RandStream('mcg16807','Seed',seed)`` -- live-verified: the seed value
    is stored as the exposed ``State`` bit pattern VERBATIM (no
    encode-transform at seed time), except ``seed<=0`` which MATLAB maps to
    a fixed default state, and ``seed % MCG_MOD == 0`` which wraps to
    ``MCG_MOD - 1`` (never a zero/invalid Lehmer state)."""
    seed_i = int(seed)
    if seed_i <= 0:
        return DEFAULT_STATE_FOR_ZERO_SEED
    seed_i %= MCG_MOD
    if seed_i == 0:
        seed_i = MCG_MOD - 1
    return seed_i


def step_raw(raw_state: int) -> int:
    """One forward step of the real, undecorated Lehmer/Park-Miller
    recurrence in raw (decoded) state space: ``state = 16807*state mod
    (2**31-1)``."""
    return (_MCG_MUL * int(raw_state)) % MCG_MOD


def draw_and_advance(encoded_state: int) -> tuple[float, int]:
    """Given the current MATLAB-exposed encoded state, perform exactly one
    ``rand()`` draw and return ``(uniform_value, next_encoded_state)`` --
    the single operation ``_mcg_rand_scalar``-style shims wrap per draw."""
    raw = decode_state(encoded_state)
    raw = step_raw(raw)
    return raw / MCG_MOD, encode_state(raw)


def steps_between(state_a: int, state_b: int, max_steps: int = 1_000_000) -> int:
    """Count forward Lehmer-recurrence steps from encoded state `state_a`
    to encoded state `state_b`, decoding both endpoints into raw
    recurrence space first (the fix for the tick=894 M5000 seed-36
    failure: comparing/stepping ENCODED values directly, without this
    decode, can never reach a real exit state reachable only in raw
    space). Raises ValueError -- never silently caps/wraps -- if `state_b`
    is not reached within `max_steps`, so a genuine desync fails loudly."""
    raw_a = decode_state(state_a)
    raw_b = decode_state(state_b)
    if raw_a == raw_b:
        return 0
    raw = raw_a
    for step in range(1, max_steps + 1):
        raw = step_raw(raw)
        if raw == raw_b:
            return step
    raise ValueError(
        f"encoded state {state_b} (raw {raw_b}) not reached from {state_a} (raw {raw_a}) "
        f"within {max_steps} Lehmer steps"
    )


def parse_captured_state(value: Any) -> int:
    """Normalize one captured ``randStreamState`` reading (from HDF5/h5py
    or MATLAB ``jsonencode`` JSON) into a single Python int, in the
    MATLAB-exposed ENCODED representation (the same representation
    ``decode_state``/``encode_state`` operate on) -- never silently
    truncating a multi-element payload nor accepting a malformed one.

    Fails loudly (``ValueError``) for every anomaly this codec was asked
    to guard against:
    - more than one element ("first-word-only" truncation risk -- a
      genuine mcg16807 capture is always exactly 1 element; more than one
      means a different generator or a corrupted/legacy capture, never a
      value to arbitrarily index into),
    - missing/empty payload,
    - non-finite (NaN/inf) values,
    - non-integer-valued floats (a genuine captured state is always a
      whole-number double even though it round-trips through HDF5 as
      float64),
    - values outside the valid mcg16807 range ``[1, MCG_MOD - 1]``.
    """
    arr = np.asarray(value, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        raise ValueError("captured mcg16807 state is empty (missing state)")
    if arr.size > 1:
        raise ValueError(
            f"captured mcg16807 state has {arr.size} elements (expected exactly 1 -- "
            "refusing to silently take the first word); got values="
            f"{arr.tolist()!r}"
        )
    raw_value = float(arr[0])
    if not math.isfinite(raw_value):
        raise ValueError(f"captured mcg16807 state is non-finite: {raw_value!r}")
    rounded = round(raw_value)
    if abs(raw_value - rounded) > 1.0e-6:
        raise ValueError(f"captured mcg16807 state is not integer-valued: {raw_value!r}")
    state_i = int(rounded)
    if state_i <= 0 or state_i >= MCG_MOD:
        raise ValueError(f"captured mcg16807 state {state_i} is out of range [1, {MCG_MOD - 1}]")
    return state_i
