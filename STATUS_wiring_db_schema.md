# STATUS - wiring DB schema

What I did:
- Designed a new per-process wiring DB contract for OpenCell/Karr ports.
- Added a revision-class design doc at `data/schemas/per_process_wiring/SCHEMA.md`.
- Added a machine-readable YAML schema at `data/schemas/per_process_wiring/_schema.yaml`.
- Added a worked Metabolism example row at `data/schemas/per_process_wiring/Metabolism.yaml`.

Key decisions:
- D1: YAML, not TOML.
- D2: one file per process, not a combined DB.
- D3: string-typed symbolic formulas, not structured ASTs.
- D4: nested method bindings under method names, not a flat cross-reference file.
- D5: per-row semantic versioning with additive minors and breaking majors.

Why this shape:
- The existing per-process TOMLs already capture state shapes, but the missing failure surfaces are wiring surfaces: allocator requests, bypasses, LP bound source, compartment routing, and method correspondence.
- The example row for Metabolism explicitly exposes the A3, A3b, and A4 deviations so later rows can be audited mechanically from the DB alone.

Open questions for the operator:
- Should later rows enumerate only canonical exemplars like the Metabolism example, or should the first batch insist on exhaustive tuple lists where the source makes them available?
- Do we want a generated cross-row index artifact in addition to the one-file-per-process layout?
- Should the schema later promote formulas from strings to a parsed expression tree once the row format stabilizes?

Validation:
- YAML parse validation still needs to be run in WSL against the new files.
- I have not run a cross-row consistency checker; that is intentionally out of scope for this revision.
