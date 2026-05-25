# Swarm Class A v3 — Audit `Transcription` (v3 runtime path)

## Why this re-audit exists

The first Class A pass audited `KarrTranscriptionProcess` in `opencell/vivarium/karr_transcription.py`. The Composition audit (`swarm/composition` branch, `composition_audit.md`) showed that `build_karr_chassis_v6` actually instantiates `KarrTranscriptionV3Process` from `opencell/vivarium/karr_transcription_v3.py` remapped under the process key `karr_transcription`.

That means the biology comparisons in `swarm/class-a/Transcription/findings.json` are scoped to a class the chassis does NOT run. We need to re-validate against the actual runtime class before trusting any of those findings (D1/D3/D4/D5 biology) and before wiring v3 into the allocator.

This audit produces a **fresh findings.json for the v3 class** plus a diff against the v1 audit, so Track-A can land allocator enrollment confidently.

## Inputs

1. **Master template**: `E:\opencell\scripts\swarm\CLASS_A_TEMPLATE.md` — read FIRST, follow the entire methodology (D1-D5 dimensions, schema, citations, WSL discipline, commit-or-stop semantics, STATUS.md protocol).
2. **Composition audit verdict**: `E:\opencell-worktrees\swarm-composition\opencell\validation\swarm\composition\composition_audit.md` — confirms runtime identity is v3.
3. **v1 audit (for diff)**: `E:\opencell-worktrees\swarm-class-a-Transcription\opencell\validation\swarm\class_a\Transcription\findings.json` — the previously-audited (wrong-class) findings. Compare your v3 findings against this.

## Substitutions

Treat this as a Class A audit with these substitutions:

- `{{PROCESS_NAME}}` = `Transcription`
- `{{PROCESS_PY_PATH}}` = `opencell/vivarium/karr_transcription_v3.py` (NOT `karr_transcription.py`)
- `{{KARR_EXTRACT}}` = `docs/karr_extracts/process/09_Transcription.md`
- `{{MATLAB_NAME}}` = `Transcription.m`
- `{{FIXTURE_MAT}}` = `Transcription_flat.mat`

Worktree: `E:\opencell-worktrees\swarm-class-a-v3-tx` (already created)
Branch: `swarm/class-a-v3/Transcription`

Output directory: `opencell/validation/swarm/class_a_v3/Transcription/`
- `findings.json` (same schema as v1)
- `activity_monitor.json` (same schema)
- `v1_v3_diff.md` (~1-2 KB): for each dimension D1-D5, state whether the v1 finding (1) **still applies** to v3, (2) **is resolved** in v3, (3) **is different** in v3 (new finding), or (4) **cannot be compared** (v1 audited code path does not exist in v3). Cite line numbers in both files.

Tests directory: `tests/swarm/class_a_v3/test_Transcription_biology_fires.py` and `test_Transcription_matches_karr.py`.

## Special considerations for v3

- v3 was a code-evolution variant; some dimensions may be substantially different from v1. Don't force-fit findings — if v3 has a clean implementation where v1 had a bug, that's a `mismatch_absent` (positive evidence), not "no finding."
- Use vocabulary discipline: `mismatch_confirmed` / `mismatch_absent` / `evidence_missing`. Never collapse to "no findings."
- If v3 imports or wraps v1 (check the imports), call this out explicitly — it changes whether v1 bugs apply transitively.

## Commit discipline

Single commit on the branch when complete. Trailer:
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

## Halt rules from template apply

If `karr_transcription_v3.py` does not exist, or v6 chassis does not actually instantiate it (revalidate the Composition audit's claim), write STATUS.md and stop.
