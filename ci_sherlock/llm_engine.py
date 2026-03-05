import logging
from ci_sherlock.models import AnalysisResult, LLMInsight

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

Fix suggestion rules (suggested_fix, suggested_fix_file, suggested_fix_original):
- Only populate these when confidence > 0.7 AND a direct_match correlation exists
- suggested_fix: the replacement lines ONLY — no surrounding context, no diff markers
- suggested_fix_file: must be exactly one of the filenames listed under "Changed files"
- suggested_fix_original: VERBATIM copy of the broken line from the diff shown in this
  prompt — strip only the leading diff prefix character (space or +), preserve all
  spacing and punctuation exactly. Do NOT paraphrase or reformat.
  If the broken line is not clearly present in the diff text you were given, set
  all three fields to null. A null original is far better than a wrong one — a
  wrong original causes the suggestion to be posted on an unrelated line.
- The fix must be self-contained and safe — do not guess at logic you cannot see
- If you cannot produce a reliable single-file fix, leave all three fields null
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

    def analyze(
        self,
        analysis: AnalysisResult,
        fingerprint_counts: dict[str, int] | None = None,
    ) -> LLMInsight | None:
        if not analysis.failed_results:
            return None

        prompt = self._build_prompt(analysis, fingerprint_counts or {})
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

    def _build_prompt(self, analysis: AnalysisResult, fingerprint_counts: dict[str, int] | None = None) -> str:
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
        sections.append(self._format_failures(analysis, fingerprint_counts or {}))

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

        # Fix eligibility hint
        has_direct = any(c.reason == "direct_match" for c in analysis.correlations)
        if has_direct and analysis.changed_files:
            file_list = "\n".join(f"- {f.filename}" for f in analysis.changed_files[:20])
            sections.append(
                "## Fix suggestion eligibility\n"
                "A direct_match correlation exists. You MAY populate suggested_fix fields.\n"
                f"Valid targets for suggested_fix_file:\n{file_list}\n\n"
                "IMPORTANT: suggested_fix_original MUST be a verbatim copy of the broken\n"
                "line exactly as it appears in the diff shown above (strip only the leading\n"
                "' ' or '+' prefix). If the broken line is not clearly visible in the diff\n"
                "text, set all three suggested_fix fields to null."
            )
        else:
            sections.append(
                "## Fix suggestion eligibility\n"
                "No direct_match correlation — leave suggested_fix fields null."
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
    def _format_failures(analysis: AnalysisResult, fingerprint_counts: dict[str, int] | None = None) -> str:
        counts = fingerprint_counts or {}
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
            seen = counts.get(test.error_fingerprint or "", 0)
            seen_note = f" [seen in {seen} previous run(s)]" if seen > 0 else " [new error]"
            lines.append(f"\n### {test.test_name}{retry_note}{seen_note}")
            lines.append(f"File: `{test.test_file}`")
            if test.error_message:
                lines.append(f"Error: {test.error_message[:400]}")
            if test.error_stack:
                lines.append(f"Stack:\n```\n{test.error_stack[:400]}\n```")
        if len(analysis.failed_results) > 10:
            lines.append(f"\n_…{len(analysis.failed_results) - 10} more failures omitted_")
        return "\n".join(lines)
