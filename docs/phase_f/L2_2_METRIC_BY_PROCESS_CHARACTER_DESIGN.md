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

Decision D1
- Question: How should L2.2 choose a per-process metric without special pleading?
- Options considered:
  1) Keep the current bucket names (`ALGORITHMIC_DEEP`, `SHALLOW`, `TRIVIAL_RNG`) as the full selector.
  2) Add a Metabolism-only exception path on top of the current runner.
  3) Require a pre-registered mathematical-object audit whose outputs select the metric family.
- Chosen option: 3.
- Rationale: The post-mortem's core lesson is "before designing a test against a mathematical object, audit the object" (`docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:94-106`). The catalog already proves that one axis is insufficient because `EVENT_CLASS` processes are explicitly routed away from the per-tick runner (`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:72-76`; `tests/vivarium/l2_2_design_a_runner.py:598-618`). The missing discipline is to make that reasoning uniform for all processes, not only for sparse-event ones.
- Tradeoffs accepted: More up-front documentation and more explicit reviewer burden before running the harness.
- Beat-4 inversion (how chosen option could be wrong): The audit could become a verbose restatement of current buckets without actually changing the decision surface.
- Falsifier (what evidence would force reopening D1): If two reviewers, using the same audit schema and cited sources, still classify the same process into different metric families, the schema is underspecified.
- Operator escalation needed? no

Required audit record for every process before evaluation:

| Axis | Required question | Allowed values in this design | Required evidence before selection |
|---|---|---|---|
| `stochasticity` | Does the process have intrinsic randomness, trivial wrapper RNG, or no RNG at all? | `deterministic`, `trivial_rng`, `stochastic` | Catalog bucket/notes, source call-graph, or trace behavior |
| `solver_type` | What dominant mathematical object determines the emitted observable? | `none`, `projection_state`, `lp`, `ode`, `event_window` | Upstream/process call-graph and current harness surface |
| `degeneracy_sensitivity` | Is the object uniquely solved, mildly sensitive, or solver-family/ill-conditioning sensitive? | `none`, `low`, `projection_only`, `lp_degenerate` | LP audit (`cond`, nullity, finite-bounds check, variant families), or equivalent object audit for other solver types |
| `event_density` | Are informative events dense enough for tick-level distributional comparison? | `dense`, `moderate`, `sparse`, `singular_windowed` | Catalog `event_density`, seed window, and trace event counts |
| `observable_sufficiency` | Can the declared output channel(s) detect interface errors directly? | `raw_output_sufficient`, `projection_sufficient`, `requires_aux_invariants`, `event_window_only` | Schema review plus a mutation thought-experiment against the declared write surface |

Pre-registration rule:
1. The audit record is authored before the metric run and stored with the threshold/baseline artifact for that process.
2. The metric family is a pure function of the audit record in D2's matrix below.
3. If an implementer wants a different metric family after seeing a result, they must change the audit record first and justify the new evidence, not overwrite the verdict logic.

Decision D2
- Question: What metric families should the audit map to for the axis combinations that exist in the current process set?
- Options considered:
  1) One universal metric (`per_tick_vector_w1_mean`) for every in-scope process.
  2) A hand-maintained per-process exception list.
  3) A small metric-family matrix keyed by the audit outputs, with examples from the current catalog.
- Chosen option: 3.
- Rationale: The current repo already contains more than one metric implementation: vector W1, projection W1, hurdle event-rate distance, and event-class refusal (`tests/vivarium/_l2_2_design_a_projections.py:152-230`; `tests/vivarium/l2_2_design_a_runner.py:598-618`). The design should name those as families and add the missing LP-degenerate family rather than hiding them behind process-specific wiring.
- Tradeoffs accepted: Some current process labels move from intuitive buckets to a more explicit matrix, which is slightly more cumbersome to read but much safer to review.
- Beat-4 inversion (how chosen option could be wrong): The matrix could be too coarse and accidentally group together processes whose observables are not equally sufficient.
- Falsifier (what evidence would force reopening D2): A current in-scope process cannot be placed into exactly one family without appeal to undocumented intuition.
- Operator escalation needed? no

Metric-family matrix:

| Family ID | Audit signature | Gating metric(s) | Informational metric(s) | Current process examples |
|---|---|---|---|---|
| `MF0_DETERMINISTIC_OUT_OF_SCOPE` | `stochasticity=deterministic` | L2.1/L2.5 only; no L2.2 gate | n/a | The 6 `DETERMINISTIC` catalog entries (`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml:446-524`) |
| `MF1_PER_TICK_VECTOR_W1` | `stochasticity=stochastic`, `solver_type=none`, `degeneracy_sensitivity in {none, low}`, `event_density in {dense, moderate, sparse}`, `observable_sufficiency=raw_output_sufficient` | Existing per-channel W1 + KS + null bootstrap | Current warnings, joint checks | Translation, Transcription, RNAProcessing, RNAModification, RNADecay, tRNAAminoacylation, ProteinModification, ProteinFolding, ProteinDecay, ProteinTranslocation, MacromolecularComplexation, ReplicationInitiation |
| `MF2_PROJECTION_DISTANCE` | `solver_type=projection_state`, `degeneracy_sensitivity=projection_only`, `observable_sufficiency=projection_sufficient` | Existing scaled projection W1 or hurdle event-rate-plus-conditional-distance | Raw channel diagnostics if present | Replication, DNASupercoiling, DNARepair |
| `MF3_TRIVIAL_RNG_CONFIRMATION` | `stochasticity=trivial_rng`, `solver_type=none`, `degeneracy_sensitivity in {none, low}`, `observable_sufficiency=raw_output_sufficient` | Existing confirmation W1 path at smaller `M_ticks` | closed-form dominance notes | ProteinProcessingI, ProteinProcessingII |
| `MF4_LP_DEGENERATE_INTERFACE_FIDELITY` | `solver_type=lp`, `degeneracy_sensitivity=lp_degenerate`, `observable_sufficiency=requires_aux_invariants` | Interface invariant suite + `<process>_regression_w1` | `trace_vertex_equivalence_w1` at the historical threshold | Metabolism |
| `MF5_UNVALIDATABLE_EVENT_CLASS` | `event_density=singular_windowed` or catalog `harness_type=event_class` or `observable_sufficiency=event_window_only` | No per-tick verdict; route to `L2.event` | Optional event-free smoke only | RibosomeAssembly, FtsZPolymerization, Cytokinesis, DNADamage |

Selection rule:
1. If `stochasticity=deterministic`, assign `MF0_DETERMINISTIC_OUT_OF_SCOPE`.
2. Else if `harness_type=event_class` or `event_density=singular_windowed`, assign `MF5_UNVALIDATABLE_EVENT_CLASS`.
3. Else if `solver_type=lp` and `degeneracy_sensitivity=lp_degenerate`, assign `MF4_LP_DEGENERATE_INTERFACE_FIDELITY`.
4. Else if `observable_sufficiency=projection_sufficient`, assign `MF2_PROJECTION_DISTANCE`.
5. Else if `stochasticity=trivial_rng`, assign `MF3_TRIVIAL_RNG_CONFIRMATION`.
6. Else assign `MF1_PER_TICK_VECTOR_W1`.

Decision D3
- Question: What should the LP-degenerate metric family require, specifically?
- Options considered:
  1) Waive W1 entirely and use only biological invariants.
  2) Keep current W1 as the hard gate and add some diagnostic invariants.
  3) Split W1 into informational trace-vertex equivalence plus baseline-controlled regression, and make interface-fidelity invariants the gate.
- Chosen option: 3.
- Rationale: The post-mortem explicitly says L2.2 should be designed around invariants, not trace replay, for Metabolism-class LPs (`docs/phase_f/METABOLISM_POSTMORTEM_DAY40.md:129-141`). But deleting W1 entirely would throw away a useful signal about solver-family divergence. Splitting the signal preserves the historical threshold as a diagnostic while moving the gating burden onto invariants that can actually distinguish biology regressions from basis changes.
- Tradeoffs accepted: The LP-degenerate family has a heavier harness and a more complex reviewer story than the default W1 families.
- Beat-4 inversion (how chosen option could be wrong): The invariant suite could still be too aggregate and fail to catch write-surface corruption.
- Falsifier (what evidence would force reopening D3): Any mandatory mutation in D6 can pass all gating invariants while violating the intended Metabolism interface.
- Operator escalation needed? no

`MF4_LP_DEGENERATE_INTERFACE_FIDELITY` specification:

1. `trace_vertex_equivalence_w1`
   - Definition: the current primary-channel W1 against Karr's recorded substrate deltas, evaluated exactly as today's runner evaluates Metabolism on its primary channel.
   - Gate status: informational only.
   - Threshold: preserve the existing historical threshold for comparability.
   - Expected behavior: may legitimately fail whenever solver-family basis selection differs, even if the biology-facing interface is acceptable.

2. `<process>_regression_w1`
   - Definition: primary-channel W1 between the candidate implementation and a pinned OC baseline generated on the same audit signature and solver fingerprint.
   - Gate status: hard fail on regression.
   - Threshold: derived from the pinned baseline's self-null/bootstrap band on the same metric path; never from the candidate run itself.

3. Interface-fidelity invariant suite
   - `per_wid_signed_delta_residual_budget`
     - For every mutated WID and sample, compare OC signed delta against Karr signed delta.
     - Budget construction: `budget[wid] = max(abs_floor_wid, q95_baseline_abs_residual[wid])`, where `q95_baseline_abs_residual` is measured from the accepted solver-stack baseline against Karr.
     - Hard-fail rule: any key-cofactor WID breach fails immediately; non-whitelist WIDs fail if breach count or total excess exceeds the preregistered budget.
   - `compartment_specific_exchange_flux_sign_range`
     - For exchange-associated reactions and writebacks (`TX_*`, `(ext_exch)`, `(int_exch)` families), preserve uptake/secretion sign and stay within baseline/Karr-derived range envelopes per compartment family.
     - Any sign inversion across the compartment boundary is a hard fail.
   - `key_cofactor_whitelist`
     - Mandatory explicit checks for ATP, GTP, CTP, UTP, amino-acid substrates, glucose, PEP, and PYR.
     - Requirement: sign, non-zero support where Karr is non-zero, and residuals within the per-WID budget.
   - `pathway_level_flux_distributions`
     - Compare aggregated signed and absolute flux over variant-family and pathway bins rather than exact vertex columns.
     - Mandatory family bins for current Metabolism: `LIPASE`, `TX`, `Pyk`, `Adk`, `PfkA`, `Gmk`.
     - Rationale: a different basis choice inside a family may be acceptable; switching pathway families or exchange direction is not.
   - `elemental_or_mass_conservation`
     - Enforce whole-sample mass conservation and element-balance checks at minimum for carbon, nitrogen, and phosphate-bearing pools when those are derivable from the process schema.
     - Any residual above the preregistered conservation tolerance is a hard fail.

4. Verdict rule for `MF4`
   - `CONDITIONAL_PASS: biology_invariants_pass / trace_vertex_divergent` if all invariants pass, `<process>_regression_w1` passes, and `trace_vertex_equivalence_w1` fails.
   - `CONDITIONAL_PASS: biology_invariants_pass / trace_vertex_within_band` if all invariants pass, `<process>_regression_w1` passes, and `trace_vertex_equivalence_w1` also happens to pass.
   - `FAIL: interface_invariants_breach` if any invariant fails.
   - `FAIL: regression_vs_baseline` if invariants pass but `<process>_regression_w1` fails.
   - `VERIFIED_GENUINE` is unavailable while the audit remains `lp_degenerate`.

Decision D4
- Question: How should the baseline for `<process>_regression_w1` be set and updated?
- Options considered:
  1) Compare only to Karr and do not maintain an OC baseline.
  2) Compare only to the current OC solver stack and stop comparing to Karr.
  3) Maintain a dual track: invariants against Karr and physics, regression against a pinned OC baseline.
- Chosen option: 3.
- Rationale: Comparing only to Karr cannot distinguish solver-family vertex drift from a true regression on an accepted solver stack. Comparing only to OC would sever the remaining tie to the source model. The dual track is the only option that preserves both source fidelity and regression sensitivity.
- Tradeoffs accepted: Baselines become versioned artifacts that require governance.
- Beat-4 inversion (how chosen option could be wrong): A baseline could be refreshed too casually and turn a regression into the new normal.
- Falsifier (what evidence would force reopening D4): A solver-stack change or code regression is accepted only because the baseline was updated in the same change without separate review.
- Operator escalation needed? yes + QO1

Baseline policy:
1. A baseline may be created only after the audit record is frozen and the full invariant suite passes.
2. The baseline fingerprint must include: process name, audit family, solver library, solver version, key solver options, schema hash for the measured observables, seed/tick plan, and the threshold snapshot used to judge `<process>_regression_w1`.
3. A baseline update requires an explicit operator-reviewed change note that explains why the old baseline is no longer the correct regression target.
4. A solver-family or solver-version change automatically invalidates the prior regression baseline and forces a re-audit plus explicit rebaselining decision.
5. The run that first discovers a regression may not also bless the replacement baseline.

Decision D5
- Question: How should final verdict labels communicate "passes biology, fails trace vertex" without pretending that is the same as full equivalence?
- Options considered:
  1) Keep plain `PASS`/`FAIL` and bury nuance in warnings.
  2) Keep `PASS` but add a suffix note for LP-degenerate processes.
  3) Introduce explicit conditional verdict labels keyed to the chosen metric family.
- Chosen option: 3.
- Rationale: The user-facing problem here is semantic, not just numeric. A clean `PASS` would be read as "same process behavior under the same object assumptions," which is not what an LP-degenerate conditional success means. The verdict itself must carry that nuance.
- Tradeoffs accepted: The verdict taxonomy grows.
- Beat-4 inversion (how chosen option could be wrong): Too many labels could make review harder instead of clearer.
- Falsifier (what evidence would force reopening D5): Reviewers still have to read the fine print to know whether a process is genuinely verified or only conditionally accepted.
- Operator escalation needed? yes + QO3

Verdict taxonomy:

| Verdict | Meaning | Applies to |
|---|---|---|
| `VERIFIED_GENUINE` | Chosen metric family passes and the audit does not flag solver-sensitive degeneracy | `MF1`, `MF2`, `MF3` |
| `CONDITIONAL_PASS: biology_invariants_pass / trace_vertex_divergent` | LP-degenerate biology-facing interface passes, baseline regression passes, historical Karr-trace W1 diverges | `MF4` |
| `CONDITIONAL_PASS: biology_invariants_pass / trace_vertex_within_band` | Same as above, but historical trace W1 also lands inside the legacy band | `MF4` |
| `FAIL: interface_invariants_breach` | Interface-fidelity suite fails | `MF4` |
| `FAIL: regression_vs_baseline` | Baseline-controlled regression W1 fails after invariants pass | `MF4` |
| `UNVALIDATABLE_EVENT_CLASS` | Tick-aligned L2.2 verdict is not defined for this process; route to `L2.event` | `MF5` |

Decision D6
- Question: What mutation-test burden is required before the LP-degenerate family can replace current W1 gating?
- Options considered:
  1) No dedicated mutation suite; trust the invariants by inspection.
  2) A few ad hoc probes during development.
  3) A required catalogue of known-bad mutations that must fail before the family is considered stronger than current W1.
- Chosen option: 3.
- Rationale: The rubber-duck critique is correct: the framework stands or falls on whether its invariants catch concrete interface failures that aggregate biology metrics can miss. Without mutation tests, the claim "stronger than W1" is only rhetorical.
- Tradeoffs accepted: More up-front harness work in the implementation phase.
- Beat-4 inversion (how chosen option could be wrong): The mutation list could be too toy and still leave obvious holes.
- Falsifier (what evidence would force reopening D6): A plausible interface corruption outside the catalogue can pass the suite without difficulty.
- Operator escalation needed? no

Mandatory mutation catalogue for `tests/vivarium/test_l2_2_metabolism_invariants_mutations.py`:

| Mutation ID | Concrete bad variant | How to construct it in a test double | Must fail | Why this matters |
|---|---|---|---|---|
| `M1_sign_flip_top_wid` | Signed writeback sign flip on a dominant WID such as `OCDCEA`, `TRP`, or `H2O2` | Multiply the chosen WID's per-sample deltas by `-1` after solve, leave magnitude unchanged | `per_wid_signed_delta_residual_budget` and usually conservation | Catches the simplest interface corruption that growth-only or mass-only checks can miss |
| `M2_compartment_permutation_exchange` | Preserve magnitudes but swap internal/external exchange bookkeeping for oxygen/water/carbon-backbone writebacks | Reassign the selected exchange-family outputs to the wrong compartment bucket while keeping totals constant | `compartment_specific_exchange_flux_sign_range` | Directly addresses the critique that biology aggregates can pass while compartments are permuted |
| `M3_cofactor_swap_whitelist` | Swap ATP with GTP, or PEP with PYR, across the emitted deltas | Exchange the per-tick deltas of two whitelist cofactors and keep all other WIDs untouched | `key_cofactor_whitelist` | Ensures the suite is sensitive to biochemical identity, not only total mass |
| `M4_exchange_direction_flip` | Reverse the sign of a `TX_*`, `(ext_exch)`, or `(int_exch)` family while keeping absolute magnitudes | Multiply the selected exchange-family flux/writeback by `-1` | `compartment_specific_exchange_flux_sign_range`, often conservation | Catches "uptake became secretion" bugs that can preserve absolute activity |
| `M5_growth_only_preserved` | Preserve biomass/growth scalar and overall mass, but redistribute writeback across the top-error WIDs or pathway bins | Replace the substrate delta vector with one that matches growth/mass totals yet shuffles residual among the Top-17 WIDs | `per_wid_signed_delta_residual_budget` and `pathway_level_flux_distributions` | Proves the suite is stricter than growth+KS+mass alone |

Example of the intended strength:
- A candidate that preserves the Day-40 observation "biology bit-matches (growth, KS, mean, stddev)" but still changes the signed `OCDCEA`, `TRP`, or `TX_*` writeback must fail this family (`docs/phase_f/METABOLISM_GAP_MAP.md:23-26,32-62,280-281`).

## 6) Expected outcomes and verification claims

Claim C1:
- If design is correct, we should observe: applying the audit retroactively to Metabolism yields `solver_type=lp`, `degeneracy_sensitivity=lp_degenerate`, `observable_sufficiency=requires_aux_invariants`, and therefore `MF4_LP_DEGENERATE_INTERFACE_FIDELITY`.
- Measurement method / command / assertion: reviewer walks the D1 audit fields using the quoted Day-40 facts (`cond=6.7e+12`, `128` null-space dimensions, `8` unbounded reactions, variant families, substrate-only mutated surface).
- Threshold or exact value: exact family assignment to `MF4`.
- Why this distinguishes from alternatives: a bucket-only selector would keep Metabolism in `TRIVIAL_RNG`; the audit-driven selector must not.

Claim C2:
- If design is correct, we should observe: the same audit leaves dense, non-solver-sensitive stochastic ports in the current W1 family instead of forcing needless complexity.
- Measurement method / command / assertion: classify Translation or Transcription from the catalog and current runner surface.
- Threshold or exact value: assignment to `MF1_PER_TICK_VECTOR_W1`.
- Why this distinguishes from alternatives: proves the design is not a disguised "everything becomes special case" rewrite.

Claim C3:
- If design is correct, we should observe: projection-centric structured-state ports remain in a projection family rather than being flattened back into raw-vector W1.
- Measurement method / command / assertion: classify Replication, DNASupercoiling, and DNARepair from their current catalog/runner usage of chromosome projections and hurdle distance.
- Threshold or exact value: assignment to `MF2_PROJECTION_DISTANCE`.
- Why this distinguishes from alternatives: proves the multi-axis audit preserves existing good exceptions instead of erasing them.

Claim C4:
- If design is correct, we should observe: every mandatory mutation in D6 fails at least one named invariant even if growth, broad KS, and mass remain acceptable.
- Measurement method / command / assertion: implement `M1`-`M5` and assert the expected invariant names trip.
- Threshold or exact value: 5 of 5 mandatory mutations detected.
- Why this distinguishes from alternatives: this is the central proof that the LP-degenerate family is stronger than current W1 replacement-by-assertion.

Claim C5:
- If design is correct, we should observe: event-window processes do not receive fake per-tick passes under the new framework.
- Measurement method / command / assertion: classify RibosomeAssembly, FtsZPolymerization, Cytokinesis, and DNADamage.
- Threshold or exact value: all receive `UNVALIDATABLE_EVENT_CLASS` from this L2.2 selection rule.
- Why this distinguishes from alternatives: it preserves the existing runner safeguard and extends the "not all stochastic processes are tick-comparable" lesson consistently.

Claim C6:
- If design is correct, we should observe: changing solver family or version forces a baseline invalidation rather than silently carrying forward the old regression guard.
- Measurement method / command / assertion: review the baseline fingerprint policy in D4 against a hypothetical `GLPK 5.0 -> HiGHS` or `GLPK 5.0 -> GLPK 5.1` change.
- Threshold or exact value: exact requirement that the old baseline is invalid and operator-reviewed rebaselining is mandatory.
- Why this distinguishes from alternatives: without this rule, `<process>_regression_w1` can decay into a cosmetic metric.

Beat-4 inversion:
- How could these claims pass while design is still wrong? The audit could assign the right family names on paper while the future implementation quietly omits one or more invariants from the LP-degenerate bundle.
- Additional guardrail to close that hole: require the implementation PR to list the invariant names and the mutation IDs they detect in a one-to-one matrix, and block merge if any mandatory mutation lacks a failing invariant.

## 7) Open questions for operator

QO1. Where should the pinned `<process>_regression_w1` baseline artifact live, and in what format?
- Why unresolved: this doc defines the policy but not the storage layer.
- Options:
  1) Store alongside other L2.2 artifacts under `tests/vivarium/` or a dedicated baseline artifact directory.
  2) Store as a phase-F design artifact under `docs/phase_f/` and have the harness read it.
- Recommended default (if no response): option 1, because the baseline is executable test data, not reviewer prose.
- Risk if wrong: rebaselining becomes either too casual (if mixed with docs) or too opaque (if buried in a test helper).

QO2. Should the audit record be represented as new fields inside `PROCESS_CATALOG.yaml`, or as a sibling preregistration artifact?
- Why unresolved: embedding it in the catalog centralizes routing, but it also turns a broad catalog file into a more volatile review surface.
- Options:
  1) Extend `PROCESS_CATALOG.yaml` with audit fields.
  2) Create a separate audit manifest keyed by process.
- Recommended default (if no response): option 2, because preregistration updates will be more frequent and should not blur the stable catalog baseline.
- Risk if wrong: either the catalog becomes noisy, or the audit drifts from the catalog and loses discoverability.

QO3. Should `CONDITIONAL_PASS: biology_invariants_pass / trace_vertex_divergent` remain a human-readable string, or become a structured verdict object with `status` plus `reason` fields?
- Why unresolved: both are readable, but they have different downstream parsing implications.
- Options:
  1) Human-readable string label.
  2) Structured object plus a rendered summary string.
- Recommended default (if no response): option 2, because it preserves machine readability without sacrificing reviewer clarity.
- Risk if wrong: verdict parsing becomes fragile, or the summary becomes too terse to communicate the distinction.

QO4. How strong should `elemental_or_mass_conservation` be in the first implementation?
- Why unresolved: the prompt requires elemental/mass conservation, but the exact element set is a policy choice.
- Options:
  1) Mass conservation only for v1.
  2) Mass plus explicit C/N/P balance from day one.
- Recommended default (if no response): option 2 for Metabolism, because the extra specificity is precisely what makes the invariant suite harder to game.
- Risk if wrong: a too-weak first version may let pathway swaps slip through; a too-strong version may demand metadata that is not yet serialized.

QO5. How should the design name the four current event-window processes in reviewer-facing output?
- Why unresolved: the current catalog uses `EVENT_CLASS`, while this design proposes `UNVALIDATABLE_EVENT_CLASS` as the L2.2 verdict label.
- Options:
  1) Keep the catalog bucket name and use `UNVALIDATABLE_EVENT_CLASS` only as the verdict.
  2) Rename the bucket itself in a later follow-up.
- Recommended default (if no response): option 1, to avoid unnecessary catalog churn in the design-only phase.
- Risk if wrong: reviewers may conflate "bucket" with "verdict" or interpret the bucket as already solved by this doc.

QO6. Should the tiny Day-40 `22409` vs `22,412` discrepancy be normalized in the first implementation PR, or only documented?
- Why unresolved: the discrepancy is too small to change the design, but it is large enough to trip literal-threshold assertions if left ambiguous.
- Options:
  1) Normalize it immediately and cite the chosen canonical artifact.
  2) Document the discrepancy and defer normalization until the implementation PR.
- Recommended default (if no response): option 1, with `22,412` as the canonical narrative figure because it is repeated in the post-mortem and decision log.
- Risk if wrong: future reviewers may think a threshold moved when only the summary literal changed.

## 8) Scope boundary

## 9) Migration and rollout path

## 10) Risks and residual unknowns

## 11) Operator review checklist
