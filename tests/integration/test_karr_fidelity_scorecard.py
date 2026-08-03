from __future__ import annotations

import sys
from pathlib import Path

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from scripts.karr_fidelity_scorecard import run_scorecard


def test_karr_fidelity_scorecard_known_processes_not_fail() -> None:
    rows = run_scorecard(write_outputs=False)
    by_name = {row.process_name: row for row in rows}

    for process_name in (
        "ChromosomeCondensation",
        "Cytokinesis",
        "FtsZPolymerization",
        "ProteinTranslocation",
        "Metabolism",
    ):
        assert process_name in by_name, f"missing scorecard row for {process_name}"
        status = by_name[process_name].status
        assert status in {"PASS", "PARTIAL"}, (
            f"{process_name} expected PASS or PARTIAL, got {status}: {by_name[process_name].reason}"
        )
