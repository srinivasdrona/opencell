# L2.2 Metric-by-Process-Character Design

## Authoritative Quotations

### PROCESS_CATALOG.yaml

Source: `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:72-76,380-392,540-548`

```text
72:  EVENT_CLASS:
73:    in_scope_L2_2: true
74:    harness_type: event_class
75:    test_required: L2.event ensemble (event-aligned, not tick-aligned)
76:    rationale: "Process fires << 1 event per 100 ticks (singular per-cell-cycle events). Tick-level distribution undefined; events compared in their natural window. L2.event harness must be built; in interim, design_a_per_tick runner MUST refuse these processes (not silently produce zero-W1 fake PASS)."

380:  - name: Metabolism
381:    oc_module: opencell/vivarium/karr_metabolism.py
382:    bucket: TRIVIAL_RNG
383:    in_scope_L2_2: true
384:    M_ticks: 20
385:    N_seeds: 50
386:    event_density: dense                  # ~1e6 flux updates/tick
387:    input_channels: [substrates, enzymes]
388:    output_channels: [substrates]
389:    primary_channel: substrates
390:    karr_artifact: per_process_traces_v2
391:    rationale_M: "FBA deterministic, only stochasticRound is RNG; small M sufficient for confirmation"
392:    notes: "PRIORITY: also serves as SB-4 noise-floor anchor (cleanest TRIVIAL-RNG; L2.1 lambda already GREEN). Run FIRST under Design-A to establish W1 noise floor for SHALLOW/DEEP thresholds."

540:tallies:
541:  total_canonical_karr_processes: 28
542:  in_scope_L2_2_design_a:
543:    ALGORITHMIC_DEEP: 4
544:    ALGORITHMIC_SHALLOW: 14
545:    TRIVIAL_RNG: 4
546:  out_of_scope:
547:    DETERMINISTIC: 6
548:  estimated_total_in_scope: 22
```

### metabolism.toml

Source: `data/schemas/per_process/metabolism.toml:18-27,32-37,50-64`

```text
18:[observables.boundEnzymes]
19:pool = "enzymes"
20:shape = [1, 104]
21:
22:[observables.enzymes]
23:pool = "enzymes"
24:shape = [1, 104]
25:
26:[observables.substrates]
27:pool = "substrates"

32:enzymes_mutated_ticks = 0
33:substrates_mutated_ticks = 100
34:monomers_mutated_ticks = 0
35:per_observable = { boundEnzymes = 0, enzymes = 0, substrates = 100 }
36:trace_hint_keys = []
37:pass_through = ["boundEnzymes", "enzymes"]

50:oc_module = "karr_metabolism"
51:oc_class = "KarrMetabolismProcess"
52:oc_source = "opencell/vivarium/karr_metabolism.py"
53:
54:[extractor_diagnostics.state_group_counts]
55:substrates = 585
56:enzymes = 104
57:monomers = 0
58:complexs = 0
59:rnas = 0
60:source_attrs = 2
61:
62:[extractor_diagnostics.cross_check]
63:substrates = { status = "oc_missing", fixture_count = 585, oc_count = 0, only_in_fixture = ["A23CMP", "A3MP", "AC", "ACAL", "ACCOA", "ACTP", "AD", "ADN", "ADP", "AEPP", "AHCYS", "AKG", "ALA", "AMET", "AMP", "AMP_Lysine", "AMP_Mor", "AMP_NH2", "ARG", "ASN", "ASP", "ATP", "AlaAla", "ArgArg", "AsnAsn", "AspAsp", "BUT", "C23CMP", "C3MP", "CA", "CAP", "CDP", "CDPDG120", "CDPDG140", "CDPDG141", "CDPDG160", "CDPDG161", "CDPDG180", "CDPDG181", "CH3OH", "CHOL", "CHP", "CITR", "CL", "CL160", "CL161", "CL181", "CMP", "CO", "CO2"], only_in_oc = [], only_in_fixture_truncated = 535, only_in_oc_truncated = 0 }
64:enzymes = { status = "match", fixture_count = 104, oc_count = 104, only_in_fixture = [], only_in_oc = [], only_in_fixture_truncated = 0, only_in_oc_truncated = 0 }
```

### l2_2_design_a_runner.py

Source: `tests/vivarium/l2_2_design_a_runner.py:338-363,598-618,1020-1049`

```text
338:def _channel_verdict(
339:    *,
340:    w1_oc_vs_karr: float,
341:    q95_null: float,
342:    threshold: float,
343:    n_nonzero_oc: int,
344:    n_nonzero_karr: int,
345:) -> str:
346:    if n_nonzero_karr >= 30 and n_nonzero_oc == 0:
347:        return "FAIL"
348:    if n_nonzero_oc < 30 or n_nonzero_karr < 30:
349:        return "INSUFFICIENT_SAMPLES"
350:    if w1_oc_vs_karr <= q95_null:
351:        return "SEED_NOISE"
352:    if w1_oc_vs_karr <= threshold:
353:        return "PASS"
354:    return "FAIL"
357:def _process_verdict(channel_verdicts: list[str]) -> str:
358:    gateable = [verdict for verdict in channel_verdicts if verdict not in {"EVENT_CHANNEL_DEFERRED", "INSUFFICIENT_SAMPLES"}]
359:    if not gateable:
360:        return "NO_GATEABLE_CHANNELS"
361:    if any(verdict == "FAIL" for verdict in gateable):
362:        return "FAIL"
363:    return "PASS"

598:def _validate_process_request(process: str) -> None:
606:    # v3 harness routing: refuse processes not destined for this harness.
607:    # design_a_per_tick is the only harness this runner implements.
608:    harness_type = entry.get("harness_type") or entry.get("_bucket_harness_type")
609:    if harness_type and harness_type != "design_a_per_tick":
610:        bucket = entry.get("bucket", "unknown")
611:        raise ValueError(
612:            f"Process {process!r} requires harness_type={harness_type!r} but this runner "
613:            f"only implements design_a_per_tick. bucket={bucket}. "
614:            f"Catalog entry's notes field for the rationale. "
615:            f"In particular, EVENT_CLASS processes (event_density:sparse + seed_window) "
616:            f"silently produce zero-W1 fake PASSes through this harness because their "
617:            f"sparse events do not fire in the 100-tick replay window. The L2.event "
618:            f"harness needs to be built; until then, do not gate these processes here."

1020:    for channel in gateable_output_channels:
1021:        null_stats = runner_helpers.compute_null_q95(
1022:            karr_vectors=after_vectors[channel],
1023:            bootstrap_B=int(bootstrap_B),
1024:        )
1025:        w1_oc_vs_karr = float(np.mean(per_sample_w1[channel]))
1026:        threshold = max(runner_helpers.ABSOLUTE_FLOOR, k_eng * float(null_stats["q95_null"]))
1027:        flat_oc = oc_vectors[channel].reshape(-1)
1028:        flat_karr = after_vectors[channel].reshape(-1)
1029:        ks_stat, ks_pvalue = ks_2samp(flat_oc, flat_karr)
1030:        ci95 = _bootstrap_ci(
1031:            oc_vectors=oc_vectors[channel],
1032:            karr_vectors=after_vectors[channel],
1033:            bootstrap_B=int(bootstrap_B),
1034:            rng_seed=runner_helpers.L2_2_VALIDATION_SEED,
1035:        )
1036:        channel_payloads[channel] = {
1037:            "verdict": _channel_verdict(
1038:                w1_oc_vs_karr=w1_oc_vs_karr,
1039:                q95_null=float(null_stats["q95_null"]),
1040:                threshold=float(threshold),
1041:                n_nonzero_oc=int(np.count_nonzero(flat_oc)),
1042:                n_nonzero_karr=int(np.count_nonzero(flat_karr)),
1043:            ),
1044:            "w1_oc_vs_karr": w1_oc_vs_karr,
1045:            "w1_oc_vs_karr_ci95": ci95,
1046:            "q95_null": float(null_stats["q95_null"]),
1047:            "threshold": float(threshold),
1048:            "absolute_floor": float(runner_helpers.ABSOLUTE_FLOOR),
1049:            "ks_stat": float(ks_stat),
```

### _l2_2_design_a_projections.py

Source: `tests/vivarium/_l2_2_design_a_projections.py:152-178,191-230`

```text
152:    oc = np.asarray(oc_projections, dtype=np.float64)
153:    karr = np.asarray(karr_projections, dtype=np.float64)
154:    if oc.shape != karr.shape:
155:        raise ValueError(f"Projection tensors must match shape; got {oc.shape} vs {karr.shape}")
156:    if oc.ndim != 3:
157:        raise ValueError(f"Expected projection tensors with shape (seed, tick, component); got {oc.shape}")
159:    component_names = list(component_scales)
160:    if len(component_names) != oc.shape[2]:
161:        raise ValueError(
162:            "component_scales must provide exactly one scale per projection component; "
163:            f"got {len(component_names)} names for {oc.shape[2]} components"
164:        )
171:    joint_pass = True
172:    for idx, component_name in enumerate(component_names):
173:        scale = float(component_scales[component_name])
176:        raw_w1 = float(wasserstein_distance(oc[:, :, idx].reshape(-1), karr[:, :, idx].reshape(-1)))
177:        scaled_w1 = raw_w1 / max(scale, _EPSILON)
178:        verdict = "PASS" if scaled_w1 <= _SCALED_DISTANCE_THRESHOLD else "FAIL"

191:) -> dict[str, Any]:
192:    oc = np.asarray(oc_projections, dtype=np.float64)
193:    karr = np.asarray(karr_projections, dtype=np.float64)
194:    if oc.shape != karr.shape:
195:        raise ValueError(f"Projection tensors must match shape; got {oc.shape} vs {karr.shape}")
196:    if oc.ndim != 3:
197:        raise ValueError(f"Expected projection tensors with shape (seed, tick, component); got {oc.shape}")
198:    if oc.shape[2] < 1:
199:        raise ValueError("Hurdle distance requires at least one projection component")
201:    oc_event_mask = oc[:, :, 0].reshape(-1) > 0.0
202:    karr_event_mask = karr[:, :, 0].reshape(-1) > 0.0
203:    event_rate_diff = float(abs(np.mean(oc_event_mask) - np.mean(karr_event_mask)))
211:    for idx in range(1, oc.shape[2]):
213:        oc_values = oc[:, :, idx].reshape(-1)[oc_event_mask]
214:        karr_values = karr[:, :, idx].reshape(-1)[karr_event_mask]
215:        if oc_values.size == 0 and karr_values.size == 0:
216:            raw_w1 = 0.0
217:            scale = 1.0
218:        elif oc_values.size == 0 or karr_values.size == 0:
219:            # Asymmetric empty: one side fired events, the other didn't.
226:            raw_w1 = float(wasserstein_distance(oc_values, karr_values))
227:            scale = _default_scale(karr_values)
228:        else:
229:            raw_w1 = float(wasserstein_distance(oc_values, karr_values))
230:            scale = _default_scale(karr_values)
```

### METABOLISM_POSTMORTEM_DAY40.md

Source: `docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:53-60,94-106,129-141,147-150`

```text
53:Today's investigation found:
54:- The LP cond = 6.7e+12 (numerically degenerate)
55:- 8 reactions have lb=-inf, ub=+inf (unbounded thermodynamically-infeasible cycles)
56:- 27 LIPASE-family reactions form a cyclical "free" subnet
57:- 7 Pyk variants, 5 PfkA variants, 3 Adk variants, 4 Gmk variants are kinetically-equivalent isoforms
58:- Karr's GLPK 4.x basis happens to favor specific variants; HiGHS/GLPK 5.0 don't
60:Swapping HiGHS → GLPK 5.0 + presolve=OFF closed 82% of writeback L1 (124,551 → 22,412 per sample). The remaining 22K is structural LP-degeneracy between GLPK 4.x and GLPK 5.0 + alternative pathway choice.

94:### RC3 — We didn't audit the LP's degeneracy structure before designing the L2.2 trace-replay test
96:L2.2's design assumes Karr's recorded substrate distributions are canonical "ground truth". For a non-degenerate LP, that's fine. For an LP with cond=6.7e+12 and 8 unbounded cycle dimensions, Karr's "ground truth" is actually "one of many degenerate optima that GLPK 4.x happened to pick on Karr's specific machine".
98:An LP-degeneracy audit (one probe run) would have shown:
99:- cond(S) = 6.7e+12
100:- 8 reactions have lb=-∞, ub=+∞
101:- Null-space dimension = 128 (504 - 376)
102:- 6 enzyme variant families (Pyk×7, Adk×3, PfkA×5, Gmk×4, ...)
106:**The lesson:** before designing a test against a mathematical object, audit the object. For LPs, this means cond, null-space, and bound-finiteness.

129:4. **Match Karr's solver family** — GLPK via swiglpk — as the default. Pin solver version in setup.py.
130:5. **Port Karr's full FBA discipline**: solver options (`presolve=OFF, scale=AUTO, tolbnd=1e-6`), post-clip, 4-step writeback. All seven steps, named and tested individually.
131:6. **Design L2.2 around invariants**, not trace-replay. Test: "biomass within X%, mass conservation, KS distance <Y for each substrate distribution". Trace-replay can be a SEPARATE regression test, not the primary acceptance gate.
137:1. **Mandatory upstream-source read-through** before any port. Document the algorithm steps as a call-graph in the design doc. Reviewer must verify call-graph matches upstream.
138:2. **Mandatory "exact answer" smoke test** as Gate 0 of any port. Bit-match within FP tolerance against published reference. No looser thresholds at this gate.
139:3. **Mandatory pre-test object audit** for any test built against a mathematical object. For LPs: cond, null-space, bound-finiteness. For ODEs: stiffness, conservation laws. For Markov chains: ergodicity, transition-matrix structure.
140:4. **Architectural re-audit after every 3rd patch** in the same module. Compare current call-graph to upstream call-graph.
141:5. **Default validation threshold = bit-match.** Looser tolerances only with documented justification and explicit operator sign-off.

147:- **Current state**: writeback L1 = 22,412 per sample (vs 124,551 with HiGHS). 82% improvement landed by switching to GLPK + presolve=OFF + Karr's options.
148:- **Remaining**: 22K is structurally split into 4 clusters (aromatic AA + dipeptides, lipid family, byproducts, carbon backbone) of which we have a per-WID map in `METABOLISM_GAP_MAP.md`.
149:- **Each cluster** is a separate variant-family or unbounded-cycle problem. Each can be fixed independently with documented intervention.
150:- **L2.2 metric itself**: even after closing all variant-family gaps, W1 may not reach below threshold if Karr's recorded trace embeds GLPK 4.x-specific basis noise. That's a separate methodological question (RC3 above).
```

### METABOLISM_GAP_MAP.md

Source: `docs/phase_f/METABOLISM_GAP_MAP.md:5-17,21-30,32-62,280-281`

```text
5:Empirical decomposition of the OC-vs-Karr substrate-writeback gap that
6:keeps L2.2 Metabolism at VERIFIED_FAIL (W1=161 vs threshold=102).
10:Audit shape: 50 seeds × 10 ticks = 500 samples.
11:Karr-recorded delta mean L1 per sample: **109393**
12:Current OC GLPK writeback error mean per sample: **22409** (20.5% of Karr mass)
14:Algorithm/RNG floor (Karr flux + OC writeback at sample (0,1)): **40** (0.04%)
15:Bounds drift (OC `cfb.compute_bounds` vs Karr MATLAB at (0,1)): **0** (bit-match)
17:Gap to close: ~22,372 per sample (22,412 - 40 floor).

21:| Cluster | Total err | % of error | Top WIDs |
23:| **Aromatic AA + dipeptides** | 5945 | 26.5% | TRP, TYR, PHE, TrpTrp, TyrTyr, PhePhe |
24:| **Metabolic byproducts (oxygen/water)** | 5744 | 25.6% | H2O2, O2, H2O, CO2, H |
25:| **Lipid family (fatty acids + triglycerides)** | 5366 | 23.9% | OCDCEA, TRIOLEIN, HDCA, TRIPALMITIN, HDCEA, TRI_HDCEA_IN |
26:| **Carbon backbone (acetate/glycerol/glucose)** | 3795 | 16.9% | GL, AC, GLC, ACAL, AEPP |
30:## Top 27 WIDs (carrying 99% of error)

32:| Rank | WID | Cluster | Mean err | % of total | Karr mass | err/mass |
34:| 1 | `OCDCEA` | Lipid family (fatty acids + triglycerides) | 3708 | 16.55% | 2535 | 1.46× |
35:| 2 | `H2O2` | Metabolic byproducts (oxygen/water) | 2276 | 10.15% | 8692 | 0.26× |
36:| 3 | `O2` | Metabolic byproducts (oxygen/water) | 2234 | 9.97% | 8758 | 0.26× |
37:| 4 | `TRP` | Aromatic AA + dipeptides | 1802 | 8.04% | 5 | 349.05× |
38:| 5 | `TRIOLEIN` | Lipid family (fatty acids + triglycerides) | 1236 | 5.52% | 845 | 1.46× |
39:| 6 | `TYR` | Aromatic AA + dipeptides | 1196 | 5.34% | 28 | 43.29× |
40:| 7 | `GL` | Carbon backbone (acetate/glycerol/glucose) | 1130 | 5.04% | 6054 | 0.19× |
41:| 8 | `AC` | Carbon backbone (acetate/glycerol/glucose) | 1055 | 4.71% | 4376 | 0.24× |
42:| 9 | `PHE` | Aromatic AA + dipeptides | 966 | 4.31% | 1333 | 0.72× |
43:| 10 | `TrpTrp` | Aromatic AA + dipeptides | 901 | 4.02% | 3 | 350.85× |
44:| 11 | `H2O` | Metabolic byproducts (oxygen/water) | 721 | 3.22% | 17110 | 0.04× |
45:| 12 | `TyrTyr` | Aromatic AA + dipeptides | 598 | 2.67% | 14 | 43.39× |
46:| 13 | `GLC` | Carbon backbone (acetate/glycerol/glucose) | 592 | 2.64% | 2203 | 0.27× |
47:| 14 | `ACAL` | Carbon backbone (acetate/glycerol/glucose) | 513 | 2.29% | 182 | 2.82× |
48:| 15 | `AEPP` | Carbon backbone (acetate/glycerol/glucose) | 505 | 2.25% | 180 | 2.80× |
49:| 16 | `CAP` | Other | 496 | 2.22% | 439 | 1.13× |
50:| 17 | `PhePhe` | Aromatic AA + dipeptides | 483 | 2.15% | 666 | 0.72× |
51:| 18 | `CO2` | Metabolic byproducts (oxygen/water) | 481 | 2.15% | 4044 | 0.12× |
62:Top 27 WIDs cumulative: 99.1% of total error.

280:'OC's GLPK 5.0 picks different LP vertex than Karr's GLPK 4.x on a cond=6.7e+12 LP.
281: Biology bit-matches (growth, KS, mean, stddev); writeback differs on ~17 WIDs
```

### DECISIONS.md

Source: `D:/OneDrive - Microsoft/.pm-os/DECISIONS.md:22-24`

```text
22:### 2026-06-26 | opencell | metabolism-port-day-40-postmortem-rcs
23:**Decision**: Log the 5 root causes from the Day-40 L2.2 Metabolism gap post-mortem (`docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md`) as durable lessons for the remaining 27 Karr-process ports. RC1: ported the LP call but not Karr's full FBA discipline — solver options (`presol=1, scale=1, tolbnd=1e-6`), post-clip enforcement, 4-step `evolveState` substrate writeback were each missing initially or replaced by ad-hoc patches over time. RC2: initial validation threshold (`median |log2(predicted/karr_stored)| < 1.0` — a 2× per-reaction tolerance) was loose enough to mask LP-vertex divergence, BIG=1e3 vs Karr's 1e6, and the entirely-missing 4-step writeback. RC3: did not audit the LP's degeneracy structure (cond=6.7e+12, 128-dim null space, 8 unbounded reactions, 6 enzyme variant families) before designing L2.2 as trace-replay against Karr's recorded substrate distributions. RC4: shipped 6 patches (Bug 4, Bug 4-followup, Bug 6a-Stage1, Bug 6a-Stage2, Bug 6b, Bug 6c) to the same module without ever re-auditing the call-graph against Karr's `Metabolism.m::evolveState` — Day-37 discovered the 4-step writeback was never ported at all. RC5: did not recognise LP solver-family non-equivalence (HiGHS vs GLPK 4.x) as a porting risk; no "Karr's exact LP -> Karr's exact flux" smoke test at port time would have shown the divergence on day one.
24:**Why**: The L2.2 Metabolism FAIL (W1=161 vs threshold=102) is not a single bug but a chain of choices made at port time that each looked reasonable but compounded. The deepest pattern: we treated the FBA solve as deterministic when in fact the LP is highly degenerate; the writeback algorithm is the deterministic part. Six structural process improvements fall out: (1) mandatory upstream-source call-graph before any port, (2) mandatory "exact answer" bit-match smoke test as Gate 0, (3) mandatory pre-test object audit (LP: cond/null-space/bound-finiteness; ODE: stiffness/conservation; Markov: ergodicity), (4) architectural re-audit after every 3rd patch to same module, (5) default validation threshold = bit-match unless documented otherwise, (6) solver/library version pinning for any numerically-sensitive module. These apply to the other 27 Karr processes still pending L2 verification.
```

## DAP Intent

Contract:
- Replace the single-metric intuition behind current L2.2 per-process gating with a pre-registered mathematical-object audit that selects a named metric bundle before evaluation, so LP-degenerate processes are judged on interface fidelity plus controlled regression rather than on solver-vertex equivalence alone.

Surface inventory intent:
- Use the process catalog for current scope and harness routing, `metabolism.toml` for the Metabolism observable contract, the runner and projection helpers for current threshold semantics, and the Day-40 post-mortem plus gap map plus durable decision log for the empirical failure mode that this design must generalize from.

Falsifiable expectation:
- If this design is correct, a reviewer should be able to apply the audit to any current L2.2 process and deterministically choose the metric family before running the harness. Applied retroactively to Metabolism, the audit must classify it as LP-degenerate, preserve `trace_vertex_equivalence_w1` as informational, require a baseline-controlled `metabolism_regression_w1`, and refuse a clean `VERIFIED_GENUINE` verdict while the LP remains degenerate.

Inversion:
- The embarrassing failure mode is special pleading: the framework could appear principled while quietly being tuned around Metabolism after the fact, or it could allow aggregate biology checks to pass even when writeback signs, compartments, or cofactors are wrong.

PM/operator sanity-check:
- The design should read like a metric-selection contract, not like a one-off Metabolism waiver.

## 1) Design contract

Contract:
- Required behavior: L2.2 must run a fixed multi-axis audit before scoring any process. The audit must at minimum classify stochasticity, numerical solver type, degeneracy/sensitivity, event density, and observable sufficiency; map that result to a named metric bundle; and emit verdict labels that distinguish genuine equivalence from conditional biological parity. For LP-degenerate processes, the bundle must include interface-fidelity invariants, `trace_vertex_equivalence_w1` as informational, and `<process>_regression_w1` as the regression gate.
- Why this matters: the current Design-A runner is built around channel-level `w1_oc_vs_karr`, bootstrap `q95_null`, and `threshold = max(ABSOLUTE_FLOOR, k_eng * q95_null)`, then reduces channel verdicts to a process `PASS` or `FAIL` (`tests/vivarium/l2_2_design_a_runner.py:338-363,1020-1049`). That contract is appropriate when the mathematical object yields a stable observable distribution. It is not appropriate when the source object itself is a highly degenerate LP whose vertex choice changes by solver family. The catalog currently classifies Metabolism as `TRIVIAL_RNG`, dense, substrate-primary, and runnable in the per-tick harness (`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:380-392`), yet the empirical record shows `W1=161 vs threshold=102`, a `cond=6.7e+12` LP, `128` null-space dimensions, `8` unbounded reactions, and biology that already bit-matches on growth, KS, mean, and stddev while writeback still differs on roughly 17 WIDs (`docs/phase_f/METABOLISM_GAP_MAP.md:5-17,32-62,280-281`; `docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:94-106`).
- Done = the implemented framework is a property of the audit, not of Metabolism. For every in-scope process, a reviewer can inspect the audit result and know which metric family applies, why that family is admissible, which signals are gating versus informational, and what failure label should be produced. For LP-degenerate processes, the implemented framework must prevent a clean `VERIFIED_GENUINE` pass until both the invariant suite and the baseline-controlled regression metric pass, even if `trace_vertex_equivalence_w1` fails.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: the audit classifies a process into a softer metric family because the current metric is red, not because the process's mathematical object demands that family.
- What would falsify this contract statement: if the audit cannot be applied prospectively to a new process before any result is seen, or if a known-bad interface mutation can still pass the chosen metric bundle, the design has failed.

## 2) Inventory of existing artifacts

- [A01] path=docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml | kind=schema | role=authoritative baseline for current process buckets, harness routing, primary channels, and the 22-process Design-A in-scope tally
- [A02] path=data/schemas/per_process/metabolism.toml | kind=schema | role=authoritative Metabolism observable contract: 585 substrate IDs, 104 enzyme IDs, substrate-only mutation surface, and enzyme pass-through semantics
- [A03] path=tests/vivarium/l2_2_design_a_runner.py | kind=code | role=current L2.2 gating contract: per-channel W1 thresholding, process verdict reduction, and explicit refusal of `EVENT_CLASS` requests in the per-tick harness
- [A04] path=tests/vivarium/_l2_2_design_a_projections.py | kind=code | role=current non-vector metric implementations: flattened projection W1 and hurdle event-rate-plus-conditional-distance
- [A05] path=docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md | kind=doc | role=authoritative statement of the 5 root causes and 6 required process-improvement lessons that motivate audit-before-metric selection
- [A06] path=docs/phase_f/METABOLISM_GAP_MAP.md | kind=doc | role=empirical Day-40 failure artifact: 500-sample baseline, WID concentration table, cluster decomposition, and solver-family interpretation of the remaining gap
- [A07] path=D:/OneDrive - Microsoft/.pm-os/DECISIONS.md | kind=doc | role=durable policy log that promotes the post-mortem RCs into project-level decision guidance
- [A08] path=SESSION_CONTEXT.md | kind=doc | role=non-negotiable local rules for this authoring session: no external fetches, WSL-only Python if needed, live STATUS discipline, and narrow scope
- [A09] path=docs/prompts/DESIGN_TEMPLATE.md | kind=doc | role=slot-2 contract for required sections, decision cards, verification claims, migration path, and operator checklist
- [A10] path=docs/prompts/COMPOSITION_MANDATE_v2.md | kind=doc | role=spec-authority rule requiring machine-loadable spec quotations before beat content and case-specific anti-metric-shopping discipline

Beat-4 inversion for inventory:
- What critical artifact could still be missing from this list? `tests/vivarium/_l2_2_design_a_runner_helpers.py`, because it owns `ABSOLUTE_FLOOR`, null-bootstrap helpers, and the current threshold-calibration mechanics that an implementation follow-up will need.
- What check did you run to reduce that risk? Repo-local `rg -n` scans over every authoritative source for bucket, harness, observable, W1, threshold, degeneracy, and cluster anchors, followed by manual line-range extraction for the quoted sections above.
- What could be WRONG in the artifacts we listed? Presence is not proof of semantic correctness. The content checks performed here verify only the cited contract surfaces: `PROCESS_CATALOG.yaml` was checked to contain the `EVENT_CLASS` routing rule, the Metabolism entry, and the current tallies; `metabolism.toml` was checked to expose 585 substrate and 104 enzyme observables with substrate-only mutation ticks; `METABOLISM_GAP_MAP.md` was checked to contain the 500-sample baseline, the cluster table, and the Top-27 WID table; `METABOLISM_POSTMORTEM_DAY40.md` was checked to contain the degeneracy audit and the invariant-first lesson. No new extraction was run, by design.

## 3) Interaction-surface map

| Surface ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |
|---|---|---|---|---|---|
| S1 | `PROCESS_CATALOG.yaml` plus the new audit record | Metric selector | `process`, audit-axis values, selected metric family, gating-vs-informational labels, preregistration fingerprint | Metric shopping after seeing a red result; two reviewers choose different metrics for the same process | `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:72-76,380-392,540-548` |
| S2 | Catalog harness routing | Runner dispatch | `harness_type`, `bucket`, `event_density`, `primary_channel`, `output_channels` | Sparse singular processes get pushed through the per-tick runner and fake a zero-W1 PASS | `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:72-76`; `tests/vivarium/l2_2_design_a_runner.py:598-618` |
| S3 | Per-process observable schema | Invariant evaluator | Observable names, WID identity/order, mutated-vs-pass-through expectations, sign convention, compartment partitioning | Aggregate metrics pass while the write surface is permuted, sign-flipped, or truncated | `data/schemas/per_process/metabolism.toml:18-37,54-64` |
| S4 | Numerical object audit | Metric selector | Solver class, solver family, condition number, nullity, bound finiteness, variant-family multiplicity, sensitivity label | A numerically degenerate object is treated as if it had a unique trace distribution | `docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:53-60,94-106`; `D:/OneDrive - Microsoft/.pm-os/DECISIONS.md:22-24` |
| S5 | Karr after-state traces | `trace_vertex_equivalence_w1` | Primary-channel per-tick delta vectors in the recorded solver's basis | Solver-family basis differences are misread as biology regressions | `tests/vivarium/l2_2_design_a_runner.py:1020-1049`; `docs/phase_f/METABOLISM_GAP_MAP.md:280-281` |
| S6 | Pinned OC solver stack plus accepted baseline snapshot | `<process>_regression_w1` | Baseline fingerprint = process + audit class + solver family/version + observable schema hash + threshold snapshot | Regression metric silently resets after a code or solver change and stops guarding anything | `docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:129-141`; `D:/OneDrive - Microsoft/.pm-os/DECISIONS.md:22-24` |
| S7 | Invariant suite | Mutation harness | Each named bad writeback mutation and the exact invariant(s) that must fail | The replacement bundle is weaker than current W1 and cannot prove interface fidelity | `docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:131,137-141`; `docs/phase_f/METABOLISM_GAP_MAP.md:21-62,64-245` |
| S8 | Projection metric implementation | Sparse/event-family processes | Tensor shape, component scaling, hurdle event-rate gate, conditional-distance semantics | A sparse process is compared by dense-vector W1 when event-rate mismatch is the real error surface | `tests/vivarium/_l2_2_design_a_projections.py:152-178,191-230` |
| S9 | Event-window traces | Future `L2.event` harness | Natural event window, event-aligned observables, no tick-alignment assumption | The framework claims to cover all processes but leaves event-class processes undefined in practice | `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:72-76`; `tests/vivarium/l2_2_design_a_runner.py:615-618` |

Beat-4 inversion:
- Which cross-surface assumption is most likely false? That `output_channels` alone are a sufficient observable contract. Metabolism shows the opposite: the substrate channel can have correct aggregate biology while still carrying wrong signed writeback at specific WIDs or compartments.
- What observation would expose that quickly? A compartment permutation, cofactor swap, or exchange-direction flip that preserves growth and broad KS but fails a signed residual or whitelist invariant immediately.

## 4) Baseline facts and constraints

1. Hard task constraints.
   - This is a design-doc-only task. Only `docs/phase_f/L2_2_METRIC_BY_PROCESS_CHARACTER_DESIGN.md` and `STATUS_l22_metric_design.md` may be created; no code, fixtures, or tests may be modified.
   - The source-selection checklist is already satisfied locally: the primary spec sources are present in the repo or on the local workstation, no external network fetch is needed, and no MATLAB or new-data extraction is allowed. If implementation later needs more data than the quoted artifacts already provide, that need must be recorded as an open question rather than satisfied ad hoc.

2. Current L2.2 scope is already multi-family, but the family selection is implicit and incomplete.
   - The catalog currently tallies 22 Design-A per-tick in-scope processes: `4` `ALGORITHMIC_DEEP`, `14` `ALGORITHMIC_SHALLOW`, and `4` `TRIVIAL_RNG`, with `6` `DETERMINISTIC` out of scope (`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:540-548`).
   - The same catalog also defines an `EVENT_CLASS` bucket whose natural contract is `L2.event ensemble (event-aligned, not tick-aligned)` and says the per-tick runner must refuse those processes because tick-level distribution is undefined for them (`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:72-76`).
   - The current runner enforces that refusal at dispatch time (`tests/vivarium/l2_2_design_a_runner.py:598-618`), which means the repo already recognizes that one metric does not fit all stochastic processes. The missing piece is a principled pre-run audit that explains when and why a process should leave the default per-tick W1 family.

3. The current per-tick runner is still fundamentally a distributional-comparison runner.
   - Channel verdicts are driven by `w1_oc_vs_karr`, `q95_null`, and a threshold derived from the bootstrap null (`tests/vivarium/l2_2_design_a_runner.py:338-363,1020-1049`).
   - Projection distances likewise flatten `(seed, tick, component)` tensors across all seeds and ticks before computing Wasserstein distance, and the hurdle helper still reduces sparse behavior to event-rate difference plus conditional distribution distance (`tests/vivarium/_l2_2_design_a_projections.py:152-178,191-230`).
   - Those are valid metrics for some process classes. They are not, by themselves, interface-fidelity checks.

4. Metabolism's observable surface is narrow but high-dimensional.
   - `metabolism.toml` declares `substrates` as the only mutated observable across the 100-tick trace, while `enzymes` and `boundEnzymes` are pass-through surfaces (`data/schemas/per_process/metabolism.toml:18-37`).
   - The same schema records `585` substrate IDs and `104` enzyme IDs (`data/schemas/per_process/metabolism.toml:54-64`).
   - Therefore, any Metabolism replacement metric that checks only biomass or aggregate substrate histograms is under-instrumented for the actual write surface.

5. The empirical Metabolism failure is concentrated and structurally solver-linked.
   - Day-40 keeps Metabolism at `W1=161 vs threshold=102` over a `50 seeds x 10 ticks = 500 samples` audit (`docs/phase_f/METABOLISM_GAP_MAP.md:5-17`).
   - The same artifact reports a Karr-recorded delta mean L1 per sample of `109393`, an algorithm/RNG floor of `40`, and bounds drift of `0` at sample `(0,1)` (`docs/phase_f/METABOLISM_GAP_MAP.md:10-17`).
   - The top four error clusters are aromatic amino acids plus dipeptides (`26.5%`), metabolic byproducts (`25.6%`), lipid family (`23.9%`), and carbon backbone (`16.9%`) (`docs/phase_f/METABOLISM_GAP_MAP.md:21-26`).
   - The Top-27 table says `99.1%` of the error is carried by 27 WIDs, and summing rows 1-17 yields `91.09%`, which matches the review shorthand that roughly 17 WIDs carry about 90% of the remaining gap (`docs/phase_f/METABOLISM_GAP_MAP.md:32-62`).
   - The gap map baseline line gives `22409` as the current mean writeback error per sample, while the post-mortem, the gap-to-close line, and the durable decision log repeat `22,412`. That three-count discrepancy is small relative to the gap but real in the artifacts, so later implementation should pin one literal and document why (`docs/phase_f/METABOLISM_GAP_MAP.md:12,17`; `docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:60,147`; `D:/OneDrive - Microsoft/.pm-os/DECISIONS.md:25`).

6. The post-mortem already states the governing lesson for this design.
   - RC3 says the LP should have been audited for `cond`, null-space, and bound finiteness before L2.2 was designed, because on a `cond=6.7e+12` LP with `8` unbounded reactions and `128` null-space dimensions the recorded trace is "one of many degenerate optima" rather than a unique biological oracle (`docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:94-106`).
   - The durable decision log promotes that into project policy: pre-test object audit is required for LPs, ODEs, and Markov objects before metric design, and default validation threshold should remain bit-match unless justified otherwise (`D:/OneDrive - Microsoft/.pm-os/DECISIONS.md:22-24`).

7. The remaining Metabolism gap is not a generic noise problem.
   - The post-mortem and gap map jointly identify LP degeneracy sources including `LIPASE` x27, `TX` x12, `Pyk` x7, `Adk` x3, `PfkA` x5, and `Gmk` x2-family behavior in the gap map tables, plus the post-mortem's higher-level statement that six enzyme variant families are implicated (`docs/phase_f/METABOLISM_GAP_MAP.md:64-176`; `docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:53-60,98-102`).
   - The same artifacts say GLPK 5.0 plus `presolve=OFF` closed about `82%` of the original writeback L1 gap, leaving a residual that is structurally tied to alternative LP vertices rather than to bounds drift or broad biological mismatch (`docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:53-60,147-150`; `docs/phase_f/METABOLISM_GAP_MAP.md:14-17,280-281`).

Beat-4 inversion:
- Which baseline "fact" is inferred rather than proven? The shorthand "17 WIDs carry 90% of error" is a derived summary from the Top-27 table, not a literal sentence in the source docs.
- What would invalidate it? If the gap-map table is regenerated and the row percentages change, the arithmetic must be recomputed; the qualitative concentration claim would still hold, but the exact cutoff might move.

## 5) Decision ledger

## 6) Expected outcomes and verification claims

## 7) Open questions for operator

## 8) Scope boundary

## 9) Migration and rollout path

## 10) Risks and residual unknowns

## 11) Operator review checklist
