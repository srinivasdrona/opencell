"""Pull M1-relevant rows from WholeCellKB data.xlsx."""
import json
import openpyxl

XLSX = r"E:\opencell\data\m1_sources\WholeCellKB\public\fixtures\data.xlsx"
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)

def headers_and_first_row(sheet_name, n_rows=2):
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True, max_row=n_rows + 1))
    if not rows:
        return [], []
    return rows[0], rows[1:]

# 1. Metabolites — what columns are available?
hdr, sample = headers_and_first_row("Metabolites", n_rows=3)
print("=== Metabolites columns ===")
for i, h in enumerate(hdr):
    print(f"  [{i:2}] {h}")
print("--- 2 sample rows ---")
for r in sample:
    print(r[:8], "...", r[-3:])

print()
# 2. Reactions
hdr, sample = headers_and_first_row("Reactions", n_rows=2)
print("=== Reactions columns ===")
for i, h in enumerate(hdr):
    print(f"  [{i:2}] {h}")

print()
# 3. Misc parameters
hdr, sample = headers_and_first_row("Misc. parameters", n_rows=3)
print("=== Misc. parameters columns ===")
for i, h in enumerate(hdr):
    print(f"  [{i:2}] {h}")
print("--- sample rows ---")
for r in sample:
    print(r)
