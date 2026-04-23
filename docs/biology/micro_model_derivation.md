# Micro-Model Analytical Derivation (Gate G1.1)

## Purpose
Verify our simulation engine against a **textbook analytical solution** with
**published parameters**. If we can't reproduce a result that undergraduates
solve on paper, nothing else we build can be trusted.

## Model Choice
We use the **constitutive gene expression model** — the simplest and most
well-studied system in quantitative biology. This model appears in:

- Alon, U. (2006). *An Introduction to Systems Biology*, Chapter 1, Box 1.1.
  DOI: 10.1201/9781420011432
- Thattai, M. & van Oudenaarden, A. (2001). *Intrinsic noise in gene regulatory
  networks*. PNAS 98(15), 8614–8619. DOI: 10.1073/pnas.151588598

Both provide the exact analytical solution (deterministic) and the noise
statistics (stochastic). Our simulation must match both.

## System Definition

### Components
| Species | Symbol | Description | Unit |
|---------|--------|-------------|------|
| mRNA    | m      | Messenger RNA transcript | copies/cell |
| Protein | p      | Translated protein | copies/cell |

The gene (DNA) is implicit and constant — constitutive expression means
it's always "on" at a fixed rate.

### Reactions

**R1: Transcription** (constitutive)
```
∅ --[α_m]--> m
```
- Rate: v₁ = α_m (constant, zero-order in mRNA)

**R2: mRNA Degradation** (first-order)
```
m --[β_m]--> ∅
```
- Rate: v₂ = β_m · m

**R3: Translation** (first-order in mRNA)
```
m --[α_p]--> m + p     (mRNA is catalyst)
```
- Rate: v₃ = α_p · m

**R4: Protein Degradation/Dilution** (first-order)
```
p --[β_p]--> ∅
```
- Rate: v₄ = β_p · p

### ODE System

```
dm/dt = α_m − β_m · m

dp/dt = α_p · m − β_p · p
```

This is a **linear cascade**: mRNA drives protein, but protein does not
feed back to mRNA. The system is analytically solvable in closed form.

## Parameters

We use values from Thattai & van Oudenaarden (2001), **Table 1 and Figure 2
legend**. The paper states: *"All rates in units of min⁻¹."*

| Parameter | Symbol | Value | Unit | Source | Verification |
|-----------|--------|-------|------|--------|--------------|
| Transcription rate | k₁ (α_m) | 0.30 | min⁻¹ | Thattai 2001, Table 1 | UNVERIFIED_WEB |
| mRNA degradation rate | γ₁ (β_m) | 0.023 | min⁻¹ | Thattai 2001, Table 1 / Fig 2 | UNVERIFIED_WEB |
| Translation rate | k₂ (α_p) | 5.0 | min⁻¹ | Thattai 2001, Table 1 | UNVERIFIED_WEB |
| Protein degradation rate | γ₂ (β_p) | 0.10 | min⁻¹ | Thattai 2001, Table 1 | UNVERIFIED_WEB |

**Notes on parameters:**
- k₁ has three values in Table 1 (0.15, 0.30, 0.60 min⁻¹). We use 0.30 (middle).
- γ₁ = 0.023 min⁻¹ → mRNA half-life = ln(2)/0.023 ≈ 30 min. This is notably
  longer than the "typical E. coli" value of ~3–5 min (Alon 2006 gives β_m ≈ 0.3 min⁻¹).
  Possible explanation: Thattai may model a specific stable transcript, or include
  only dilution-driven clearance. **This discrepancy should be resolved by reading
  the actual PDF.**
- γ₂ = 0.10 min⁻¹ → protein half-life = ln(2)/0.10 ≈ 6.9 min. This is faster
  than typical E. coli protein degradation (hours), suggesting it includes both
  active degradation and dilution, or models a rapidly turned-over protein.
- **Verification status: UNVERIFIED_WEB** — all values obtained via AI web search,
  not human-verified against the PDF. The original version of this document
  contained fabricated "mid-range" values that were 10-20× off from Table 1.

**Cross-reference with Alon (2006) Box 1.1 (typical E. coli):**

| Parameter | Thattai 2001 | Alon 2006 | Discrepancy |
|-----------|-------------|-----------|-------------|
| α_m | 0.30 /min | ~1 /min | 3× |
| β_m | 0.023 /min | ~0.3 /min | 13× |
| α_p | 5.0 /min | ~10 /min | 2× |
| β_p | 0.10 /min | ~0.023 /min | 4× |

These represent different biological scenarios. Alon describes "typical" rapidly-
degraded E. coli mRNA; Thattai appears to model a different regime.
**Resolution requires reading both sources in full.**

**Initial conditions:** m(0) = 0, p(0) = 0 (gene just turned on).

## Exact Analytical Solution

### mRNA (first-order linear ODE)
```
m(t) = (α_m / β_m) · (1 − e^(−β_m · t))
```

### Protein (driven first-order linear ODE)
For β_m ≠ β_p (which is always true biologically: mRNA turns over much faster
than protein):

```
p(t) = (α_m · α_p) / (β_m · β_p) · [1 + (β_p · e^(−β_m·t) − β_m · e^(−β_p·t)) / (β_m − β_p)]
```

This is the **Alon (2006) Box 1.1 solution**, verified in dozens of textbooks.

### Derivation sketch
1. Solve dm/dt = α_m − β_m·m → standard first-order with integrating factor
2. Substitute m(t) into dp/dt = α_p·m(t) − β_p·p → linear ODE with known forcing
3. Solve via integrating factor or variation of parameters

## Steady-State Values

At t → ∞:

| Species | Formula | Value | Unit |
|---------|---------|-------|------|
| m* | α_m / β_m | 0.30 / 0.023 = **13.04** | copies/cell |
| p* | (α_m · α_p) / (β_m · β_p) | (0.30 × 5.0) / (0.023 × 0.10) = **652.2** | copies/cell |

### Characteristic Timescales

| Process | Formula | Value | Interpretation |
|---------|---------|-------|----------------|
| mRNA equilibration | 1/β_m | 43.5 min | mRNA reaches ~63% of steady state |
| Protein equilibration | 1/β_p | 10.0 min | Protein reaches ~63% of steady state |
| Timescale separation | β_m/β_p | 0.23× | Unusual — protein turns over *faster* than mRNA |

**Note on timescale separation:** With these Thattai parameters, the protein
degrades faster than mRNA (β_p > β_m). This is atypical for E. coli but is
the parameter regime in their paper. The analytical solution still holds —
the math doesn't care which species is faster. For a more "typical" regime
(mRNA fast, protein slow), use Alon's parameters.

## Stochastic Benchmark (for tau-leaping validation)

Thattai & van Oudenaarden (2001) derived the exact noise statistics for this system:

### Protein variance at steady state
```
Var(p) = p* · (1 + b / (1 + β_p/β_m))
```
where **b = α_p / β_m** is the "burst size" (average proteins produced per mRNA
before it degrades).

With our parameters:
```
b = α_p / β_m = 5.0 / 0.023 ≈ 217.4
Var(p) = 652.2 · (1 + 217.4 / (1 + 0.10/0.023))
       = 652.2 · (1 + 217.4 / 5.348)
       = 652.2 · (1 + 40.65)
       ≈ 652.2 · 41.65
       ≈ 27,155
```

Fano factor: Var(p)/p* ≈ 27155/652 ≈ 41.6 (highly super-Poissonian, strong
translational bursting — consistent with high burst size b ≈ 217).

CV (coefficient of variation): √(27155)/652 ≈ 0.253 (25.3% noise).

## Verification Criteria

### Gate G1.2: Deterministic solver match
Run simulation to t = 2000 min (well past both equilibration times).
- m(t_end) must match m* ≈ 13.04 with relative error < 1e-8
- p(t_end) must match p* ≈ 652.2 with relative error < 1e-6
- m(t) and p(t) at intermediate timepoints must match analytical curves
  with relative error < 1e-5

### Gate G1.3: Cross-solver agreement
JAX/Diffrax and SciPy/BDF must agree within relative tolerance 1e-5 at all
output timepoints.

### Gate G1.7: Oracle validation
PySCeS simulation of same system must agree with our output within 1e-4.

### Stochastic validation (tau-leaping)
Run 1000 independent stochastic simulations to steady state:
- Mean protein count should be within 10% of p* ≈ 652
- Variance should be within 30% of Var(p) ≈ 27,155
- No negative molecule counts in any run

## What This Model Does NOT Test

This micro-model deliberately omits:
- **Energy metabolism** (no ATP/ADP coupling)
- **Resource competition** (no shared substrates)
- **Multiple sub-model coupling** (single ODE system, no operator splitting)
- **Atom balance** (no atomic composition tracked)

These are tested separately:
- Energy coupling → separate benchmark after gate passes
- Resource competition → existing resource_ledger tests
- Sub-model coupling → bench_coupling.py (Producer+Consumer)
- Atom balance → Gate G1.4 (uses coupling benchmark, not this model)

## References

1. Alon, U. (2006). An Introduction to Systems Biology: Design Principles of
   Biological Circuits. Chapman & Hall/CRC. Chapter 1, Box 1.1.
   DOI: 10.1201/9781420011432

2. Thattai, M. & van Oudenaarden, A. (2001). Intrinsic noise in gene regulatory
   networks. PNAS 98(15), 8614–8619. DOI: 10.1073/pnas.151588598

3. Paulsson, J. (2005). Models of stochastic gene expression. Physics of Life
   Reviews 2(2), 157–175. DOI: 10.1016/j.plrev.2005.03.003
