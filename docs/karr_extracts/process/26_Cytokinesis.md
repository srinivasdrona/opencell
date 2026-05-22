# Karr Process - Cytokinesis

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Cytokinesis.m`
**WholeCellModelID:** `Process_Cytokinesis`
**Karr functional area:** cytokinesis
**OpenCell fixture:** `data/karr_fixtures/per_process/Cytokinesis_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Cytokinesis

@wholeCellModelID Process_Cytokinesis
@name             Cytokinesis
@description

  Cytokinesis is the division of the cytoplasm, achieved by the pinching of
  the cell membrane. At a high level, it occurs by the formation of a
  contractile Z ring along the interior surface of the cell membrane. The ring
  is comprised of GTP-activated ftsZ polymer filaments that bend when their
  GTP is hydrolized. Cytokinesis is thus a cycle of filament binding, bending,
  and dissociation.

  This process is based on the model described in Li et al. 2007.
    1. Filaments bind the membrane end-to-end to form a regular polygon
       (inscribed in the pinched cell circumference). Two filaments bind at
       each polygon edge.
    2. If there was a previous cycle, then when at least one filament has
       bound each polygon edge, the last remaining ring of bent filaments from
       the previous cycle can begin to dissociate.
    3. When all polygon edges have two filaments bound and all residual bent
       filaments have dissociated, the bending of the edges of the newly
       completed polygon may begin. For simplicity, all of the GTP in the pair
       of filaments at a particular edge hydrolyze at the same time.
    4. When all the filaments have been bent, the bent filaments can begin
       dissociating -- but only one from each polygon edge. The other ring
       must remain to maintain the new smaller pinched circumference.
    5. When only one ring of bent filaments remains, the cycle repeats.
    6. Cytokinesis concludes when the pinched diameter is smaller than the
       length of one filament.

  How bending works:
   - Filaments are bound in the straight configuration, forming a polygon
     inscribed in the cell circumference.
   - When the filaments bend, their length does not change. They bend just
     enough so that when they've all bent, a new circle is formed. Its
     circumference equals the old polygon's perimeter. Each fragment is now
     an arc.

  In this version of the model, all filaments are of a fixed length. When they
  are joined end-to-end to form a regular polygon, the polygon does not quite
  fully inscribe the entire circumference. This remaining portion of the
  circumference does not bent when the polygon does. It is preserved and
  accounted for in the next iteration. For more details, see Li et al. 2007.

  Note: Lluch-Senar et al have shown that M. genitalium cell division can occur 
  in the absence of FtsZ. Lluch-Senar showed that division occurs in ftsZ knockouts
  through motility.      

  References
  ==========
  1. Lluch-Senar M, Querol E, Pinol J (2010). Cell division in a minimal bacterium 
     in the absence of ftsZ. Mol Microbiol. 78(2): 278-89. [PUB_0796]

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 9/7/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `FtsZRing.*`, `CellGeometry.*`, `Chromosome.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_224_MONOMER`
- Key parameters with values:
- Not explicitly quantified in the header beyond symbolic algorithm expressions.
- Any algorithm subtlety that an implementer would miss reading only the @description summary? must remain to maintain the new smaller pinched circumference.
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
