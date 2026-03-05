import fnmatch
import json as _json
import os
import sys
from typing import List

import typer
from rich.console import Console

app = typer.Typer(name="ci-sherlock", help="AI-powered CI failure investigation.")
console = Console()


@app.command()
def analyze(
    report: List[str] = typer.Option(None, help="Path(s) to test report(s). Repeat for multiple."),
    db: str = typer.Option(None, help="Path to SQLite DB (overrides config)"),
):
    """Analyze test results, correlate with PR diff, post summary comment."""
    from ci_sherlock.config import Config, apply_toml_config
    from ci_sherlock.parsers.playwright import PlaywrightParser
    from ci_sherlock.parsers.jest import JestParser
    from ci_sherlock.db import Database
    from ci_sherlock.github_client import GitHubClient, first_added_line, find_original_in_patch
    from ci_sherlock.analyzer import Analyzer
    from ci_sherlock.commenter import format_comment, post_or_update_comment
    from ci_sherlock.llm_engine import LLMEngine
    from ci_sherlock.optimization import OptimizationEngine
    from ci_sherlock.notifier import notify_slack

    apply_toml_config()
    cfg = Config()

    report_paths = list(report) if report else [cfg.sherlock_report_path]
    db_path = db or cfg.sherlock_db_path

    console.print(f"[bold]CI Sherlock[/bold] — analyzing {len(report_paths)} report(s)")

    # Parse + merge all reports
    all_results = []
    for path in report_paths:
        try:
            with open(path) as f:
                data = _json.load(f)
            parser = JestParser() if "testResults" in data else PlaywrightParser()
        except (FileNotFoundError, _json.JSONDecodeError):
            parser = PlaywrightParser()

        console.print(f"  [cyan]{path}[/cyan] → [bold]{parser.name}[/bold] parser")
        try:
            all_results.extend(parser.parse(path))
        except FileNotFoundError:
            console.print(f"[red]Report not found:[/red] {path}")
            raise typer.Exit(1)

    # Deduplicate if same test appears in multiple reports (keep worst status)
    _STATUS_RANK = {"failed": 0, "flaky": 1, "skipped": 2, "passed": 3}
    seen: dict[tuple, object] = {}
    for r in all_results:
        key = (r.test_name, r.test_file)
        if key not in seen or _STATUS_RANK[r.status] < _STATUS_RANK[seen[key].status]:
            seen[key] = r
    results = list(seen.values())

    # Filter ignored tests
    ignored_patterns = cfg.ignored_test_patterns
    if ignored_patterns:
        before = len(results)
        results = [
            r for r in results
            if not any(fnmatch.fnmatch(r.test_name, p) for p in ignored_patterns)
        ]
        ignored_count = before - len(results)
        if ignored_count:
            console.print(f"  [dim]Ignored {ignored_count} test(s) matching patterns[/dim]")

    console.print(f"  Parsed [bold]{len(results)}[/bold] tests total")

    # Fetch PR diff
    changed_files = []
    client = None
    if cfg.github_token and cfg.repo and cfg.pr_number:
        client = GitHubClient(token=cfg.github_token, repo=cfg.repo)
        changed_files = client.get_pr_files(cfg.pr_number)
        console.print(f"  Fetched [bold]{len(changed_files)}[/bold] changed files from PR #{cfg.pr_number}")
    else:
        console.print("  [yellow]No GitHub token/repo/PR — skipping diff fetch and PR comment[/yellow]")

    # Correlate
    analyzer = Analyzer()
    analysis = analyzer.correlate(
        results=results,
        changed_files=changed_files,
        run_id=cfg.github_run_id or "local",
        repo=cfg.repo or "local",
        pr_number=cfg.pr_number,
        commit_sha=cfg.github_sha or "unknown",
        branch=cfg.branch,
    )

    failed = analysis.failed_tests
    console.print(
        f"  [green]{analysis.passed_tests}[/green] passed  "
        f"[red]{analysis.failed_tests}[/red] failed  "
        f"[yellow]{analysis.skipped_tests}[/yellow] skipped"
    )

    if failed:
        console.print(f"  [bold]{len(analysis.correlations)}[/bold] failure-to-diff correlations found")

    # Write to DB early so fingerprint history is queryable
    database = Database(db_path)
    database.write_run(analysis)
    database.write_results(analysis.run_id, results)
    database.write_correlations(analysis.run_id, analysis.correlations)

    # Fingerprint history
    fingerprints = [r.error_fingerprint for r in analysis.failed_results if r.error_fingerprint]
    fp_counts = database.get_fingerprint_counts(fingerprints) if fingerprints else {}
    recurring = sum(1 for c in fp_counts.values() if c > 0)
    if recurring:
        console.print(f"  [dim]{recurring} failure(s) seen in previous runs[/dim]")

    # Delta vs previous run for this PR
    new_failures: set[str] | None = None
    fixed_failures: set[str] | None = None
    if cfg.pr_number:
        prev_failed = database.get_previous_run_failures(cfg.pr_number, analysis.run_id)
        if prev_failed:
            current_failed = {r.test_name for r in analysis.failed_results}
            new_failures = current_failed - prev_failed
            fixed_failures = prev_failed - current_failed
            console.print(
                f"  Delta vs last run: [red]+{len(new_failures)} new[/red]  "
                f"[green]{len(fixed_failures)} fixed[/green]"
            )

    # LLM analysis
    insight = None
    if cfg.openai_api_key and analysis.failed_tests > 0:
        console.print("  Running LLM root cause analysis...")
        engine = LLMEngine.from_api_key(cfg.openai_api_key, model=cfg.sherlock_model)
        insight = engine.analyze(analysis, fingerprint_counts=fp_counts)
        if insight:
            console.print(f"  Root cause: [italic]{insight.root_cause[:80]}[/italic] ({int(insight.confidence * 100)}% confidence)")
        else:
            console.print("  [yellow]LLM analysis unavailable — posting raw analysis[/yellow]")
    elif not cfg.openai_api_key:
        console.print("  [yellow]OPENAI_API_KEY not set — skipping LLM analysis[/yellow]")

    # Flaky detection
    flaky_signals = analyzer.detect_flaky_current(results)
    flaky_rows = []
    try:
        flaky_rows = database.get_flaky_tests(threshold=cfg.sherlock_flaky_threshold)
    except Exception:
        pass
    flaky_signals += analyzer.detect_flaky_historical(flaky_rows, threshold=cfg.sherlock_flaky_threshold)
    if flaky_signals:
        console.print(f"  [yellow]{len(flaky_signals)}[/yellow] flaky test(s) detected")

    # Optimization signals
    opt_engine = OptimizationEngine(slow_test_ms=cfg.sherlock_slow_test_ms)
    suggestions = opt_engine.analyze(results)
    suggestions += opt_engine.check_missing_cache()
    if suggestions:
        console.print(f"  [yellow]{len(suggestions)}[/yellow] optimization suggestion(s)")

    # Persist insight
    if insight:
        database.write_insight(analysis.run_id, insight, model=cfg.sherlock_model)
    console.print(f"  Results written to [cyan]{db_path}[/cyan]")

    # GitHub Checks API
    if client and cfg.github_sha:
        conclusion = "failure" if analysis.failed_tests > 0 else "success"
        check_title = (
            f"{analysis.failed_tests} test(s) failed"
            if analysis.failed_tests > 0
            else f"All {analysis.passed_tests} tests passed"
        )
        check_summary = (
            f"{analysis.passed_tests} passed · {analysis.failed_tests} failed · {analysis.skipped_tests} skipped"
        )
        if insight:
            check_summary += f"\n\n**Root cause:** {insight.root_cause}"
        try:
            client.create_check_run(
                head_sha=cfg.github_sha,
                conclusion=conclusion,
                title=check_title,
                summary=check_summary,
            )
            console.print("  GitHub Check Run created")
        except Exception as exc:
            console.print(f"  [dim]Check Run skipped: {exc}[/dim]")

    # Inline review comments on direct_match correlations
    if client and cfg.pr_number and cfg.github_sha and analysis.correlations:
        review_comments = []
        direct = [c for c in analysis.correlations if c.reason == "direct_match"]
        for corr in direct[:5]:  # cap to avoid noise
            cf = next((f for f in analysis.changed_files if f.filename == corr.changed_file), None)
            patch = cf.patch if cf else None

            # Check if LLM produced a suggested fix targeting this file
            fix_for_this_file = (
                insight
                and insight.suggested_fix
                and insight.suggested_fix_file == corr.changed_file
            )

            if fix_for_this_file:
                # Find the exact line the fix applies to.
                # If suggested_fix_original was provided, only post when we can
                # locate the right line — wrong-line suggestions are worse than none.
                if insight.suggested_fix_original:
                    line = find_original_in_patch(patch, insight.suggested_fix_original)
                else:
                    line = first_added_line(patch)
                if line is None:
                    # Could not locate target line — skip inline suggestion
                    line = None
                    body = None
                else:
                    body = (
                        f"**CI Sherlock proposed fix** — test `{corr.test_name}` failed here.\n\n"
                        f"```suggestion\n{insight.suggested_fix}\n```"
                    )
            else:
                line = first_added_line(patch)
                body = (
                    f"**CI Sherlock:** test `{corr.test_name}` failed and correlates directly with this file.\n\n"
                    f"> error in `{corr.test_file}`"
                )

            if line is not None and body is not None:
                review_comments.append({"path": corr.changed_file, "line": line, "body": body})

        if review_comments:
            try:
                client.create_pull_review(cfg.pr_number, cfg.github_sha, review_comments)
                fix_posted = any(
                    insight and insight.suggested_fix and insight.suggested_fix_file == c["path"]
                    for c in review_comments
                )
                label = "proposed fix" if fix_posted else "inline review comment(s)"
                console.print(f"  {len(review_comments)} {label} posted")
            except Exception as exc:
                console.print(f"  [dim]Inline review skipped: {exc}[/dim]")

    # Post PR comment
    comment_url = None
    if client and cfg.pr_number:
        comment_url = post_or_update_comment(
            client, cfg.pr_number, analysis, insight, flaky_signals, suggestions,
            new_failures=new_failures, fixed_failures=fixed_failures,
        )
        if comment_url:
            console.print(f"  PR comment posted: [link]{comment_url}[/link]")

    # GitHub Actions step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        comment_body = format_comment(
            analysis, insight, flaky_signals, suggestions,
            new_failures=new_failures, fixed_failures=fixed_failures,
        )
        with open(summary_path, "a") as _sf:
            _sf.write(comment_body)
        console.print("  Step summary written to GITHUB_STEP_SUMMARY")

    # Slack notification (only on failures)
    if cfg.sherlock_slack_webhook and analysis.failed_tests > 0:
        notify_slack(cfg.sherlock_slack_webhook, analysis, insight, pr_url=comment_url)
        console.print("  Slack notification sent")

    # Exit with failure code if tests failed
    if analysis.failed_tests > 0:
        raise typer.Exit(1)


@app.command()
def dashboard(
    db: str = typer.Option(None, help="Path to SQLite DB (overrides config)"),
):
    """Launch the Streamlit dashboard."""
    import subprocess
    from ci_sherlock.config import Config

    cfg = Config()
    db_path = db or cfg.sherlock_db_path

    env = os.environ.copy()
    env["SHERLOCK_DB_PATH"] = db_path

    import importlib.util
    app_path = importlib.util.find_spec("ci_sherlock.dashboard.app").origin
    subprocess.run(
        ["streamlit", "run", app_path],
        env=env,
        check=True,
    )


if __name__ == "__main__":
    app()
