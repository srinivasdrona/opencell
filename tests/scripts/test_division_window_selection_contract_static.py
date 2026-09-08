"""Static/parse-only regression tests for the MATLAB-side selection-contract
loader `scripts/matlab/division_window_selection_contract.m`, mirroring
`tests/scripts/test_extract_dual_division_window_static.py`'s approach: no
MATLAB/Octave invocation, only lightweight dependency-free assertions on
the source text plus a JSON-level cross-check against the real repo spec
file this loader reads.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.division_window_spec import SPEC_PATH, selection_contract  # noqa: E402

LOADER_PATH = REPO_ROOT / "scripts" / "matlab" / "division_window_selection_contract.m"

_BLOCK_OPENERS = re.compile(r"\b(function|if|for|while|switch|try)\b")
_STANDALONE_END_LINE_RE = re.compile(r"^\s*end\s*;?\s*$")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _strip_comments_and_strings(source: str) -> str:
    out_lines = []
    for line in source.splitlines():
        result = []
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if ch == "'":
                j = i + 1
                while j < n:
                    if line[j] == "'":
                        if j + 1 < n and line[j + 1] == "'":
                            j += 2
                            continue
                        j += 1
                        break
                    j += 1
                result.append("''")
                i = j
                continue
            if ch == "%":
                break
            result.append(ch)
            i += 1
        out_lines.append("".join(result))
    return "\n".join(out_lines)


def _block_balance(source: str) -> tuple[int, int]:
    code = _strip_comments_and_strings(source)
    openers = len(_BLOCK_OPENERS.findall(code))
    closers = sum(1 for line in code.splitlines() if _STANDALONE_END_LINE_RE.match(line))
    return openers, closers


def test_loader_file_exists_and_is_nonempty():
    assert len(_read(LOADER_PATH)) > 0


def test_loader_block_keyword_balance():
    openers, closers = _block_balance(_read(LOADER_PATH))
    assert openers == closers, (
        f"division_window_selection_contract.m block-keyword balance mismatch: "
        f"{openers} opener(s) vs {closers} standalone 'end' statement(s)"
    )


def test_loader_reads_the_same_canonical_spec_path_as_the_python_loader():
    source = _read(LOADER_PATH)
    assert "'docs', 'phase_f', 'l2_event', 'division_window_spec.json'" in source
    # Sanity: the path fragments above really do resolve to SPEC_PATH.
    assert SPEC_PATH.name == "division_window_spec.json"
    assert SPEC_PATH.parent.name == "l2_event"


def test_loader_fails_closed_never_defaults():
    source = _read(LOADER_PATH)
    assert "error('division_window_selection_contract:missing_file'" in source
    assert "error('division_window_selection_contract:invalid_json'" in source
    assert "error('division_window_selection_contract:missing_block'" in source
    assert "error('division_window_selection_contract:missing_field'" in source
    # No fallback/default assignment for any of the required fields.
    assert "candidate_seed_start = 0;" not in source
    assert "required_completed_windows = 50;" not in source
    assert "max_search_ticks = 100000;" not in source


def test_loader_checks_every_required_field_the_python_accessor_requires():
    source = _read(LOADER_PATH)
    contract = selection_contract()
    for key in contract:
        if key in ("preregistered_at", "preregistered_by", "rationale", "$comment", "horizon_vs_existing_traces",
                    "known_censored_seeds_pending_backfill"):
            continue
        assert f"'{key}'" in source, f"loader never references required field {key!r}"


def test_real_repo_spec_file_is_valid_json_and_matches_python_accessor():
    doc = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    contract = doc["selection_contract"]
    assert contract["candidate_seed_start"] == 0
    assert contract["required_completed_windows"] == 50
    assert contract["max_search_ticks"] == 100000
    assert contract["selection_order"] == "ascending_seed"
    assert contract["attempt_record_filename"] == "division_window_attempt.json"
