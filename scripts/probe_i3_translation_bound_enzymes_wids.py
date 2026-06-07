from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests" / "vivarium"
for candidate in (REPO_ROOT, TESTS_DIR):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


def main() -> int:
    process = runner_helpers._translation_process(0)
    wids = [str(wid) for wid in getattr(process, "enzyme_wids", ())]
    counts = Counter(wids)
    duplicates = sorted(
        ((wid, n) for wid, n in counts.items() if n > 1),
        key=lambda item: (-item[1], item[0]),
    )
    print(
        json.dumps(
            {
                "process": "Translation",
                "channel": "boundEnzymes",
                "wid_source": "enzyme_wids",
                "total": int(len(wids)),
                "unique": int(len(counts)),
                "duplicate_wids": int(len(duplicates)),
                "top_duplicates": [
                    {"wid": wid, "occurrences": int(n)}
                    for wid, n in duplicates[:10]
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
