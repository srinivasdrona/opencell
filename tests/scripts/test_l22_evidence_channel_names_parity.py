"""Parity test: `scripts/l22_evidence/channel_names.CHANNEL_NAME_ALIASES` must
stay byte-for-byte identical to the runner's own
`tests.vivarium.l2_2_design_a_runner._CHANNEL_NAME_ALIASES`.

`scripts/l22_evidence/verdict.py` cannot import the runner module directly
at its own module scope (the runner pulls in numpy/scipy/
`opencell.m1.calc_flux_bounds`/`opencell.m1.fva` at import time -- heavy,
side-effectful for a small evaluator-only normalization helper), so
`channel_names.py` maintains a deliberate, hand-written DUPLICATE of the
runner's alias table instead. This test is the only thing standing between
that duplication and silent drift (e.g. a future alias added to the runner
but forgotten here would silently reintroduce the exact P0 byte-exact-
comparison bug this fix exists to close) -- it is test-only, so importing
the runner module here (unlike from verdict.py) is an acceptable cost.

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_channel_names_parity.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import channel_names  # noqa: E402
from tests.vivarium import l2_2_design_a_runner as runner  # noqa: E402


def test_channel_name_aliases_match_runner_byte_for_byte():
    assert channel_names.CHANNEL_NAME_ALIASES == runner._CHANNEL_NAME_ALIASES


def test_channel_name_aliases_is_not_accidentally_empty():
    """Guards against a future refactor emptying the dict and this parity
    test trivially passing against another empty dict."""
    assert channel_names.CHANNEL_NAME_ALIASES
    assert runner._CHANNEL_NAME_ALIASES


def test_normalize_channel_name_matches_runner_normalize_channel_name():
    """Same function, same inputs (including case-folding and unregistered
    passthrough behavior), same outputs."""
    samples = [
        "rnas",
        "RNAs",
        "RNAS",
        "mrnas",
        "mRNAs",
        "substrates",
        "SUBSTRATES",
        "chromosome",
        "",
    ]
    for sample in samples:
        assert channel_names.normalize_channel_name(sample) == runner._normalize_channel_name(sample), sample


def test_normalize_channel_name_applies_known_aliases():
    assert channel_names.normalize_channel_name("rnas") == "RNAs"
    assert channel_names.normalize_channel_name("RNAS") == "RNAs"
    assert channel_names.normalize_channel_name("mrnas") == "mRNAs"


def test_normalize_channel_name_passes_through_unknown_names_unchanged():
    assert channel_names.normalize_channel_name("substrates") == "substrates"
    assert channel_names.normalize_channel_name("chromosome") == "chromosome"
