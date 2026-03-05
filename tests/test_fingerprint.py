import pytest
from ci_sherlock.fingerprint import normalize_error, fingerprint


def test_normalize_strips_line_col():
    result = normalize_error("Error at 42:7", None)
    assert "42" not in result
    assert "<POS>" in result


def test_normalize_strips_line_ref():
    result = normalize_error("Failure at line 123", None)
    assert "123" not in result
    assert "<LINE>" in result


def test_normalize_strips_hex_address():
    result = normalize_error("Segfault at 0xdeadbeef", None)
    assert "0xdeadbeef" not in result
    assert "<HEX>" in result


def test_normalize_strips_long_hex():
    result = normalize_error("ref: abc123def456", None)
    assert "abc123def456" not in result


def test_normalize_strips_absolute_path():
    result = normalize_error("Error in /home/runner/work/app/src/foo.ts", None)
    assert "/home/runner" not in result
    assert "<PATH>" in result


def test_normalize_merges_stack_and_message():
    result = normalize_error("Expected true", "  at Object.<anonymous> (tests/foo.spec.ts:10:5)")
    assert "Expected true" in result
    assert "Object.<anonymous>" in result


def test_normalize_collapses_whitespace():
    result = normalize_error("Error   with   spaces", None)
    assert "  " not in result


def test_fingerprint_same_error_same_hash():
    fp1 = fingerprint("Expected true", "at line 10")
    fp2 = fingerprint("Expected true", "at line 10")
    assert fp1 == fp2


def test_fingerprint_line_number_change_same_hash():
    """Same error, different line number → same fingerprint."""
    fp1 = fingerprint("Expected true", "at Object.<anonymous> (foo.spec.ts:10:5)")
    fp2 = fingerprint("Expected true", "at Object.<anonymous> (foo.spec.ts:42:5)")
    assert fp1 == fp2


def test_fingerprint_different_error_different_hash():
    fp1 = fingerprint("Expected true", None)
    fp2 = fingerprint("Expected false", None)
    assert fp1 != fp2


def test_fingerprint_length():
    fp = fingerprint("some error", "some stack")
    assert len(fp) == 12


def test_fingerprint_none_inputs():
    fp = fingerprint(None, None)
    assert len(fp) == 12


def test_fingerprint_only_message():
    fp = fingerprint("TypeError: cannot read property", None)
    assert len(fp) == 12


def test_fingerprint_path_change_same_hash():
    """Absolute paths differ between local and CI but hash should match."""
    fp1 = fingerprint("Error in /home/runner/work/app/src/utils.ts", None)
    fp2 = fingerprint("Error in /Users/slav/dev/app/src/utils.ts", None)
    assert fp1 == fp2
