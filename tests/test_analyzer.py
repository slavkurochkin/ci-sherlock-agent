import pytest
from ci_sherlock.analyzer import Analyzer
from ci_sherlock.models import TestResult, ChangedFile


def make_test(name: str, file: str, status: str = "failed") -> TestResult:
    return TestResult(
        test_name=name,
        test_file=file,
        status=status,
        duration_ms=1000,
        retry_count=0,
        error_message="something broke" if status == "failed" else None,
    )


def make_changed(filename: str, status: str = "modified") -> ChangedFile:
    return ChangedFile(filename=filename, status=status, additions=5, deletions=2)


@pytest.fixture
def analyzer():
    return Analyzer()


def test_direct_match(analyzer):
    results = [make_test("should login", "tests/auth/login.spec.ts")]
    changed = [make_changed("tests/auth/login.spec.ts")]

    analysis = analyzer.correlate(
        results=results,
        changed_files=changed,
        run_id="run-1",
        repo="org/repo",
        pr_number=42,
        commit_sha="abc123",
        branch="feature/login",
    )

    assert len(analysis.correlations) == 1
    assert analysis.correlations[0].score == 1.0
    assert analysis.correlations[0].reason == "direct_match"
    assert len(analysis.unmatched_failures) == 0


def test_same_directory_match(analyzer):
    results = [make_test("should checkout", "tests/checkout/payment.spec.ts")]
    changed = [make_changed("tests/checkout/Cart.tsx")]

    analysis = analyzer.correlate(
        results=results,
        changed_files=changed,
        run_id="run-1",
        repo="org/repo",
        pr_number=1,
        commit_sha="abc",
        branch="main",
    )

    assert len(analysis.correlations) == 1
    assert analysis.correlations[0].score == 0.6
    assert analysis.correlations[0].reason == "same_directory"


def test_no_match_goes_to_unmatched(analyzer):
    results = [make_test("should render", "tests/ui/button.spec.ts")]
    changed = [make_changed("src/api/users.ts")]

    analysis = analyzer.correlate(
        results=results,
        changed_files=changed,
        run_id="run-1",
        repo="org/repo",
        pr_number=1,
        commit_sha="abc",
        branch="main",
    )

    assert len(analysis.correlations) == 0
    assert len(analysis.unmatched_failures) == 1


def test_direct_match_preferred_over_same_dir(analyzer):
    results = [make_test("should login", "tests/auth/login.spec.ts")]
    changed = [
        make_changed("tests/auth/login.spec.ts"),   # direct
        make_changed("tests/auth/signup.spec.ts"),  # same dir
    ]

    analysis = analyzer.correlate(
        results=results,
        changed_files=changed,
        run_id="run-1",
        repo="org/repo",
        pr_number=1,
        commit_sha="abc",
        branch="main",
    )

    scores = {c.changed_file: c.score for c in analysis.correlations}
    assert scores["tests/auth/login.spec.ts"] == 1.0
    assert scores["tests/auth/signup.spec.ts"] == 0.6


def test_passed_tests_not_correlated(analyzer):
    results = [
        make_test("should pass", "tests/auth/login.spec.ts", status="passed"),
        make_test("should fail", "tests/auth/login.spec.ts", status="failed"),
    ]
    changed = [make_changed("tests/auth/login.spec.ts")]

    analysis = analyzer.correlate(
        results=results,
        changed_files=changed,
        run_id="run-1",
        repo="org/repo",
        pr_number=1,
        commit_sha="abc",
        branch="main",
    )

    # Only the failed test produces a correlation
    assert len(analysis.correlations) == 1
    assert analysis.correlations[0].test_name == "should fail"


def test_counts_are_correct(analyzer):
    results = [
        make_test("t1", "tests/a.spec.ts", "passed"),
        make_test("t2", "tests/b.spec.ts", "failed"),
        make_test("t3", "tests/c.spec.ts", "skipped"),
        make_test("t4", "tests/d.spec.ts", "flaky"),
    ]

    analysis = analyzer.correlate(
        results=results,
        changed_files=[],
        run_id="run-1",
        repo="org/repo",
        pr_number=None,
        commit_sha="abc",
        branch="main",
    )

    assert analysis.total_tests == 4
    assert analysis.passed_tests == 1
    assert analysis.failed_tests == 2  # failed + flaky
    assert analysis.skipped_tests == 1


def test_no_changed_files_all_unmatched(analyzer):
    results = [make_test("should work", "tests/foo.spec.ts")]

    analysis = analyzer.correlate(
        results=results,
        changed_files=[],
        run_id="run-1",
        repo="org/repo",
        pr_number=None,
        commit_sha="abc",
        branch="main",
    )

    assert len(analysis.correlations) == 0
    assert len(analysis.unmatched_failures) == 1
