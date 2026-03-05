import streamlit as st
import pandas as pd


def render(runs: list[dict]) -> None:
    st.subheader("Run History")

    if not runs:
        st.info("No runs recorded yet.")
        return

    df = pd.DataFrame(runs, columns=["id", "repo", "pr_number", "commit_sha", "branch",
                                      "status", "total_tests", "passed_tests", "failed_tests",
                                      "skipped_tests", "duration_ms", "release_readiness_score",
                                      "created_at"])

    df["created_at"] = pd.to_datetime(df["created_at"])
    df["duration_s"] = (df["duration_ms"] / 1000).round(1)
    df["pass_rate"] = (df["passed_tests"] / df["total_tests"].replace(0, 1) * 100).round(1)

    # Status colour map
    status_icon = df["status"].map({"passed": "✅", "failed": "❌", "partial": "⚠️"}).fillna("❓")
    df.insert(0, "", status_icon)

    st.dataframe(
        df[["", "created_at", "branch", "pr_number", "total_tests",
            "passed_tests", "failed_tests", "pass_rate", "duration_s"]],
        use_container_width=True,
        hide_index=True,
    )

    # Timeline chart
    st.line_chart(
        df.set_index("created_at")[["passed_tests", "failed_tests"]].sort_index(),
        color=["#22c55e", "#ef4444"],
    )
