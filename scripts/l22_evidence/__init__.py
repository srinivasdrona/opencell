"""L2.2 evidence-index generator.

This package replaces the hand-written verdict dictionaries that used to
live in ``tests/vivarium/test_l2_2_strict_rubric.py`` and
``scripts/probe_l2_2_strict_audit.py`` with a generator-only machine
evidence index (``docs/phase_f/l2_2_design_a/evidence_index.json``).

See ``docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md`` for the full
contract: scope derivation, authority files, mechanical verdict
re-derivation, and the two-stage integrity-vs-acceptance model.

Modules:
    catalog.py   -- lightweight PROCESS_CATALOG.yaml access (reuses
                    scripts/l22_extraction/derive_scope.py's parsing).
    schema.py    -- versioned constants: paths, required files, status codes.
    verdict.py   -- mechanical per-channel/per-process verdict re-derivation
                    from raw evidence numbers (stored verdict strings are
                    never trusted).
    generator.py -- build_evidence_index() / audit() / CLI entry point.
"""
