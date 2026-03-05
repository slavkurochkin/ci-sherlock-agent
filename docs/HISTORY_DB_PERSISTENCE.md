# History DB Persistence Strategies

CI Sherlock stores run history in a SQLite file (`.ci-sherlock/history.db`).
This file must persist across CI runs for the dashboard, flaky detection, and
release readiness score to work correctly (minimum 3 runs required).

This document compares available strategies, with trade-offs around effort and
concurrency safety.

---

## The concurrency problem

When two PRs run simultaneously:

1. Both jobs download the same DB (e.g. after 5 runs it contains 5 rows)
2. Both append their run locally (6 rows each)
3. Both upload — whichever finishes last wins
4. The other run's data is silently lost

How often this matters depends on your team size and PR throughput.

---

## Option 1 — GitHub Actions Artifacts (current default)

Each run uploads the DB as an artifact named `sherlock-db`. The next run
downloads it before analyzing, appends its result, then re-uploads.

**Concurrency:** last-writer-wins. Data loss is possible under concurrent runs.

**Setup:** already implemented in the example `ci.yml` using
`dawidd6/action-download-artifact`.

**Best for:** solo projects, small teams with low PR concurrency.

---

## Option 2 — GitHub Actions Cache

Use `actions/cache` keyed on a fixed key (e.g. `sherlock-db-main`).
The cache is restored at the start of the job and saved at the end.

```yaml
- name: Restore history DB
  uses: actions/cache@v4
  with:
    path: .ci-sherlock/history.db
    key: sherlock-db-main
    restore-keys: sherlock-db-
```

**Concurrency:** same last-writer-wins problem as artifacts. Cache also has a
10 GB total limit and evicts entries after 7 days of inactivity.

**Best for:** same audience as Option 1, slightly simpler setup.

---

## Option 3 — Commit DB to a dedicated git branch

Store the DB on a long-lived branch (e.g. `ci-history`) in the repo. Each CI
run pulls the latest, appends, commits, and pushes. Git's push rejection forces
a retry loop that naturally serializes concurrent writers.

```yaml
- name: Restore history DB
  run: |
    git fetch origin ci-history || true
    git checkout origin/ci-history -- .ci-sherlock/history.db 2>/dev/null || true

- name: Run CI Sherlock
  run: ci-sherlock analyze

- name: Commit updated history DB
  run: |
    git config user.name  "ci-sherlock[bot]"
    git config user.email "ci-sherlock[bot]@users.noreply.github.com"
    git add .ci-sherlock/history.db
    git commit -m "chore: update sherlock history [skip ci]" || true
    for i in 1 2 3; do
      git pull --rebase origin ci-history && git push origin HEAD:ci-history && break
      sleep $((i * 5))
    done
```

**Concurrency:** safe — push rejection + rebase retry serializes writers.
A binary SQLite file does not merge gracefully; under high concurrency the
rebase will conflict. In practice, 3 retries with back-off covers most cases.

**Considerations:**
- Requires `contents: write` permission in the workflow
- Binary commits grow repo size over time (use `git gc` or shallow clone)
- Add `.ci-sherlock/` to `.gitignore` on the default branch to avoid
  accidentally committing the DB there

**Best for:** teams with moderate PR concurrency who want zero external
dependencies.

---

## Option 4 — External persistent store

Host the DB (or replace it) with a proper persistent backend. Options:

| Backend | Notes |
|---|---|
| **AWS S3 / GCS** | Download before run, upload after. Use object versioning or conditional writes for safety. |
| **Supabase (Postgres)** | Replace SQLite with a Postgres connection. Full ACID concurrency. Requires schema migration. |
| **PlanetScale / Turso** | Distributed SQLite-compatible, built for edge/serverless. Minimal code changes. |
| **GitHub releases** | Upload DB as a release asset on a fixed tag. Simple but not atomic. |

**Concurrency:** fully safe with proper locking (Postgres) or object
versioning (S3 conditional put).

**Best for:** teams running many concurrent PRs, or where history data is
considered critical.

---

## Decision matrix

| | Effort | Concurrent-safe | External dependency |
|---|---|---|---|
| Artifacts (Option 1) | none | no | no |
| Cache (Option 2) | low | no | no |
| Git branch (Option 3) | medium | mostly yes | no |
| External store (Option 4) | high | yes | yes |

For most projects **Option 1** is the right starting point. Move to
**Option 3** once concurrent PR runs become common. Move to **Option 4** only
if history data is business-critical.
