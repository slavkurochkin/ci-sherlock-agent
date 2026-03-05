import os
import sys
import typer
from rich.console import Console

app = typer.Typer(name="ci-sherlock", help="AI-powered CI failure investigation.")
console = Console()


@app.command()
def analyze(
    report: str = typer.Option(None, help="Path to test report (overrides config)"),
    db: str = typer.Option(None, help="Path to SQLite DB (overrides config)"),
):
    """Analyze test results, correlate with PR diff, post summary comment."""
    from ci_sherlock.config import Config
    from ci_sherlock.parsers.playwright import PlaywrightParser
    from ci_sherlock.parsers.jest import JestParser
    from ci_sherlock.db import Database
    from ci_sherlock.github_client import GitHubClient
    from ci_sherlock.analyzer import Analyzer
    from ci_sherlock.commenter import format_comment, post_or_update_comment
    from ci_sherlock.llm_engine import LLMEngine
    from ci_sherlock.optimization import OptimizationEngine
    from ci_sherlock.notifier import notify_slack

    cfg = Config()
    report_path = report or cfg.sherlock_report_path
    db_path = db or cfg.sherlock_db_path

    console.print(f"[bold]CI Sherlock[/bold] — analyzing [cyan]{report_path}[/cyan]")

    # Detect parser
    import json as _json
    try:
        with open(report_path) as _f:
            _data = _json.load(_f)
        parser = JestParser() if "testResults" in _data else PlaywrightParser()
    except (FileNotFoundError, _json.JSONDecodeError):
        parser = PlaywrightParser()

    console.print(f"  Using [bold]{parser.name}[/bold] parser")

    try:
        results = parser.parse(report_path)
    except FileNotFoundError:
        console.print(f"[red]Report not found:[/red] {report_path}")
        raise typer.Exit(1)

    console.print(f"  Parsed [bold]{len(results)}[/bold] tests")

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

    # LLM analysis
    insight = None
    if cfg.openai_api_key and analysis.failed_tests > 0:
        console.print("  Running LLM root cause analysis...")
        engine = LLMEngine.from_api_key(cfg.openai_api_key, model=cfg.sherlock_model)
        insight = engine.analyze(analysis)
        if insight:
            console.print(f"  Root cause: [italic]{insight.root_cause[:80]}[/italic] ({int(insight.confidence * 100)}% confidence)")
        else:
            console.print("  [yellow]LLM analysis unavailable — posting raw analysis[/yellow]")
    elif not cfg.openai_api_key:
        console.print("  [yellow]OPENAI_API_KEY not set — skipping LLM analysis[/yellow]")

    # Flaky detection (Phase 3)
    flaky_signals = analyzer.detect_flaky_current(results)
    flaky_rows = []
    try:
        # Historical flaky needs existing DB — best-effort
        tmp_db = Database(db_path)
        flaky_rows = tmp_db.get_flaky_tests()
    except Exception:
        pass
    flaky_signals += analyzer.detect_flaky_historical(flaky_rows)
    if flaky_signals:
        console.print(f"  [yellow]{len(flaky_signals)}[/yellow] flaky test(s) detected")

    # Optimization signals (Phase 3)
    opt_engine = OptimizationEngine()
    suggestions = opt_engine.analyze(results)
    suggestions += opt_engine.check_missing_cache()
    if suggestions:
        console.print(f"  [yellow]{len(suggestions)}[/yellow] optimization suggestion(s)")

    # Write to DB
    database = Database(db_path)
    database.write_run(analysis)
    database.write_results(analysis.run_id, results)
    database.write_correlations(analysis.run_id, analysis.correlations)
    if insight:
        database.write_insight(analysis.run_id, insight, model=cfg.sherlock_model)
    console.print(f"  Results written to [cyan]{db_path}[/cyan]")

    # Post PR comment
    comment_url = None
    if client and cfg.pr_number:
        comment_url = post_or_update_comment(client, cfg.pr_number, analysis, insight, flaky_signals, suggestions)
        if comment_url:
            console.print(f"  PR comment posted: [link]{comment_url}[/link]")

    # GitHub Actions step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        comment_body = format_comment(analysis, insight, flaky_signals, suggestions)
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
    import os
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
