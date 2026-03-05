# Architecture

## Overview

CI Sherlock is a Python CLI tool and GitHub Action. It has no external service dependency — everything runs inside GitHub Actions or locally. Persistence is a SQLite file that can live in the repo or be passed around as a GitHub Actions artifact.

---

## Component map

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Actions CI                       │
│                                                             │
│   test job                      sherlock job               │
│   ─────────                     ─────────────               │
│   run tests          →          ci-sherlock analyze         │
│   upload artifact               │                           │
│                                 ├── PlaywrightParser        │
│                                 ├── GitHubClient            │
│                                 ├── Analyzer                │
│                                 ├── LLMEngine               │
│                                 ├── DB (SQLite)             │
│                                 └── PRCommenter             │
└─────────────────────────────────────────────────────────────┘
                                          │
                              optional: upload DB artifact
                                          │
                                          ▼
                              ci-sherlock dashboard (Streamlit)
                              run locally or as separate job
```

---

## Components

### PlaywrightParser

- Reads `playwright-report.json`
- Extracts: test names, status, duration, retry count, error messages, trace paths
- Implements the `BaseParser` interface (see [Extending](EXTENDING.md))

### GitHubClient

- Wraps GitHub REST API via `httpx`
- Fetches: PR diff (changed files + patch), previous workflow runs, run jobs and steps
- Posts: PR comment with analysis summary
- Auth: `GITHUB_TOKEN` (standard Actions secret, no extra setup)

### Analyzer

- Core correlation engine
- Inputs: parsed test results + PR diff
- Logic:
  - Match failing test file names against changed file paths
  - Score correlation strength (direct match, same directory, indirect)
  - Detect flaky signals: `retry_count > 0` and eventual pass
  - Detect slow tests: duration above configurable threshold
- Outputs: structured `AnalysisResult` (Pydantic model)

### LLMEngine

- Sends `AnalysisResult` to GPT-4o via the OpenAI SDK
- Uses `instructor` for guaranteed structured JSON output via Pydantic models
- Prompt includes: changed files, failed tests, error messages, correlation scores
- Returns: `LLMInsight` — root cause, confidence, recommendation, flaky flags
- Graceful fallback: if API unavailable, skips LLM section and posts raw analysis only

### DB (SQLite)

- Stores run history: each `ci-sherlock analyze` invocation writes one run record
- Tables: `runs`, `test_results`, `insights` (see [Data Model](DATA_MODEL.md))
- File location: configurable, defaults to `.ci-sherlock/history.db`
- Can be committed to the repo or passed between jobs as an artifact

### PRCommenter

- Formats `AnalysisResult` + `LLMInsight` into a Markdown comment
- Posts or updates existing comment on the PR (identified by a hidden HTML marker)
- No duplicate comments: edits the existing one if present

### Dashboard (Streamlit)

- Reads from SQLite
- Views: run history, test health over time, flaky test leaderboard, slowest tests, release readiness score
- Run locally: `ci-sherlock dashboard`
- Can also run as a GitHub Actions job that uploads the rendered HTML (future)

---

## Data flow

```
1. test job finishes
2. Playwright writes playwright-report.json
3. artifact uploaded to GitHub Actions

4. sherlock job starts
5. artifact downloaded
6. PlaywrightParser reads report → TestResult[]
7. GitHubClient fetches PR diff → ChangedFile[]
8. Analyzer correlates → AnalysisResult
9. LLMEngine sends to GPT-4o → LLMInsight
10. DB writes run + results + insight
11. PRCommenter formats + posts comment

12. (optional) DB artifact uploaded
13. (optional) dashboard job reads DB + renders UI
```

---

## Deployment options

| Option | How | Best for |
|---|---|---|
| **GitHub Action** (primary) | `uses: your-org/ci-sherlock@v1` | Any team, zero setup |
| **CLI in workflow** | `pip install ci-sherlock && ci-sherlock analyze` | Teams that want version control over the tool |
| **Local dashboard** | `ci-sherlock dashboard` | Engineers reviewing history offline |
| **Self-hosted dashboard** | Run Streamlit app on internal server pointing at shared DB | Teams wanting a persistent web UI |

---

## Boundaries and non-goals

- CI Sherlock does **not** run your tests — it only analyzes their output
- It does **not** require a database server — SQLite only
- It does **not** store secrets — API keys are passed as environment variables
- It does **not** modify your test files or CI configuration
- The LLM layer is **optional** — the tool is useful without it (correlation + optimization signals)
- `OPENAI_API_KEY` is only required if the LLM layer is enabled
