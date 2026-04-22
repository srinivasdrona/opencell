## Biology/Model PR Checklist

Before merging any PR that changes biology or model behavior:

### Assumptions Changed
- [ ] Which biological assumptions changed?
- [ ] Which parameters changed (values, units, sources)?
- [ ] Were any parameter confidence levels downgraded?

### Impact Assessment
- [ ] Which modules/species are affected?
- [ ] Which invariants were re-run and passed?
- [ ] Did the estimated parameter count increase?

### Evidence
- [ ] New DOIs cited for changed assumptions?
- [ ] Evidence snippets included (not just DOI links)?
- [ ] Contradicting evidence acknowledged?

### Validation
- [ ] Unit tests pass?
- [ ] Property-based tests pass?
- [ ] Conservation invariants pass?
- [ ] Sentinel checks pass (no order-of-magnitude violations)?

### Decision Registry
- [ ] Does this PR change behavior tied to an active decision?
- [ ] If yes, does it reference or supersede the decision in `decisions/_decision_index.yaml`?

### Reproducibility
- [ ] Golden-run regression tests updated if behavior changed?
- [ ] Run manifest captures new parameter versions?
