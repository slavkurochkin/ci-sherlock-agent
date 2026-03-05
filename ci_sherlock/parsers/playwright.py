import json
from typing import Any
from ci_sherlock.parsers.base import BaseParser
from ci_sherlock.models import TestResult


class PlaywrightParser(BaseParser):
    @property
    def name(self) -> str:
        return "playwright"

    def parse(self, report_path: str) -> list[TestResult]:
        with open(report_path) as f:
            data = json.load(f)

        if "suites" not in data:
            raise ValueError(f"Not a valid Playwright JSON report: {report_path}")

        results: list[TestResult] = []
        for suite in data.get("suites", []):
            self._walk_suite(suite, results)
        return results

    def _walk_suite(self, suite: dict[str, Any], results: list[TestResult]) -> None:
        file_path = suite.get("file", suite.get("title", "unknown"))

        for spec in suite.get("specs", []):
            self._parse_spec(spec, file_path, results)

        for child_suite in suite.get("suites", []):
            # Preserve the parent file path for nested describes
            child = dict(child_suite)
            child.setdefault("file", file_path)
            self._walk_suite(child, results)

    def _parse_spec(self, spec: dict[str, Any], file_path: str, results: list[TestResult]) -> None:
        spec_title = spec.get("title", "")
        spec_file = spec.get("file", file_path)

        for test in spec.get("tests", []):
            test_results = test.get("results", [])
            if not test_results:
                continue

            overall_status = self._map_status(test.get("status", "skipped"))
            retry_count = len(test_results) - 1

            # Duration is the sum of all attempt durations
            duration_ms = sum(r.get("duration", 0) for r in test_results)

            # Error comes from the first failed attempt
            error_message = None
            error_stack = None
            trace_path = None

            for result in test_results:
                if result.get("status") == "failed" or result.get("status") == "timedOut":
                    err = result.get("error", {})
                    error_message = err.get("message")
                    error_stack = err.get("stack")
                    break

            # Trace from attachments (any attempt)
            for result in test_results:
                for attachment in result.get("attachments", []):
                    if attachment.get("name") == "trace":
                        trace_path = attachment.get("path") or attachment.get("contentType")
                        break
                if trace_path:
                    break

            results.append(TestResult(
                test_name=spec_title,
                test_file=spec_file,
                status=overall_status,
                duration_ms=duration_ms,
                retry_count=retry_count,
                error_message=error_message,
                error_stack=error_stack,
                trace_path=trace_path,
            ))

    @staticmethod
    def _map_status(pw_status: str) -> str:
        return {
            "expected": "passed",
            "passed": "passed",
            "unexpected": "failed",
            "failed": "failed",
            "timedOut": "failed",
            "interrupted": "failed",
            "flaky": "flaky",
            "skipped": "skipped",
        }.get(pw_status, "skipped")
