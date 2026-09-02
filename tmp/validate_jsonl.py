import json

n = 0
with open("opencell/provenance/llm_interactions.jsonl", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            json.loads(line)
            n += 1
print(f"all {n} lines valid json")
