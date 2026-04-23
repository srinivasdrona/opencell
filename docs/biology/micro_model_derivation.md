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

Values from Thattai & van Oudenaarden (2001), **Figure 1 caption "base case"**
(verified against the PDF on 2026-04-23 — the paper has **no** Table 1).

> Verbatim quote (Fig. 1c caption, p. 8615):
> *"The mRNA half-life is fixed at 2 min. The base case corresponds to a
> burst size b = 20, a transcript initiation rate k_R = 0.01 s⁻¹ and a
> protein half-life ln(2)/g_P = 1 h."*

| Parameter | Symbol | Paper value | Internal value (min⁻¹) | Source | Verification |
|-----------|--------|-------------|------------------------|--------|--------------|
| Transcription rate | k_R (α_m) | 0.01 s⁻¹ | **0.60** | Fig. 1 caption | PDF-verified |
| mRNA decay | γ_R (β_m) | t½ = 2 min | **ln(2)/2 ≈ 0.3466** | Fig. 1 caption | PDF-verified |
| Translation rate | k_P (α_p) | b = 20 (derived) | **20·ln(2)/2 ≈ 6.9315** | Fig. 1 caption | PDF-verified |
| Protein decay | γ_P (β_p) | t½ = 1 h | **ln(2)/60 ≈ 0.01155** | Fig. 1 caption | PDF-verified |

**Transformations applied:**
- k_R: unit conversion s⁻¹ → min⁻¹ (×60).
- γ_R, γ_P: half-life → first-order rate constant (γ = ln 2 / t½).
- k_P: derived from burst-size definition b = k_P / γ_R, so k_P = b × γ_R.
  (The paper does not state k_P directly.)

**Cross-reference with E. coli literature:**

| Parameter | Thattai 2001 | Cross-source | Agreement |
|-----------|--------------|--------------|-----------|
| γ_R = 0.347 /min (t½=2 min) | Bernstein 2002 PNAS: median t½ ~5 min (γ≈0.14) | within E. coli range |
| γ_R = 0.347 /min | Alon 2006 typical β_m ~0.3 /min | matches |
| γ_P = 0.01155 /min (t½=1 h) | Alon 2006 dilution-dominated ~0.023 /min | same OOM |
| k_P = 6.93 /min | Alon 2006 typical α_p ~10 /min | same OOM |
| k_R = 0.6 /min | Alon 2006 typical ~1 /min | same OOM |

**Provenance history (preserved as institutional memory):**
1. Round 1 (synthetic): values 0.2, 0.5, 0.5, 0.005 — invented; no source.
2. Round 2 ("Table 1"): values 0.30, 0.023, 5.0, 0.10 — fabricated quote
   (paper has no Table 1); values 2× to 15× off from real "base case".
3. Round 3 (this document): values from Fig. 1 caption, PDF in hand.

The Round-2 failure is the canonical example for our parameter-verification
system: cross-source numerical agreement and confident citations are not
sufficient evidence — only direct PDF reading by a human is.

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
| m* | k_R / γ_R | 0.60 / 0.34657 ≈ **1.731** | copies/cell |
| p* | (k_R · k_P) / (γ_R · γ_P) | (0.60 × 6.9315) / (0.34657 × 0.011552) ≈ **1038.7** | copies/cell |

### Characteristic Timescales

| Process | Formula | Value | Interpretation |
|---------|---------|-------|----------------|
| mRNA equilibration | 1/γ_R | 2.89 min | mRNA reaches ~63% of steady state |
| Protein equilibration | 1/γ_P | 86.6 min | Protein reaches ~63% of steady state |
| Timescale separation | γ_R/γ_P | 30× | mRNA fast, protein slow (typical E. coli) |

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
b = k_P / γ_R = 20  (by construction — this is the paper's base case)
Var(p) = 1038.7 · (1 + 20 / (1 + 0.01155/0.34657))
       = 1038.7 · (1 + 20 / 1.03333)
       = 1038.7 · (1 + 19.355)
       ≈ 1038.7 · 20.355
       ≈ 21,145
```

Fano factor: Var(p)/p* ≈ 21145/1038.7 ≈ 20.36 (highly super-Poissonian, strong
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
