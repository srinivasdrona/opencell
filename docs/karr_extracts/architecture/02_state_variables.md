# Karr Architecture - State Variables

**Source directory:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/*.m`

---

## Verbatim state header extracts

### CellGeometry

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/CellGeometry.m`


```
CellGeometry

@wholeCellModelID State_CellGeometry
@name             Cell geometry
@description

The Cell Shape process calculates the length and surface area of the cell
across its lifespan. It also keeps track of the cell volume. The cell is
approximated to be of a rod shape similar to E. coli, even though
M. genitalium is known to have a less uniform flask shape. Initially, the
cell is modeled as a cylinder with two hemispherical caps. Once cell
pinching commences at the midline of the cell, the shape and size of a
"septum region" is also modeled.

General geometric equations to represent the shape of a cell, and the
idea that the density of the cell does not change across the cell cycle
are borrowed from Domach et al. (1983). We add the assumption that the
width of the cell remains constant during the lifespan of a cell. Thus,
the density and cell width are inputs into our model. The cell density of
E. coli is used 1100g/L (Baldwin et al., 1995). The cell width is
calculated based on the initial cell mass and density and the assumption
that the cell is a sphere. The initial cell mass is fit to result in a
cell width of 200nm (Lind et al, 1984).

Our model calculates the mass of the cell at all timesteps. The mass and
constant density provide us with the volume at all time points.
Volume = [2 hemispheres] + [2 cylinders] + [septum region]
The volume of the septum region is calculated as a cylinder of length,
2*septumLength, and width of the cell. Then two cones (height=septum,
radius=septum) are subtracted from this cylinder.
(This approximation was used in Shuler et al. 1979).

Since we know the volume of the cell from the cell's mass and density,
and the septum length from our cytokinesis process, the volume formula
gives us the length of the cell at each timestep.

Similarly, we can also calculate the surface area of the cell.
Surface Area = [2 hemispheres] + [2 cylinders] + [septum region]
The surface area of the septum region is calculated as a cylinder of
length, 2*septum, and width of the cell.

References
==================
1. Shuler, M.L., Leung, S., Dick, C.C. (1979). A Mathematical Model for the
   Growth of a Single Bacteria Cell. Annals of the New York Academy of Sciences
   326: 35-52.
2. Domach, M.M., Leung, S.K., Cahn, R.E., Cocks, G.G., Shuler, M.L. (1983).
   Computer model for glucose-limited growth of a single cell of Escherichia
   coli B/r-A. Biotechnology and Bioengineering 26: 203-216.
3. Lind, K., Lindhardt, B., Schutten, H.J., Blom, J., Christiansen, C.
   (1984). Serological Cross-Reactions Between Mycoplasma genitalium and
   Mycoplasma pneumoniae. Journal of Clinical Microbiology 20: 1036-1043.
4. Baldwin WW, Myer R, Powell N, Anderson E, Koch AL. (1995). Buoyant
   density of Escherichia coli is determined solely by the osmolarity of the
   culture medium. Arch Microbiology 164: 155-157.

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 6/3/2010
```

### CellMass

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/CellMass.m`


```
CellWeight
Calculates weight of various fractions of the simulation:
- cell/media
- metabolite/RNA/protein
- cytosol/membrane/terminal organelle/extracellular

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 9/12/2010
```

### Chromosome

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Chromosome.m`


```
Chromosome
Integration point for processes which interact with specific
positions/strands of the cell's chromosome(s).
- Represents the portion of chromosome(s) accessible to enzymes. That is
  positions/strands which are NOT
  - damaged in any way (no gap sites, abasic sites, damaged
    sugar-phosphates, damaged bases, cross links, strand breaks,
    or Holliday junctions)
  - stably bound by enzymes
  - single stranded

Terminology:
==================
        Site  single base/bond of chromosomes, indicated by strand index and
              number of bases/bonds along 5'->3' strand from ORI [position X
              strand]
      Region  contiguous set of bases/bonds of chromosomes, indicated by start
              and end positions (bases/bonds along 5'->3' strand from ORI and
              strand (positive/negative)
  Accessible  polymerized, not bound by protein, and not damaged
Inaccessible  not polymerized, bound by protein, or damaged

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 9/12/2010
```

### FtsZRing

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/FtsZRing.m`


```
FtsZRing

@wholeCellModelID State_FtsZRing
@name             FtsZ ring
@description

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 11/30/2010
```

### Host

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Host.m`


```
Host

@wholeCellModelID State_Host
@name             Host
@description
  This class reports qualitative metrics regarding the ability of M.
  genitalium to interact with host human urogenital tract epithelial
  cells:
  - ability of M. genitalium to adhere to the urogenital epithelium,
    which requires adhesins and a functional terminal organelle
  - ability of M. genitalium lipoproteins to interact with host TLR
    receptors 1, 2, and 6

  References
  ==========
  See HostInteraction process.

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 5/25/2011
```

### MetabolicReaction

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/MetabolicReaction.m`


```
MetabolicReaction

@wholeCellModelID State_MetabolicReaction
@name             Metabolic reaction
@description

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/5/2011
```

### Metabolite

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Metabolite.m`


```
Metabolite

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 1/5/2011
```

### Polypeptide

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Polypeptide.m`


```
Polypeptide

@wholeCellModelID State_Polypeptide
@name             Polypeptide
@description


Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 12/16/2010
```

### ProteinComplex

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/ProteinComplex.m`


```
ProteinComplex
- nascent
- mature
- bound

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 1/5/2011
```

### ProteinMonomer

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/ProteinMonomer.m`


```
ProteinMonomer
- nascent
- processed
- folded
- mature
- bound

Translation    NTPs->nascent
Processing     nascent->processedI->processedII->folded->mature
Modification   mature->mature
Misfolding     mature->misfolded
              inactivated->misfolded
Refolding      misfolded->mature
Activation     inactivated->mature
Inactivation   mature->inactivated
Damage         Damaged complex->damaged monomer
Enzymatic Use  mature->bound
              bound->mature (upon completion)

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 1/5/2011
```

### RNAPolymerase

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/RNAPolymerase.m`


```
RNA Polymerase

@wholeCellModelID State_RNAPolymerase
@name             RNA Polymerases
@description

  states represents the current state / pseudostate (actively
  transcribing, specifically bound, non-specifically bound, free,
  non-existent) of each RNA polymerase, where each state is indicated by the
  enumeration:
  - rnaPolymeraseActivelyTranscribingValue
  - rnaPolymeraseSpecificallyBoundValue
  - rnaPolymeraseNonSpecificallyBoundValue
  - rnaPolymeraseFreeValue
  - rnaPolymeraseNotExistValue (state exists as a way to account for memory
    allocated for future RNA polymerases)

Information about positions of the polymerases on the DNA and the
progress of RNA polymerases transcribing specific transcrips is all
contained within the chromosomeState class and newTranscriptState class.

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 12/13/2010
```

### Ribosome

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Ribosome.m`


```
Ribosome

@wholeCellModelID State_Ribosome
@name             Ribosome
@description


Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2011
```

### Rna

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Rna.m`


```
Rna
1. nascent
2. processed
3. intergenic segments
4. modified
5. bound
6. misfolded
7. damaged
8. aminoacylated

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 1/5/2011
```

### Stimulus

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Stimulus.m`


```
Stimulus

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 1/5/2011
```

### Time

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Time.m`


```
Time

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last Updated: 1/5/2011
```

### Transcript

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Transcript.m`


```
Transcripts

@wholeCellModelID State_Transcript
@name             Transcripts
@description


Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 12/16/2010
```
