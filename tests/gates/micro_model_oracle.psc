# Thattai & van Oudenaarden (2001) — constitutive gene expression.
# Paper DOI: 10.1073/pnas.151588598
# Figure 1 caption "base case" (see data/params/micro_model_thattai2001.yaml).
#
# Oracle model for Gate G1.7: independent third-party solver (PySCeS)
# must agree with our JAX and SciPy solvers within 1e-4 relative.

# --- Reactions ---
R1:
    $pool > mRNA
    kR

R2:
    mRNA > $pool
    gammaR * mRNA

R3:
    $pool > Protein
    kP * mRNA

R4:
    Protein > $pool
    gammaP * Protein

# --- Species (initial conditions) ---
mRNA = 0.0
Protein = 0.0

# --- Parameters (min^-1) ---
kR = 0.6
gammaR = 0.34657359027997264
kP = 6.9314718055994530
gammaP = 0.011552453009332421
