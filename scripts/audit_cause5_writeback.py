"""Audit CAUSE_5 processes for missing-channel-writeback pattern.

For each process, instantiate it with default params, call next_update with a
minimal states dict (no trace_hint -> exercises no-hints branch), then check
which channels are emitted vs the per-process TOML's declared output channels.

Classification:
- SIMPLE: process emits FEWER channels than declared -> missing writeback
- COMPLEX: process emits all declared channels but values diverge -> biology port
- INCONCLUSIVE: instantiation/call failed -> needs hands-on look
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import tomllib  # py311+

SCHEMA_DIR = Path("data/schemas/per_process")
PROCESSES_TO_AUDIT = [
    ("DNASupercoiling",       "opencell.vivarium.karr_dna_supercoiling",       "KarrDNASupercoilingProcess"),
    ("FtsZPolymerization",    "opencell.vivarium.karr_ftsz_polymerization",    "KarrFtsZPolymerizationProcess"),
    ("ProteinModification",   "opencell.vivarium.karr_protein_modification",   "KarrProteinModificationProcess"),
    ("RNADecay",              "opencell.vivarium.karr_rna_decay",              "RnaDecayLightProcess"),
    ("Transcription",         "opencell.vivarium.karr_transcription",          "KarrTranscriptionProcess"),
    ("Replication",           "opencell.vivarium.karr_replication",            "KarrReplicationProcess"),
]


def load_expected_channels(process_name: str) -> set[str]:
    """Read the per-process TOML and extract the expected output channel names."""
    # The TOML files are named after the process; try a few common conventions
    candidates = [
        SCHEMA_DIR / f"{process_name}.toml",
        SCHEMA_DIR / f"karr_{process_name.lower()}.toml",
        SCHEMA_DIR / f"{process_name.lower()}.toml",
    ]
    toml_path = next((p for p in candidates if p.exists()), None)
    if toml_path is None:
        # Try a wider scan
        for p in SCHEMA_DIR.glob("*.toml"):
            with open(p, "rb") as f:
                d = tomllib.load(f)
            meta = d.get("metadata", {}) or d.get("process", {}) or {}
            if meta.get("name") == process_name or meta.get("process_name") == process_name:
                toml_path = p
                break
    if toml_path is None:
        print(f"  WARN: no TOML found for {process_name}; scanned {SCHEMA_DIR}")
        return set()

    with open(toml_path, "rb") as f:
        d = tomllib.load(f)

    # Look for observable channels in a few likely keys
    channels: set[str] = set()
    # Common locations from the v2.1 schema
    for key in ("observables", "output_channels", "observable_channels"):
        v = d.get(key)
        if isinstance(v, list):
            channels.update(str(x) for x in v)
        elif isinstance(v, dict):
            channels.update(v.keys())
    # Some schemas nest under "states_after" or "outputs"
    sa = d.get("states_after")
    if isinstance(sa, dict):
        channels.update(sa.keys())
    return channels


def emit_channels_from_proc(module_path: str, class_name: str) -> tuple[set[str], str | None]:
    """Instantiate the process and call next_update with a minimal states dict.

    Returns (emitted_channels, error_message_or_None).
    """
    try:
        mod = __import__(module_path, fromlist=[class_name])
        ProcClass = getattr(mod, class_name)
    except Exception as e:
        return set(), f"import_failure: {type(e).__name__}: {e}"

    try:
        proc = ProcClass({})
    except Exception:
        try:
            # Some processes need positional args
            proc = ProcClass()
        except Exception as e:
            return set(), f"instantiation_failure: {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"

    # Try to build a minimal states dict from the port_schema
    try:
        schema = proc.ports_schema()
    except Exception as e:
        return set(), f"ports_schema_failure: {type(e).__name__}: {e}"

    states = _build_minimal_states_from_schema(schema)
    # Ensure no trace_hint (forces no-hints branch)
    states["trace_hint"] = {}

    try:
        update = proc.next_update(1.0, states)
    except Exception as e:
        return set(), f"next_update_failure: {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"

    if not isinstance(update, dict):
        return set(), f"next_update_returned_non_dict: {type(update).__name__}"

    return set(update.keys()), None


def _build_minimal_states_from_schema(schema: dict) -> dict:
    """Walk schema and build a dict of zero-valued defaults for every WID."""
    out: dict = {}
    for port_name, port_def in (schema or {}).items():
        if port_name == "trace_hint":
            out[port_name] = {}
            continue
        if not isinstance(port_def, dict):
            out[port_name] = 0
            continue
        # Recurse: at each leaf with _default, take it (or 0)
        out[port_name] = _walk_schema_node(port_def)
    return out


def _walk_schema_node(node: dict):
    if not isinstance(node, dict):
        return 0
    if "_default" in node:
        return node["_default"]
    out: dict = {}
    for k, v in node.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            out[k] = _walk_schema_node(v)
        else:
            out[k] = 0
    return out


def main() -> int:
    print("=" * 70)
    print("CAUSE_5 audit: which processes have a SIMPLE missing-writeback bug?")
    print("=" * 70)
    print()

    summary: list[tuple[str, str, str]] = []  # (proc_name, verdict, detail)

    for proc_name, mod_path, cls_name in PROCESSES_TO_AUDIT:
        print(f"\n--- {proc_name} ---")
        expected = load_expected_channels(proc_name)
        print(f"  expected channels (from TOML): {sorted(expected) if expected else '(none found)'}")
        emitted, err = emit_channels_from_proc(mod_path, cls_name)
        if err:
            print(f"  EMIT ERROR: {err.splitlines()[0]}")
            summary.append((proc_name, "INCONCLUSIVE", err.splitlines()[0]))
            continue
        print(f"  emitted channels (no-hints next_update): {sorted(emitted)}")
        # Filter out non-observable keys from emitted (e.g., 'requests' is internal)
        observable_emit = {c for c in emitted if c in expected} if expected else emitted
        missing = expected - emitted
        extra = emitted - expected
        if expected and missing:
            verdict = "SIMPLE: missing-writeback"
            detail = f"missing={sorted(missing)}, extra={sorted(extra)}"
        elif expected and not missing:
            verdict = "COMPLEX: all channels emitted (need value-level investigation)"
            detail = f"emitted_all_{len(expected)}, extra={sorted(extra)}"
        elif not expected:
            verdict = "INCONCLUSIVE: no TOML expected channels"
            detail = f"emitted={sorted(emitted)}"
        else:
            verdict = "?"
            detail = "?"
        print(f"  VERDICT: {verdict}")
        print(f"  DETAIL:  {detail}")
        summary.append((proc_name, verdict, detail))

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for proc_name, verdict, detail in summary:
        print(f"  {proc_name:25s}  {verdict}")
        print(f"  {'':25s}  -> {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
