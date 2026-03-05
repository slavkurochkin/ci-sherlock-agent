import pytest
from ci_sherlock.db import Database
from ci_sherlock.models import TestResult, AnalysisResult, Correlation


def make_analysis(run_id: str, pr_number: int | None = 1, failed: int = 1) -> AnalysisResult:
    return AnalysisResult(
        run_id=run_id,
        repo="org/repo",
        pr_number=pr_number,
        commit_sha="abc123",
        branch="main",
        total_tests=failed + 1,
        passed_tests=1,
        failed_tests=failed,
        skipped_tests=0,
        duration_ms=1000,
        failed_results=[],
        correlations=[],
        unmatched_failures=[],
    )


def make_result(test_name: str, status: str = "failed", fingerprint: str | None = None) -> TestResult:
    return TestResult(
        test_name=test_name,
        test_file="tests/foo.spec.ts",
        status=status,
        duration_ms=500,
        error_message="boom" if status == "failed" else None,
        error_fingerprint=fingerprint,
    )


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


# --- get_previous_run_failures ---

def test_previous_run_failures_returns_prior_run(db):
    analysis1 = make_analysis("run-1")
    db.write_run(analysis1)
    db.write_results("run-1", [make_result("should login")])

    analysis2 = make_analysis("run-2")
    db.write_run(analysis2)
    db.write_results("run-2", [make_result("should signup")])

    prev = db.get_previous_run_failures(pr_number=1, exclude_run_id="run-2")
    assert "should login" in prev
    assert "should signup" not in prev


def test_previous_run_failures_excludes_current_run(db):
    analysis = make_analysis("run-1")
    db.write_run(analysis)
    db.write_results("run-1", [make_result("should work")])

    prev = db.get_previous_run_failures(pr_number=1, exclude_run_id="run-1")
    assert prev == set()


def test_previous_run_failures_only_for_pr(db):
    a1 = make_analysis("run-1", pr_number=10)
    db.write_run(a1)
    db.write_results("run-1", [make_result("pr10-test")])

    a2 = make_analysis("run-2", pr_number=20)
    db.write_run(a2)
    db.write_results("run-2", [make_result("pr20-test")])

    prev = db.get_previous_run_failures(pr_number=20, exclude_run_id="run-3")
    assert "pr20-test" in prev
    assert "pr10-test" not in prev


def test_previous_run_failures_empty_when_no_history(db):
    prev = db.get_previous_run_failures(pr_number=99, exclude_run_id="run-1")
    assert prev == set()


def test_previous_run_failures_includes_flaky(db):
    analysis = make_analysis("run-1")
    db.write_run(analysis)
    db.write_results("run-1", [make_result("flaky-test", status="flaky")])

    prev = db.get_previous_run_failures(pr_number=1, exclude_run_id="run-2")
    assert "flaky-test" in prev


# --- get_fingerprint_counts ---

def test_fingerprint_counts_returns_run_counts(db):
    a1 = make_analysis("run-1")
    db.write_run(a1)
    db.write_results("run-1", [make_result("t1", fingerprint="fp_aaa")])

    a2 = make_analysis("run-2")
    db.write_run(a2)
    db.write_results("run-2", [make_result("t1", fingerprint="fp_aaa")])

    counts = db.get_fingerprint_counts(["fp_aaa"])
    assert counts["fp_aaa"] == 2


def test_fingerprint_counts_empty_list(db):
    assert db.get_fingerprint_counts([]) == {}


def test_fingerprint_counts_unknown_fingerprint(db):
    counts = db.get_fingerprint_counts(["unknown_fp"])
    assert "unknown_fp" not in counts


def test_fingerprint_counts_multiple_fingerprints(db):
    a1 = make_analysis("run-1")
    db.write_run(a1)
    db.write_results("run-1", [
        make_result("t1", fingerprint="fp_aaa"),
        make_result("t2", fingerprint="fp_bbb"),
    ])

    counts = db.get_fingerprint_counts(["fp_aaa", "fp_bbb", "fp_ccc"])
    assert counts.get("fp_aaa") == 1
    assert counts.get("fp_bbb") == 1
    assert "fp_ccc" not in counts
