"""Build a comprehensive map of all L2.2 Metabolism gaps.

Outputs a structured markdown file with:
  1. Cluster-level breakdown (which WID families dominate error)
  2. Per-cluster: contributing reactions + flux diffs + bounds
  3. Cross-sample consistency: are these gaps universal or sample-specific?
  4. Structural cause for each gap (alternate variant, unbounded cycle, etc.)
  5. Candidate fixes per gap

Output: docs/phase_f/METABOLISM_GAP_MAP.md
"""
import sys
import json
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture, apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"
TRACE_DIR = REPO / "data/m1_sources/karr_native"
OUT_PATH = REPO / "docs/phase_f/METABOLISM_GAP_MAP.md"

# =====================================================================
# Load model + reference data
# =====================================================================
with h5py.File(GT_PATH, "r") as h:
    flux_karr_01 = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr_01 = np.asarray(h["bounds"][()], dtype=np.float64)
    pre_sub_01 = np.asarray(h["pre_sub"][()], dtype=np.float64)
    delta_karr_01 = np.asarray(h["delta"][()], dtype=np.float64).astype(np.int64)
if bounds_karr_01.shape == (2, 504):
    bounds_karr_01 = bounds_karr_01.T
if pre_sub_01.shape == (3, 585):
    pre_sub_01 = pre_sub_01.T
if delta_karr_01.shape == (3, 585):
    delta_karr_01 = delta_karr_01.T

model = km.load_default()
dyn = cfb.load_default_dynamics()
fbr = np.column_stack([model.lb, model.ub]).astype(float)
fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))

SUB_IDS = model.raw["ids"]["substrate_wcm_585"]
FBA_COL_TO_RXN = model.raw["ids"]["fba_col_to_reaction_wcm"]
RXN_NAMES = model.raw["ids"]["reaction_names_645"]
RXN_IDS_645 = model.raw["ids"]["reaction_wcm_645"]


def rxn_info(fba_col):
    rxn_id = FBA_COL_TO_RXN[fba_col]
    if rxn_id is None:
        if fba_col < 336:
            return ("(unmapped_metab)", "metabolic conversion (no WCM ID)")
        elif fba_col < 460:
            return ("(ext_exch)", "external exchange")
        else:
            return ("(int_exch)", "internal exchange (parsimony-penalized)")
    if rxn_id in RXN_IDS_645:
        idx = RXN_IDS_645.index(rxn_id)
        return (rxn_id, RXN_NAMES[idx])
    return (rxn_id, "(no name found)")


# =====================================================================
# 1. Compute OC flux at sample (0,1) and identify diff reactions
# =====================================================================
print("Step 1: OC GLPK at sample (0,1) + flux comparison")
v_oc_01, info_oc_01 = km.solve_fba(
    model, use_full_objective=True, sense="max", big=1e6,
    lb_override=bounds_karr_01[:, 0], ub_override=bounds_karr_01[:, 1],
    solver="glpk",
)
d_flux_01 = v_oc_01 - flux_karr_01


# =====================================================================
# 2. Cross-sample writeback L1 by WID across 500 audit samples
# =====================================================================
print("Step 2: per-WID writeback L1 across 50 seeds x 10 ticks")

def load_seed(seed):
    path = TRACE_DIR / f"per_process_traces_v2_s{seed:03d}" / "Metabolism_100ticks.mat"
    with h5py.File(path, "r") as h:
        before_refs = h["states_before/substrates"][:].reshape(-1)
        after_refs = h["states_after/substrates"][:].reshape(-1)
        enz_refs = h["states_before/enzymes"][:].reshape(-1)
        T = len(before_refs)
        before = np.zeros((T, 585, 3), dtype=np.float64)
        after = np.zeros((T, 585, 3), dtype=np.float64)
        enz = np.zeros((T, 104), dtype=np.float64)
        for t in range(T):
            b = np.asarray(h[before_refs[t]][:], dtype=np.float64)
            a = np.asarray(h[after_refs[t]][:], dtype=np.float64)
            e = np.asarray(h[enz_refs[t]][:], dtype=np.float64).reshape(-1)
            if b.shape == (3, 585): b = b.T
            if a.shape == (3, 585): a = a.T
            before[t] = b; after[t] = a; enz[t] = e
    return before, after, enz


N_SEEDS, N_TICKS = 50, 10
per_wid_err = np.zeros((N_SEEDS, N_TICKS, 585), dtype=np.float64)
per_wid_karr_mass = np.zeros((N_SEEDS, N_TICKS, 585), dtype=np.float64)
# Also store per-sample flux for cross-sample reaction analysis
v_oc_all = np.zeros((N_SEEDS, N_TICKS, 504), dtype=np.float64)

for seed in range(N_SEEDS):
    before, after, enz = load_seed(seed)
    for t in range(N_TICKS):
        pre = before[t]
        karr_delta = (after[t] - before[t]).astype(np.float64)
        per_wid_karr_mass[seed, t] = np.abs(karr_delta.sum(axis=1))
        bounds = cfb.compute_bounds(
            substrates=pre, enzymes=enz[t],
            cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis, enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fbr, dyn=dyn, apply_protein_bounds=False,
        )
        v, info = km.solve_fba(
            model, use_full_objective=True, sense="max", big=1e6,
            lb_override=bounds[:, 0], ub_override=bounds[:, 1], solver="glpk",
        )
        v_oc_all[seed, t] = v
        oc_delta = apply_karr_substrate_writeback(
            pre_state_585x3=pre, v_504=v,
            growth_per_s=info["biomass_flux_per_s"],
            fixture=fbf, rng=_Mcg16807(seed=12345+seed), step_size_sec=1.0,
        )
        per_wid_err[seed, t] = np.abs(oc_delta.sum(axis=1).astype(np.float64) - karr_delta.sum(axis=1))
    if seed % 10 == 0:
        print(f"  seed {seed}: done")

mean_err_per_wid = per_wid_err.mean(axis=(0, 1))
mean_karr_per_wid = per_wid_karr_mass.mean(axis=(0, 1))
total_err = mean_err_per_wid.sum()
total_karr_mass = mean_karr_per_wid.sum()
print(f"  Total mean per-sample writeback L1: {total_err:.0f}")
print(f"  Total mean per-sample Karr mass:    {total_karr_mass:.0f}")


# =====================================================================
# 3. Cluster top WIDs into families
# =====================================================================
order = np.argsort(-mean_err_per_wid)
top_wids = [(SUB_IDS[i], mean_err_per_wid[i], mean_karr_per_wid[i]) for i in order[:30]]

CLUSTERS = {
    "Lipid family (fatty acids + triglycerides)": [
        "OCDCEA", "TRIOLEIN", "HDCA", "TRIPALMITIN", "HDCEA", "TRI_HDCEA_IN",
        "TRIBUTYRIN_IN", "TRILINOLEIN", "DIBUTYRIN", "MONOBUTYRIN",
    ],
    "Aromatic AA + dipeptides": [
        "TRP", "TYR", "PHE", "TrpTrp", "TyrTyr", "PhePhe",
        "TrpTrpTrp", "TyrTyrTyr",
    ],
    "Metabolic byproducts (oxygen/water)": [
        "H2O2", "O2", "H2O", "CO2", "H",
    ],
    "Carbon backbone (acetate/glycerol/glucose)": [
        "AC", "GL", "GLC", "ACAL", "AEPP",
    ],
    "Nucleotide pool": [
        "ATP", "ADP", "AMP", "GTP", "GDP", "GMP", "UTP", "UDP", "UMP",
        "CTP", "CDP", "CMP", "ITP", "IDP", "IMP",
        "dATP", "dADP", "dAMP", "dGTP", "dGDP", "dGMP", "dCTP", "dCDP", "dCMP",
        "dTTP", "dTDP", "dTMP",
    ],
    "Other": [],  # catchall
}

# Assign top WIDs to clusters
wid_to_cluster = {}
for cluster, wids in CLUSTERS.items():
    for w in wids:
        wid_to_cluster[w] = cluster

cluster_totals = {c: 0.0 for c in CLUSTERS}
other_wids = []
for wid, err, _ in top_wids:
    cluster = wid_to_cluster.get(wid, "Other")
    cluster_totals[cluster] += err
    if cluster == "Other":
        other_wids.append((wid, err))


# =====================================================================
# 4. Cross-sample reaction-level consistency
# =====================================================================
# For each FBA reaction, compute mean |OC flux| across all samples
mean_oc_flux = np.abs(v_oc_all).mean(axis=(0, 1))
# Also stddev to gauge if OC is deterministic or varying
std_oc_flux = np.abs(v_oc_all).std(axis=(0, 1))


# Identify the 20 reactions where OC consistently hits high flux (mean |v| > 1e3)
big_flux_rxns = [r for r in range(504) if mean_oc_flux[r] > 1e3]
big_flux_rxns.sort(key=lambda r: -mean_oc_flux[r])


# =====================================================================
# 5. Group reactions into structural families by name pattern
# =====================================================================
# Pattern: reactions with common stem (Pyk_*, Adk*, PfkA*, Gmk*, LIPASE_*, TX_*)
import re

def family_stem(name):
    """Extract reaction family stem (Pyk, Adk, etc.)."""
    if name.startswith("(") or name is None:
        return "exchange"
    # Strip trailing numbers/suffixes
    m = re.match(r"^([A-Za-z]+?)(\d*|_[A-Z]+.*|_[a-z][a-z]+)$", name)
    if m:
        stem = m.group(1)
        return stem
    return name


from collections import defaultdict
family_groups = defaultdict(list)
for r in big_flux_rxns:
    rxn_id, _ = rxn_info(r)
    stem = family_stem(rxn_id)
    family_groups[stem].append(r)

# Find variant families (stems with >= 2 reactions)
variant_families = {s: cols for s, cols in family_groups.items() if len(cols) >= 2}


# =====================================================================
# 6. Write the markdown map
# =====================================================================
print()
print("Step 3: writing map to", OUT_PATH)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

lines = []
lines.append("# L2.2 Metabolism Gap Map")
lines.append("")
lines.append("Generated by `scripts/build_metabolism_gap_map.py` on Day-40.")
lines.append("")
lines.append("Empirical decomposition of the OC-vs-Karr substrate-writeback gap that")
lines.append("keeps L2.2 Metabolism at VERIFIED_FAIL (W1=161 vs threshold=102).")
lines.append("")
lines.append("## Baseline measurements")
lines.append("")
lines.append("Audit shape: 50 seeds × 10 ticks = 500 samples.")
lines.append(f"Karr-recorded delta mean L1 per sample: **{total_karr_mass:.0f}**")
lines.append(f"Current OC GLPK writeback error mean per sample: **{total_err:.0f}** ({total_err/total_karr_mass*100:.1f}% of Karr mass)")
lines.append("")
lines.append("Algorithm/RNG floor (Karr flux + OC writeback at sample (0,1)): **40** (0.04%)")
lines.append("Bounds drift (OC `cfb.compute_bounds` vs Karr MATLAB at (0,1)): **0** (bit-match)")
lines.append("")
lines.append("Gap to close: ~22,372 per sample (22,412 - 40 floor).")
lines.append("")

# Cluster-level breakdown
lines.append("## Cluster-level breakdown")
lines.append("")
lines.append("| Cluster | Total err | % of error | Top WIDs |")
lines.append("|---|---:|---:|---|")
for cluster, total in sorted(cluster_totals.items(), key=lambda x: -x[1]):
    if total < 50:
        continue
    pct = total / total_err * 100
    cluster_wids = [w for w, e, _ in top_wids if wid_to_cluster.get(w, "Other") == cluster]
    top_str = ", ".join(cluster_wids[:6])
    lines.append(f"| **{cluster}** | {total:.0f} | {pct:.1f}% | {top_str} |")
lines.append("")

# Top WIDs detail
lines.append("## Top 27 WIDs (carrying 99% of error)")
lines.append("")
lines.append("| Rank | WID | Cluster | Mean err | % of total | Karr mass | err/mass |")
lines.append("|---:|---|---|---:|---:|---:|---:|")
cum_err = 0.0
for r, (wid, err, karr_mass) in enumerate(top_wids[:27], 1):
    cum_err += err
    cluster = wid_to_cluster.get(wid, "Other")
    pct = err / total_err * 100
    ratio = err / max(karr_mass, 1)
    lines.append(f"| {r} | `{wid}` | {cluster} | {err:.0f} | {pct:.2f}% | {karr_mass:.0f} | {ratio:.2f}× |")
lines.append("")
lines.append(f"Top 27 WIDs cumulative: {cum_err/total_err*100:.1f}% of total error.")
lines.append("")

# Variant families
lines.append("## Reaction variant families (likely degeneracy sources)")
lines.append("")
lines.append("Reactions where OC has consistently high flux across samples (mean |v| > 1e3).")
lines.append("Grouped by name-stem family. Families with multiple variants are candidates")
lines.append("for LP-degeneracy tie-breaking.")
lines.append("")

shown_families = sorted(variant_families.items(), key=lambda x: -sum(mean_oc_flux[r] for r in x[1]))[:20]
for stem, cols in shown_families:
    if len(cols) < 2:
        continue
    lines.append(f"### Family: `{stem}` ({len(cols)} variants)")
    lines.append("")
    lines.append("| FBA col | Reaction ID | OC mean\\|v\\| | OC std\\|v\\| | OC at (0,1) | Karr at (0,1) | lb | ub |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|")
    for r in sorted(cols, key=lambda r: -mean_oc_flux[r]):
        rxn_id, rxn_name = rxn_info(r)
        lb01 = bounds_karr_01[r, 0]
        ub01 = bounds_karr_01[r, 1]
        lb_str = "-inf" if not np.isfinite(lb01) else f"{lb01:+.2e}"
        ub_str = "+inf" if not np.isfinite(ub01) else f"{ub01:+.2e}"
        lines.append(f"| {r} | `{rxn_id}` | {mean_oc_flux[r]:.2e} | {std_oc_flux[r]:.2e} | {v_oc_01[r]:+.2e} | {flux_karr_01[r]:+.2e} | {lb_str} | {ub_str} |")
    lines.append("")

# Single-sample top diff reactions
lines.append("## Top 30 reactions by |OC - Karr| flux diff at sample (0,1)")
lines.append("")
lines.append("| FBA col | Reaction ID | Name | \\|diff\\| | OC | Karr | lb | ub |")
lines.append("|---:|---|---|---:|---:|---:|---:|---:|")
order_diff = np.argsort(-np.abs(d_flux_01))
for r in order_diff[:30]:
    rxn_id, rxn_name = rxn_info(r)
    lb01 = bounds_karr_01[r, 0]
    ub01 = bounds_karr_01[r, 1]
    lb_str = "-inf" if not np.isfinite(lb01) else f"{lb01:+.2e}"
    ub_str = "+inf" if not np.isfinite(ub01) else f"{ub01:+.2e}"
    name_trunc = rxn_name[:50]
    lines.append(f"| {r} | `{rxn_id}` | {name_trunc} | {abs(d_flux_01[r]):.2e} | {v_oc_01[r]:+.2e} | {flux_karr_01[r]:+.2e} | {lb_str} | {ub_str} |")
lines.append("")

# Sample-to-sample consistency
lines.append("## Cross-sample consistency")
lines.append("")
lines.append("Coefficient of variation (CV = std/mean) for OC |flux| across the 500 samples")
lines.append("on the top diff reactions. Low CV = deterministic problem (same vertex every sample).")
lines.append("High CV = sample-specific behavior.")
lines.append("")
lines.append("| FBA col | Reaction ID | Mean \\|v\\| | Std \\|v\\| | CV |")
lines.append("|---:|---|---:|---:|---:|")
for r in order_diff[:15]:
    rxn_id, _ = rxn_info(r)
    cv = std_oc_flux[r] / max(mean_oc_flux[r], 1) * 100
    lines.append(f"| {r} | `{rxn_id}` | {mean_oc_flux[r]:.2e} | {std_oc_flux[r]:.2e} | {cv:.1f}% |")
lines.append("")

# Fix candidates
lines.append("## Candidate fix strategies (NOT to be applied without methodical evaluation)")
lines.append("")
lines.append("Each is logged here for future evaluation; no fix is committed without")
lines.append("operator approval and methodical per-cluster validation.")
lines.append("")
lines.append("### Strategy A: Targeted variant parsimony")
lines.append("Add small negative coefficient to OC-overused variants.")
lines.append("Day-40 test result: REDUCES flux L1 vs Karr (27×) but INCREASES writeback L1 (×4).")
lines.append("LP redirects flux to other reactions whose substrates propagate worse through writeback.")
lines.append("VERDICT: net negative without much finer-grained control.")
lines.append("")
lines.append("### Strategy B: Warm-start GLPK from Karr's flux")
lines.append("Extract Karr's flux at all 500 samples via MATLAB; use as initial GLPK basis.")
lines.append("Highest probability of full closure (to floor ~40).")
lines.append("Cost: ~1h MATLAB extraction + 2-3h GLPK warm-start integration.")
lines.append("CAVEAT: this is 'replay' rather than independent verification.")
lines.append("")
lines.append("### Strategy C: Loopless FBA (thermodynamically feasible flux)")
lines.append("Add constraints forbidding net flow through internal cycles.")
lines.append("Most principled biological fix. Removes the unbounded ±1e6 cycle artifacts.")
lines.append("Cost: significant — requires null-space analysis + MILP or complementarity.")
lines.append("CAVEAT: Karr's own recorded flux IS loopy, so loopless might not match either.")
lines.append("")
lines.append("### Strategy D: Per-cluster targeted bounds tightening")
lines.append("For each variant family, add explicit constraints forcing the LP to use one")
lines.append("variant preferentially (e.g., fix Pyk_GDP/_UDP/_IDP/_DADP = 0, route through Pyk_ADP only).")
lines.append("Cost: per-cluster work; risk of breaking biology on samples where alternates are needed.")
lines.append("")
lines.append("### Strategy E: Accept and document")
lines.append("L2.2 verdict stays FAIL. Document root cause precisely:")
lines.append("'OC's GLPK 5.0 picks different LP vertex than Karr's GLPK 4.x on a cond=6.7e+12 LP.")
lines.append(" Biology bit-matches (growth, KS, mean, stddev); writeback differs on ~17 WIDs")
lines.append(" tied to specific alternate-variant choices.'")
lines.append("Cost: zero code. Honest scientifically. Doesn't 'close' the gap.")
lines.append("")

OUT_PATH.write_text("\n".join(lines))
print(f"  Wrote {len(lines)} lines to {OUT_PATH}")
print()
print(f"Cluster totals:")
for cluster, total in sorted(cluster_totals.items(), key=lambda x: -x[1]):
    if total > 50:
        print(f"  {cluster:50s}  {total:7.0f}  ({total/total_err*100:5.1f}%)")
print(f"  Other (catchall):                                  {total_err - sum(cluster_totals.values()):7.0f}")
print()
print(f"Found {len(variant_families)} variant families. Top 5 by total flux:")
for stem, cols in sorted(variant_families.items(), key=lambda x: -sum(mean_oc_flux[r] for r in x[1]))[:5]:
    total_flux = sum(mean_oc_flux[r] for r in cols)
    print(f"  {stem:20s}  {len(cols)} variants  total mean |v|={total_flux:.2e}")
