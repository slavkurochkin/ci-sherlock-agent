import pytest
from ci_sherlock.github_client import first_added_line


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
