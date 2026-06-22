"""Audit Seg pair failures: which side is the harness blaming?"""
import json
import subprocess
import re

PAIRS = [
    "ChromosomeSegregation+FtsZPolymerization",
    "ChromosomeSegregation+Metabolism",
    "ChromosomeSegregation+ProteinDecay",
    "ChromosomeSegregation+ProteinTranslocation",
    "ChromosomeSegregation+DNASupercoiling",
    "ChromosomeSegregation+Replication",
    "ChromosomeSegregation+DNARepair",
    "ChromosomeSegregation+ReplicationInitiation",
    "ChromosomeSegregation+Transcription",
    "ChromosomeSegregation+ProteinModification",
    "ChromosomeSegregation+RNADecay",
]

def get_failure_record(pair):
    """Run pytest and extract structured failure JSON."""
    proc = subprocess.run(
        ["python", "-m", "pytest",
         f"tests/vivarium/test_l25_deterministic_stochastic_pairs.py::test_l25_deterministic_stochastic_pair_no_hints[{pair}-rng_seed_0]",
         "-v", "--tb=short"],
        capture_output=True, text=True, timeout=180,
    )
    out = proc.stdout + proc.stderr
    m = re.search(r'\{"cause_code".*?\}(?=\n)', out, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

print(f"{'pair':45s} {'process':25s} {'cause_code':40s} {'tick':>4s} {'compare_mode':12s} {'observable':12s} {'wid':15s} {'karr':>8s} {'oc':>8s}")
print("-" * 200)
for p in PAIRS:
    rec = get_failure_record(p)
    if rec is None:
        print(f"{p:45s}  (no record)")
        continue
    proc_name = rec.get('process', '?')
    cause = rec.get('cause_code', '?')
    tick = rec.get('tick', '?')
    mode = rec.get('compare_mode', '?')
    obs = rec.get('observable', '?')
    wid = rec.get('process_wid', '?') or rec.get('owner_wid', '?')
    karr = rec.get('karr_val', '?')
    oc = rec.get('oc_val', '?')
    print(f"{p:45s} {proc_name:25s} {cause:40s} {str(tick):>4s} {mode:12s} {obs:12s} {str(wid):15s} {str(karr):>8s} {str(oc):>8s}")
