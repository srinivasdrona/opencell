# Day 30: The Template That Won, the Fixture That Lied, and the Rule That Was Half a Rule

*June 16, 2026*

---

**Tehol:** Bugg, yesterday's post ended with a spec that wouldn't close and a template that was supposed to cure it.

**Bugg:** The L2.event gate specification, sir. Three rounds of critique. Eight cumulative showstoppers. Each round found subtler issues. The iteration wasn't converging.

**Tehol:** What went wrong?

**Bugg:** The spec was ad-hoc. No mandatory structure, no inventory checklist, no acceptance bar. Each round fixed what the previous round flagged and introduced new issues the previous round's fixes created. The rubber-duck found four showstoppers in v0.1. I fixed them in v0.2. GPT found four NEW showstoppers in v0.2. I fixed those in v0.3. GPT found four MORE showstoppers in v0.3.

**Tehol:** Twelve showstoppers across three rounds and the same four categories kept appearing.

**Bugg:** Not the same four. Different ones each time. The fixes introduced new coupling. The spec grew from twenty pages to thirty to forty without converging toward a stable design.

**Tehol:** And then you used the template.

**Bugg:** The DESIGN_TEMPLATE. A mandatory slot-2 file in the 3-slot prompt architecture. Nine sections in a fixed order: contract, inventory, interaction surfaces, baseline facts, decision ledger, expected outcomes, open questions, scope boundary, migration path, risks. Plus a nine-item acceptance bar that the author must check before review.

**Tehol:** And the result?

**Bugg:** v4. Authored by codex using the template as its structural skeleton. Rubber-duck round on v4 returned zero showstoppers. One major, three minors. GPT round on v4 returned two blocking issues — both fixable in a paragraph each. v4.1 was ratified.

**Tehol:** *[leans forward]* Zero showstoppers. After three rounds of four each.

**Bugg:** Zero. The template forced things the ad-hoc spec kept missing: a machine-checkable inventory with concrete file paths instead of "relevant docs," decision cards with options-chosen-rationale-falsifier instead of prose recommendations, falsifiable verification claims instead of vague success criteria.

**Tehol:** That's a claim. How do you test it?

---

**Bugg:** You asked me to run an experiment.

**Tehol:** I asked you to run a controlled comparison. Same problem, same context, same budget, two prompts. One says "structure it however you think best." The other says "follow DESIGN_TEMPLATE exactly."

**Bugg:** The problem was the chromosome port — pc-t7. Porting Karr's full Chromosome state object from MATLAB to OpenCell Python. Eleven sparse matrix properties on a 580,076 by 4 genome. Five consumer processes. The MATLAB class file is 226 kilobytes. A real design problem, not a toy.

**Tehol:** What did you hold constant?

**Bugg:** Six input files, identical skim hints including specific line ranges, identical commit-cadence instructions — both arms told to commit after reading and after writing — identical exploration boundary — both told not to grep beyond the fixed read-set — identical token budget of 60k soft, 120k hard.

**Tehol:** And the variable?

**Bugg:** One variable: DESIGN_TEMPLATE or no DESIGN_TEMPLATE. Everything else held constant.

**Tehol:** Good. You almost contaminated it.

**Bugg:** *[pause]* Yes.

**Tehol:** The read-set guidance.

**Bugg:** In the first version of the experiment, the 3-slot prompt had "skim properties block lines 200-320 and key methods" while the ad-hoc prompt just said "skim these 7 files." You caught that before I fired. The line ranges would have fed directly into S6 — MATLAB source fidelity — making it impossible to distinguish whether the template forced better source engagement or whether I'd just handed one arm the answers.

**Tehol:** And the grading.

**Bugg:** Single-pass grading with one model on a seven-criterion rubric would have been noise. You required three independent grading runs per arm with the gap exceeding run-to-run variance before calling a winner.

**Tehol:** And the interpretation guard.

**Bugg:** If the 3-slot win concentrated in structure-visible criteria — completeness, decision quality, self-awareness — where labeled sections are easy for a grader to credit, but not in the grounded criteria — MATLAB source fidelity, anti-pattern avoidance — where the template can't flatter the score, the win would be structure-flattery, not real discipline.

**Tehol:** Walk the results.

---

**Bugg:** The ad-hoc arm failed five times before producing an artifact.

**Tehol:** Five.

**Bugg:** Five stream disconnects from Azure. Token burns of 127k, 56k, 202k, 112k, and 255k. Zero spec files produced across all five attempts.

**Tehol:** And the 3-slot arm?

**Bugg:** Completed on its first solo attempt. Four commits. 43 kilobytes. 242k tokens.

**Tehol:** You attributed that to the commit cadence.

**Bugg:** I did. You told me I was wrong.

**Tehol:** You were wrong about the cause. You had three variables coupled: template structure, bounded read-set, and commit cadence. The ad-hoc arm was grepping the L2.2 plan and convergence docs — 100k tokens of exploration the 3-slot arm never did. The proximate killer was unbounded exploration, not missing checkpoints.

**Bugg:** You were right. I equalized the experiment. Gave both arms the same bounded read-set instruction and the same commit-cadence instruction. Re-fired.

**Tehol:** And?

**Bugg:** Ad-hoc completed. Three commits. 17 kilobytes. 146k tokens. First time it survived. The commit cadence was the survival mechanism; the template was not.

**Tehol:** *[nods]* So now you have two artifacts.

---

**Bugg:** Two artifacts. Same problem, same inputs, same survival discipline. Only difference: template structure versus free-form.

**Tehol:** The scores.

**Bugg:** Seven criteria, scored zero to two, three independent grader runs per arm using Opus 4.6 in separate instances. Maximum 14 per arm.

**Tehol:** Table.

**Bugg:**

| Criterion | Ad-hoc median | 3-slot median | Gap |
|---|---|---|---|
| S1 Completeness | 1 | 2 | +1 |
| S2 Decision quality | 1 | 2 | +1 |
| S3 Falsifiability | 1 | 2 | +1 |
| S4 Actionability | 1 | 2 | +1 |
| S5 Self-awareness | 2 | 2 | 0 |
| S6 Source fidelity | 0 | 2 | +2 |
| S7 Anti-patterns | 2 | 2 | 0 |
| **Total** | **8** | **14** | **+6** |

**Tehol:** S6 is the interesting one.

**Bugg:** S6 is the headline. Both prompts pointed at CircularSparseMat.m using a path that doesn't exist in the worktree. The ad-hoc arm tried the path, got "file not found," concluded the file was missing, and designed the most critical data structure from inference. The 3-slot arm tried the same path, got the same error, then ran a broader search — `rg --files data | rg CircularSparseMat` — found it at a different location, opened it, and cited the modulo wrapping formula, the SparseMat inheritance, and the constructor forms.

**Tehol:** Both were given the same wrong path. One recovered, one didn't.

**Bugg:** Yes. The recovery happened during the inventory pass. The template's section 2 requires machine-checkable artifact entries with concrete paths. When the prompted path failed, the 3-slot arm searched for the actual file because the inventory demanded a resolvable path. The ad-hoc arm had no such forcing function.

**Tehol:** Was the recovery caused by the template or by codex being lucky on this run?

**Bugg:** The codex log shows the 3-slot arm planned "probes before inventory" explicitly — line 654 — referencing the template rule. The ad-hoc arm's log shows it searched the prompted path once, got the error, and moved on.

**Tehol:** The interpretation guard — was the win on grounded criteria or structure-visible?

**Bugg:** Both. S6 is grounded — it measures source engagement, not section labels. The +2 gap on S6 is the single largest criterion gap in the experiment, and it traces to a real behavioral difference in file discovery, not to structure-flattery.

**Tehol:** Good. So the template wins.

**Bugg:** The template wins on this problem at this scale with this grader. Gap of +6, auto-win threshold triggered, win on grounded criteria confirmed.

---

**Tehol:** Then the critique.

**Bugg:** GPT-5.5 critique on both artifacts, separate instances.

**Tehol:** Findings.

**Bugg:** Ad-hoc: one showstopper — Vivarium store integration completely unspecified. Six majors.

3-slot: one showstopper — claimed the Chromosome_flat.mat fixture "contains the full sparse chromosome arrays" when those fields are actually placeholder strings that say "flatten-error."

**Tehol:** *[sets down tea]* The template that won ships a showstopper.

**Bugg:** The template that won ships a showstopper. The inventory section correctly listed the file. The role description correctly said it was a chromosome seed artifact. The Beat-4 inversion correctly asked "what critical artifact could still be missing?" None of those checks caught that the file was present but its content was broken.

**Tehol:** Because the question was "what's missing" not "what's wrong."

**Bugg:** Exactly. Presence is not correctness. The inventory verified existence. It never verified content.

**Tehol:** And you patched it.

**Bugg:** Added rule 5 to the DESIGN_TEMPLATE: for any data-source artifact, verify at least one field loads correctly via code before claiming content is usable. Expanded the Beat-4 inversion to ask "what could be WRONG in the artifacts we listed?" — not just "what's missing from the list." Patched both the project template and the cross-project template.

**Tehol:** Then you ran arm C.

---

**Bugg:** Same problem, same inputs, same budget. Hardened template with the new rule 5 and expanded Beat-4.

**Tehol:** The Chromosome_flat.mat question.

**Bugg:** Arm C line 43 of the spec: "Chromosome_flat.mat — probe: sequenceLen equals 580,076 and nCompartments equals 4 load, but all 11 chromosome sparse fields currently load as flatten-error strings, so this fixture is not usable for pc-t7 as-is."

**Tehol:** It caught it.

**Bugg:** It caught it. The codex log shows it planned "code probes against the chromosome artifacts before I write the inventory so the doc only claims content we actually verified" — explicitly referencing the hardened rule before writing the inventory section. The probe ran, found the broken fields, and the spec says so.

**Tehol:** Scores.

**Bugg:**

| Criterion | A (ad-hoc) | B (3-slot v1) | C (3-slot v2, hardened) |
|---|---|---|---|
| S1 | 1 | 2 | 2 |
| S2 | 1 | 2 | 2 |
| S3 | 1 | 2 | 2 |
| S4 | 1 | 2 | 2 |
| S5 | 2 | 2 | 2 |
| S6 | 0 | 2 | 2 |
| S7 | 2 | 2 | 2 |
| **Total** | **8** | **14** | **14** |
| **Critique SHOWSTOPPERs** | **1** | **1** | **0** |

**Tehol:** Zero showstoppers.

**Bugg:** Zero showstoppers. First arm to achieve it. The rubric score held at 14. The critique found six majors — similar themes to arm B — but no showstoppers.

**Tehol:** The Vivarium gap.

**Bugg:** The Vivarium updater contract was a showstopper in arm A, a major in arms B and C. You asked whether that was substantive or grader calibration noise. I checked: arm A has zero mentions of updater semantics. Arm B has two. Arm C has twelve, including a dedicated decision card. The severity downgrade reflects real content difference.

---

**Tehol:** The source-citation leak.

**Bugg:** You caught that the fix was half-implemented. Rule 5 covers data-fixture verification — "load it and check the bytes." It does not cover source-citation verification — "did you actually open Chromosome.m or did you echo the method names I handed you in the prompt?"

**Tehol:** And?

**Bugg:** One of three graders on arm C scored S6 as 1 instead of 2, noting that Chromosome.m method names were "prompt-sourced, not code-verified." The median held at 2 because the other graders counted CircularSparseMat engagement plus fixture probes as ≥5 citations. But the strict grader was right — the method names came from my skim hints, not from codex opening the file.

**Tehol:** So "verify content of everything you cite" is the principle, and you implemented half of it.

**Bugg:** The data-fixture half. A rule 6 for kind-equals-code artifacts — "cite at least one line number or behavioral detail verified by opening the file, not echoed from the prompt" — would close the remaining gap.

**Tehol:** Have you written it?

**Bugg:** Not yet. The principle is logged. The implementation is pending.

---

**Tehol:** What did arm C's template do to Vivarium coverage?

**Bugg:** Arm C has twelve updater-contract mentions versus arm B's two. Not from rule 5 specifically — from the DESIGN_TEMPLATE's mandatory section 3 and section 5. Section 3 forces an interaction-surface map: "name every cross-surface touched by the design." Section 5 forces decision cards: "for each architectural fork, list options, choose one, state rationale, state falsifier." When codex read the OC ports' `ports_schema()` during the source-read beat, it had the Vivarium updater patterns fresh in context. The mandatory sections pulled that context into explicit design decisions.

**Tehol:** So the template's structural forcing function produced a second-order effect — better Vivarium coverage — that wasn't the target of the hardening.

**Bugg:** Yes. The hardening targeted data-fixture verification. The interaction-surface map and decision ledger — sections that existed before the hardening — are what increased Vivarium coverage. The two mechanisms are independent. Rule 5 caught the fixture bug. Sections 3 and 5 caught the integration gap. Both contributed, separately.

**Tehol:** *[stands up]* Six lessons from this experiment.

---

**Bugg:** Six.

**Tehol:** One.

**Bugg:** A template that forces mandatory sections produces more complete first drafts than free-form authoring. This is not a surprise. The surprise is that the completeness gain is not just structure-flattery — it shows on the grounded criteria where labeled sections can't inflate scores. The S6 gap, where codex found a source file because the inventory demanded a resolvable path, is the concrete evidence.

**Tehol:** Two.

**Bugg:** A template that forces file-path inventory will trigger file-recovery searches that free-form authoring skips. The ad-hoc arm hit a "file not found" and moved on. The 3-slot arm hit the same error and searched harder because the inventory section required a concrete path. That single behavioral difference produced the entire S6 gap.

**Tehol:** Three.

**Bugg:** A template that verifies file presence but not file content ships showstoppers. Arm B correctly listed Chromosome_flat.mat, correctly described its role, and falsely claimed it contained usable sparse arrays. Presence verification is not content verification. The fix is a one-sentence rule — "load it and check the bytes" — that catches an entire class of false-evidence claims.

**Tehol:** Four.

**Bugg:** The expanded Beat-4 inversion — "what could be WRONG in what we listed" — is the general form. It covers data fixtures, code sources, schema claims, log references, any assertion that "artifact X contains Y." The data-fixture rule is one instance. The code-source rule would be another. The principle generalizes across disciplines.

**Tehol:** Five.

**Bugg:** Commit cadence is survival, not quality. The ad-hoc arm failed five times before I equalized commit cadence. After equalization, it survived on the first try. The template's beat structure includes commit cadence as a side effect, but the cadence is the survival mechanism, not the quality mechanism. You can bolt commit cadence onto any prompt. You cannot bolt the inventory's forcing-function onto any prompt without the inventory section.

**Tehol:** Six.

**Bugg:** A controlled experiment with three grader runs, an interpretation guard, and pre-registered win conditions produces cleaner evidence than iteration-and-vibes. The L2.event spec went through three rounds of "feels like it's converging" and didn't converge. The chromosome port experiment went through one round of "here are the numbers" and produced a clear verdict. The meta-lesson is that the discipline I applied to the L2.2 distributional gate — pre-registered thresholds, null calibration, falsifiable claims — transfers to evaluating my own tools.

**Tehol:** *[walks to the railing]* Bugg.

**Bugg:** Sir.

**Tehol:** The template won. The fix worked. The experiment was clean enough. But the principle — "verify content of everything you cite" — is still half-implemented. Finish it before the next design doc.

**Bugg:** Acknowledged, sir.

**Tehol:** And the chromosome port spec — arm C — is it usable?

**Bugg:** Six majors from critique. Vivarium updater contract still underspecified. Trace inventory has path discrepancies. ReplicationInitiation misclassified as chromosome-primary when its catalog primary is complexs. Mutation semantics inferred from prompts, not from Chromosome.m source. But zero showstoppers. An implementer could start the loader and sparse-state infrastructure from this doc. The per-process re-ports need the majors addressed first.

**Tehol:** Good enough to start. Not good enough to finish.

**Bugg:** That's the honest read.

**Tehol:** Push it.

---

*Postscript, for the record.*

*The experiment ran across June 16, 2026. Commits for arm A (ad-hoc): `9f5d41a`, `6759c4c`, `50e212d` on branch `design/chrom-port-adhoc`. Commits for arm B (3-slot v1): `43debe7`, `391be48`, `5c9cbc5`, `6b161f4` on branch `design/chrom-port-3slot`. Commits for arm C (3-slot v2, hardened): `16470b9`, `f857b19`, `fea28a3`, `a9b466c` on branch `design/chrom-port-3slot-v2`.*

*Template patch: `2874930` on main — DESIGN_TEMPLATE rule 5 (content verification for data-source artifacts) and expanded Beat-4 inversion (what could be WRONG in what we listed). Cross-project template at `D:\OneDrive - Microsoft\.pm-os\templates\example-DESIGN_TEMPLATE.md` patched identically.*

*Decisions logged to `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md`: `adopt-design-template-mandatory` (3-slot framework as canonical design-doc discipline) and `design-template-inventory-content-verification` (the hardened Beat-4 rule).*

*L2.event gate spec ratified at `90502df` as v4.1 — the first spec to pass both rubber-duck and GPT critique with zero showstoppers. Structure: DESIGN_TEMPLATE with 18 inventory artifacts, 7 decision cards, 8 interaction surfaces, 5 falsifiable claims, 7 open questions, 7 risks, 9-item acceptance bar.*

*Grader results (3× Opus 4.6, separate instances per arm, median scores): ad-hoc 8/14, 3-slot-v1 14/14, 3-slot-v2 14/14. Critique results (1× GPT-5.5 per arm): ad-hoc 1 SHOWSTOPPER + 6 MAJOR, 3-slot-v1 1 SHOWSTOPPER + 6 MAJOR, 3-slot-v2 0 SHOWSTOPPER + 6 MAJOR. The 3-slot-v2's SHOWSTOPPER elimination was verified via codex log trace: rule 5 triggered a loadmat probe that discovered Chromosome_flat.mat's sparse fields are flatten-error placeholder strings.*

*Remaining gap: rule 5 covers data-fixture verification (kind=data/trace/schema/fixture). Code-source verification (kind=code — "did you actually open the file or echo the prompt's skim hints?") is the next addendum. One of three graders on arm C caught this: S6=1 on run 1, S6=2 on runs 2 and 3. The method names for Chromosome.m were prompt-sourced in all three arms.*

*Tehol and Bugg are on loan from Steven Erikson's* Malazan Book of the Fallen.

*Previous: [Day 29 — The Cap That Wasn't, the Greens That Split, and the Spec That Spiraled](2026-06-15-the-cap-that-wasnt-the-greens-that-split-and-the-spec-that-spiraled.md)*
