import pytest
from ci_sherlock.analyzer import Analyzer
from ci_sherlock.models import TestResult


def make_test(name: str, status: str, retry_count: int = 0) -> TestResult:
    return TestResult(
        test_name=name,
        test_file="tests/foo.spec.ts",
        status=status,
        duration_ms=1000,
        retry_count=retry_count,
    )


@pytest.fixture
def analyzer():
    return Analyzer()


# --- detect_flaky_current ---

def test_retry_pass_flagged_as_flaky(analyzer):
    results = [make_test("should login", "passed", retry_count=1)]
    signals = analyzer.detect_flaky_current(results)
    assert len(signals) == 1
    assert signals[0].source == "retry"
    assert signals[0].test_name == "should login"


def test_retry_still_failed_not_flagged(analyzer):
    results = [make_test("should login", "failed", retry_count=2)]
    signals = analyzer.detect_flaky_current(results)
    assert len(signals) == 0


def test_no_retry_not_flagged(analyzer):
    results = [make_test("should pass", "passed", retry_count=0)]
    signals = analyzer.detect_flaky_current(results)
    assert len(signals) == 0


def test_multiple_flaky_detected(analyzer):
    results = [
        make_test("t1", "passed", retry_count=1),
        make_test("t2", "passed", retry_count=2),
        make_test("t3", "passed", retry_count=0),  # not flaky
        make_test("t4", "failed", retry_count=1),  # failed, not flaky
    ]
    signals = analyzer.detect_flaky_current(results)
    assert len(signals) == 2
    names = {s.test_name for s in signals}
    assert "t1" in names
    assert "t2" in names


# --- detect_flaky_historical ---

def test_historical_above_threshold(analyzer):
    rows = [
        {"test_name": "unstable test", "test_file": "tests/a.spec.ts", "failure_rate": 0.25, "total_runs": 20, "failures": 5},
    ]
    signals = analyzer.detect_flaky_historical(rows, threshold=0.10)
    assert len(signals) == 1
    assert signals[0].source == "historical"
    assert signals[0].failure_rate == 0.25


def test_historical_below_threshold_not_flagged(analyzer):
    rows = [
        {"test_name": "stable test", "test_file": "tests/a.spec.ts", "failure_rate": 0.05, "total_runs": 20, "failures": 1},
    ]
    signals = analyzer.detect_flaky_historical(rows, threshold=0.10)
    assert len(signals) == 0


def test_historical_exactly_at_threshold_not_flagged(analyzer):
    rows = [
        {"test_name": "borderline", "test_file": "tests/a.spec.ts", "failure_rate": 0.10, "total_runs": 10, "failures": 1},
    ]
    signals = analyzer.detect_flaky_historical(rows, threshold=0.10)
    assert len(signals) == 0  # strictly greater than threshold


def test_historical_empty_rows(analyzer):
    signals = analyzer.detect_flaky_historical([], threshold=0.10)
    assert signals == []
