from ci_sherlock.models import AnalysisResult, LLMInsight, FlakySignal, OptimizationSuggestion
from ci_sherlock.github_client import GitHubClient, COMMENT_MARKER


def format_comment(
    analysis: AnalysisResult,
    insight: LLMInsight | None = None,
    flaky_signals: list[FlakySignal] | None = None,
    optimization_suggestions: list[OptimizationSuggestion] | None = None,
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
        lines += ["### Failures", ""]
        for test in analysis.failed_results[:10]:
            lines.append(f"- **{test.test_name}** `{test.test_file}`")
            if test.error_message:
                msg = test.error_message[:200].replace("\n", " ")
                lines.append(f"  ```\n  {msg}\n  ```")
        if len(analysis.failed_results) > 10:
            lines.append(f"- _…and {len(analysis.failed_results) - 10} more_")
        lines.append("")

    # Correlation section
    if analysis.correlations:
        lines += ["### Failure → Diff Correlation", ""]
        lines.append("| Test | Changed file | Signal | Score |")
        lines.append("|---|---|---|---|")
        for c in sorted(analysis.correlations, key=lambda x: -x.score)[:10]:
            lines.append(
                f"| `{c.test_name}` | `{c.changed_file}` | {c.reason} | {c.score:.1f} |"
            )
        lines.append("")

    if analysis.unmatched_failures:
        lines += [
            "### Unmatched Failures",
            "_These failures have no correlation to changed files — possibly environmental or flaky._",
            "",
            *[f"- `{t.test_name}` ({t.test_file})" for t in analysis.unmatched_failures[:5]],
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
        lines += ["### CI Optimization", ""]
        for s in optimization_suggestions:
            icon = impact_icon.get(s.impact, "•")
            lines.append(f"- {icon} {s.description}")
        lines.append("")

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
) -> str | None:
    body = format_comment(analysis, insight, flaky_signals, optimization_suggestions)
    existing_id = client.get_existing_comment(pr_number)
    if existing_id:
        return client.update_comment(existing_id, body)
    return client.create_comment(pr_number, body)
