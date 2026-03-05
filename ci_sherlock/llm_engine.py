import logging
import re
from ci_sherlock.models import AnalysisResult, LLMInsight

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a CI reliability engineer analyzing test failures in a pull request.

Given a list of failing tests, their error messages, and the files changed in the PR,
determine the most likely root cause and provide a concise, actionable recommendation.

Rules:
- Be specific — name the file or change that likely caused the failure
- If failures look unrelated to any diff, say so and flag them as potentially environmental
- If a test has retries that eventually passed, flag it as flaky
- Confidence should reflect how strong the evidence is (0.0 = guess, 1.0 = certain)
- duration_ms includes ALL retry attempts — a 90s duration on a test with 2 retries
  means ~30s per attempt, not a genuinely slow test. Do not flag retried tests as slow.
"""


class LLMEngine:
    def __init__(self, client, model: str = "gpt-4o") -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_api_key(cls, api_key: str, model: str = "gpt-4o") -> "LLMEngine":
        import instructor
        from openai import OpenAI
        client = instructor.from_openai(OpenAI(api_key=api_key))
        return cls(client=client, model=model)

    def analyze(self, analysis: AnalysisResult) -> LLMInsight | None:
        if not analysis.failed_results:
            return None

        prompt = self._build_prompt(analysis)
        try:
            return self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_model=LLMInsight,
                max_retries=2,
            )
        except Exception as exc:
            logger.warning("LLM analysis failed: %s — posting raw analysis only", exc)
            return None

    def _build_prompt(self, analysis: AnalysisResult) -> str:
        sections: list[str] = []

        # Changed files with diff patches
        if analysis.failed_results:
            if analysis.changed_files:
                lines = ["## Changed files in this PR"]
                for f in analysis.changed_files[:20]:
                    lines.append(f"### {f.filename} ({f.status}, +{f.additions}/-{f.deletions})")
                    if f.patch:
                        lines.append(f"```diff\n{f.patch[:800]}\n```")
                sections.append("\n".join(lines))
            else:
                sections.append("## Changed files\nNo diff available (push event or missing token).")

        # Failed tests
        sections.append(self._format_failures(analysis))

        # Correlation signals
        if analysis.correlations:
            lines = ["## Failure → diff correlation"]
            for c in sorted(analysis.correlations, key=lambda x: -x.score)[:10]:
                lines.append(f"- `{c.test_name}` ↔ `{c.changed_file}` (score {c.score:.1f}, {c.reason})")
            sections.append("\n".join(lines))

        if analysis.unmatched_failures:
            names = [t.test_name for t in analysis.unmatched_failures[:5]]
            sections.append(
                "## Unmatched failures (no correlation to diff)\n"
                + "\n".join(f"- {n}" for n in names)
            )

        return "\n\n".join(sections)

    @staticmethod
    def _get_changed_files(analysis: AnalysisResult) -> list[str]:
        # Prefer the full diff stored on the result; fall back to correlation-derived
        if analysis.changed_files:
            return [f.filename for f in analysis.changed_files]
        files: set[str] = set()
        for c in analysis.correlations:
            files.add(c.changed_file)
        return sorted(files)

    @staticmethod
    def _format_failures(analysis: AnalysisResult) -> str:
        lines = [f"## Failed tests ({analysis.failed_tests} total)"]
        for test in analysis.failed_results[:10]:
            if test.retry_count:
                approx_ms = test.duration_ms // (test.retry_count + 1)
                retry_note = (
                    f" [retried {test.retry_count}x, still {test.status}]"
                    f" — duration {test.duration_ms}ms is total across all attempts"
                    f" (~{approx_ms}ms per attempt)"
                )
            else:
                retry_note = ""
            lines.append(f"\n### {test.test_name}{retry_note}")
            lines.append(f"File: `{test.test_file}`")
            if test.error_message:
                msg = _ANSI_RE.sub("", test.error_message)[:400]
                lines.append(f"Error: {msg}")
            if test.error_stack:
                stack = _ANSI_RE.sub("", test.error_stack)[:400]
                lines.append(f"Stack:\n```\n{stack}\n```")
        if len(analysis.failed_results) > 10:
            lines.append(f"\n_…{len(analysis.failed_results) - 10} more failures omitted_")
        return "\n".join(lines)
