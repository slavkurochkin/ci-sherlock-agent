# Implementation Plan

Four phases. Each phase produces something runnable and independently useful. Later phases build on top without breaking earlier work.

---

## Phase 1 — Runnable skeleton

**Goal:** End-to-end flow works. Parse a report, write to DB, post a basic PR comment. No LLM yet.

**Acceptance criteria:**
- `ci-sherlock analyze` runs without errors given a Playwright JSON report and a GitHub token
- Results are written to SQLite
- A comment appears on the PR with a raw failure summary

### Tasks

**Project setup**
- [x] `pyproject.toml` with all dependencies and `ci-sherlock` entry point
- [x] `ci_sherlock/__init__.py`
- [x] `ci_sherlock/cli.py` — `typer` app with `analyze` and `dashboard` subcommands (stubs)
- [x] `ci_sherlock/config.py` — `pydantic-settings` config class (reads env vars)

**Parser**
- [x] `ci_sherlock/parsers/base.py` — `BaseParser` abstract class with `parse() -> list[TestResult]`
- [x] `ci_sherlock/models.py` — `TestResult`, `ChangedFile`, `AnalysisResult` Pydantic models
- [x] `ci_sherlock/parsers/playwright.py` — implements `BaseParser`, reads `playwright-report.json`

**Database**
- [x] `ci_sherlock/db.py` — `Database` class wrapping `sqlite-utils`, creates schema on init, exposes `write_run()`, `write_results()`, `get_runs()`

**GitHub client**
- [x] `ci_sherlock/github_client.py` — `GitHubClient` class with `get_pr_files()` and `post_comment()` methods

**Analyzer (no LLM)**
- [x] `ci_sherlock/analyzer.py` — `Analyzer.correlate()` — matches test file names to changed file paths, returns `AnalysisResult` with correlation scores

**PR comment**
- [x] `ci_sherlock/commenter.py` — `format_comment()` renders Markdown from `AnalysisResult`, `post_or_update_comment()` creates/edits comment with hidden marker

**Wire it together**
- [x] `cli.py analyze` command calls: parse → fetch diff → correlate → write DB → post comment

**Tests**
- [x] `tests/parsers/test_playwright.py` — unit test parser with fixture JSON
- [x] `tests/test_analyzer.py` — unit test correlation logic

---

## Phase 2 — LLM root cause

**Goal:** GPT-4o analyzes failures and the PR comment includes AI-generated root cause, confidence, and recommendation.

**Acceptance criteria:**
- `LLMInsight` is populated with structured output from GPT-4o
- Comment includes root cause section with confidence level
- If `OPENAI_API_KEY` is not set, analysis runs without LLM and logs a warning

### Tasks

**LLM engine**
- [x] `ci_sherlock/llm_engine.py` — `LLMEngine` class using `instructor` + `openai`
- [x] `ci_sherlock/models.py` — add `LLMInsight` Pydantic model (root_cause, confidence, recommendation, flaky_tests)
- [x] Prompt construction from `AnalysisResult` — include changed files, failures, errors, correlation scores
- [x] Token budget management — truncate large diffs/errors to fit context window
- [x] Graceful fallback — catch API errors, return `None`, log warning

**DB update**
- [x] `ci_sherlock/db.py` — add `write_insight()` method, add `insights` table

**Comment update**
- [x] `ci_sherlock/commenter.py` — extend `format_comment()` to include LLM insight block

**Wire it together**
- [x] `cli.py analyze` — add `LLMEngine.analyze()` step after correlation

**Tests**
- [x] `tests/test_llm_engine.py` — mock OpenAI client, test prompt construction and fallback

---

## Phase 3 — Flaky detection + optimization signals

**Goal:** The agent surfaces flaky tests based on retry patterns and run history, and flags CI optimization opportunities (slow tests, missing caches, parallelization).

**Acceptance criteria:**
- Flaky tests listed in PR comment when detected
- Slowest N tests listed in PR comment
- Flaky detection uses both current run (retry signals) and history (failure rate)
- DB `test_results` table has enough history to compute failure rate

### Tasks

**Flaky detection**
- [x] `ci_sherlock/analyzer.py` — `detect_flaky_current()`: flag tests where `retry_count > 0` and status is `passed`
- [x] `ci_sherlock/analyzer.py` — `detect_flaky_historical()`: query DB for tests with `failure_rate > 10%` over last N runs
- [x] `ci_sherlock/models.py` — add `FlakySignal` model

**Optimization engine**
- [x] `ci_sherlock/optimization.py` — `OptimizationEngine` class
  - `slow_tests()`: top N by duration from current run
  - `check_parallelization()`: if total suite > 2 min, flag sharding
- [x] `ci_sherlock/models.py` — add `OptimizationSuggestion` model

**Comment update**
- [x] `ci_sherlock/commenter.py` — add flaky tests section and optimization suggestions section

**Tests**
- [x] `tests/test_flaky.py`
- [x] `tests/test_optimization.py`

---

## Phase 4 — Dashboard + release readiness

**Goal:** `ci-sherlock dashboard` launches a Streamlit UI showing run history, test health, and a release readiness score.

**Acceptance criteria:**
- Dashboard loads from SQLite with no additional config
- Shows: run timeline, test failure heatmap, flaky leaderboard, slowest tests, release readiness score
- Release readiness score is computed from: stability, flake rate, performance trend, pipeline health

### Tasks

**Release readiness score**
- [x] `ci_sherlock/scoring.py` — `compute_release_readiness()` takes last N runs from DB, returns score 0–100 with factor breakdown
- [x] Factors and weights:
  - Test stability (pass rate): 30%
  - Failure rate (recent runs): 25%
  - Performance trend (duration delta): 20%
  - Flaky test count: 15%
  - Pipeline health (job success rate): 10%

**Dashboard views**
- [x] `ci_sherlock/dashboard/app.py` — Streamlit app entry point
- [x] `ci_sherlock/dashboard/views/run_history.py` — timeline of runs with pass/fail status
- [x] `ci_sherlock/dashboard/views/flaky.py` — table: test name, failure rate, last seen
- [x] `ci_sherlock/dashboard/views/slowest.py` — bar chart: top 10 slowest tests by avg duration
- [x] `ci_sherlock/dashboard/views/score.py` — gauge chart: release readiness score + factor breakdown

**CLI**
- [x] `cli.py dashboard` — calls `streamlit run` on `app.py`, passes DB path as env var

**GitHub Action**
- [x] `action.yml` — composite action: `pip install ci-sherlock`, `ci-sherlock analyze`
- [x] Example workflow in `examples/ci.yml`

---

## File structure (end state)

```
ci-sherlock/
├── README.md
├── action.yml
├── pyproject.toml
├── examples/
│   └── ci.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── STACK.md
│   ├── IMPLEMENTATION.md
│   ├── DATA_MODEL.md
│   └── EXTENDING.md
├── ci_sherlock/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── db.py
│   ├── github_client.py
│   ├── analyzer.py
│   ├── llm_engine.py
│   ├── optimization.py
│   ├── commenter.py
│   ├── scoring.py
│   ├── parsers/
│   │   ├── base.py
│   │   └── playwright.py
│   └── dashboard/
│       ├── app.py
│       └── views/
│           ├── run_history.py
│           ├── test_health.py
│           ├── flaky.py
│           ├── slowest.py
│           └── score.py
└── tests/
    ├── fixtures/
    │   └── playwright-report.json
    ├── parsers/
    │   └── test_playwright.py
    ├── test_analyzer.py
    ├── test_llm_engine.py
    ├── test_flaky.py
    └── test_optimization.py
```
