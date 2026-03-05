import re
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    github_token: str = ""
    openai_api_key: str = ""
    sherlock_db_path: str = ".ci-sherlock/history.db"
    sherlock_report_path: str = "playwright-report.json"
    sherlock_model: str = "gpt-4o"

    # Injected by GitHub Actions automatically
    github_repository: str = ""
    github_sha: str = ""
    github_ref: str = ""
    github_run_id: str = ""

    # Optional override — inferred from GITHUB_REF if not set
    sherlock_pr_number: int | None = None
    sherlock_slack_webhook: str | None = None

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
