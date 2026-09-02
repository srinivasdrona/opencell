import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_1" / "L21_ACTIVE_WINDOWS_MANIFEST.json"

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
rows_by_process = {row["process"]: row for row in manifest["rows"]}


def build_row(audit_json_path: Path, *, replay_nodeid: str, activity_predicate_override: str | None = None) -> dict:
    payload = json.loads(audit_json_path.read_text(encoding="utf-8"))
    audit_rows = payload["rows"]
    assert len(audit_rows) == 1, f"expected 1 row in {audit_json_path}"
    audit_row = audit_rows[0]
    chosen = audit_row["chosen_trace"]
    assert chosen is not None
    honest = audit_row["honest_replay"]
    bit_identity = audit_row["bit_identity"]
    code_gap_anchor = audit_row.get("code_gap_anchor")

    return {
        "process": audit_row["process"],
        "classification": audit_row["classification"],
        "existing_trace_suffices": audit_row["existing_trace_suffices"],
        "activity_predicate": activity_predicate_override or audit_row["activity_predicate"],
        "source": {
            "path": chosen["path"],
            "repo_relative_hint": chosen["repo_relative_hint"],
            "sha256": chosen["sha256"],
            "trace_family": chosen["trace_family"],
            "source_manifest": chosen.get("source_manifest"),
        },
        "trace_window": {
            "n_ticks": chosen["n_ticks"],
            "tick_offset": chosen["tick_offset"],
            "first_active_local_tick": chosen["first_active_tick"],
            "first_active_absolute_tick": chosen["first_active_absolute_tick"],
            "active_tick_count": chosen["active_tick_count"],
            "first_active_detail": chosen["first_active_detail"],
        },
        "mechanical_scan": {
            "scanned_candidate_count": audit_row["scanned_candidate_count"],
            "command": (
                f"bin\\\\oc-py.cmd scripts/l21_active_window_audit.py --process {audit_row['process']} "
                f"--write-json <temp>"
            ),
        },
        "replay_evidence": {
            "type": "pytest+audit_tool_honest_replay",
            "nodeid": replay_nodeid,
            "outcome": "code_gap",
            "command": f"bin\\\\oc-pytest.cmd -q {replay_nodeid}",
        },
        "code_gap_evidence": {
            "bit_identity": bit_identity,
            "honest_replay": honest,
            "code_gap_anchor": code_gap_anchor,
        },
    }


updates = [
    build_row(
        REPO_ROOT / "tmp" / "audit_tr_full.json",
        replay_nodeid=(
            "tests/vivarium/test_karr_transcriptional_regulation_l2_replay.py::"
            "test_karr_transcriptional_regulation_l2_event_replay[event_seed_0]"
        ),
    ),
    build_row(
        REPO_ROOT / "tmp" / "audit_cyto.json",
        replay_nodeid=(
            "tests/vivarium/test_karr_cytokinesis_l2_replay.py::test_karr_cytokinesis_l2_event_replay[event_seed_0]"
        ),
    ),
]

for new_row in updates:
    process_name = new_row["process"]
    old_row = rows_by_process[process_name]
    print(f"{process_name}: {old_row['classification']} -> {new_row['classification']}")
    rows_by_process[process_name] = new_row

order = [row["process"] for row in manifest["rows"]]
manifest["rows"] = [rows_by_process[name] for name in order]
manifest["counts"] = {
    "EXISTING_WINDOW_PASS": sum(1 for r in manifest["rows"] if r["classification"] == "EXISTING_WINDOW_PASS"),
    "CODE_GAP": sum(1 for r in manifest["rows"] if r["classification"] == "CODE_GAP"),
    "MISSING_ACTIVE_EXTRACTION": sum(
        1 for r in manifest["rows"] if r["classification"] == "MISSING_ACTIVE_EXTRACTION"
    ),
}

MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
print("Wrote", MANIFEST_PATH)
print("counts:", manifest["counts"])
