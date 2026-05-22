"""Cost tracker: per-call token/cost logging to SQLite.

Logs every LLM API call with token counts, cost estimates, and metadata.
Provides CLI-style queries: summary, by-phase, by-tier, by-role.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (input/output) — UNVERIFIED estimates
COST_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-haiku": {"input": 0.25, "output": 1.25},
    "gpt-5": {"input": 5.0, "output": 15.0},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6},
    "grok-3": {"input": 3.0, "output": 15.0},
}


@dataclass
class APICallRecord:
    """Record of a single API call."""

    timestamp: str
    model_id: str
    tier: str
    task_type: str
    phase: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    duration_ms: float = 0.0
    success: bool = True
    notes: str = ""


class CostTracker:
    """Track LLM API costs in a SQLite database."""

    def __init__(self, db_path: str | Path = "opencell_costs.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model_id TEXT NOT NULL,
                tier TEXT NOT NULL,
                task_type TEXT NOT NULL,
                phase TEXT DEFAULT '',
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                duration_ms REAL DEFAULT 0,
                success INTEGER DEFAULT 1,
                notes TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()

    def log_call(self, record: APICallRecord) -> None:
        """Log an API call."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO api_calls
            (timestamp, model_id, tier, task_type, phase,
             input_tokens, output_tokens, estimated_cost_usd,
             duration_ms, success, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.timestamp,
                record.model_id,
                record.tier,
                record.task_type,
                record.phase,
                record.input_tokens,
                record.output_tokens,
                record.estimated_cost_usd,
                record.duration_ms,
                int(record.success),
                record.notes,
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a call based on token counts."""
        rates = COST_PER_1M_TOKENS.get(model_id, {"input": 5.0, "output": 15.0})
        cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
        return round(cost, 6)

    def summary(self) -> dict[str, Any]:
        """Get cost summary."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total_calls,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(estimated_cost_usd) as total_cost,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_calls
            FROM api_calls
        """)
        row = cursor.fetchone()
        conn.close()
        return {
            "total_calls": row[0] or 0,
            "total_input_tokens": row[1] or 0,
            "total_output_tokens": row[2] or 0,
            "total_cost_usd": round(row[3] or 0, 4),
            "failed_calls": row[4] or 0,
        }

    def by_tier(self) -> list[dict[str, Any]]:
        """Get costs grouped by tier."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT tier, COUNT(*), SUM(estimated_cost_usd)
            FROM api_calls GROUP BY tier ORDER BY tier
        """)
        results = [{"tier": r[0], "calls": r[1], "cost_usd": round(r[2], 4)} for r in cursor]
        conn.close()
        return results
