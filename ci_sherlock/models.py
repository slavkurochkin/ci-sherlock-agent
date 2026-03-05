from typing import Literal
from pydantic import BaseModel


class TestResult(BaseModel):
    test_name: str
    test_file: str
    status: Literal["passed", "failed", "skipped", "flaky"]
    duration_ms: int
    retry_count: int = 0
    error_message: str | None = None
    error_stack: str | None = None
    trace_path: str | None = None
    error_fingerprint: str | None = None  # computed at parse time


class ChangedFile(BaseModel):
    filename: str
    status: Literal["added", "modified", "removed", "renamed"]
    additions: int = 0
    deletions: int = 0
    patch: str | None = None


class Correlation(BaseModel):
    test_name: str
    test_file: str
    changed_file: str
    score: float
    reason: Literal["direct_match", "same_directory", "imported_module", "diff_content_match"]


class AnalysisResult(BaseModel):
    run_id: str
    repo: str
    pr_number: int | None
    commit_sha: str
    branch: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    duration_ms: int
    failed_results: list[TestResult]
    correlations: list[Correlation]
    unmatched_failures: list[TestResult]
    changed_files: list[ChangedFile] = []


# Phase 2 — populated by LLMEngine
class LLMInsight(BaseModel):
    root_cause: str
    confidence: float
    recommendation: str
    flaky_tests: list[str]


# Phase 3
class FlakySignal(BaseModel):
    test_name: str
    test_file: str
    source: Literal["retry", "historical"]
    failure_rate: float | None = None  # only set for historical signals


class OptimizationSuggestion(BaseModel):
    type: Literal["slow_test", "missing_cache", "no_parallelization", "sequential_jobs"]
    description: str
    impact: Literal["high", "medium", "low"]
    metadata: dict = {}
