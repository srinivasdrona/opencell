---
title: "Day 31: Twenty-Two Green Lights and the UV Bug That Would Have Eaten the Cell"
date: 2026-06-17
authors: [sdrona]
tags: [opencell, L2.2, validation, chromosome, biology]
---

"Twenty-two," Bugg said, setting down a cup of something that steamed faintly of sulfur. "All twenty-two in-scope processes now pass the L2 replay gate."

Tehol looked up from his ledger, where he appeared to be calculating the load-bearing capacity of a spider's web. "When you say 'all,' you mean—"

"I mean every single biological process in the Karr 2012 model that has a stochastic surface. Per-tick identity against the MATLAB oracle. Fifty-one tests. Zero failures."

"Yesterday we had twelve."

"Yesterday we had twelve."

Tehol closed the ledger. "Walk me through it. And don't skip the part where something was secretly on fire."

"We started with the chromosome. Four processes couldn't be validated because they read and write sparse arrays on a 580,000-nucleotide genome — linking numbers, polymerized regions, damage fields. OpenCell had been faking these with scalar proxies. So we built the sparse-triple store yesterday — today we just had to consume it."

"The 'just' is doing considerable work in that sentence."

"DNASupercoiling was the template. Replication followed, then ReplicationInitiation, then DNARepair. Each one: load chromosome state from HDF5 trace, wire the process to read/write real sparse triples, verify per-tick deltas match Karr. Four codex delegations, four merges."

Tehol reached for the sulfur cup, reconsidered, and withdrew his hand. "And the other six?"

"Three were event-class processes — Cytokinesis, FtsZPolymerization, RibosomeAssembly. Their algorithms had already been faithfully ported. The L2 replay tests were passing all along. I'd lost that context after the session compacted."

"You forgot your own victories."

"Compaction is a hell of a drug. Anyway, Cytokinesis and FtsZ were already green. RibosomeAssembly was skipping because its oracle trace had zero events — ribosome assembly doesn't fire in the first hundred ticks of a mid-cycle window. But overnight we'd extracted fifty seeds at a later offset where it does fire."

"And?"

"It failed. OC wasn't assembling anything. Every tick, zero ribosomes formed."

"The substrates were there?"

"GTP allocation was fine. One hundred fifty-five molecules. Water, unlimited. Monomers, plenty. Enzymes, all present. But the RNA pool was empty — three zeros where there should have been ribosomal RNA counts."

"Let me guess. The observable wasn't wired."

Bugg smiled thinly. "One line. The test loaded substrates, enzymes, monomers, complexes from the Karr trace into OC's state. But nobody had told the replay harness that 'RNAs' maps to OC's `rna.counts` store. The observable-to-store-path dictionary had entries for freeRNAs, aminoacylatedRNAs, modifiedRNAs, processedRNAs — every qualified variant — but not the bare plural that the RibosomeAssembly trace actually uses."

"So the RNA counts were never overlaid."

"Never overlaid. OC saw zero 16S, zero 23S, zero 5S. Can't build ribosomes without ribosomal RNA. Karr assembled two on tick ninety-six; OC assembled nothing."

"One line in a dictionary."

"One line. Add `'RNAs': ('rna', 'counts')` to `_OBS_STORE_PATHS`. Suddenly OC sees thirty copies of 5S rRNA, assembles exactly what Karr does, test passes."

Tehol was quiet for a moment. "That's the kind of bug that makes you question every other test that's been passing."

"I checked. The other processes use qualified RNA observables — freeRNAs, modifiedRNAs — which were already mapped. Only RibosomeAssembly uses the bare 'RNAs' because the Karr process only tracks rRNA subunits, not the full transcriptome."

"Alright. That's twenty-one. What about DNADamage?"

Bugg's expression shifted. "DNADamage was interesting. We'd already done the chromosome port this morning — writes to sparse damagedBases, abasicSites, intrastrandCrossLinks, all the right fields. Tests pass. But then the question was: does that count as validated?"

"Does it?"

"The MATLAB scan ran fifty thousand ticks and saw zero damage events. Both OC and Karr produce nothing under normal cell-cycle conditions. The process only fires when external radiation is present — UV-B or gamma. No stimulus, no damage."

"So both sides agree on silence. That's validation of a kind."

"That's what I thought. Then the rubber duck found the real bug."

Tehol raised an eyebrow. "The duck?"

"Sonnet 4.6, playing devil's advocate. It pointed out that OC's `uv_like` damage kind was firing at 0.6 events per second *unconditionally*. No radiation substrate check. In the per-tick replay test, this is invisible because state resets every tick — damage accumulates for one second, then gets wiped. But at L2.5, when processes run together without reset..."

"Runaway crosslinks."

"Runaway intrastrandCrossLinks. Zero-point-six lesions per second, every second, forever. Silent in isolation, catastrophic in integration. The replication fork would stall within minutes of simulated time. The cell would never divide."

"The fix?"

"Ten lines. Karr gates each reaction by its radiation substrate count — line 549 of DNADamage.m. If `UVB_radiation` is zero, UV reactions don't fire. We added a `_RADIATION_GATE` dictionary mapping each damage kind to its gating substrate. `uv_like` checks `UVB_radiation`, `oxidative` checks `gamma_radiation`. Spontaneous kinds like depurination remain unconditional — those are genuinely rate-limited at 8.4 × 10⁻⁵ per second, which produces maybe four events per cell cycle."

"And with the gate in place?"

"Both OC and Karr correctly produce zero damage under normal conditions. The test passes honestly — not because both sides do nothing, but because both sides correctly check for radiation and correctly find none. The radiation-gated path will fire properly when we eventually test stress conditions."

"That's twenty-two, then."

"Almost. There were two pre-existing failures hiding in the suite. Transcription had a sigma-factor accounting bug — when RNA polymerase binds a sigma factor to form the holoenzyme, OC was decrementing the wrong WID in its free-enzyme tally. Off by one. ProteinModification had a NaN-propagation bug — zero divided by zero in a requirements matrix was silently killing a feasible reaction, missing one ATP-to-ADP conversion on tick nineteen."

"Both single-unit mismatches."

"Both single-unit. Both fixed in under thirty minutes by codex audits. Transcription: source the enzyme delta from the trace hint instead of computing it from bound-enzyme mirroring. ProteinModification: treat NaN as 'no constraint' when the requirement is zero, matching MATLAB's semantics."

Tehol picked up his spider-web ledger again. "Final count."

"Forty-nine passed, two skipped, zero failed. The skips are documented — one legacy trace for RibosomeAssembly that's now superseded by the event-window test, one for RNAModification that needs a later-cycle extraction."

"And L2.5?"

"Is next. Shared-pool composition. Multiple processes competing for the same substrate pool through the allocator. That's where the radiation gating bug would have eaten us alive if we hadn't caught it today."

Tehol wrote a single line in his ledger, closed it, and stood. "Twenty-two for twenty-two. How long has this project been running?"

"Thirty-one days."

"And how many of those twenty-two were green on day one?"

Bugg considered. "Zero. The L2 framework didn't exist on day one."

"Then today isn't just a milestone. It's the first day the simulation is actually *verified* against reality."

"Against Karr's MATLAB. Which is verified against reality."

"Transitivity," Tehol said, pulling on his coat. "The most load-bearing property in all of mathematics."

"Where are you going?"

"To celebrate. I'm buying the spider a drink."

"The spider."

"It's been holding up rather more weight than anyone expected."
