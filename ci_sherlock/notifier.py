import logging
from ci_sherlock.models import AnalysisResult, LLMInsight

logger = logging.getLogger(__name__)


def notify_slack(
    webhook_url: str,
    analysis: AnalysisResult,
    insight: LLMInsight | None,
    pr_url: str | None,
) -> None:
    """Post a concise Slack message. Only called when failed_tests > 0."""
    import httpx

    status_icon = ":x:" if analysis.failed_tests > 0 else ":white_check_mark:"
    summary = (
        f"{status_icon} *{analysis.repo}*"
        + (f" — PR #{analysis.pr_number}" if analysis.pr_number else "")
        + f"\n>{analysis.passed_tests} passed, {analysis.failed_tests} failed, {analysis.skipped_tests} skipped"
    )

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
        }
    ]

    if insight:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Root cause:* {insight.root_cause}\n*Recommendation:* {insight.recommendation}",
            },
        })

    if pr_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View PR"},
                    "url": pr_url,
                }
            ],
        })

    try:
        resp = httpx.post(webhook_url, json={"blocks": blocks}, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Slack notification failed: %s", exc)
