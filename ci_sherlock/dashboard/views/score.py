import streamlit as st
from ci_sherlock.scoring import ReadinessScore


def render(score: ReadinessScore) -> None:
    st.subheader("Release Readiness Score")

    if score.insufficient_data:
        st.warning("Not enough run history to compute a score (minimum 3 runs required).")
        return

    # Score gauge using metric + progress
    colour = "green" if score.score >= 80 else "orange" if score.score >= 60 else "red"
    label = "Ready" if score.score >= 80 else "Needs attention" if score.score >= 60 else "Not ready"

    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric(label="Score", value=f"{score.score} / 100", delta=label)
        st.progress(score.score / 100)

    with col2:
        st.markdown("**Factor breakdown**")
        for factor in score.factors:
            factor_pct = int(factor.score * 100)
            st.markdown(f"**{factor.name}** — {factor_pct}% _(weight {int(factor.weight * 100)}%)_")
            st.progress(factor.score)
            st.caption(factor.detail)
