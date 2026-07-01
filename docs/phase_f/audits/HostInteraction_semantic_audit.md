# HostInteraction Semantic Audit (L1b)

## Deliberate Action Prefix (v2)
- Beat 1 (contract): Audit `data/schemas/per_process_wiring/HostInteraction.yaml` against MATLAB and OC execution semantics, and classify each claim with the allowed verdicts only. Done means another auditor can reproduce the same verdicts from the same source lines.
- Beat 2 (surface): Row file `data/schemas/per_process_wiring/HostInteraction.yaml`; MATLAB files `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/HostInteraction.m`, `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`; OC files `opencell/vivarium/karr_host_interaction.py`, `opencell/vivarium/karr_composite.py`.
- Beat 3 (expected outcome): A complete S1-S6 claim table with deterministic claim IDs, constrained verdict vocabulary, aggregate counts, and Priority-1 remediation list.
- Beat 4 (invert/pre-mortem): Most likely false pass is treating row prose as truth while skipping executable branches (allocator loop, runtime topology wiring, or formula bodies), which would make divergence attribution incorrect.
- Beat 5 (act/verify): Claims below cite executable logic and topology anchors; aggregate counts and remediation list are included.
- PM sanity-check: "PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed."

## Revision-Class Minimum
Design contract sentence: Semantic truth checked here is whether HostInteraction row wiring claims match executable MATLAB and OC behavior for S1-S6, not whether anchors merely exist.

Decision ledger (non-obvious attribution calls):
1. D1 (empty stoichiometry interpretation)
Chosen: Treat empty `consume_stoichiometry` and `produce_stoichiometry` as strict empty-set claims (not exemplar rows), because no exemplar scope disclaimer exists in the row.
Why: Avoid silently downgrading completeness checks.
2. D2 (S5 for non-stoichiometric process)
Chosen: Evaluate both strict substrate-compartment routing (empty set) and state-store projection/routing divergence as a `judgment=required` extension.
Why: HostInteraction primarily mutates host/cell booleans rather than metabolite compartments.
3. D3 (allocator mode with zero-length substrate list)
Chosen: Keep MATLAB mode as allocator-engaged (process participates in allocator pass even with zero/empty demand) and OC as bypass.
Why: MATLAB scheduler calls `calcResourceRequirements_Current()` for all processes before evolution.

Risks (unresolved ambiguity):
- R1: S5 category is substrate-compartment centric, while HostInteraction is mostly host-state logic; mapping this to state-store routing requires judgment.
- R2: Row `soft_after: TerminalOrganelleAssembly` may represent advisory pressure rather than executable order; row semantics are ambiguous against runtime enforcement.
- R3: MATLAB allocator participation is operationally degenerate (empty substrate set), so "allocation" vs "bypass" classification can be interpreted differently without explicit policy.

## Header
- Process name: `HostInteraction`
- Audited files:
  - `data/schemas/per_process_wiring/HostInteraction.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/HostInteraction.m`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
  - `opencell/vivarium/karr_host_interaction.py`
  - `opencell/vivarium/karr_composite.py`
- Scope policy: `strict completeness` (row does not declare exemplar-scoped stoichiometry)

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| HI-S1-01 | S1 | `consume_stoichiometry: []` (`HostInteraction.yaml:83`). | `substrateWholeCellModelIDs = {}` (`HostInteraction.m:185`) and `evolveState` only mutates host booleans (`HostInteraction.m:271-303`), so no substrate consume set exists. | `next_update` reads `cell`/`protein` and only computes adhesion state (`karr_host_interaction.py:259-300`); no substrate consume operation. | VERIFIED | Strict empty-set completeness holds. |
| HI-S2-01 | S2 | No consume entries are declared (`HostInteraction.yaml:83`). | No substrate consume path appears in process logic (`HostInteraction.m:271-303`). | Runtime topology for `karr_host_interaction` exposes only `cell` and `protein` (`karr_composite.py:2451-2454`), and no `substrates_allocated`/`requests` path exists for this process. | VERIFIED | Vacuous fabrication check: zero row consume entries to fabricate. |
| HI-S3-01 | S3 | `produce_stoichiometry: []` (`HostInteraction.yaml:84`). | Process produces host-state booleans, not substrate deltas (`HostInteraction.m:277-302`); no substrate produce tuple exists. | OC emits only `cell.host_adhesion_strength` delta and `cell.host_attached` toggles (`karr_host_interaction.py:293-299`), not substrate outputs. | VERIFIED | Completeness + fabrication both satisfied for empty produce set. |
| HI-S4-01 | S4 | Row states OC `evolveState` is a "Karr-light approximation, not a literal port" (`HostInteraction.yaml:54-55`). | Adhesion formula is boolean: `all(terminalOrganelle) && all(adhesin)` (`HostInteraction.m:277-279`). | Adhesion uses fractional expression product + stochastic bind/unbind Poisson updates (`karr_host_interaction.py:266-287`). | CODE_DEVIATES | Row correctly attributes formula-family divergence. |
| HI-S4-02 | S4 | Known deviation says OC replaces MATLAB boolean host cascade with aggregate adhesion state (`HostInteraction.yaml:206-208`). | MATLAB computes TLR, NF-kB, and inflammatory boolean formulas (`HostInteraction.m:281-302`). | OC has no TLR/NFkB/inflammatory formula branches; only adhesion strength/attachment threshold (`karr_host_interaction.py:287-290`). | CODE_DEVIATES | Row correctly captures MATLAB-vs-OC non-equivalence. |
| HI-S5-01 | S5 | `compartment_routing: []` (`HostInteraction.yaml:85`). | No `(substrate, compartment)` writeback tuples are formed by HostInteraction (`HostInteraction.m:271-303`). | HostInteraction topology omits substrate ports entirely (`karr_composite.py:2451-2454`), so no substrate compartment projection/merge path exists. | VERIFIED | Explicit projection/merge check found no substrate tuple surface. `judgment=required` (process is largely non-stoichiometric). |
| HI-S5-02 | S5 | Row notes OC reads `cell` + `protein` and uses aggregate adhesion state, not MATLAB host cascade (`HostInteraction.yaml:12`, `207-208`). | MATLAB writes `host.isBacteriumAdherent`, `host.isTLRActivated`, `host.isNFkBActivated`, `host.isInflammatoryResponseActivated` (`HostInteraction.m:277-302`). | OC wiring provides `cell`/`protein` stores (`karr_composite.py:2451-2454`); process writes only `cell.host_adhesion_strength` and `cell.host_attached` (`karr_host_interaction.py:293-299`). | CODE_DEVIATES | Store-routing projection differs and is correctly disclosed by row. `judgment=required` (S5 generalized beyond strict substrate tuples). |
| HI-S6-01 | S6 | Row states `karr: allocation`, `oc_current: bypass`, with MATLAB request formula `zeros(size(this.substrates))` and no OC request calculator (`HostInteraction.yaml:74-80`). | Simulation allocator calls every process `calcResourceRequirements_Current()` before evolve (`Simulation/evolveState.m:28-37`), and HostInteraction returns zero vector (`HostInteraction.m:266-268`). | OC process has no request/grant ports in topology (`karr_composite.py:2451-2454`) and `next_update` never reads allocator state (`karr_host_interaction.py:255-300`). | CODE_DEVIATES | MATLAB allocator participation exists but is zero-demand; OC bypasses allocator mediation. `judgment=required`. |
| HI-S6-02 | S6 | Row encodes `soft_after: TerminalOrganelleAssembly` while also stating no explicit Karr order exception (`HostInteraction.yaml:113-115`). | MATLAB process order is random `randperm` with only tRNA-aminoacylation vs translation exception (`Simulation/evolveState.m:48-57`); no HostInteraction-specific order edge. | OC adds `karr_host_interaction` without flow dependency edge (`karr_composite.py:2449-2454` and no corresponding `flow[...]` entry nearby). | ROW_WRONG | Row ordering entry is ambiguous/non-executable against observed runtimes. `judgment=required`. |

Aggregate counts:
- VERIFIED: 4
- ROW_WRONG: 1
- CODE_DEVIATES: 4
- MISSING: 0

Priority-1 fixes:
- `HI-S6-02` (`ROW_WRONG`): remediate row ordering semantics (`soft_after: TerminalOrganelleAssembly`) to distinguish advisory dependency from executable scheduler constraint.

Known-deviation mapping:
- KD1 (boolean cascade replaced by aggregate adhesion model) -> `HI-S4-01`, `HI-S4-02`, `HI-S5-02`.
- KD2 (allocator mediation bypass in OC) -> `HI-S6-01`.

Auditor discretion list (`judgment=required`):
- `HI-S5-01`
- `HI-S5-02`
- `HI-S6-01`
- `HI-S6-02`
