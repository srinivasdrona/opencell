# Zero-grant contract recommendation

## Diff vs Karr

Python currently interprets zero allocation as "fallback to global substrates" at multiple sites, for example:

- `opencell/vivarium/karr_chromosome_segregation.py:219-222`
- `opencell/vivarium/karr_cytokinesis.py:270-273`
- `opencell/vivarium/karr_dna_repair.py:553-556`
- `opencell/vivarium/karr_replication.py:185-188`
- `opencell/vivarium/karr_replication_initiation.py:280-283`
- `opencell/vivarium/karr_trna_aminoacylation.py:129-131` (inline)

Karr MATLAB does not do this fallback. It overwrites each process substrate vector with the allocation before process execution (`evolveState.m:63-70`) and then applies only the delta from that allocated vector back to global metabolites (`evolveState.m:72-73`).

## Recommended contract

Choose **(A) Strict zero**.

Definition: if allocator grants `0` for a substrate to a process, that process must treat available amount as `0` for that tick; it must not read `states["substrates"]` as a substitute for allocated zero.

Operationally:

- For helper-based readers, return allocated amount directly (or `0` if missing), not global pool fallback.
- For inline readers, replace `allocated_if_positive_else_global` logic with strict allocated semantics.
- Keep presence-only fallback (for truly missing keys) only if composition intentionally omits allocation for that process/substrate; otherwise missing should also be treated as zero to fail closed.

## Justification

- Karr allocator assignment is explicit and per-process (`evolveState.m:63-70`), and sampled process code gates on `this.substrates` values (e.g., `ChromosomeSegregation.m:201-203`, `Replication.m:637-643`, `ReplicationInitiation.m:537-543`, `DNARepair.m:958-963`, `tRNAAminoacylation.m:395-423`).
- Therefore the MATLAB contract is allocator-authoritative for per-process substrate availability at each tick, with zero grants producing gated/no-op behavior, not global fallback.

## Impact on the 6 known Class A findings

- `ChromosomeSegregation`: zero-grant consumption finding becomes moot after strict-zero helper behavior; progression should stop when allocated GTP/H2O is zero.
- `Cytokinesis`: zero-grant consumption finding becomes moot for the same reason; progress should be substrate-gated by allocated budget.
- `DNARepair`: zero-grant repair-through-global-pool finding becomes moot; repair count should remain zero under zero allocated tracked substrates.
- `Replication`: zero-grant fork advance finding becomes moot; fork advance should remain zero when allocated dNTP/ATP are zero.
- `ReplicationInitiation`: zero-grant ATP/H2O consumption finding becomes moot; activation/inactivation steps should no-op.
- `tRNAAminoacylation`: zero-grant substrate consumption finding becomes moot; reaction limits should collapse to zero.

Note: independent allocator/enrollment defects called out elsewhere in Class A are unaffected by this contract decision.

## Fix locus for Track A (no edits applied here)

Primary loci for strict-zero change:

- Helper definitions:
  - `opencell/vivarium/karr_chromosome_condensation.py:326-335`
  - `opencell/vivarium/karr_chromosome_segregation.py:213-222`
  - `opencell/vivarium/karr_cytokinesis.py:265-273`
  - `opencell/vivarium/karr_dna_repair.py:547-556`
  - `opencell/vivarium/karr_dna_supercoiling.py:310-319`
  - `opencell/vivarium/karr_replication.py:179-188`
  - `opencell/vivarium/karr_replication_initiation.py:274-283`
  - `opencell/vivarium/karr_protein_folding.py:234-242`
  - `opencell/vivarium/karr_protein_translocation.py:194-199`

- Inline fallback call sites:
  - `opencell/vivarium/karr_protein_modification.py:151-153`
  - `opencell/vivarium/karr_protein_processing_i.py:246-248`
  - `opencell/vivarium/karr_protein_processing_ii.py:184-186`
  - `opencell/vivarium/karr_rna_modification.py:143-145`
  - `opencell/vivarium/karr_rna_processing.py:246-248`
  - `opencell/vivarium/karr_trna_aminoacylation.py:129-131`

- Related presence-based variant to review explicitly:
  - `opencell/vivarium/karr_ftsz_polymerization.py:218-226` (falls back only when allocation key is absent).
