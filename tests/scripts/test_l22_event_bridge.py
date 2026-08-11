"""End-to-end tests for the RibosomeAssembly L2.event -> L2.2 bridge."""

# ruff: noqa: E402

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import (
    event_bridge,  # noqa: E402
    schema,  # noqa: E402
)
from scripts.l22_evidence import generator as gen  # noqa: E402


def _entry() -> cat.ProcessEntry:
    return cat.in_scope_processes()["RibosomeAssembly"]


def _copy_real_source_bundle(tmp_path: Path) -> Path:
    dst = tmp_path / "l2_event_bundle"
    shutil.copytree(event_bridge.SOURCE_EVENT_BUNDLE_DIR, dst)
    return dst


def _row_for(root: Path) -> dict:
    return gen.build_process_row(_entry(), root)


def test_real_ribosome_event_bundle_bridges_to_pass(tmp_path):
    source_bundle = _copy_real_source_bundle(tmp_path)
    event_bridge.write_bridge_bundle(output_root=tmp_path / "evidence_root", source_bundle_dir=source_bundle)

    row = _row_for(tmp_path / "evidence_root")
    assert row["mechanical_verdict"] == schema.STATUS_PASS
    assert row["green"] is True
    assert row["channel_verdicts"]["complexs"] in schema.GREEN_CHANNEL_VERDICTS
    assert row["channel_verdicts"]["timing"] in schema.GREEN_CHANNEL_VERDICTS
    assert row["channel_verdicts"]["payload"] in schema.GREEN_CHANNEL_VERDICTS


def test_bridge_rederives_from_raw_metrics_not_source_verdict_strings(tmp_path):
    source_bundle = _copy_real_source_bundle(tmp_path)
    result_path = source_bundle / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["verdict"] = "PASS"
    for channel in result["channels"]:
        channel["verdict"] = "PASS"
        if channel["channel"] == "timing":
            channel["statistic_value"] = float(channel["threshold"]) + 10.0
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    event_bridge.write_bridge_bundle(output_root=tmp_path / "evidence_root", source_bundle_dir=source_bundle)
    row = _row_for(tmp_path / "evidence_root")

    assert row["mechanical_verdict"] == schema.STATUS_FAIL
    assert row["green"] is False
    assert row["channel_verdicts"]["timing"] == schema.STATUS_FAIL


def test_bridge_row_stales_when_upstream_event_bundle_changes(tmp_path):
    source_bundle = _copy_real_source_bundle(tmp_path)
    event_bridge.write_bridge_bundle(output_root=tmp_path / "evidence_root", source_bundle_dir=source_bundle)

    summary_path = source_bundle / "SUMMARY.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["scope_caveat"] = "tampered-after-bridge"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    row = _row_for(tmp_path / "evidence_root")
    assert row["mechanical_verdict"] == schema.STATUS_FAIL
    assert any(schema.STATUS_STALE_VS_TREE in reason for reason in row["reasons"])


def test_event_bridge_dependency_change_stales_ribosome_row(tmp_path, monkeypatch):
    source_bundle = _copy_real_source_bundle(tmp_path)
    event_bridge.write_bridge_bundle(output_root=tmp_path / "evidence_root", source_bundle_dir=source_bundle)

    fake_bridge = tmp_path / "src" / "fake_event_bridge.py"
    fake_bridge.parent.mkdir(parents=True, exist_ok=True)
    fake_bridge.write_text("# fake event bridge drift\n", encoding="utf-8")
    monkeypatch.setitem(schema.EVENT_CLASS_SOURCE_FILES, "event_bridge", fake_bridge)

    row = _row_for(tmp_path / "evidence_root")
    assert row["mechanical_verdict"] == schema.STATUS_FAIL
    assert any("event_bridge" in reason for reason in row["reasons"])
