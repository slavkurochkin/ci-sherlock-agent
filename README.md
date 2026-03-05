# CI Sherlock

> AI-powered CI failure investigation for GitHub Actions. Understands what changed, why tests broke, and what to fix.

CI Sherlock plugs into any GitHub Actions workflow. After your tests run, it correlates failed tests with the files changed in the PR, asks an LLM to reason about the root cause, posts a summary comment on the PR, and stores history for flaky test detection over time.

---

## What it does

- **Failure analysis** — matches failing tests to changed files in the PR diff
- **Root cause reasoning** — uses GPT-4o to explain what likely broke and why
- **Flaky test detection** — tracks retry patterns and failure rates over runs
- **CI optimization** — surfaces slow tests, missing caches, parallelization opportunities
- **Dashboard** — Streamlit UI for browsing run history and test health trends
- **Release readiness score** — composite score based on stability, flake rate, and performance

---

## How it works

```
PR opened / push
      │
      ▼
GitHub Actions runs your tests (Playwright)
      │
      ▼
ci-sherlock analyze
  ├── Parses Playwright JSON report
  ├── Fetches PR diff from GitHub API
  ├── Correlates failures ↔ changed files
  ├── Asks GPT-4o for root cause + suggestions
  ├── Writes results to SQLite
  └── Posts summary comment on PR
      │
      ▼
ci-sherlock dashboard   (optional, run locally or as separate job)
  └── Streamlit UI over SQLite history
```

---

## Quick start

**1. Add to your workflow**

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm install
      - run: npx playwright test
      - uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report.json

  sherlock:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/ci-sherlock@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
```

**2. Run the dashboard locally**

```bash
pip install ci-sherlock
ci-sherlock dashboard
```

---

## CLI reference

| Command | Description |
|---|---|
| `ci-sherlock analyze` | Run analysis on latest test report, post PR comment |
| `ci-sherlock dashboard` | Launch Streamlit dashboard |
| `ci-sherlock history` | Print run history to terminal |

---

## Documentation

| Doc | Description |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | System design, data flow, component breakdown |
| [Stack](docs/STACK.md) | Technology choices and rationale |
| [Implementation Plan](docs/IMPLEMENTATION.md) | Phased build plan |
| [Data Model](docs/DATA_MODEL.md) | SQLite schema and entity relationships |
| [Extending](docs/EXTENDING.md) | Adding parsers for other test frameworks |

---

## Configuration

Configuration is read from environment variables or a `ci-sherlock.yml` file at the repo root.

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | For PR comments and diff fetching |
| `OPENAI_API_KEY` | Yes | For LLM analysis |
| `SHERLOCK_DB_PATH` | No | Path to SQLite file (default: `.ci-sherlock/history.db`) |
| `SHERLOCK_REPORT_PATH` | No | Path to Playwright JSON report (default: `playwright-report.json`) |
| `SHERLOCK_PR_NUMBER` | No | Inferred from `GITHUB_REF` if not set |
