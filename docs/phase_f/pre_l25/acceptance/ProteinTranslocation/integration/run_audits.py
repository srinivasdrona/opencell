import sys
sys.dont_write_bytecode = True
from integration_common import *
import subprocess
from dataclasses import asdict
from scripts.l22_evidence import generator
from scripts import pre_l25_honesty as honesty

commands = [
    ("full_portable_index_audit", ["scripts/l22_evidence/generator.py", "audit",
                                  "--index", "docs/phase_f/l2_2_design_a/evidence_index.json",
                                  "--evidence-root", "docs/phase_f/l2_2_design_a/evidence_bundle"]),
    ("honesty_baseline_audit", ["scripts/pre_l25_honesty.py", "audit",
                               "--baseline", "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml"]),
]
records = []
for name, args in commands:
    command = [sys.executable, *args]
    started = now()
    with (OUT / f"{name}.log").open("w") as stream:
        child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        event("existing_audit_child_started", name=name, command=command,
              child_pid=child.pid, started_at=started)
        rc = child.wait()
    record = {"name": name, "command": command, "child_pid": child.pid,
              "started_at": started, "finished_at": now(), "exit_code": rc,
              "log": f"{name}.log", "log_sha256": sha(OUT / f"{name}.log")}
    records.append(record)
    save("audit_commands.json", records)
    event("existing_audit_child_completed", **record)
    assert rc == 0, record
portable = generator.audit(index_path=ROOT / "docs/phase_f/l2_2_design_a/evidence_index.json",
                           evidence_root=BUNDLE_ROOT)
assert portable.ok and portable.aggregate_verdict == "NON_GREEN"
assert portable.tally == {"FAIL": 18, "MISSING_EVIDENCE": 2, "PASS": 4}
baseline = honesty.audit_baseline(ROOT / "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml",
                                 root=ROOT)
assert baseline.integrity_ok and baseline.process_count == 28
assert baseline.eligible_count == 6 and baseline.blocked_count == 22
assert not baseline.all_eligible and not baseline.problems
save("structured_audit_results.json", {
    "portable_full_index": asdict(portable), "honesty_baseline": asdict(baseline),
    "commands": records,
    "scope": "Existing portable full-index and honesty integration audits only; no biological gate or calibration rerun"})
event("existing_integration_audits_complete", portable_integrity=portable.ok,
      tally=portable.tally, aggregate=portable.aggregate_verdict,
      honesty_integrity=baseline.integrity_ok, eligible=baseline.eligible_count,
      blocked=baseline.blocked_count, processes=baseline.process_count)
