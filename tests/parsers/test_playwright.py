import pytest
from pathlib import Path
from ci_sherlock.parsers.playwright import PlaywrightParser

FIXTURE = str(Path(__file__).parent.parent / "fixtures" / "playwright-report.json")


@pytest.fixture
def parser():
    return PlaywrightParser()


@pytest.fixture
def results(parser):
    return parser.parse(FIXTURE)


def test_parser_name(parser):
    assert parser.name == "playwright"


def test_total_count(results):
    # fixture has: 1 passed (login), 1 failed (login), 1 flaky (payment),
    # 1 nested-passed (payment order summary), 1 failed (payment discount),
    # 1 passed (search), 1 skipped (search)
    assert len(results) == 7


def test_passed_tests(results):
    passed = [r for r in results if r.status == "passed"]
    assert len(passed) == 3


def test_failed_tests(results):
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 2


def test_flaky_test(results):
    flaky = [r for r in results if r.status == "flaky"]
    assert len(flaky) == 1
    assert flaky[0].retry_count == 1
    assert flaky[0].test_name == "should process card payment"


def test_skipped_test(results):
    skipped = [r for r in results if r.status == "skipped"]
    assert len(skipped) == 1
    assert skipped[0].test_name == "should filter by category"


def test_error_message_on_failure(results):
    failed = [r for r in results if r.status == "failed"]
    login_failure = next(r for r in failed if "login" in r.test_file)
    assert login_failure.error_message is not None
    assert ".btn-primary" in login_failure.error_message


def test_trace_path_captured(results):
    login_failure = next(
        r for r in results
        if r.status == "failed" and "login" in r.test_file
    )
    assert login_failure.trace_path is not None


def test_test_files_correct(results):
    files = {r.test_file for r in results}
    assert "tests/auth/login.spec.ts" in files
    assert "tests/checkout/payment.spec.ts" in files
    assert "tests/search/search.spec.ts" in files


def test_duration_ms_positive(results):
    for r in results:
        assert r.duration_ms >= 0


def test_file_not_found(parser):
    with pytest.raises(FileNotFoundError):
        parser.parse("nonexistent-report.json")


def test_invalid_json_raises(parser, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a playwright report"}')
    with pytest.raises(ValueError):
        parser.parse(str(bad))
