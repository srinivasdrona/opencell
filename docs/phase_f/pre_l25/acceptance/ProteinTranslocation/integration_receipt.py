import sys
sys.dont_write_bytecode = True
from review_common import *
import yaml
from scripts import pre_l25_honesty as honesty

event("parent_integration_metadata_start")
baseline_path = ROOT / "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml"
baseline = yaml.safe_load(baseline_path.read_text())
row = next(r for r in baseline["processes"] if r["name"] == "ProteinTranslocation")
digest, count = honesty.compute_source_digest(ROOT)
catalog_path = ROOT / "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml"
lines = catalog_path.read_text().splitlines(keepends=True)
start = next(i for i, line in enumerate(lines) if line.strip() == "- name: ProteinTranslocation")
end = next(i for i in range(start + 1, len(lines))
           if lines[i].startswith("  - name:") or lines[i].startswith("  # ====="))
verbatim = "".join(lines[start:end]).rstrip() + "\n"
(OUT / "catalog_entry_verbatim.txt").write_text(verbatim)
save("parent_integration_metadata.json", {
    "current_baseline_PT_row": row,
    "baseline_source_tree": baseline["source_tree"],
    "actual_source_tree": {"sha256": digest, "file_count": count},
    "source_tree_metadata_is_stale": baseline["source_tree"] != {"sha256": digest, "file_count": count},
    "staleness_disposition": "Parent integration metadata requirement after approved F1 source delta, not a new PT biological rejection",
    "catalog_source": relative(catalog_path), "catalog_sha256": sha(catalog_path),
    "verbatim_entry_lines": f"{start + 1}-{end}",
    "resolved_findings_to_preserve": [f for f in row["findings"] if f["disposition"] == "RESOLVED"],
    "read_only": True,
})
event("parent_integration_metadata_complete", source_digest=digest,
      source_files=count, baseline_stale=baseline["source_tree"]["sha256"] != digest)
