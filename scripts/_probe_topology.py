from opencell.vivarium.karr_composite import build_karr_chassis_v6
c = build_karr_chassis_v6()
names = [
    "karr_metabolism", "karr_dna_repair", "karr_ftsz_polymerization",
    "karr_protein_folding", "karr_rna_decay",
    "karr_transcription", "karr_translation",
    "karr_replication_initiation", "karr_allocation_step",
    "request_calculator_transcription", "request_calculator_translation",
    "request_calculator_ribasm", "request_calculator_metabolism",
]
for name in names:
    t = c.topology.get(name, {})
    sub = t.get("substrates") if isinstance(t, dict) else None
    ports = list(t.keys()) if isinstance(t, dict) else None
    matches = isinstance(sub, tuple) and sub == ("substrates",)
    print(f"{name}: trace_match={matches} | substrates_port={sub} | all_ports={ports}")
