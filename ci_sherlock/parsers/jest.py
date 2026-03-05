import json
import re
from ci_sherlock.parsers.base import BaseParser
from ci_sherlock.models import TestResult

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class JestParser(BaseParser):
    @property
    def name(self) -> str:
        return "jest"

    def parse(self, report_path: str) -> list[TestResult]:
        with open(report_path) as f:
            data = json.load(f)

        if "testResults" not in data:
            raise ValueError(f"Not a valid Jest JSON report: {report_path}")

        results: list[TestResult] = []
        for suite in data.get("testResults", []):
            self._parse_suite(suite, results)
        return results

    def _parse_suite(self, suite: dict, results: list[TestResult]) -> None:
        file_path = self._clean(suite.get("testFilePath", "unknown"))

        for assertion in suite.get("assertionResults", []):
            title = assertion.get("title", "")
            ancestors = assertion.get("ancestorTitles", [])
            test_name = " > ".join(ancestors + [title]) if ancestors else title

            raw_status = assertion.get("status", "pending")
            status = self._map_status(raw_status)

            duration_ms = int(assertion.get("duration") or 0)

            failure_messages = assertion.get("failureMessages", [])
            error_message = None
            if failure_messages:
                raw = failure_messages[0]
                error_message = _ANSI_RE.sub("", raw) if raw else None

            results.append(TestResult(
                test_name=test_name,
                test_file=file_path,
                status=status,
                duration_ms=duration_ms,
                retry_count=0,
                error_message=error_message,
            ))

    @staticmethod
    def _map_status(jest_status: str) -> str:
        return {
            "passed": "passed",
            "failed": "failed",
            "pending": "skipped",
            "todo": "skipped",
            "skipped": "skipped",
        }.get(jest_status, "skipped")

    @staticmethod
    def _clean(path: str) -> str:
        """Strip absolute path prefix to return a repo-relative-looking path."""
        # Replace backslashes, then try to find a reasonable relative segment
        path = path.replace("\\", "/")
        # Heuristic: keep everything after common CI workspace prefixes
        for prefix in ("/home/runner/work/", "/github/workspace/", "/workspace/"):
            idx = path.find(prefix)
            if idx != -1:
                rest = path[idx + len(prefix):]
                # strip one more segment (the repo name duplicated by GitHub Actions)
                parts = rest.split("/", 1)
                if len(parts) == 2:
                    return parts[1]
                return rest
        return path
