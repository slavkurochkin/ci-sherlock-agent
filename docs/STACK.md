# Stack

## Language: Python 3.12+

**Why not TypeScript:**
GitHub Actions can be written in TypeScript, but distribution as a reusable action then requires either bundling (fragile) or Docker (slow cold starts). Python-based tools published to PyPI are simpler to consume: one `pip install` step, no runtime version conflicts, works on any runner.

The AI/data ecosystem in Python is also significantly more mature — structured LLM outputs, SQLite tooling, and Streamlit are all first-class.

---

## Layer breakdown

### CLI — `typer` + `rich`

| | |
|---|---|
| **typer** | Builds the CLI from type-annotated Python functions. Auto-generates `--help`, handles argument parsing, supports subcommands cleanly. |
| **rich** | Terminal output with colour, tables, and progress bars. Makes `ci-sherlock analyze` readable when run in local dev, not just in CI logs. |

### GitHub API — `httpx` + `PyGithub`

| | |
|---|---|
| **httpx** | Async-capable HTTP client. Used for raw API calls where we need full control (e.g. fetching patch text from PR diff). |
| **PyGithub** | Higher-level GitHub API wrapper for standard operations (posting comments, listing runs). Reduces boilerplate. |

Alternative considered: `ghapi` — rejected, less maintained.

### LLM — `openai` SDK + `instructor`

| | |
|---|---|
| **openai** | Official SDK. Handles auth, retries, streaming. |
| **instructor** | Patches the OpenAI client to guarantee structured JSON output via Pydantic models. Eliminates manual prompt engineering for output format and JSON parsing/validation. |

Example:
```python
import instructor
from openai import OpenAI
from pydantic import BaseModel

client = instructor.from_openai(OpenAI())

class LLMInsight(BaseModel):
    root_cause: str
    confidence: float
    recommendation: str
    flaky_tests: list[str]

insight = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}],
    response_model=LLMInsight,
)
```

### Persistence — `SQLite` + `sqlite-utils`

| | |
|---|---|
| **SQLite** | Zero-config, file-based, no server. The DB file can live in the repo, be passed as a GitHub artifact, or sit on a shared volume. |
| **sqlite-utils** | Pythonic API over SQLite — insert dicts, upsert, query. No ORM overhead. Fast to iterate on schema. |

Alternative considered: `SQLModel` (SQLAlchemy-based ORM) — rejected for MVP. Too much ceremony for what is essentially append-only structured logging. Can migrate later if needed.

### Dashboard — `streamlit`

| | |
|---|---|
| **streamlit** | Pure Python UI. No frontend code. Reads from SQLite and renders charts, tables, and metrics. The `ci-sherlock dashboard` command launches it. |

Key views planned:
- Run history timeline
- Test failure heatmap (test × run)
- Flaky test leaderboard (failure rate over N runs)
- Slowest tests chart
- Release readiness score gauge

### Config — `pydantic-settings`

| | |
|---|---|
| **pydantic-settings** | Reads config from environment variables and/or a YAML file. Type-validated. Works seamlessly with GitHub Actions secrets and local `.env` files. |

### Packaging — `pyproject.toml` + PyPI

| | |
|---|---|
| **pyproject.toml** | Single source of truth for package metadata, dependencies, and entry points. |
| **PyPI** | Distribution target. `pip install ci-sherlock` in any workflow. |
| **GitHub Action** | Thin composite action (`action.yml`) that runs `pip install` and then `ci-sherlock analyze`. |

---

## Full dependency list (planned)

```toml
[project]
dependencies = [
    "openai>=1.30.0",
    "instructor>=1.0.0",
    "httpx>=0.27.0",
    "PyGithub>=2.0.0",
    "sqlite-utils>=3.36.0",
    "streamlit>=1.40.0",
    "typer>=0.12.0",
    "rich>=13.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
]

[project.scripts]
ci-sherlock = "ci_sherlock.cli:app"
```

---

## Model choice

Default: `gpt-4o`

- Best balance of reasoning quality and cost for CI analysis
- Runs fast enough that the `sherlock` job adds minimal wall-clock time to a pipeline
- Configurable via `SHERLOCK_MODEL` env var — swap in `gpt-4o-mini` to reduce cost or `o1` for deeper reasoning on complex failures
