import re
import tomllib
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_toml(path: str = "ci-sherlock.toml") -> dict:
    """Read ci-sherlock.toml and return its contents (empty dict if absent)."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def apply_toml_config(path: str = "ci-sherlock.toml") -> None:
    """
    Load ci-sherlock.toml and set env vars for any keys not already set.
    Called before Config() is instantiated so pydantic-settings picks them up.
    """
    mapping = {
        "model":            "SHERLOCK_MODEL",
        "report_path":      "SHERLOCK_REPORT_PATH",
        "db_path":          "SHERLOCK_DB_PATH",
        "slow_test_ms":     "SHERLOCK_SLOW_TEST_MS",
        "flaky_threshold":  "SHERLOCK_FLAKY_THRESHOLD",
        "ignored_tests":    "SHERLOCK_IGNORED_TESTS",
    }
    for key, env_key in mapping.items():
        value = _load_toml(path).get(key)
        if value is not None and env_key not in os.environ:
            if isinstance(value, list):
                os.environ[env_key] = ",".join(str(v) for v in value)
            else:
                os.environ[env_key] = str(value)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    github_token: str = ""
    openai_api_key: str = ""
    sherlock_db_path: str = ".ci-sherlock/history.db"
    sherlock_report_path: str = "playwright-report.json"
    sherlock_model: str = "gpt-4o"
    sherlock_slow_test_ms: int = 10_000
    sherlock_flaky_threshold: float = 0.10
    sherlock_ignored_tests: str = ""  # comma-separated glob patterns

    # Injected by GitHub Actions automatically
    github_repository: str = ""
    github_sha: str = ""
    github_ref: str = ""
    github_run_id: str = ""

    # Optional override — inferred from GITHUB_REF if not set
    sherlock_pr_number: int | None = None
    sherlock_slack_webhook: str | None = None

    @property
    def ignored_test_patterns(self) -> list[str]:
        return [p.strip() for p in self.sherlock_ignored_tests.split(",") if p.strip()]

    @property
    def pr_number(self) -> int | None:
        if self.sherlock_pr_number:
            return self.sherlock_pr_number
        # refs/pull/123/merge
        match = re.search(r"refs/pull/(\d+)/", self.github_ref)
        return int(match.group(1)) if match else None

    @property
    def repo(self) -> str:
        return self.github_repository

    @property
    def branch(self) -> str:
        # refs/heads/my-branch or refs/pull/123/merge
        match = re.match(r"refs/heads/(.+)", self.github_ref)
        return match.group(1) if match else self.github_ref
