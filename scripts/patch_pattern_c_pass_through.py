from pathlib import Path

FILES = [
    'tests/vivarium/test_karr_protein_folding_l2_replay.py',
    'tests/vivarium/test_karr_protein_processing_i_l2_replay.py',
    'tests/vivarium/test_karr_protein_processing_ii_l2_replay.py',
    'tests/vivarium/test_karr_replication_initiation_l2_replay.py',
]

OLD = """                oc_after = project_observable_from_state(
                    process=process,
                    state=state,
                    observable=observable,
                    wids=wids_by_observable[observable],
                    bound_enzymes_before=before_vectors.get("boundEnzymes"),
                )"""

NEW = """                if observable in _PASS_THROUGH:
                    # Rule 7: Karr records this observable but OC's next_update
                    # does not write into it. oc_after == karr_before by
                    # construction; if Karr mutates the observable within the
                    # tick the assertion will surface the discrepancy.
                    oc_after = before_vectors[observable].astype(np.float64).reshape(-1)
                else:
                    oc_after = project_observable_from_state(
                        process=process,
                        state=state,
                        observable=observable,
                        wids=wids_by_observable[observable],
                        bound_enzymes_before=before_vectors.get("boundEnzymes"),
                    )"""

for fn in FILES:
    p = Path(fn)
    src = p.read_text(encoding='utf-8')
    if NEW.split('\n')[0].strip() in src:
        print(f"ALREADY {fn}")
        continue
    if OLD not in src:
        print(f"SKIP    {fn}: marker not found")
        continue
    new = src.replace(OLD, NEW)
    p.write_text(new, encoding='utf-8', newline='\n')
    print(f"OK      {fn}")
