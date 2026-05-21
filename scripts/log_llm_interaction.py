#!/usr/bin/env python3
"""CLI wrapper around ``opencell.provenance.llm_log.log_interaction``.

Typical agent invocation::

    python scripts/log_llm_interaction.py \\
        --role main_agent \\
        --model claude-opus-4.7 \\
        --task-summary "Wire MATLAB MCOS extract path" \\
        --output-summary "Chose option b2; 44 fixtures extracted; npz bloat fixed" \\
        --linked-todo m1-mcos-decision \\
        --linked-commits 611bb0e,b219c6a \\
        --linked-artifacts scripts/matlab/extract_per_process_fixtures.m \\
        --verification-status verified \\
        --verification-notes "44/44 extracted, 89/89 hash match, m1 tests 70/70"

For longer prompt/output bodies, use ``--prompt-file`` / ``--output-file``
to read from disk instead of passing on the command line.

See ``opencell/provenance/llm_log.py`` for the design and field reference.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.provenance.llm_log import LlmLog, log_interaction  # noqa: E402


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _read_file_or_value(value: str | None, file_path: str | None) -> str | None:
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Append an entry to data/provenance/llm_interactions.jsonl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--role", required=True,
                   choices=["main_agent", "sub_agent", "background_agent",
                            "cross_model_critique", "user_prompt", "retrospective"])
    p.add_argument("--model", required=True,
                   help="Model identifier (e.g. claude-opus-4.7, gpt-5.4)")
    p.add_argument("--task-summary", required=True,
                   help="One-line description of the task")
    p.add_argument("--output-summary",
                   help="One-line description of what was produced. Use --output-file for longer.")
    p.add_argument("--output-file", help="Read the output summary from this file")

    p.add_argument("--prompt-summary",
                   help="Optional summary of the user/agent prompt")
    p.add_argument("--prompt-file", help="Read the prompt summary from this file")

    p.add_argument("--decision-impact",
                   help="Downstream effect (e.g. 'unblocked d2-design-v3-rework BLOCKER #1')")
    p.add_argument("--linked-todo", help="Single todo id this exchange relates to")
    p.add_argument("--linked-commits",
                   help="Comma-separated commit SHAs produced by this exchange")
    p.add_argument("--linked-artifacts",
                   help="Comma-separated artifact paths produced/touched")
    p.add_argument("--tags", help="Comma-separated free-form tags")

    p.add_argument("--verification-status", default="pending",
                   choices=["verified", "accepted", "rejected",
                            "pending", "retrospective_inferred"])
    p.add_argument("--verification-notes",
                   help="How the output was validated (test counts, hash matches, etc.)")

    p.add_argument("--temperature", type=float, help="Sampling temperature if known")
    p.add_argument("--tokens-in", type=int, help="Input tokens if known")
    p.add_argument("--tokens-out", type=int, help="Output tokens if known")
    p.add_argument("--session-id", help="Copilot CLI session id, if known")
    p.add_argument("--supersedes",
                   help="event_id of a prior record this one corrects/replaces")

    p.add_argument(
        "--log-path",
        help="Override the JSONL log path "
             "(default: data/provenance/llm_interactions.jsonl)",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Print the record that would be written but do not append")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output = _read_file_or_value(args.output_summary, args.output_file)
    if not output:
        parser.error("--output-summary or --output-file is required")

    prompt = _read_file_or_value(args.prompt_summary, args.prompt_file)

    record = LlmLog(
        role=args.role,
        model=args.model,
        task_summary=args.task_summary,
        output_summary=output,
        prompt_summary=prompt,
        decision_impact=args.decision_impact,
        linked_todo=args.linked_todo,
        linked_commits=_split_csv(args.linked_commits),
        linked_artifacts=_split_csv(args.linked_artifacts),
        tags=_split_csv(args.tags),
        verification_status=args.verification_status,  # type: ignore[arg-type]
        verification_notes=args.verification_notes,
        temperature=args.temperature,
        tokens_in=args.tokens_in,
        tokens_out=args.tokens_out,
        session_id=args.session_id,
        supersedes=args.supersedes,
    )

    if args.dry_run:
        import json
        from dataclasses import asdict
        record.timestamp_utc = record.timestamp_utc or "<would-be-set-on-write>"
        record.event_id = record.compute_event_id()
        print(json.dumps(asdict(record), indent=2, sort_keys=True))
        return 0

    event_id = log_interaction(record, log_path=args.log_path)
    print(event_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
