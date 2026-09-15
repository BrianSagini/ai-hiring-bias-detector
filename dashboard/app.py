"""AI Hiring Bias Detector -- Streamlit dashboard.

100% synthetic data (see docs/methodology_hiring_bias.md). This dashboard
is a FAIRNESS AUDIT view -- it never scores, ranks, or recommends a
hire/no-hire decision for any candidate.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from shared.database import get_engine

st.set_page_config(page_title="AI Hiring Bias Detector", layout="wide")
st.title("⚖️ AI Hiring Bias Detector")
st.warning(
    "**100% synthetic data.** No real applicant or employer data is used. Bias is "
    "deliberately injected and exaggerated so the fairness metrics below have clear "
    "signal to detect -- see docs/methodology_hiring_bias.md. This is a fairness "
    "*audit* tool: it does not decide who should be hired.",
    icon="⚠️",
)


@st.cache_data(ttl=300)
def load(query: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(text(query), engine)


try:
    metrics = load("SELECT * FROM hiring_bias.fairness_metrics ORDER BY group_attribute, stage")
    coefs = load("SELECT * FROM hiring_bias.audit_model_coefficients ORDER BY coef_mean DESC")
    candidates = load("SELECT gender, ethnicity, reached_screen, reached_interview, reached_offer, reached_hire FROM hiring_bias.candidates")
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not connect to the analytics database: {exc}")
    st.stop()

if metrics.empty:
    st.warning(
        "No data yet. Trigger the `hiring_bias_pipeline` DAG in Airflow "
        "(http://localhost:8081) and wait for it to complete, then refresh."
    )
    st.stop()

STAGE_ORDER = ["screen", "interview", "offer", "hire"]
metrics["stage"] = pd.Categorical(metrics["stage"], categories=STAGE_ORDER, ordered=True)
metrics = metrics.sort_values("stage")

st.subheader("Funnel overview")
funnel_counts = pd.DataFrame({
    "Stage": ["Applied", "Screened", "Interviewed", "Offered", "Hired"],
    "Count": [
        len(candidates), candidates["reached_screen"].sum(), candidates["reached_interview"].sum(),
        candidates["reached_offer"].sum(), candidates["reached_hire"].sum(),
    ],
})
fig_funnel = px.funnel(funnel_counts, x="Count", y="Stage")
st.plotly_chart(fig_funnel, use_container_width=True)

attribute = st.radio("Group by", options=["gender", "ethnicity"], horizontal=True)
attr_metrics = metrics[metrics["group_attribute"] == attribute]

st.subheader(f"Selection rate by {attribute} and stage")
fig_rate = px.bar(
    attr_metrics, x="stage", y="selection_rate", color="group_value", barmode="group",
    labels={"selection_rate": "Selection rate", "stage": "Funnel stage", "group_value": attribute.title()},
)
st.plotly_chart(fig_rate, use_container_width=True)

st.subheader("4/5ths-rule adverse impact ratio")
st.caption(
    "Ratio of each group's selection rate to the highest selection rate among groups at that "
    "stage. Below the dashed line (0.8) is the traditional EEOC screening threshold for possible "
    "adverse impact -- a statistical heuristic, not a legal determination."
)
fig_air = px.bar(
    attr_metrics, x="stage", y="adverse_impact_ratio", color="group_value", barmode="group",
    labels={"adverse_impact_ratio": "Adverse impact ratio", "stage": "Funnel stage", "group_value": attribute.title()},
)
fig_air.add_hline(y=0.8, line_dash="dash", line_color="red")
st.plotly_chart(fig_air, use_container_width=True)

st.dataframe(
    attr_metrics[["stage", "group_value", "total_at_risk", "passed", "selection_rate", "adverse_impact_ratio"]]
    .rename(columns={"stage": "Stage", "group_value": attribute.title(), "total_at_risk": "Eligible",
                      "passed": "Passed", "selection_rate": "Selection rate", "adverse_impact_ratio": "Adverse impact ratio"})
    .round(3),
    use_container_width=True, hide_index=True,
)

with st.expander("Interpretable audit model coefficients (NOT a hiring decision tool)"):
    st.caption(
        "Logistic regression predicting 'reached hire' from candidate features, with 95% "
        "bootstrap confidence intervals. Reported for interpretability only -- never used to "
        "score or decide on any candidate."
    )
    fig_coef = px.bar(
        coefs, x="coef_mean", y="feature", orientation="h", error_x=coefs["coef_ci_high"] - coefs["coef_mean"],
        error_x_minus=coefs["coef_mean"] - coefs["coef_ci_low"],
        labels={"coef_mean": "Coefficient (standardized)", "feature": "Feature"},
    )
    st.plotly_chart(fig_coef, use_container_width=True)

with st.expander("Methodology & ethical constraints"):
    st.markdown(
        """
        - **All data is synthetic** -- no real candidates. Bias multipliers are deliberately
          exaggerated to produce clear signal (see `docs/methodology_hiring_bias.md`).
        - The 4/5ths rule is a statistical screening heuristic, not a legal determination.
        - This tool **never** scores, ranks, or recommends hire/no-hire decisions for any candidate.
        """
    )
