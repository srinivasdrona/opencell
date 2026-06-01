from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = REPO_ROOT / "opencell" / "vivarium"

CALL_TOKENS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("loadmat(", re.compile(r"\bloadmat\s*\(")),
    ("h5py.File(", re.compile(r"\bh5py\.File\s*\(")),
    ("np.load(", re.compile(r"\bnp\.load\s*\(")),
    ("numpy.load(", re.compile(r"\bnumpy\.load\s*\(")),
    ("read_csv(", re.compile(r"\bread_csv\s*\(")),
    ("open(", re.compile(r"\bopen\s*\(")),
    ("pickle.load(", re.compile(r"\bpickle\.load\s*\(")),
    ("joblib.load(", re.compile(r"\bjoblib\.load\s*\(")),
)

FILENAME_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("_100ticks", re.compile(r"_100ticks", re.IGNORECASE)),
    ("states_before", re.compile(r"states_before", re.IGNORECASE)),
    ("states_after", re.compile(r"states_after", re.IGNORECASE)),
    ("_init.mat", re.compile(r"_init\.mat", re.IGNORECASE)),
    ("karr_fixtures/states_", re.compile(r"karr_fixtures[/\\]states_", re.IGNORECASE)),
    ("extract_per_process_traces", re.compile(r"extract_per_process_traces", re.IGNORECASE)),
)

ALLOWLIST_TAG = re.compile(r"#\s*rule8-ok\b", re.IGNORECASE)
ALLOWLIST_WITH_REASON = re.compile(r"#\s*rule8-ok\s*:\s*(\S.*)$", re.IGNORECASE)


def _source_files() -> list[Path]:
    return sorted(SCAN_ROOT.rglob("*.py"))


def _valid_allowlist_reason(line: str) -> bool:
    return bool(ALLOWLIST_WITH_REASON.search(line))


def test_rule8_no_oracle_reads_in_production_code() -> None:
    malformed_allowlist: list[tuple[str, int, str]] = []
    violations: list[tuple[str, int, str, str, str]] = []

    for source_path in _source_files():
        rel_path = source_path.relative_to(REPO_ROOT).as_posix()
        lines = source_path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            line_no = idx + 1
            prev_line = lines[idx - 1] if idx > 0 else ""

            if ALLOWLIST_TAG.search(line) and not _valid_allowlist_reason(line):
                malformed_allowlist.append((rel_path, line_no, line.strip()))

            matched_calls = [name for name, pattern in CALL_TOKENS if pattern.search(line)]
            matched_markers = [
                name for name, pattern in FILENAME_MARKERS if pattern.search(line)
            ]
            if not matched_calls or not matched_markers:
                continue

            if _valid_allowlist_reason(line) or _valid_allowlist_reason(prev_line):
                continue

            for call_token in matched_calls:
                for filename_marker in matched_markers:
                    violations.append(
                        (rel_path, line_no, line.rstrip(), call_token, filename_marker)
                    )

    if malformed_allowlist:
        details = "\n".join(
            f"({path!r}, {line_no}, {line_text!r})"
            for path, line_no, line_text in malformed_allowlist
        )
        pytest.fail(
            "Rule 8 allowlist comment must include a reason: "
            "`# rule8-ok: <reason>`.\nMalformed entries:\n" + details
        )

    if violations:
        details = "\n".join(
            f"({path!r}, {line_no}, {line_text!r}, {call_token!r}, {marker!r})"
            for path, line_no, line_text, call_token, marker in violations
        )
        pytest.fail(
            "Rule 8 violation(s): line contains both forbidden call token and oracle/trace "
            "filename marker without `# rule8-ok: <reason>` on that line or the line above.\n"
            + details
        )
