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
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.provenance.llm_log import LlmLog, iter_log, log_interaction  # noqa: E402

_ROLES = [
    "main_agent",
    "sub_agent",
    "background_agent",
    "cross_model_critique",
    "user_prompt",
    "retrospective",
]
_VERIFICATION_STATUSES = [
    "verified",
    "accepted",
    "rejected",
    "pending",
    "retrospective_inferred",
]


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _read_file_or_value(value: str | None, file_path: str | None) -> str | None:
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    return value


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid date/time '{value}'. Use ISO format like 2026-05-22 or 2026-05-22T13:30:00+00:00"
            ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_week_label(week_key: tuple[int, int]) -> str:
    year, week = week_key
    week_start = date.fromisocalendar(year, week, 1)
    week_end = date.fromisocalendar(year, week, 7)
    return f"{year}-W{week:02d} ({week_start.isoformat()} to {week_end.isoformat()})"


def _parse_record_ts(record: dict) -> datetime:
    ts = record.get("timestamp_utc")
    if not isinstance(ts, str):
        return datetime.min.replace(tzinfo=UTC)
    try:
        return _parse_datetime(ts)
    except argparse.ArgumentTypeError:
        return datetime.min.replace(tzinfo=UTC)


def _iter_filtered_records(
    *,
    by_model: str | None,
    by_role: str | None,
    since: datetime | None,
    log_path: str | None,
) -> list[dict]:
    records = list(iter_log(log_path=log_path))
    filtered: list[dict] = []
    for record in records:
        if by_model and record.get("model") != by_model:
            continue
        if by_role and record.get("role") != by_role:
            continue
        if since and _parse_record_ts(record) < since:
            continue
        filtered.append(record)
    return filtered


def _configure_log_parser(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--role", required=True, choices=_ROLES)
    subparser.add_argument(
        "--model",
        required=True,
        help="Model identifier (e.g. claude-opus-4.7, gpt-5.4)",
    )
    subparser.add_argument("--task-summary", required=True, help="One-line description of the task")
    subparser.add_argument(
        "--output-summary",
        help="One-line description of what was produced. Use --output-file for longer.",
    )
    subparser.add_argument("--output-file", help="Read the output summary from this file")

    subparser.add_argument("--prompt-summary", help="Optional summary of the user/agent prompt")
    subparser.add_argument("--prompt-file", help="Read the prompt summary from this file")

    subparser.add_argument(
        "--decision-impact",
        help="Downstream effect (e.g. 'unblocked d2-design-v3-rework BLOCKER #1')",
    )
    subparser.add_argument("--linked-todo", help="Single todo id this exchange relates to")
    subparser.add_argument(
        "--linked-commits", help="Comma-separated commit SHAs produced by this exchange"
    )
    subparser.add_argument(
        "--linked-artifacts", help="Comma-separated artifact paths produced/touched"
    )
    subparser.add_argument("--tags", help="Comma-separated free-form tags")

    subparser.add_argument(
        "--verification-status", default="pending", choices=_VERIFICATION_STATUSES
    )
    subparser.add_argument(
        "--verification-notes",
        help="How the output was validated (test counts, hash matches, etc.)",
    )

    subparser.add_argument("--temperature", type=float, help="Sampling temperature if known")
    subparser.add_argument("--tokens-in", type=int, help="Input tokens if known")
    subparser.add_argument("--tokens-out", type=int, help="Output tokens if known")
    subparser.add_argument("--session-id", help="Copilot CLI session id, if known")
    subparser.add_argument(
        "--supersedes", help="event_id of a prior record this one corrects/replaces"
    )

    subparser.add_argument(
        "--log-path",
        help="Override the JSONL log path (default: opencell/provenance/llm_interactions.jsonl)",
    )
    subparser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the record that would be written but do not append",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Write/query/report opencell/provenance/llm_interactions.jsonl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = p.add_subparsers(dest="command")

    log_parser = subparsers.add_parser("log", help="Append one interaction record")
    _configure_log_parser(log_parser)

    append_parser = subparsers.add_parser("append", help="Alias for log")
    _configure_log_parser(append_parser)

    query_parser = subparsers.add_parser("query", help="Query records with simple filters")
    query_parser.add_argument("--by-model", help="Filter by model identifier")
    query_parser.add_argument("--by-role", choices=_ROLES, help="Filter by role")
    query_parser.add_argument(
        "--since",
        type=_parse_datetime,
        help="Filter to records on/after this ISO date or datetime",
    )
    query_parser.add_argument(
        "--log-path",
        help="Override the JSONL log path (default: opencell/provenance/llm_interactions.jsonl)",
    )

    stats_parser = subparsers.add_parser("stats", help="Show summary counts")
    stats_parser.add_argument(
        "--log-path",
        help="Override the JSONL log path (default: opencell/provenance/llm_interactions.jsonl)",
    )

    report_parser = subparsers.add_parser("report", help="Emit a weekly report")
    report_parser.add_argument("--markdown", action="store_true", help="Emit Markdown output")
    report_parser.add_argument(
        "--log-path",
        help="Override the JSONL log path (default: opencell/provenance/llm_interactions.jsonl)",
    )

    return p


def _run_log(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
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
        from dataclasses import asdict

        record.timestamp_utc = record.timestamp_utc or "<would-be-set-on-write>"
        record.event_id = record.compute_event_id()
        print(json.dumps(asdict(record), indent=2, sort_keys=True))
        return 0

    event_id = log_interaction(record, log_path=args.log_path)
    print(event_id)
    return 0


def _run_query(args: argparse.Namespace) -> int:
    records = _iter_filtered_records(
        by_model=args.by_model,
        by_role=args.by_role,
        since=args.since,
        log_path=args.log_path,
    )
    for record in records:
        print(json.dumps(record, sort_keys=True))
    return 0


def _run_stats(args: argparse.Namespace) -> int:
    records = list(iter_log(log_path=args.log_path))
    models = {r.get("model") for r in records if r.get("model")}
    per_role = Counter(r.get("role") for r in records if r.get("role"))

    print(f"Total records: {len(records)}")
    print(f"Unique models: {len(models)}")
    print("Records per role:")
    for role, count in sorted(per_role.items()):
        print(f"- {role}: {count}")
    return 0


def _is_notable(record: dict) -> bool:
    if record.get("decision_impact"):
        return True
    if record.get("linked_commits"):
        return True
    status = record.get("verification_status")
    return status in {"verified", "accepted", "rejected"}


def _run_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.markdown:
        parser.error("report currently supports only --markdown output")

    records = list(iter_log(log_path=args.log_path))
    print("# LLM Interaction Weekly Report")
    print()
    print(f"- Total records: {len(records)}")
    if not records:
        print("- Weeks covered: 0")
        return 0

    by_week: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for record in records:
        ts = _parse_record_ts(record)
        iso = ts.isocalendar()
        by_week[(iso.year, iso.week)].append(record)

    print(f"- Weeks covered: {len(by_week)}")
    for week_key in sorted(by_week):
        week_records = by_week[week_key]
        models = Counter(str(rec.get("model", "")) for rec in week_records if rec.get("model"))
        roles = Counter(str(rec.get("role", "")) for rec in week_records if rec.get("role"))
        notables = [rec for rec in week_records if _is_notable(rec)]
        if not notables and week_records:
            notables = [week_records[0]]

        print()
        print(f"## Week {_format_week_label(week_key)}")
        print(f"- Records: {len(week_records)}")
        print(
            "- Models: "
            + ", ".join(f"{model} ({count})" for model, count in sorted(models.items()))
        )
        print("- Roles: " + ", ".join(f"{role} ({count})" for role, count in sorted(roles.items())))
        print("- Notable events:")
        for record in notables[:5]:
            timestamp = str(record.get("timestamp_utc", ""))[:10]
            summary = str(record.get("task_summary", "")).strip() or "<no task summary>"
            model = str(record.get("model", ""))
            role = str(record.get("role", ""))
            print(f"  - {timestamp} {role}/{model}: {summary}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if not args_list or args_list[0].startswith("-"):
        args_list = ["log", *args_list]
    args = parser.parse_args(args_list)

    if args.command in {"log", "append"}:
        return _run_log(args, parser)
    if args.command == "query":
        return _run_query(args)
    if args.command == "stats":
        return _run_stats(args)
    if args.command == "report":
        return _run_report(args, parser)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
