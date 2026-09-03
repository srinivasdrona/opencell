"""ChromosomeCondensation-only replay-state applier.

Background: ``ChromosomeCondensation.next_update`` emits the chromosome
state's NEW post-tick sparse structure (e.g. ``complexBoundSites`` triples),
not an accumulator delta. The generic, shared
``tests/vivarium/l2_replay_common.py::apply_count_update`` only ever
iterates a fixed channel list (``substrates``/``protein``/``rna``/
``complex``/``boundEnzymes``/``enzymes``) and never reads or writes
``update["chromosome"]`` at all -- it is not recursive over arbitrary keys,
so it does not corrupt the chromosome sparse structure; it simply ignores
it, leaving ``state["chromosome"]`` completely untouched by the update.
That is wrong for a different reason: without applying
``update["chromosome"]`` onto ``state["chromosome"]``, a replay harness that
rebuilds fresh oracle-fed state each tick would compare Karr's real
post-tick chromosome trace against OC's still-pre-tick (never-updated)
state, which is not a faithful hidden-replay check at all -- it would not
exercise `next_update`'s actual chromosome writeback. This module isolates
the correct chromosome-aware apply logic (numeric leaves still accumulate;
non-numeric values -- the sparse structures -- are replaced wholesale) so it
can be used by ChromosomeCondensation's own L2.1 hidden-replay proof and
diagnostic probes WITHOUT changing ``l2_replay_common.py`` itself.

Why this is a separate module rather than a branch in the shared file: the
shared ``apply_count_update`` is a registered provenance dependency
(``schema.py``'s ``HARNESS_DEPENDENCY_FILES``/``PROCESS_DEPENDENCY_FILES``)
for all 18 ``design_a_per_tick`` L2.2 processes plus DNADamage's event-class
evidence. Any edit to that file's bytes invalidates every one of those rows'
recorded sweep-provenance hash, forcing a full L2.2 re-sweep even though
only ChromosomeCondensation (itself explicitly OUT of L2.2 scope) needed the
new behavior. Keeping the fix local here means ``l2_replay_common.py``
stays byte-for-byte identical to main and the L2.2 evidence board's
provenance hashes are untouched.

Scope: ChromosomeCondensation ONLY, and specifically only the tests/probes
that read ``state["chromosome"]`` back out after applying an update (the
L2.1 strict-rubric script/test does NOT -- its bit-identity check only ever
projects substrates/enzymes/boundEnzymes, never chromosome itself -- so this
module is provably inert there; direct verification showed byte-identical
verdicts with the plain ``apply_count_update``, and the rubric files use
that plain function unconditionally for every process, including
ChromosomeCondensation).

* DO import this from: ChromosomeCondensation's own L2.1 replay test
  (``test_karr_chromosome_condensation_l2_replay.py``, whose hidden-replay
  proof and inversion test read ``state["chromosome"]`` back out) and the
  committed ChromCond hidden-replay diagnostic probes under ``tmp/`` (same
  reason).
* DO NOT import this from any Design-A L2.2 runner
  (``tests/vivarium/_l2_2_design_a_runner_helpers.py`` and friends), from
  ``scripts/l22_evidence/dna_damage_event_verifier.py``, or from the L2.1
  strict-rubric script/test -- all three must keep using the plain,
  main-identical ``apply_count_update`` (the first two so their accepted
  evidence's provenance hash stays valid; the rubric because this module is
  inert there and adding it would be needless, misleading complexity).
"""

from __future__ import annotations

import copy
from numbers import Number
from typing import Any

from l2_replay_common import apply_count_update

__all__ = ["apply_chromcond_replay_update"]


def _apply_chromosome_replacement(target: dict[str, Any], delta: dict[str, Any]) -> None:
    for key, value in delta.items():
        if isinstance(value, Number):
            prev = target.get(key, 0.0)
            try:
                prev_f = float(prev)
            except Exception:
                prev_f = 0.0
            target[key] = float(prev_f + float(value))
            continue
        target[key] = copy.deepcopy(value)


def apply_chromcond_replay_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Apply ``update`` onto ``state`` for ChromosomeCondensation's own L2.1
    hidden-replay proof.

    Delegates the standard count channels (substrates/protein/rna/complex/
    boundEnzymes/enzymes) to the shared, main-identical ``apply_count_update``
    unchanged (which ignores ``update["chromosome"]`` entirely), then
    additionally applies ``update["chromosome"]`` onto ``state["chromosome"]``:
    numeric leaves accumulate (matching the generic behavior), non-numeric
    leaves (sparse triple structures) are replaced wholesale via
    ``copy.deepcopy`` rather than recursively summed.
    """
    apply_count_update(state, update)

    chromosome_update = update.get("chromosome")
    if isinstance(chromosome_update, dict):
        chromosome_state = state.get("chromosome")
        if not isinstance(chromosome_state, dict):
            chromosome_state = {}
            state["chromosome"] = chromosome_state
        _apply_chromosome_replacement(chromosome_state, chromosome_update)
