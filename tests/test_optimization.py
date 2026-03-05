import pytest
from ci_sherlock.optimization import OptimizationEngine, SLOW_TEST_MS, SUITE_SLOW_TOTAL_MS
from ci_sherlock.models import TestResult


def make_test(name: str, duration_ms: int, status: str = "passed") -> TestResult:
    return TestResult(
        test_name=name,
        test_file="tests/foo.spec.ts",
        status=status,
        duration_ms=duration_ms,
        retry_count=0,
    )


@pytest.fixture
def engine():
    return OptimizationEngine()


# --- slow_tests ---

def test_slow_test_flagged(engine):
    results = [make_test("slow test", SLOW_TEST_MS + 1000)]
    suggestions = engine.slow_tests(results)
    assert len(suggestions) == 1
    assert suggestions[0].type == "slow_test"
    assert "slow test" in suggestions[0].description


def test_fast_test_not_flagged(engine):
    results = [make_test("fast test", SLOW_TEST_MS - 1)]
    suggestions = engine.slow_tests(results)
    assert len(suggestions) == 0


def test_slow_tests_capped_at_top_n(engine):
    results = [make_test(f"slow-{i}", SLOW_TEST_MS + i * 1000) for i in range(10)]
    suggestions = engine.slow_tests(results)
    assert len(suggestions) == 5  # SLOW_TEST_TOP_N


def test_slow_tests_sorted_by_duration(engine):
    results = [
        make_test("medium", 15_000),
        make_test("slowest", 30_000),
        make_test("slow", 12_000),
    ]
    suggestions = engine.slow_tests(results)
    assert suggestions[0].metadata["test_name"] == "slowest"
    assert suggestions[1].metadata["test_name"] == "medium"


def test_slow_test_impact_is_medium(engine):
    results = [make_test("slow", SLOW_TEST_MS + 1)]
    assert engine.slow_tests(results)[0].impact == "medium"


# --- check_parallelization ---

def test_parallelization_flagged_when_slow(engine):
    # total > SUITE_SLOW_TOTAL_MS
    results = [make_test(f"t{i}", SUITE_SLOW_TOTAL_MS // 3) for i in range(4)]
    suggestions = engine.check_parallelization(results)
    assert len(suggestions) == 1
    assert suggestions[0].type == "no_parallelization"
    assert suggestions[0].impact == "high"


def test_parallelization_not_flagged_when_fast(engine):
    results = [make_test("t1", 1000), make_test("t2", 2000)]
    suggestions = engine.check_parallelization(results)
    assert len(suggestions) == 0


# --- analyze (combined) ---

def test_analyze_returns_all_suggestions(engine):
    results = [make_test("slow test", SLOW_TEST_MS + 5000)]
    results += [make_test(f"t{i}", SUITE_SLOW_TOTAL_MS // 3) for i in range(4)]
    suggestions = engine.analyze(results)
    types = {s.type for s in suggestions}
    assert "slow_test" in types
    assert "no_parallelization" in types


def test_analyze_empty_results(engine):
    assert engine.analyze([]) == []
