import pytest
from ci_sherlock.github_client import first_added_line, find_original_in_patch


def test_first_added_line_basic():
    patch = "@@ -1,3 +10,4 @@\n context\n+added line\n-removed\n"
    assert first_added_line(patch) == 11  # line 10 is context, 11 is the + line


def test_first_added_line_no_context():
    patch = "@@ -0,0 +1,2 @@\n+line one\n+line two\n"
    assert first_added_line(patch) == 1


def test_first_added_line_no_patch():
    assert first_added_line(None) == 1


def test_first_added_line_empty_patch():
    assert first_added_line("") == 1


def test_first_added_line_only_deletions():
    patch = "@@ -5,3 +5,0 @@\n-gone\n-also gone\n"
    # no + lines — fallback to hunk start
    result = first_added_line(patch)
    assert isinstance(result, int)
    assert result >= 1


# --- find_original_in_patch ---

def test_find_original_in_added_line():
    patch = "@@ -1,3 +1,4 @@\n context\n+await page.click('.btn-primary');\n+new line\n"
    result = find_original_in_patch(patch, "await page.click('.btn-primary');")
    assert result == 2  # line 1 is context, line 2 is the + line


def test_find_original_in_context_line():
    patch = "@@ -1,3 +1,3 @@\n const x = 1;\n-old\n+new\n"
    result = find_original_in_patch(patch, "const x = 1;")
    assert result == 1


def test_find_original_not_found_returns_none():
    patch = "@@ -1,2 +1,2 @@\n context line\n+added line\n"
    result = find_original_in_patch(patch, "this does not exist")
    assert result is None


def test_find_original_none_patch():
    assert find_original_in_patch(None, "anything") is None


def test_find_original_none_original():
    patch = "@@ -1,2 +1,2 @@\n context\n+added\n"
    assert find_original_in_patch(patch, None) is None


def test_find_original_strips_whitespace():
    patch = "@@ -1,2 +1,2 @@\n+  const x = 1;\n context\n"
    # original passed with extra spaces — should still match
    result = find_original_in_patch(patch, "const x = 1;")
    assert result == 1


def test_find_original_fuzzy_quote_style():
    # LLM returns double quotes, patch has single quotes — fuzzy should match
    patch = "@@ -1,3 +1,3 @@\n context\n+await page.click('.btn-primary');\n context\n"
    result = find_original_in_patch(patch, 'await page.click(".btn-primary");')
    assert result == 2


def test_find_original_fuzzy_missing_semicolon():
    # LLM omits trailing semicolon — fuzzy should match
    patch = "@@ -5,3 +5,3 @@\n context\n+const x = value;\n context\n"
    result = find_original_in_patch(patch, "const x = value")
    assert result == 6


def test_find_original_fuzzy_no_false_positive():
    # Completely unrelated string — even fuzzy should return None
    patch = "@@ -1,2 +1,2 @@\n context line\n+added line\n"
    result = find_original_in_patch(patch, "totally different content xyz")
    assert result is None
