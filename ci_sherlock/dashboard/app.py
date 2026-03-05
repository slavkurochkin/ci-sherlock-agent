import os
import streamlit as st
from ci_sherlock.db import Database
from ci_sherlock.scoring import compute_release_readiness
from ci_sherlock.dashboard.views import run_history, flaky, slowest, score as score_view

DB_PATH = os.environ.get("SHERLOCK_DB_PATH", ".ci-sherlock/history.db")

st.set_page_config(
    page_title="CI Sherlock",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 CI Sherlock Dashboard")

try:
    db = Database(DB_PATH)
except Exception as e:
    st.error(f"Could not open database at `{DB_PATH}`: {e}")
    st.stop()

runs = db.get_runs(limit=50)

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    st.caption(f"DB: `{DB_PATH}`")
    st.metric("Total runs", len(runs))
    if runs:
        passed = sum(1 for r in runs if r[5] == "passed")
        st.metric("Pass rate", f"{passed / len(runs):.0%}")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["Run History", "Flaky Tests", "Slowest Tests", "Release Readiness"])

with tab1:
    run_history.render(runs)

with tab2:
    flaky.render(db)

with tab3:
    slowest.render(db)

with tab4:
    if runs:
        all_results = []
        for run in runs:
            all_results.extend(db.get_test_results(run[0]))
        readiness = compute_release_readiness(
            [dict(zip(["id", "repo", "pr_number", "commit_sha", "branch", "status",
                       "total_tests", "passed_tests", "failed_tests", "skipped_tests",
                       "duration_ms", "release_readiness_score", "created_at"], r)) for r in runs],
            [dict(zip(["id", "run_id", "test_name", "test_file", "status",
                       "duration_ms", "retry_count", "error_message", "error_stack", "trace_path"], r))
             for r in all_results],
        )
        score_view.render(readiness)
    else:
        st.info("No runs yet.")
