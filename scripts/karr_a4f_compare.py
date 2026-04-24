"""Compare the three .mat fixtures we have against the .m source to
confirm whether s0/s1/s2/arr is a test-fixture serializer format
(invariant across state classes) or carries the actual state field
names.

Karr's State classes declare:
  Time.stateNames               = {'values'}              # 1 field
  Host.stateNames               = {'isBacteriumAdherent',
                                    'isTLRActivated',
                                    'isNFkBActivated',
                                    'isInflammatoryResponseActivated'} # 4 fields
  MetabolicReaction.stateNames  = {'growth', 'fluxs'}     # 2 fields

If all three .mat files carry the same structural shell (s0/s1/s2/arr),
then the fixture format is a test-framework serializer — not a state
dump — and we cannot map .mat→biology directly without that serializer.
"""
import json
from pathlib import Path

import numpy as np
import scipy.io


FIXTURES = {
    "MetabolicReaction": "data/karr_fixtures/MetabolicReaction.mat",
    "Time":              "data/karr_fixtures/Time.mat",
    "Host":              "data/karr_fixtures/Host.mat",
}

EXPECTED_STATE_FIELDS = {
    "MetabolicReaction": ["growth", "fluxs"],
    "Time":              ["values"],
    "Host":              ["isBacteriumAdherent", "isTLRActivated",
                          "isNFkBActivated", "isInflammatoryResponseActivated"],
}


def describe_top(mat_path: Path) -> dict:
    raw = scipy.io.loadmat(str(mat_path), squeeze_me=False, struct_as_record=True)
    keys = [k for k in raw.keys() if not k.startswith("__")]
    info = {"top_keys": keys, "structure": {}}
    for k in keys:
        v = raw[k]
        info["structure"][k] = {
            "shape": list(v.shape),
            "dtype": str(v.dtype),
            "fields": list(v.dtype.names) if v.dtype.names else None,
        }
        if v.dtype.names:
            sq = v.squeeze() if v.size > 0 else v
            for fname in v.dtype.names:
                try:
                    sub = sq[fname] if isinstance(sq, np.void) else v[fname]
                    info["structure"][k][f"{fname}_shape"] = list(np.asarray(sub).shape)
                    info["structure"][k][f"{fname}_dtype"] = str(np.asarray(sub).dtype)
                except Exception as e:
                    info["structure"][k][f"{fname}_error"] = str(e)[:80]
    return info


def main() -> int:
    table = []
    for name, path in FIXTURES.items():
        info = describe_top(Path(path))
        expected = EXPECTED_STATE_FIELDS[name]
        observed_fields = []
        for k, struct in info["structure"].items():
            if struct["fields"]:
                observed_fields.extend(struct["fields"])
        match = sorted(observed_fields) == sorted(expected)
        table.append({
            "class": name,
            "expected_state_fields": expected,
            "observed_top_struct_fields": observed_fields,
            "match": match,
            "structure": info["structure"],
        })
        print(f"\n=== {name} ===")
        print(f"  expected (.m stateNames): {expected}")
        print(f"  observed (.mat top struct fields): {observed_fields}")
        print(f"  MATCH: {match}")
        print(f"  full structure: {json.dumps(info['structure'], indent=2)}")

    out = Path("artifacts/karr_a4f_comparison.json")
    out.write_text(json.dumps(table, indent=2, default=str))

    print("\n\n=== VERDICT ===")
    invariant_shape = all(
        list(row["structure"][k].get("fields") or []) == ["s0", "s1", "s2", "arr"]
        for row in table for k in row["structure"]
    )
    if invariant_shape:
        print("All three fixtures share fields ['s0','s1','s2','arr'] regardless of")
        print(f"declared state field count (1, 2, and 4 respectively).")
        print(f"=> .mat fixtures use a custom serializer; field-name semantics are")
        print(f"   NOT recoverable from the .mat alone, EVEN with the .m source.")
        print(f"   M-phase ingestion needs the serializer code (likely in")
        print(f"   src_test/+edu/+stanford/+covert/+test/.../*.m).")
    else:
        print("Fields differ across fixtures — investigate per-class.")

    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
