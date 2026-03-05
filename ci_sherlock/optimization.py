import glob as _glob
from ci_sherlock.models import TestResult, OptimizationSuggestion

# Thresholds
SLOW_TEST_MS = 10_000       # tests slower than this are flagged
SLOW_TEST_TOP_N = 5         # report top N slow tests
SUITE_SLOW_TOTAL_MS = 120_000  # flag parallelization if total > 2 min


class OptimizationEngine:
    def analyze(self, results: list[TestResult]) -> list[OptimizationSuggestion]:
        suggestions: list[OptimizationSuggestion] = []
        suggestions.extend(self.slow_tests(results))
        suggestions.extend(self.check_parallelization(results))
        return suggestions

    def slow_tests(self, results: list[TestResult]) -> list[OptimizationSuggestion]:
        # Exclude failed tests — their duration is inflated by retries, not genuine slowness
        candidates = [r for r in results if r.status not in ("failed",) and r.duration_ms >= SLOW_TEST_MS]
        slow = sorted(candidates, key=lambda r: -r.duration_ms)[:SLOW_TEST_TOP_N]

        return [
            OptimizationSuggestion(
                type="slow_test",
                description=f"`{r.test_name}` took {r.duration_ms / 1000:.1f}s — consider splitting or optimising",
                impact="medium",
                metadata={"test_name": r.test_name, "test_file": r.test_file, "duration_ms": r.duration_ms},
            )
            for r in slow
        ]

    def check_missing_cache(self, workflow_dir: str = ".github/workflows") -> list[OptimizationSuggestion]:
        suggestions = []
        patterns = [f"{workflow_dir}/*.yml", f"{workflow_dir}/*.yaml"]
        workflow_files: list[str] = []
        for pattern in patterns:
            workflow_files.extend(_glob.glob(pattern))

        for wf_path in workflow_files:
            try:
                content = open(wf_path).read()
            except OSError:
                continue
            if "playwright install" in content and "actions/cache" not in content:
                suggestions.append(OptimizationSuggestion(
                    type="missing_cache",
                    description=(
                        f"`{wf_path}` runs `playwright install` but has no `actions/cache` step. "
                        "Cache `~/.cache/ms-playwright` to speed up browser downloads."
                    ),
                    impact="medium",
                    metadata={"workflow_file": wf_path},
                ))
        return suggestions

    def check_parallelization(self, results: list[TestResult]) -> list[OptimizationSuggestion]:
        # Only count passing tests for total duration — failed tests inflate via retries
        passing = [r for r in results if r.status not in ("failed",)]
        total_ms = sum(r.duration_ms for r in passing)
        if total_ms > SUITE_SLOW_TOTAL_MS:
            minutes = total_ms / 60_000
            return [
                OptimizationSuggestion(
                    type="no_parallelization",
                    description=(
                        f"Suite took {minutes:.1f} min total. "
                        "Consider enabling Playwright sharding (`--shard=1/4`) to parallelise across runners."
                    ),
                    impact="high",
                    metadata={"total_duration_ms": total_ms},
                )
            ]
        return []
