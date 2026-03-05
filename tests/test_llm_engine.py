import pytest
from unittest.mock import MagicMock
from ci_sherlock.llm_engine import LLMEngine
from ci_sherlock.models import (
    AnalysisResult, TestResult, Correlation, LLMInsight
)


def make_analysis(
    failed: list[TestResult] | None = None,
    correlations: list[Correlation] | None = None,
    unmatched: list[TestResult] | None = None,
) -> AnalysisResult:
    failed = failed or []
    return AnalysisResult(
        run_id="run-test",
        repo="org/repo",
        pr_number=1,
        commit_sha="abc123",
        branch="main",
        total_tests=len(failed) + 1,
        passed_tests=1,
        failed_tests=len(failed),
        skipped_tests=0,
        duration_ms=5000,
        failed_results=failed,
        correlations=correlations or [],
        unmatched_failures=unmatched or [],
    )


def make_failed(name: str = "should work", file: str = "tests/foo.spec.ts") -> TestResult:
    return TestResult(
        test_name=name,
        test_file=file,
        status="failed",
        duration_ms=3000,
        retry_count=0,
        error_message="Locator '.btn-primary' not found",
        error_stack="Error at tests/foo.spec.ts:42",
    )


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def engine(mock_client):
    return LLMEngine(client=mock_client, model="gpt-4o")


def test_returns_insight_on_success(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="Button class renamed from .btn-primary to .btn-default",
        confidence=0.85,
        recommendation="Update selectors in login spec",
        flaky_tests=[],
    )
    analysis = make_analysis(failed=[make_failed()])
    result = engine.analyze(analysis)

    assert result is not None
    assert result.confidence == 0.85
    assert "btn" in result.root_cause


def test_returns_none_when_no_failures(engine, mock_client):
    analysis = make_analysis(failed=[])
    result = engine.analyze(analysis)

    assert result is None
    mock_client.chat.completions.create.assert_not_called()


def test_returns_none_on_api_error(engine, mock_client):
    mock_client.chat.completions.create.side_effect = Exception("API timeout")
    analysis = make_analysis(failed=[make_failed()])
    result = engine.analyze(analysis)

    assert result is None


def test_prompt_includes_test_name(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    analysis = make_analysis(failed=[make_failed("should process payment", "tests/checkout/payment.spec.ts")])
    engine.analyze(analysis)

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")

    assert "should process payment" in user_content
    assert "tests/checkout/payment.spec.ts" in user_content


def test_prompt_includes_correlation(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    correlation = Correlation(
        test_name="should login",
        test_file="tests/auth/login.spec.ts",
        changed_file="src/components/Button.tsx",
        score=1.0,
        reason="direct_match",
    )
    analysis = make_analysis(
        failed=[make_failed("should login", "tests/auth/login.spec.ts")],
        correlations=[correlation],
    )
    engine.analyze(analysis)

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")

    assert "Button.tsx" in user_content
    assert "direct_match" in user_content


def test_prompt_truncates_long_errors(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    long_error = "A" * 2000
    failed = TestResult(
        test_name="slow test",
        test_file="tests/foo.spec.ts",
        status="failed",
        duration_ms=1000,
        error_message=long_error,
        error_stack=long_error,
    )
    analysis = make_analysis(failed=[failed])
    engine.analyze(analysis)

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")

    # Should not include the full 2000-char string verbatim
    assert len(user_content) < 5000


def test_model_passed_to_client(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    analysis = make_analysis(failed=[make_failed()])
    engine.analyze(analysis)

    call_args = mock_client.chat.completions.create.call_args
    assert call_args.kwargs["model"] == "gpt-4o"


def test_fingerprint_count_appears_in_prompt(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    failed = TestResult(
        test_name="known failure",
        test_file="tests/foo.spec.ts",
        status="failed",
        duration_ms=1000,
        error_message="Expected true to be false",
        error_fingerprint="abc123def456",
    )
    analysis = make_analysis(failed=[failed])
    engine.analyze(analysis, fingerprint_counts={"abc123def456": 5})

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "5 previous run" in user_content


def test_new_error_label_in_prompt(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    failed = TestResult(
        test_name="brand new failure",
        test_file="tests/foo.spec.ts",
        status="failed",
        duration_ms=1000,
        error_message="Something new broke",
        error_fingerprint="newfingerprint",
    )
    analysis = make_analysis(failed=[failed])
    engine.analyze(analysis, fingerprint_counts={})

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "new error" in user_content


def test_fix_eligibility_hint_in_prompt_when_direct_match(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.9, recommendation="y", flaky_tests=[]
    )
    from ci_sherlock.models import ChangedFile, Correlation
    corr = Correlation(
        test_name="should login",
        test_file="tests/auth.spec.ts",
        changed_file="src/Button.tsx",
        score=1.0,
        reason="direct_match",
    )
    analysis = make_analysis(
        failed=[make_failed("should login", "tests/auth.spec.ts")],
        correlations=[corr],
    )
    analysis.changed_files = [ChangedFile(filename="src/Button.tsx", status="modified", additions=2, deletions=1)]
    engine.analyze(analysis)

    call_args = mock_client.chat.completions.create.call_args
    user_content = next(m["content"] for m in call_args.kwargs["messages"] if m["role"] == "user")
    assert "direct_match" in user_content
    assert "src/Button.tsx" in user_content
    assert "suggested_fix" in user_content.lower() or "Fix suggestion" in user_content


def test_fix_eligibility_hint_suppressed_when_no_direct_match(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    from ci_sherlock.models import Correlation
    corr = Correlation(
        test_name="should load",
        test_file="tests/foo.spec.ts",
        changed_file="src/api/users.ts",
        score=0.6,
        reason="same_directory",
    )
    analysis = make_analysis(
        failed=[make_failed("should load", "tests/foo.spec.ts")],
        correlations=[corr],
    )
    engine.analyze(analysis)

    call_args = mock_client.chat.completions.create.call_args
    user_content = next(m["content"] for m in call_args.kwargs["messages"] if m["role"] == "user")
    assert "leave suggested_fix fields null" in user_content


def test_system_prompt_present(engine, mock_client):
    mock_client.chat.completions.create.return_value = LLMInsight(
        root_cause="x", confidence=0.5, recommendation="y", flaky_tests=[]
    )
    analysis = make_analysis(failed=[make_failed()])
    engine.analyze(analysis)

    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert "CI reliability" in system_msgs[0]["content"]
