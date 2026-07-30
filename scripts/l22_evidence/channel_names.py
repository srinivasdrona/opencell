"""Canonical channel-name normalization for the L2.2 evidence evaluator.

``tests/vivarium/l2_2_design_a_runner.py`` normalizes a handful of
lowercase/plural channel-name aliases (e.g. catalog ``rnas`` -> result.json
key ``RNAs``) via its own ``_CHANNEL_NAME_ALIASES``/``_normalize_channel_name``
BEFORE it ever writes a ``result.json`` -- so every stored primary-channel
dict key is already normalized, while ``PROCESS_CATALOG.yaml``'s
``primary_channel`` field is never rewritten and still holds the raw,
un-normalized spelling. ``scripts/l22_evidence/catalog.py`` intentionally
reads the catalog raw (so `catalog_soft_flags` stays byte-exact to the
YAML), which means anything comparing a result.json channel-name key
against ``ProcessEntry.primary_channel`` byte-exact will spuriously mismatch
for every one of these aliased processes.

This module is the ONE place `scripts/l22_evidence/verdict.py` normalizes
both sides of that comparison. ``CHANNEL_NAME_ALIASES`` below is a
deliberate, hand-maintained DUPLICATE of the runner's own alias table --
not an import of it -- because the runner module pulls in numpy/scipy/
`opencell.m1.calc_flux_bounds`/`opencell.m1.fva` at module scope (heavy,
side-effectful for a small evaluator-only helper). The duplication is
never allowed to silently drift: see
`tests/scripts/test_l22_evidence_channel_names_parity.py`, which imports
the runner directly (test-only cost is acceptable) and asserts byte-exact
equality against this table.
"""

from __future__ import annotations

# Keep this dict byte-for-byte identical to
# `tests.vivarium.l2_2_design_a_runner._CHANNEL_NAME_ALIASES`. Any drift is
# caught by the parity test referenced in the module docstring above.
CHANNEL_NAME_ALIASES: dict[str, str] = {
    "mrnas": "mRNAs",
    "rnas": "RNAs",
}


def normalize_channel_name(name: str) -> str:
    """Mirrors the runner's own `_normalize_channel_name`: lowercase-keyed
    alias lookup, falling through to the original (non-lowercased) name
    when there is no alias registered."""
    channel = str(name)
    return CHANNEL_NAME_ALIASES.get(channel.lower(), channel)
