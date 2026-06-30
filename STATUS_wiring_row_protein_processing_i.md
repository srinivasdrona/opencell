# STATUS

Authored `data/schemas/per_process_wiring/ProteinProcessingI.yaml` for `Process_ProteinProcessingI`.

What I captured:
- Class identity and file mapping for MATLAB and OC.
- Allocation mode as `allocation` on both sides, with OC reading only `substrates_allocated[self.name]`.
- The allocator request surface for the only mediated input, `H2O`.
- Count-domain stoichiometry for water consumption and the `H`, `FOR`, `MET` writebacks.
- Compartment routing as cytosol-only.
- The OC request calculator and process update anchors, plus the composite wiring anchors.
- Provenance, including the OC commit SHA and the fixture files loaded by the OC constructor.

Uncertainties and notes:
- `calcFluxBounds` does not appear to be a real process method for ProteinProcessingI in either the raw MATLAB file or the OC port, so I marked it `NOT_IMPLEMENTED`.
- The MATLAB line anchors are taken from the raw source at `E:/opencell` and the local process extract / diagnostics; the worktree copy itself did not need to host the MATLAB source.
- OC differs from MATLAB in the stochastic event sampler (`multivariate_hypergeometric` versus MATLAB's `stochasticRound` + `mnrnd` + `min` clipping).

Deviations observed:
- Strict-zero allocator read in OC.
- Request logic split out of the process into `RequestCalculatorProteinPathway`.
- No flux-bound routine in the OC port.

PARTIAL: the row is authored and schema-shaped, but the MATLAB request block is represented as a symbolic summary rather than a verbatim executable formula string.
