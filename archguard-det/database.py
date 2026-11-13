"""SQLite persistence layer for ArchGuard-Det audit runs and benchmark experiments."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any


def get_db_path() -> str:
    """Resolve database path from ARCHGUARD_DB_PATH with safe default."""
    return os.environ.get("ARCHGUARD_DB_PATH", "audit_benchmarks.db")


class AuditDatabase:
    """Manages deterministic SQLite storage for audit and ablation benchmark runs."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_db_path()
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    node_count INTEGER NOT NULL,
                    edge_count INTEGER NOT NULL,
                    adi_score REAL NOT NULL,
                    total_violations INTEGER NOT NULL,
                    execution_ms REAL NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    ground_truth_count INTEGER NOT NULL,
                    proposed_precision REAL NOT NULL,
                    proposed_recall REAL NOT NULL,
                    proposed_f1 REAL NOT NULL,
                    proposed_adi REAL NOT NULL,
                    csv_content TEXT NOT NULL,
                    latex_content TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )

    def save_audit_run(
        self,
        repo_path: str,
        node_count: int,
        edge_count: int,
        adi_score: float,
        total_violations: int,
        execution_ms: float,
        result: dict[str, Any],
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_runs (
                    created_at, repo_path, node_count, edge_count,
                    adi_score, total_violations, execution_ms, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    repo_path,
                    node_count,
                    edge_count,
                    adi_score,
                    total_violations,
                    execution_ms,
                    json.dumps(result),
                ),
            )
            return int(cursor.lastrowid)

    def get_latest_audit(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row["result_json"])
            payload["audit_id"] = row["id"]
            payload["created_at"] = row["created_at"]
            return payload

    def save_benchmark_run(self, benchmark_result: dict[str, Any]) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        methods = benchmark_result.get("methods", [])
        proposed = methods[-1] if methods else {}
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO benchmark_runs (
                    created_at, ground_truth_count, proposed_precision,
                    proposed_recall, proposed_f1, proposed_adi,
                    csv_content, latex_content, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    int(benchmark_result.get("ground_truth_count", 0)),
                    float(proposed.get("precision", 0.0)),
                    float(proposed.get("recall", 0.0)),
                    float(proposed.get("f1_score", 0.0)),
                    float(benchmark_result.get("proposed_adi_score", 0.0)),
                    benchmark_result.get("csv_content", ""),
                    benchmark_result.get("latex_content", ""),
                    json.dumps(benchmark_result),
                ),
            )
            return int(cursor.lastrowid)

    def get_latest_benchmark(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM benchmark_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row["result_json"])
            payload["benchmark_id"] = row["id"]
            payload["created_at"] = row["created_at"]
            return payload

    def list_history(self, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as conn:
            audits = conn.execute(
                """
                SELECT id, created_at, repo_path, node_count, edge_count,
                       adi_score, total_violations, execution_ms
                FROM audit_runs ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            benchmarks = conn.execute(
                """
                SELECT id, created_at, ground_truth_count, proposed_precision,
                       proposed_recall, proposed_f1, proposed_adi
                FROM benchmark_runs ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return {
                "audits": [dict(r) for r in audits],
                "benchmarks": [dict(r) for r in benchmarks],
            }
