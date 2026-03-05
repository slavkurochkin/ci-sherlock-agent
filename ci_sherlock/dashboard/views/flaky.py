import streamlit as st
import pandas as pd


def render(db) -> None:
    st.subheader("Flaky Test Leaderboard")

    rows = db.get_flaky_tests(last_n_runs=30, threshold=0.0)  # all tests with any failures
    if not rows:
        st.success("No flaky tests detected in the last 30 runs.")
        return

    df = pd.DataFrame(rows, columns=["test_name", "test_file", "total_runs", "failures", "failure_rate"])
    df["failure_rate_pct"] = (df["failure_rate"] * 100).round(1)
    df = df.sort_values("failure_rate", ascending=False)

    # Highlight high failure rate
    def highlight(val):
        if val >= 20:
            return "background-color: #fecaca"
        if val >= 10:
            return "background-color: #fef08a"
        return ""

    st.dataframe(
        df[["test_name", "test_file", "total_runs", "failures", "failure_rate_pct"]]
        .rename(columns={"failure_rate_pct": "failure rate (%)"}),
        use_container_width=True,
        hide_index=True,
    )
