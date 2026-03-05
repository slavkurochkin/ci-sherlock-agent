import os
import pytest
from ci_sherlock.config import apply_toml_config, _load_toml


def test_load_toml_missing_file_returns_empty(tmp_path):
    result = _load_toml(str(tmp_path / "nonexistent.toml"))
    assert result == {}


def test_load_toml_reads_keys(tmp_path):
    cfg = tmp_path / "ci-sherlock.toml"
    cfg.write_bytes(b'model = "gpt-4o-mini"\nslow_test_ms = 5000\n')
    result = _load_toml(str(cfg))
    assert result["model"] == "gpt-4o-mini"
    assert result["slow_test_ms"] == 5000


def test_apply_toml_sets_env_var(tmp_path, monkeypatch):
    cfg = tmp_path / "ci-sherlock.toml"
    cfg.write_bytes(b'model = "gpt-4o-mini"\n')
    monkeypatch.delenv("SHERLOCK_MODEL", raising=False)
    apply_toml_config(str(cfg))
    assert os.environ.get("SHERLOCK_MODEL") == "gpt-4o-mini"


def test_apply_toml_does_not_override_existing_env(tmp_path, monkeypatch):
    cfg = tmp_path / "ci-sherlock.toml"
    cfg.write_bytes(b'model = "gpt-4o-mini"\n')
    monkeypatch.setenv("SHERLOCK_MODEL", "gpt-4-turbo")
    apply_toml_config(str(cfg))
    assert os.environ["SHERLOCK_MODEL"] == "gpt-4-turbo"


def test_apply_toml_handles_list_as_csv(tmp_path, monkeypatch):
    cfg = tmp_path / "ci-sherlock.toml"
    cfg.write_bytes(b'ignored_tests = ["test *skip*", "flaky *"]\n')
    monkeypatch.delenv("SHERLOCK_IGNORED_TESTS", raising=False)
    apply_toml_config(str(cfg))
    assert os.environ.get("SHERLOCK_IGNORED_TESTS") == "test *skip*,flaky *"


def test_apply_toml_missing_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("SHERLOCK_MODEL", raising=False)
    apply_toml_config(str(tmp_path / "nonexistent.toml"))
    assert os.environ.get("SHERLOCK_MODEL") is None


def test_load_toml_slow_test_ms(tmp_path):
    cfg = tmp_path / "ci-sherlock.toml"
    cfg.write_bytes(b'slow_test_ms = 5000\nflaky_threshold = 0.2\n')
    result = _load_toml(str(cfg))
    assert result["slow_test_ms"] == 5000
    assert result["flaky_threshold"] == pytest.approx(0.2)
