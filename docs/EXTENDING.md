# Extending CI Sherlock

CI Sherlock is designed around a `BaseParser` interface. The core analysis pipeline doesn't know anything about Playwright — it only works with `TestResult` objects. Adding support for another test framework means implementing one class.

---

## Adding a new parser

### 1. Understand the interface

```python
# ci_sherlock/parsers/base.py

from abc import ABC, abstractmethod
from ci_sherlock.models import TestResult

class BaseParser(ABC):
    """
    Parse a test report file into a list of TestResult objects.
    Each subclass handles one report format.
    """

    @abstractmethod
    def parse(self, report_path: str) -> list[TestResult]:
        """
        Read the report at report_path and return a flat list of TestResult.
        Raise FileNotFoundError if the file doesn't exist.
        Raise ValueError if the file is not a valid report for this parser.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name, e.g. 'playwright', 'jest', 'vitest'."""
        ...
```

### 2. Understand the `TestResult` model

```python
# ci_sherlock/models.py (relevant fields)

class TestResult(BaseModel):
    test_name: str          # Full test title / describe path
    test_file: str          # Relative path to the spec file
    status: Literal["passed", "failed", "skipped", "flaky"]
    duration_ms: int        # Test duration in milliseconds
    retry_count: int        # Number of retries (0 = no retries)
    error_message: str | None = None
    error_stack: str | None = None
    trace_path: str | None = None  # Optional, framework-specific
```

### 3. Implement your parser

Create `ci_sherlock/parsers/<framework>.py`:

```python
# ci_sherlock/parsers/jest.py

import json
from ci_sherlock.parsers.base import BaseParser
from ci_sherlock.models import TestResult

class JestParser(BaseParser):

    @property
    def name(self) -> str:
        return "jest"

    def parse(self, report_path: str) -> list[TestResult]:
        with open(report_path) as f:
            data = json.load(f)

        results = []
        for suite in data.get("testResults", []):
            file_path = suite["testFilePath"]
            for test in suite.get("testResults", []):
                status = self._map_status(test["status"])
                results.append(TestResult(
                    test_name=test["fullName"],
                    test_file=file_path,
                    status=status,
                    duration_ms=test.get("duration", 0),
                    retry_count=0,  # Jest doesn't report retries in the default JSON
                    error_message=test["failureMessages"][0] if test["failureMessages"] else None,
                ))
        return results

    def _map_status(self, jest_status: str) -> str:
        return {
            "passed": "passed",
            "failed": "failed",
            "pending": "skipped",
            "todo": "skipped",
        }.get(jest_status, "skipped")
```

### 4. Register your parser

Add it to the parser registry in `cli.py`:

```python
# ci_sherlock/cli.py

from ci_sherlock.parsers.playwright import PlaywrightParser
from ci_sherlock.parsers.jest import JestParser

PARSERS = {
    "playwright": PlaywrightParser,
    "jest": JestParser,
}
```

Users select it via config or CLI flag:

```bash
ci-sherlock analyze --parser jest --report jest-results.json
```

Or in `ci-sherlock.yml`:

```yaml
parser: jest
report_path: jest-results.json
```

### 5. Add a fixture and test

```python
# tests/parsers/test_jest.py

from ci_sherlock.parsers.jest import JestParser

def test_parse_failures():
    parser = JestParser()
    results = parser.parse("tests/fixtures/jest-report.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) > 0
    assert failed[0].error_message is not None
```

Add a real or synthetic `tests/fixtures/jest-report.json` from a local Jest run.

---

## Supported report formats

| Framework | Parser | Report flag | Status |
|---|---|---|---|
| Playwright | `PlaywrightParser` | `--reporter json` | Shipped |
| Jest / Vitest | `JestParser` | `--json --outputFile` | Shipped |
| Cypress | `CypressParser` | mochawesome JSON | Future |
| pytest | `PytestParser` | `--json-report` | Future |

### Auto-detection

The CLI auto-detects the parser based on the JSON structure:

```python
# ci_sherlock/cli.py — _detect_parser logic
if "testResults" in data:
    return JestParser()   # Jest / Vitest JSON format
return PlaywrightParser()  # default
```

You can also pass a Jest report directly:

```bash
ci-sherlock analyze --report jest-results.json
```

### Jest / Vitest setup

Generate the JSON report with:

```bash
# Jest
jest --json --outputFile jest-results.json

# Vitest
vitest run --reporter=json --outputFile=vitest-results.json
```

The JSON root must contain a `"testResults"` key (the Jest `--json` default). ANSI escape codes in failure messages are stripped automatically.

---

## What the parser does NOT need to handle

- Fetching the report file from GitHub artifacts — the CLI does this
- Writing to the database — `db.py` does this
- Posting comments — `commenter.py` does this
- Anything related to GitHub or the LLM

The parser's only job is: **file path in → `list[TestResult]` out**.
