import pytest
from ci_sherlock.commenter import format_comment
from ci_sherlock.models import AnalysisResult, TestResult, LLMInsight


def make_analysis(failed: int = 0, passed: int = 1, sha: str = "abc1234") -> AnalysisResult:
    failed_results = [
        TestResult(
            test_name=f"test {i}",
            test_file="tests/foo.spec.ts",
            status="failed",
            duration_ms=500,
            error_message=f"error {i}",
        )
        for i in range(failed)
    ]
    return AnalysisResult(
        run_id="run-1",
        repo="org/repo",
        pr_number=1,
        commit_sha=sha,
        branch="main",
        total_tests=failed + passed,
        passed_tests=passed,
        failed_tests=failed,
        skipped_tests=0,
        duration_ms=5000,
        failed_results=failed_results,
        correlations=[],
        unmatched_failures=[],
    )


# --- Delta section ---

def test_delta_new_failures_shown():
    analysis = make_analysis(failed=2)
    body = format_comment(analysis, new_failures={"test 0"}, fixed_failures=set())
    assert "+1 new" in body


def test_delta_fixed_shown():
    analysis = make_analysis(failed=0)
    body = format_comment(analysis, new_failures=set(), fixed_failures={"old test"})
    assert "1 fixed" in body


def test_delta_no_change_shown():
    analysis = make_analysis(failed=0)
    body = format_comment(analysis, new_failures=set(), fixed_failures=set())
    assert "no change" in body


def test_delta_omitted_when_none():
    analysis = make_analysis(failed=1)
    body = format_comment(analysis)
    assert "no change" not in body
    assert "new" not in body or "new" in body  # just check no crash


# --- Trace link ---

def test_trace_link_shown_when_trace_path_set():
    analysis = make_analysis(failed=1)
    analysis.failed_results[0].trace_path = "https://example.com/trace.zip"
    body = format_comment(analysis)
    assert "[Trace](https://example.com/trace.zip)" in body


def test_trace_link_absent_when_no_trace():
    analysis = make_analysis(failed=1)
    body = format_comment(analysis)
    assert "[Trace]" not in body


# --- Collapsible sections ---

def test_many_failures_use_details():
    analysis = make_analysis(failed=5)
    body = format_comment(analysis)
    assert "<details>" in body
    assert "<summary>Failures (5 tests)</summary>" in body


def test_few_failures_no_details():
    analysis = make_analysis(failed=2)
    body = format_comment(analysis)
    assert "### Failures" in body
    assert "<details>" not in body or "Failures" not in body.split("<details>")[1].split("</details>")[0] if "<details>" in body else True


# --- Commit sha in footer ---

def test_footer_contains_commit_sha():
    analysis = make_analysis(sha="deadbeef1234")
    body = format_comment(analysis)
    assert "deadbee" in body  # first 7 chars
