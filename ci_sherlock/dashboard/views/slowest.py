import streamlit as st
import pandas as pd


def render(db) -> None:
    st.subheader("Slowest Tests (avg duration)")

    rows = db._db.execute("""
        SELECT
            test_name,
            test_file,
            COUNT(*) AS runs,
            ROUND(AVG(duration_ms)) AS avg_duration_ms,
            ROUND(MAX(duration_ms)) AS max_duration_ms
        FROM test_results
        WHERE status IN ('passed', 'failed', 'flaky')
        GROUP BY test_name, test_file
        ORDER BY avg_duration_ms DESC
        LIMIT 15
    """).fetchall()

    if not rows:
        st.info("No test duration data yet.")
        return

    df = pd.DataFrame(rows, columns=["test_name", "test_file", "runs", "avg_duration_ms", "max_duration_ms"])
    df["avg_s"] = (df["avg_duration_ms"] / 1000).round(2)
    df["max_s"] = (df["max_duration_ms"] / 1000).round(2)

    st.bar_chart(df.set_index("test_name")["avg_s"], color="#6366f1")

    st.dataframe(
        df[["test_name", "test_file", "runs", "avg_s", "max_s"]]
        .rename(columns={"avg_s": "avg (s)", "max_s": "max (s)"}),
        use_container_width=True,
        hide_index=True,
    )
