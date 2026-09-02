"""One-shot conflict resolver for opencell/provenance/llm_interactions.jsonl.

Append-only provenance log: HEAD and main both appended distinct event_ids
after a shared ancestor. Resolution = union of both sides, sorted by
timestamp_utc so the merged file stays roughly chronological. Deletes
itself from the working tree is NOT done here (kept as a session artifact);
caller removes the conflict markers by rewriting the target file in place.
"""
import re
import sys
from pathlib import Path

path = Path("opencell/provenance/llm_interactions.jsonl")
text = path.read_text(encoding="utf-8")

m = re.search(r"<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> main\n", text, re.S)
if not m:
    print("No conflict markers found", file=sys.stderr)
    sys.exit(1)

head_block = [ln for ln in m.group(1).split("\n") if ln.strip()]
main_block = [ln for ln in m.group(2).split("\n") if ln.strip()]

import json

combined = head_block + main_block
# Sanity: no duplicate event_id, all valid JSON.
seen = set()
for ln in combined:
    rec = json.loads(ln)
    eid = rec["event_id"]
    if eid in seen:
        raise SystemExit(f"duplicate event_id in union: {eid}")
    seen.add(eid)

combined.sort(key=lambda ln: json.loads(ln)["timestamp_utc"])

new_block = "\n".join(combined)
new_text = text[: m.start()] + new_block + "\n" + text[m.end() :]
path.write_text(new_text, encoding="utf-8")
print(f"Resolved: {len(head_block)} HEAD + {len(main_block)} main = {len(combined)} lines, sorted by timestamp_utc")
