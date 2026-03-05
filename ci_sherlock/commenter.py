from ci_sherlock.models import AnalysisResult, LLMInsight, FlakySignal, OptimizationSuggestion
from ci_sherlock.github_client import GitHubClient, COMMENT_MARKER


def format_comment(
    analysis: AnalysisResult,
    insight: LLMInsight | None = None,
    flaky_signals: list[FlakySignal] | None = None,
    optimization_suggestions: list[OptimizationSuggestion] | None = None,
    new_failures: set[str] | None = None,
    fixed_failures: set[str] | None = None,
) -> str:
    lines = [COMMENT_MARKER, "## CI Sherlock Analysis", ""]

    # Summary line
    status_icon = "✅" if analysis.failed_tests == 0 else "❌"
    lines.append(
        f"{status_icon} "
        f"**{analysis.passed_tests}** passed &nbsp; "
        f"**{analysis.failed_tests}** failed &nbsp; "
        f"**{analysis.skipped_tests}** skipped &nbsp; "
        f"— {analysis.duration_ms / 1000:.1f}s total"
    )

    # Delta line (new/fixed vs previous run)
    if new_failures is not None or fixed_failures is not None:
        delta_parts = []
        if new_failures:
            delta_parts.append(f"**+{len(new_failures)} new**")
        if fixed_failures:
            delta_parts.append(f"**{len(fixed_failures)} fixed** since last run")
        if not new_failures and not fixed_failures:
            delta_parts.append("_no change vs last run_")
        lines.append(f"_{' · '.join(delta_parts)}_")

    lines.append("")

    # LLM insight block
    if insight:
        confidence_pct = int(insight.confidence * 100)
        lines += [
            "### Root Cause",
            f"> {insight.root_cause}",
            "",
            f"**Confidence:** {confidence_pct}% &nbsp; **Recommendation:** {insight.recommendation}",
            "",
        ]
        if insight.flaky_tests:
            lines += [
                "### Flaky Tests (AI detected)",
                *[f"- `{t}`" for t in insight.flaky_tests],
                "",
            ]

    # Failures section
    if analysis.failed_results:
        failure_lines = []
        for test in analysis.failed_results[:10]:
            failure_lines.append(f"- **{test.test_name}** `{test.test_file}`")
            if test.error_message:
                msg = test.error_message[:200].replace("\n", " ")
                failure_lines.append(f"  ```\n  {msg}\n  ```")
            if test.trace_path:
                failure_lines.append(f"  [Trace]({test.trace_path})")
        if len(analysis.failed_results) > 10:
            failure_lines.append(f"- _…and {len(analysis.failed_results) - 10} more_")

        n_fail = len(analysis.failed_results)
        if n_fail > 3:
            lines += [
                f"<details>",
                f"<summary>Failures ({n_fail} tests)</summary>",
                "",
                *failure_lines,
                "",
                "</details>",
                "",
            ]
        else:
            lines += ["### Failures", ""] + failure_lines + [""]

    # Correlation section
    if analysis.correlations:
        sorted_corr = sorted(analysis.correlations, key=lambda x: -x.score)[:10]
        corr_lines = [
            "| Test | Changed file | Signal | Score |",
            "|---|---|---|---|",
            *[
                f"| `{c.test_name}` | `{c.changed_file}` | {c.reason} | {c.score:.1f} |"
                for c in sorted_corr
            ],
        ]
        n_corr = len(analysis.correlations)
        if n_corr > 3:
            lines += [
                "<details>",
                f"<summary>Failure → Diff Correlation ({n_corr} signals)</summary>",
                "",
                *corr_lines,
                "",
                "</details>",
                "",
            ]
        else:
            lines += ["### Failure → Diff Correlation", ""] + corr_lines + [""]

    if analysis.unmatched_failures:
        unmatched_lines = [f"- `{t.test_name}` ({t.test_file})" for t in analysis.unmatched_failures[:5]]
        lines += [
            "<details>",
            "<summary>Unmatched Failures</summary>",
            "",
            "_These failures have no correlation to changed files — possibly environmental or flaky._",
            "",
            *unmatched_lines,
            "",
            "</details>",
            "",
        ]

    # Proposed fix
    if insight and insight.suggested_fix and insight.suggested_fix_file:
        lines += [
            "### Proposed Fix",
            f"_Apply via the inline suggestion comment on `{insight.suggested_fix_file}`, "
            "or copy the diff below._",
            "",
            f"**File:** `{insight.suggested_fix_file}`",
            "",
        ]
        if insight.suggested_fix_original:
            lines += [
                "```diff",
                *[f"- {l}" for l in insight.suggested_fix_original.splitlines()],
                *[f"+ {l}" for l in insight.suggested_fix.splitlines()],
                "```",
                "",
            ]
        else:
            lines += [
                "```",
                insight.suggested_fix,
                "```",
                "",
            ]

    # Flaky signals (Phase 3)
    if flaky_signals:
        lines += ["### Flaky Tests Detected", ""]
        for s in flaky_signals[:8]:
            source_label = "retry signal" if s.source == "retry" else f"historical ({s.failure_rate:.0%} fail rate)"
            lines.append(f"- `{s.test_name}` — {source_label}")
        lines.append("")

    # Optimization suggestions (Phase 3)
    if optimization_suggestions:
        impact_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        opt_lines = []
        for s in optimization_suggestions:
            icon = impact_icon.get(s.impact, "•")
            opt_lines.append(f"- {icon} {s.description}")
        lines += [
            "<details>",
            f"<summary>CI Optimization ({len(optimization_suggestions)} suggestion{'s' if len(optimization_suggestions) != 1 else ''})</summary>",
            "",
            *opt_lines,
            "",
            "</details>",
            "",
        ]

    lines += [
        "---",
        f"_Run `{analysis.run_id}` · commit `{analysis.commit_sha[:7]}`_",
    ]

    return "\n".join(lines)


def post_or_update_comment(
    client: GitHubClient,
    pr_number: int,
    analysis: AnalysisResult,
    insight: LLMInsight | None = None,
    flaky_signals: list[FlakySignal] | None = None,
    optimization_suggestions: list[OptimizationSuggestion] | None = None,
    new_failures: set[str] | None = None,
    fixed_failures: set[str] | None = None,
) -> str | None:
    body = format_comment(
        analysis, insight, flaky_signals, optimization_suggestions,
        new_failures=new_failures, fixed_failures=fixed_failures,
    )
    existing_id = client.get_existing_comment(pr_number)
    if existing_id:
        return client.update_comment(existing_id, body)
    return client.create_comment(pr_number, body)
