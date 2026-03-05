import os
import re
import string
from ci_sherlock.models import TestResult, ChangedFile, Correlation, AnalysisResult, FlakySignal


class Analyzer:
    def correlate(
        self,
        results: list[TestResult],
        changed_files: list[ChangedFile],
        run_id: str,
        repo: str,
        pr_number: int | None,
        commit_sha: str,
        branch: str,
    ) -> AnalysisResult:
        failed = [r for r in results if r.status in ("failed", "flaky")]
        passed = [r for r in results if r.status == "passed"]
        skipped = [r for r in results if r.status == "skipped"]
        duration_ms = sum(r.duration_ms for r in results)

        correlations: list[Correlation] = []
        unmatched: list[TestResult] = []

        for test in failed:
            matched = self._match(test, changed_files)
            if matched:
                correlations.extend(matched)
            else:
                unmatched.append(test)

        return AnalysisResult(
            run_id=run_id,
            repo=repo,
            pr_number=pr_number,
            commit_sha=commit_sha,
            branch=branch,
            total_tests=len(results),
            passed_tests=len(passed),
            failed_tests=len(failed),
            skipped_tests=len(skipped),
            duration_ms=duration_ms,
            failed_results=failed,
            correlations=correlations,
            unmatched_failures=unmatched,
            changed_files=changed_files,
        )

    def _match(self, test: TestResult, changed_files: list[ChangedFile]) -> list[Correlation]:
        matches: list[Correlation] = []

        test_file = test.test_file
        test_dir = os.path.dirname(test_file)

        for cf in changed_files:
            changed = cf.filename
            changed_dir = os.path.dirname(changed)

            if self._same_file(test_file, changed):
                matches.append(Correlation(
                    test_name=test.test_name,
                    test_file=test_file,
                    changed_file=changed,
                    score=1.0,
                    reason="direct_match",
                ))
            elif test_dir and changed_dir and self._same_dir(test_dir, changed_dir):
                matches.append(Correlation(
                    test_name=test.test_name,
                    test_file=test_file,
                    changed_file=changed,
                    score=0.6,
                    reason="same_directory",
                ))
            else:
                diff_score = self.check_diff_content(test, cf)
                if diff_score > 0:
                    matches.append(Correlation(
                        test_name=test.test_name,
                        test_file=test_file,
                        changed_file=changed,
                        score=diff_score,
                        reason="diff_content_match",
                    ))

        # Deduplicate — keep highest score per changed file
        seen: dict[str, Correlation] = {}
        for c in matches:
            if c.changed_file not in seen or c.score > seen[c.changed_file].score:
                seen[c.changed_file] = c

        return list(seen.values())

    @staticmethod
    def check_diff_content(test: TestResult, changed: ChangedFile) -> float:
        """Return 0.9 if any meaningful token from the error message appears in the patch."""
        if not changed.patch or not test.error_message:
            return 0.0
        # Extract tokens longer than 4 chars, strip punctuation
        translator = str.maketrans("", "", string.punctuation)
        tokens = [
            w.translate(translator)
            for w in re.split(r"\s+", test.error_message)
            if len(w) > 4
        ]
        tokens = [t for t in tokens if len(t) > 4]
        if not tokens:
            return 0.0
        patch = changed.patch
        return 0.9 if any(t in patch for t in tokens) else 0.0

    @staticmethod
    def _clean(path: str) -> str:
        """Normalise to forward-slash lowercase, strip leading ./ or /."""
        return path.replace("\\", "/").lower().lstrip("./")

    @classmethod
    def _same_file(cls, a: str, b: str) -> bool:
        """Match paths that may differ in prefix (absolute CI path vs repo-relative)."""
        ca, cb = cls._clean(a), cls._clean(b)
        return ca == cb or ca.endswith("/" + cb) or cb.endswith("/" + ca)

    @classmethod
    def _same_dir(cls, a: str, b: str) -> bool:
        ca, cb = cls._clean(a), cls._clean(b)
        return bool(ca) and bool(cb) and (ca == cb or ca.endswith("/" + cb) or cb.endswith("/" + ca))

    # --- Phase 3: Flaky detection ---

    def detect_flaky_current(self, results: list[TestResult]) -> list[FlakySignal]:
        """Flag tests that retried and eventually passed — classic flaky signal."""
        return [
            FlakySignal(
                test_name=r.test_name,
                test_file=r.test_file,
                source="retry",
            )
            for r in results
            if r.retry_count > 0 and r.status == "passed"
        ]

    def detect_flaky_historical(self, db_rows: list[dict], threshold: float = 0.10) -> list[FlakySignal]:
        """
        Flag tests with a historical failure rate above `threshold`.
        Expects rows as returned by Database.get_flaky_tests().
        """
        return [
            FlakySignal(
                test_name=row["test_name"],
                test_file=row["test_file"],
                source="historical",
                failure_rate=row["failure_rate"],
            )
            for row in db_rows
            if row["failure_rate"] > threshold
        ]
