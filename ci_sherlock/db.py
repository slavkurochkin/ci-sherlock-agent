import os
from datetime import datetime, timezone
from sqlite_utils import Database as SqliteDatabase
from ci_sherlock.models import AnalysisResult, TestResult, Correlation, LLMInsight


class Database:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        self._db = SqliteDatabase(path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._db["runs"].create(
            {
                "id": str,
                "repo": str,
                "pr_number": int,
                "commit_sha": str,
                "branch": str,
                "status": str,
                "total_tests": int,
                "passed_tests": int,
                "failed_tests": int,
                "skipped_tests": int,
                "duration_ms": int,
                "release_readiness_score": float,
                "created_at": str,
            },
            pk="id",
            if_not_exists=True,
        )

        self._db["test_results"].create(
            {
                "id": int,
                "run_id": str,
                "test_name": str,
                "test_file": str,
                "status": str,
                "duration_ms": int,
                "retry_count": int,
                "error_message": str,
                "error_stack": str,
                "trace_path": str,
            },
            pk="id",
            if_not_exists=True,
        )

        self._db["correlations"].create(
            {
                "id": int,
                "run_id": str,
                "test_name": str,
                "test_file": str,
                "changed_file": str,
                "score": float,
                "reason": str,
            },
            pk="id",
            if_not_exists=True,
        )

        self._db["insights"].create(
            {
                "id": int,
                "run_id": str,
                "root_cause": str,
                "confidence": float,
                "recommendation": str,
                "flaky_tests": str,  # JSON array
                "model": str,
                "created_at": str,
            },
            pk="id",
            if_not_exists=True,
        )

        self._db["optimization_suggestions"].create(
            {
                "id": int,
                "run_id": str,
                "type": str,
                "description": str,
                "impact": str,
                "metadata": str,  # JSON blob
            },
            pk="id",
            if_not_exists=True,
        )

    def write_run(self, analysis: AnalysisResult) -> None:
        status = "failed" if analysis.failed_tests > 0 else "passed"
        self._db["runs"].upsert(
            {
                "id": analysis.run_id,
                "repo": analysis.repo,
                "pr_number": analysis.pr_number,
                "commit_sha": analysis.commit_sha,
                "branch": analysis.branch,
                "status": status,
                "total_tests": analysis.total_tests,
                "passed_tests": analysis.passed_tests,
                "failed_tests": analysis.failed_tests,
                "skipped_tests": analysis.skipped_tests,
                "duration_ms": analysis.duration_ms,
                "release_readiness_score": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            pk="id",
        )

    def write_results(self, run_id: str, results: list[TestResult]) -> None:
        self._db["test_results"].insert_all(
            [
                {
                    "run_id": run_id,
                    "test_name": r.test_name,
                    "test_file": r.test_file,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "retry_count": r.retry_count,
                    "error_message": r.error_message,
                    "error_stack": r.error_stack,
                    "trace_path": r.trace_path,
                }
                for r in results
            ],
            ignore=True,
        )

    def write_correlations(self, run_id: str, correlations: list[Correlation]) -> None:
        self._db["correlations"].insert_all(
            [
                {
                    "run_id": run_id,
                    "test_name": c.test_name,
                    "test_file": c.test_file,
                    "changed_file": c.changed_file,
                    "score": c.score,
                    "reason": c.reason,
                }
                for c in correlations
            ],
            ignore=True,
        )

    def write_insight(self, run_id: str, insight: LLMInsight, model: str) -> None:
        import json
        self._db["insights"].insert(
            {
                "run_id": run_id,
                "root_cause": insight.root_cause,
                "confidence": insight.confidence,
                "recommendation": insight.recommendation,
                "flaky_tests": json.dumps(insight.flaky_tests),
                "model": model,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_runs(self, limit: int = 50) -> list[dict]:
        return list(self._db.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", [limit]
        ).fetchall())

    def get_test_results(self, run_id: str) -> list[dict]:
        return list(self._db.execute(
            "SELECT * FROM test_results WHERE run_id = ?", [run_id]
        ).fetchall())

    def get_flaky_tests(self, last_n_runs: int = 20, threshold: float = 0.10) -> list[dict]:
        return list(self._db.execute(
            """
            SELECT
                test_name,
                test_file,
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures,
                ROUND(
                    1.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 3
                ) AS failure_rate
            FROM test_results
            WHERE run_id IN (
                SELECT id FROM runs ORDER BY created_at DESC LIMIT ?
            )
            GROUP BY test_name, test_file
            HAVING failure_rate > ?
            ORDER BY failure_rate DESC
            """,
            [last_n_runs, threshold],
        ).fetchall())
