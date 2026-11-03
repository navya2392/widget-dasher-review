"""app.py — Streamlit review app for the widget Dasher program.

No logic lives here: pipeline.py computes, ai.py interprets and explains, a human approves.
Every count, tier size and tier-change list on screen is rendered from pipeline output; the AI
text is commentary shown below those numbers, never their source.

Run:  streamlit run app.py
"""
import datetime as dt
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import ai
import pipeline

DEMO_XLSX = Path("data/2026_Platform_Ops_Widget_Data.xlsx")
DEMO_PRIOR = Path("demo/prior_scorecard.csv")
APPROVED_PATH = Path("approved_tiers.csv")
SCORECARD_VIEW = ["DASHER", "asap_n", "ontime_adj", "shrunk_rating", "severe_late_rate", "arrival_logged",
                  "pts_reliability", "pts_quality", "pts_consistency", "pts_professionalism", "selection_score", "tier", "fraud_review"]


def ensure_api_key() -> None:
    """Env var (from .env via python-dotenv in ai.py) first; st.secrets as the Streamlit Cloud fallback."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    try:
        key = st.secrets["ANTHROPIC_API_KEY"]
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
    except Exception:
        pass


def run_everything(raw: pd.DataFrame, prior: pd.DataFrame | None, source: str) -> dict:
    """One pipeline run plus at most one call per AI function. Stored in session state so reruns don't re-call."""
    result = pipeline.run_raw(raw)
    ensure_api_key()
    qa = ai.qa_summary(result["profile"])
    qa_error = ai.last_error
    briefing = briefing_error = None
    diff = pipeline.diff(result["scorecard"], prior)
    if prior is not None:
        qa_note = qa.splitlines()[-1] if qa else None
        briefing = ai.briefing(result["scorecard"], prior, qa_note=qa_note)
        briefing_error = ai.last_error
    return {**result, "prior": prior, "diff": diff, "qa": qa, "qa_error": qa_error,
            "briefing": briefing, "briefing_error": briefing_error, "source": source,
            "ran_at": dt.datetime.now().isoformat(timespec="seconds")}


def profile_facts(p: dict) -> pd.DataFrame:
    rows = [
        ("rows after cleaning", p["rows"]),
        ("rows per city", ", ".join(f"{k} {v}" for k, v in p["rows_per_city"].items())),
        ("Dashers per city", ", ".join(f"{k} {v}" for k, v in p["dashers_per_city"].items())),
        ("date window per city", "; ".join(f"{k} {v['first']} to {v['last']} ({v['days']} days)" for k, v in p["date_window_per_city"].items())),
        ("ASAP / scheduled rows", f"{p['asap_rows']} / {p['scheduled_rows']}"),
        ("missing wait", f"{p['missing_wait']['total']} rows: {p['missing_wait']['no_arrival_logged']} no arrival logged, "
                         f"{p['missing_wait']['arrival_after_pickup']} arrival after pickup"),
        ("schema vs expected", f"{p['schema']['actual_raw_columns']} of {p['schema']['expected_columns']} columns; "
                               f"missing {p['schema']['missing_vs_expected'] or 'none'}; unexpected {p['schema']['unexpected'] or 'none'}"),
        ("duplicate DELIVERY_NAME", p["duplicates"]["DELIVERY_NAME_duplicates"]),
        ("anomaly rows", f"delivered before pickup {p['anomaly_rows']['delivered_before_pickup']}; estimate after quote "
                         f"{p['anomaly_rows']['estimate_after_quote']}; duration mismatch {p['anomaly_rows']['confirm_to_deliver_duration_mismatch']}; "
                         f"arrival before confirmation {p['anomaly_rows']['arrival_before_confirmation_n']} rows"),
        ("fraud-flagged rows", p["fraud_flagged_rows"]),
        ("standing exclusions", ", ".join(p["standing_exclusions"])),
    ]
    return pd.DataFrame(rows, columns=["fact", "value"]).set_index("fact")


def highlight_tier1(row):
    return ["background-color: #d9f2d9" if row["tier"] == "Tier 1" else "" for _ in row]


def ai_panel(label: str, text: str | None, error: str | None) -> None:
    with st.expander(label):
        if text:
            st.markdown(text)
        else:
            st.warning(f"AI unavailable — pipeline results below. ({error})")


# ----------------------------------------------------------------------------- page
st.set_page_config(page_title="Widget Dasher Review", layout="wide")
st.title("Widget Dasher Review")
st.caption("AI interprets and explains; code computes; a human approves.")

upload = st.file_uploader("Deliveries workbook (.xlsx)", type=["xlsx"])
prior_upload = st.file_uploader("Prior run scorecard (.csv, optional)", type=["csv"])
col_run, col_demo = st.columns(2)
if col_run.button("Run", disabled=upload is None):
    prior = pd.read_csv(prior_upload) if prior_upload is not None else (pd.read_csv(DEMO_PRIOR) if DEMO_PRIOR.exists() else None)
    with st.spinner("Running pipeline and AI stages..."):
        st.session_state["run"] = run_everything(pd.read_excel(upload), prior, source=upload.name)
if col_demo.button("Run with demo data"):
    with st.spinner("Running pipeline and AI stages on the case data..."):
        st.session_state["run"] = run_everything(pd.read_excel(DEMO_XLSX), pd.read_csv(DEMO_PRIOR) if DEMO_PRIOR.exists() else None,
                                                 source=f"demo: {DEMO_XLSX.name}")

run = st.session_state.get("run")
if run is None:
    st.info("Upload a workbook and press Run, or press Run with demo data.")
    st.stop()

st.caption(f"Source: {run['source']} · ran {run['ran_at']}")

# ----------------------------------------------------------------------------- data check
st.header("Data check")
st.table(profile_facts(run["profile"]))
with st.expander("Cleaning log"):
    for line in run["cleaning_log"]:
        st.markdown(f"- {line}")
ai_panel("AI read of the data", run["qa"], run["qa_error"])

# ----------------------------------------------------------------------------- scorecard
st.header("Scorecard")
scorecard = run["scorecard"]
tabs = st.tabs(list(pipeline.TIER1_SIZE))
for tab, market in zip(tabs, pipeline.TIER1_SIZE):
    with tab:
        passers = (scorecard[(scorecard["MARKET_NAME"] == market) & scorecard["passes_gates"]]
                   .sort_values("selection_score", ascending=False)[SCORECARD_VIEW].reset_index(drop=True))
        n_t1 = int((passers["tier"] == "Tier 1").sum())
        st.write(f"{len(passers)} gate-passers · Tier 1 = {n_t1} (top {pipeline.TIER1_SIZE[market]}) · "
                 f"fraud review: {int(passers['fraud_review'].sum())}")
        st.dataframe(passers.style.apply(highlight_tier1, axis=1).format(precision=3), use_container_width=True)
        cohort = pipeline.bike_cohort(scorecard)
        cohort = cohort[cohort["MARKET_NAME"] == market]
        if len(cohort):
            with st.expander(f"Conditional bike cohort — {market} (display only; fails only the vehicle gate)"):
                st.dataframe(cohort[["DASHER", "vehicles", "lifetime_deliveries", "asap_n", "ontime_adj", "shrunk_rating",
                                     "selection_score", "fraud_review", "top_4"]].style.format(precision=3), use_container_width=True)

# ----------------------------------------------------------------------------- changes vs prior
if run["prior"] is not None:
    st.header("Changes vs prior run")
    d = run["diff"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Gate-passers now", ", ".join(f"{k} {v}" for k, v in d["gate_passers_now"].items()))
    m2.metric("Tier 1 now", ", ".join(f"{k} {len(v)}" for k, v in d["tier1_now"].items()))
    m3.metric("Tier changes", len(d["tier_changes"]))
    st.subheader("Tier changes (recommendations pending approval)")
    st.dataframe(pd.DataFrame(d["tier_changes"]) if d["tier_changes"] else pd.DataFrame({"tier changes": ["none"]}), use_container_width=True)
    st.subheader("Largest score movers")
    st.dataframe(pd.DataFrame(d["score_movers"]), use_container_width=True)
    if d["new_dashers"] or d["dropped_dashers"]:
        st.write("New:", d["new_dashers"] or "none", " · Dropped:", d["dropped_dashers"] or "none")
    ai_panel("AI briefing", run["briefing"], run["briefing_error"])

# ----------------------------------------------------------------------------- approve
st.header("Approve")
if st.button("Approve tier changes"):
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    tiers = scorecard.loc[scorecard["passes_gates"], ["MARKET_NAME", "DASHER", "selection_score", "tier", "fraud_review"]].copy()
    tiers["approved_at"] = stamp
    tiers["approved_by"] = "operator"
    with APPROVED_PATH.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"# approved by operator at {stamp}; source {run['source']}\n")
        tiers.to_csv(fh, index=False)
    st.session_state["approved"] = (stamp, len(tiers))
if "approved" in st.session_state:
    stamp, n = st.session_state["approved"]
    st.success(f"Approved {n} tier assignments at {stamp} — written to {APPROVED_PATH}")
