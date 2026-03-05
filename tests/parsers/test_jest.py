import pytest
from pathlib import Path
from ci_sherlock.parsers.jest import JestParser

FIXTURE = str(Path(__file__).parent / "fixtures" / "jest-report.json")


@pytest.fixture
def parser():
    return JestParser()


@pytest.fixture
def results(parser):
    return parser.parse(FIXTURE)


def test_parser_name(parser):
    assert parser.name == "jest"


def test_total_count(results):
    # 3 from auth + 1 from cart = 4 total
    assert len(results) == 4


def test_passed_count(results):
    passed = [r for r in results if r.status == "passed"]
    assert len(passed) == 1


def test_failed_count(results):
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 2


def test_skipped_count(results):
    skipped = [r for r in results if r.status == "skipped"]
    assert len(skipped) == 1


def test_test_name_includes_ancestors(results):
    # "Auth > login > should reject invalid password"
    names = {r.test_name for r in results}
    assert "Auth > login > should reject invalid password" in names


def test_test_name_no_ancestors(results):
    # Cart > should add item to cart
    names = {r.test_name for r in results}
    assert "Cart > should add item to cart" in names


def test_ansi_stripped_from_error(results):
    failed = [r for r in results if r.status == "failed"]
    reject_test = next(r for r in failed if "invalid password" in r.test_name)
    assert reject_test.error_message is not None
    assert "\x1b[" not in reject_test.error_message
    assert "Expected: 401" in reject_test.error_message


def test_duration_set(results):
    passed = next(r for r in results if r.status == "passed")
    assert passed.duration_ms == 123


def test_retry_count_is_zero(results):
    for r in results:
        assert r.retry_count == 0


def test_file_path_cleaned(results):
    # Absolute /home/runner/work/todo-app/todo-app/src/... → src/...
    for r in results:
        assert not r.test_file.startswith("/home/runner")


def test_file_not_found(parser):
    with pytest.raises(FileNotFoundError):
        parser.parse("nonexistent.json")


def test_invalid_report_raises(parser, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"notJest": true}')
    with pytest.raises(ValueError):
        parser.parse(str(bad))


def test_fingerprint_set_on_failed_tests(results):
    failed = [r for r in results if r.status == "failed"]
    for r in failed:
        assert r.error_fingerprint is not None
        assert len(r.error_fingerprint) == 12


def test_fingerprint_none_on_passed_tests(results):
    passed = [r for r in results if r.status == "passed"]
    for r in passed:
        assert r.error_fingerprint is None


def test_null_duration_defaults_to_zero(parser, tmp_path):
    report = tmp_path / "report.json"
    report.write_text('{"testResults": [{"testFilePath": "/abs/path/test.js", "status": "passed", '
                      '"assertionResults": [{"title": "t", "status": "passed", "duration": null, '
                      '"failureMessages": [], "ancestorTitles": []}]}]}')
    results = parser.parse(str(report))
    assert results[0].duration_ms == 0
