# Data Model

All data is stored in a single SQLite file. Default location: `.ci-sherlock/history.db`.

---

## Tables

### `runs`

One row per `ci-sherlock analyze` invocation.

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (UUID) | Primary key |
| `repo` | TEXT | `owner/repo` |
| `pr_number` | INTEGER | PR number, null for push events |
| `commit_sha` | TEXT | HEAD commit SHA |
| `branch` | TEXT | Branch name |
| `workflow_run_id` | INTEGER | GitHub Actions run ID |
| `status` | TEXT | `passed`, `failed`, `partial` |
| `total_tests` | INTEGER | Total test count |
| `passed_tests` | INTEGER | |
| `failed_tests` | INTEGER | |
| `skipped_tests` | INTEGER | |
| `duration_ms` | INTEGER | Total suite duration |
| `release_readiness_score` | REAL | 0–100, null if not enough history |
| `created_at` | TEXT | ISO 8601 timestamp |

---

### `test_results`

One row per test per run.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key (autoincrement) |
| `run_id` | TEXT | Foreign key → `runs.id` |
| `test_name` | TEXT | Full test title |
| `test_file` | TEXT | Relative path to spec file |
| `status` | TEXT | `passed`, `failed`, `skipped`, `flaky` |
| `duration_ms` | INTEGER | Test duration |
| `retry_count` | INTEGER | Number of retries before final status |
| `error_message` | TEXT | First error message if failed, null otherwise |
| `error_stack` | TEXT | Stack trace, null otherwise |
| `trace_path` | TEXT | Path to Playwright trace file, null if not captured |

---

### `changed_files`

Files changed in the PR for each run. Populated from GitHub API.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `run_id` | TEXT | Foreign key → `runs.id` |
| `filename` | TEXT | Relative file path |
| `status` | TEXT | `added`, `modified`, `removed`, `renamed` |
| `additions` | INTEGER | Lines added |
| `deletions` | INTEGER | Lines deleted |

---

### `correlations`

Which changed files are linked to which failing tests, and how strongly.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `run_id` | TEXT | Foreign key → `runs.id` |
| `test_name` | TEXT | |
| `changed_file` | TEXT | |
| `score` | REAL | 0.0–1.0 correlation strength |
| `reason` | TEXT | `direct_match`, `same_directory`, `imported_module` |

---

### `insights`

LLM-generated analysis per run. One row per run (null if LLM was skipped).

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `run_id` | TEXT | Foreign key → `runs.id` |
| `root_cause` | TEXT | LLM-generated root cause description |
| `confidence` | REAL | 0.0–1.0 |
| `recommendation` | TEXT | Suggested fix |
| `flaky_tests` | TEXT | JSON array of test names flagged as flaky |
| `model` | TEXT | Model used (e.g. `gpt-4o`) |
| `prompt_tokens` | INTEGER | |
| `completion_tokens` | INTEGER | |
| `created_at` | TEXT | ISO 8601 timestamp |

---

### `optimization_suggestions`

CI optimization signals per run.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `run_id` | TEXT | Foreign key → `runs.id` |
| `type` | TEXT | `slow_test`, `missing_cache`, `no_parallelization`, `sequential_jobs` |
| `description` | TEXT | Human-readable suggestion |
| `impact` | TEXT | `high`, `medium`, `low` |
| `metadata` | TEXT | JSON blob with type-specific data (e.g. test name + duration for slow_test) |

---

## Entity relationships

```
runs
 ├── test_results      (1 run → many results)
 ├── changed_files     (1 run → many files)
 ├── correlations      (1 run → many correlations)
 ├── insights          (1 run → 0 or 1 insight)
 └── optimization_suggestions  (1 run → many suggestions)
```

---

## Key queries

**Failure rate for a test over last 30 runs**
```sql
SELECT
    test_name,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS failure_rate_pct
FROM test_results
WHERE run_id IN (
    SELECT id FROM runs ORDER BY created_at DESC LIMIT 30
)
GROUP BY test_name
ORDER BY failure_rate_pct DESC;
```

**Slowest tests on average**
```sql
SELECT test_name, ROUND(AVG(duration_ms)) AS avg_duration_ms
FROM test_results
WHERE status IN ('passed', 'failed')
GROUP BY test_name
ORDER BY avg_duration_ms DESC
LIMIT 10;
```

**Flaky tests (retry > 0 but eventually passed)**
```sql
SELECT DISTINCT test_name
FROM test_results
WHERE retry_count > 0 AND status = 'passed';
```

**Release readiness input data**
```sql
SELECT
    r.id,
    r.created_at,
    r.passed_tests,
    r.failed_tests,
    r.total_tests,
    r.duration_ms,
    (SELECT COUNT(*) FROM test_results tr WHERE tr.run_id = r.id AND tr.retry_count > 0) AS flaky_count
FROM runs r
ORDER BY r.created_at DESC
LIMIT 20;
```

---

## Schema initialization

The `Database` class creates all tables on first use if they don't exist. No migrations needed for MVP — `sqlite-utils` handles `alter()` for additive schema changes.
