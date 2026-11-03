"""app.py — Streamlit review app for the widget Dasher program.

No logic lives here: pipeline.py computes, ai.py interprets and explains, a human approves.
Every count, tier size and tier-change list on screen is rendered from pipeline output; the AI
text is commentary shown below those numbers, never their source. The operator may override any
gate-passer's tier before approving; every override is recorded next to the recommendation.

Run:  streamlit run app.py
"""
import datetime as dt
import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import ai
import pipeline

DEMO_XLSX = Path("data/2026_Platform_Ops_Widget_Data.xlsx")
DEMO_PRIOR = Path("demo/prior_scorecard.csv")
APPROVED_PATH = Path("approved_tiers.csv")
OVERRIDES_PATH = Path("approved_overrides.csv")
MARKETS = list(pipeline.TIER1_SIZE)
COMPACT_COLUMNS = ["Dasher", "Score", "Recommended", "Tier", "Review"]
COMPONENT_COLUMNS = {"Reliability /50": "pts_reliability", "Quality /30": "pts_quality",
                     "Consistency /10": "pts_consistency", "Professionalism /10": "pts_professionalism"}
INPUT_COLUMNS = {"On-time adj %": ("ontime_adj", 100), "Rating": ("shrunk_rating", 1),
                 "Severe %": ("severe_late_rate", 100), "Logged %": ("arrival_logged", 100)}


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


@st.cache_data(show_spinner=False)
def cached_run(raw_bytes: bytes, prior_bytes: bytes | None, source: str) -> dict:
    """One pipeline run plus at most one call per AI function, cached on the input bytes: the first session to
    run a given workbook pays once per server process; every later session (and every rerun) gets it instantly."""
    raw = pd.read_excel(io.BytesIO(raw_bytes))
    prior = pd.read_csv(io.BytesIO(prior_bytes)) if prior_bytes else None
    result = pipeline.run_raw(raw)
    ensure_api_key()
    qa = ai.qa_summary(result["profile"])
    qa_error = ai.last_error
    briefing = briefing_error = None
    diff = pipeline.diff(result["scorecard"], prior)
    if prior is not None:
        verdict = [line for line in (qa or "").splitlines() if "VERDICT" in line]
        qa_note = verdict[-1] if verdict else ("QA report truncated before its verdict" if qa else None)
        briefing = ai.briefing(result["scorecard"], prior, qa_note=qa_note)
        briefing_error = ai.last_error
    return {**result, "prior": prior, "diff": diff, "qa": qa, "qa_error": qa_error,
            "briefing": briefing, "briefing_error": briefing_error, "source": source,
            "ran_at": dt.datetime.now().isoformat(timespec="seconds")}


def run_everything(raw_bytes: bytes, prior_bytes: bytes | None, source: str) -> dict:
    """Session-side wrapper: resets any operator overrides, then returns the (cached) run."""
    for market in MARKETS:
        st.session_state.pop(f"tier_override_{market}", None)
        st.session_state.pop(f"edited_{market}", None)
    st.session_state.pop("approved", None)
    return cached_run(raw_bytes, prior_bytes, source)


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
    return pd.DataFrame(rows, columns=["fact", "value"]).astype({"value": str}).set_index("fact")   # one dtype: Arrow-clean


def ai_panel(label: str, text: str | None, error: str | None) -> None:
    with st.expander(label):
        if text:
            st.markdown(text)
        else:
            st.warning(f"AI unavailable — pipeline results below. ({error})")


def scorecard_view(scorecard: pd.DataFrame, market: str, show_components: bool) -> pd.DataFrame:
    """Friendly-named view of one market's gate-passers; Tier starts from the recommendation or the operator's edit."""
    passers = (scorecard[(scorecard["MARKET_NAME"] == market) & scorecard["passes_gates"]]
               .sort_values("selection_score", ascending=False))
    overrides = st.session_state.get(f"tier_override_{market}", {})
    view = pd.DataFrame({
        "Dasher": passers["DASHER"].values,
        "Score": passers["selection_score"].round(1).values,
        "Recommended": passers["tier"].values,
        "Tier": [overrides.get(d, t) for d, t in zip(passers["DASHER"], passers["tier"])],
        "Review": ["✓" if f else "" for f in passers["fraud_review"]],
    })
    if show_components:
        for label, col in COMPONENT_COLUMNS.items():
            view[label] = passers[col].round(1).values
        for label, (col, mult) in INPUT_COLUMNS.items():
            view[label] = (passers[col] * mult).round(1).values
    return view


def render_market(scorecard: pd.DataFrame, market: str) -> None:
    st.subheader(market)
    passers = scorecard[(scorecard["MARKET_NAME"] == market) & scorecard["passes_gates"]]
    m1, m2, m3 = st.columns(3)
    m1.metric("Gate-passers", int(len(passers)))
    m2.metric("Tier 1", int((passers["tier"] == "Tier 1").sum()))
    m3.metric("Fraud reviews", int(passers["fraud_review"].sum()))
    show = st.session_state.get(f"components_{market}", False)
    view = scorecard_view(scorecard, market, show)
    config = {
        "Dasher": st.column_config.TextColumn("Dasher"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        "Recommended": st.column_config.TextColumn("Recommended", help="Pipeline tier (read-only)"),
        "Tier": st.column_config.SelectboxColumn("Tier", options=pipeline.TIER_OPTIONS, required=True,
                                                 help="Operator's decision — change to override"),
        "Review": st.column_config.TextColumn("Review", help="✓ = fraud flag in sample, manual review"),
    }
    for label in list(COMPONENT_COLUMNS) + list(INPUT_COLUMNS):
        config[label] = st.column_config.NumberColumn(label, format="%.1f")
    edited = st.data_editor(view, column_config=config, disabled=[c for c in view.columns if c != "Tier"],
                            hide_index=True, width="stretch",
                            height=35 * (len(view) + 1) + 3,          # show every gate-passer without an inner scrollbar
                            key=f"editor_{market}_{'full' if show else 'compact'}")
    st.session_state[f"tier_override_{market}"] = dict(zip(edited["Dasher"], edited["Tier"]))
    st.session_state[f"edited_{market}"] = edited[COMPACT_COLUMNS].assign(MARKET_NAME=market)
    st.toggle("Show score components", key=f"components_{market}")


def approve(source: str) -> None:
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    frames = [st.session_state[f"edited_{m}"] for m in MARKETS if f"edited_{m}" in st.session_state]
    approved, overrides = pipeline.approval_records(pd.concat(frames, ignore_index=True), stamp, "operator")
    with APPROVED_PATH.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"# approved by operator at {stamp}; source {source}; overrides {len(overrides)}\n")
        approved.to_csv(fh, index=False)
    with OVERRIDES_PATH.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"# operator overrides at {stamp}; source {source}\n")
        overrides.to_csv(fh, index=False)
    st.session_state["approved"] = (stamp, len(approved), len(overrides))


# ----------------------------------------------------------------------------- page
st.set_page_config(page_title="Widget Dasher Review", layout="wide")
st.title("Widget Dasher Review")
st.caption("AI interprets and explains; code computes; a human approves.")

upload = st.file_uploader("Deliveries workbook (.xlsx)", type=["xlsx"])
prior_upload = st.file_uploader("Prior run scorecard (.csv, optional)", type=["csv"])
col_run, col_demo = st.columns(2)
demo_prior_bytes = DEMO_PRIOR.read_bytes() if DEMO_PRIOR.exists() else None
if col_run.button("Run", disabled=upload is None):
    prior_bytes = prior_upload.getvalue() if prior_upload is not None else demo_prior_bytes
    with st.spinner("Running pipeline and AI stages..."):
        st.session_state["run"] = run_everything(upload.getvalue(), prior_bytes, source=upload.name)
if col_demo.button("Run with demo data"):
    with st.spinner("Running pipeline and AI stages on the case data (cached after the first run)..."):
        st.session_state["run"] = run_everything(DEMO_XLSX.read_bytes(), demo_prior_bytes, source=f"demo: {DEMO_XLSX.name}")

run = st.session_state.get("run")
if run is None:
    st.info("Upload a workbook and press Run, or press Run with demo data.")
    st.stop()

st.caption(f"Source: {run['source']} · ran {run['ran_at']}")
scorecard = run["scorecard"]
tab_score, tab_data, tab_changes = st.tabs(["Scorecard", "Data check", "Changes vs prior run"])

# ----------------------------------------------------------------------------- scorecard (first)
with tab_score:
    left, right = st.columns(2)
    with left:
        render_market(scorecard, "Dashattan")
        cohort = pipeline.bike_cohort(scorecard)
        cohort = cohort[cohort["MARKET_NAME"] == "Dashattan"]
        if len(cohort):
            with st.expander("Conditional bike cohort — Dashattan (display only; fails only the vehicle gate)"):
                st.dataframe(cohort[["DASHER", "vehicles", "lifetime_deliveries", "asap_n", "ontime_adj", "shrunk_rating",
                                     "selection_score", "fraud_review", "top_4"]].round(3), hide_index=True, width="stretch")
    with right:
        render_market(scorecard, "Doorlanta")
    st.write("")
    _, mid, _ = st.columns([2, 1, 2])
    if mid.button("Approve tier changes", width="stretch"):
        approve(run["source"])
    if "approved" in st.session_state:
        stamp, n, m = st.session_state["approved"]
        st.success(f"Approved {n} assignments, {m} overrides — written to {APPROVED_PATH} and {OVERRIDES_PATH} at {stamp}")

# ----------------------------------------------------------------------------- data check
with tab_data:
    st.table(profile_facts(run["profile"]))
    with st.expander("Cleaning log"):
        for line in run["cleaning_log"]:
            st.markdown(f"- {line}")
    ai_panel("AI read of the data", run["qa"], run["qa_error"])

# ----------------------------------------------------------------------------- changes vs prior
with tab_changes:
    if run["prior"] is None:
        st.info("No prior run given (upload one, or use the demo data, which includes a labelled prior).")
    else:
        d = run["diff"]
        m1, m2, m3 = st.columns(3)
        m1.metric("Gate-passers now", ", ".join(f"{k} {v}" for k, v in d["gate_passers_now"].items()))
        m2.metric("Tier 1 now", ", ".join(f"{k} {len(v)}" for k, v in d["tier1_now"].items()))
        m3.metric("Tier changes", len(d["tier_changes"]))
        st.subheader("Tier changes (recommendations pending approval)")
        changes = pd.DataFrame(d["tier_changes"]) if d["tier_changes"] else pd.DataFrame({"tier changes": ["none"]})
        st.dataframe(changes.round(1), hide_index=True, width="stretch")
        st.subheader("Largest score movers")
        st.dataframe(pd.DataFrame(d["score_movers"]).round(1), hide_index=True, width="stretch")
        if d["new_dashers"] or d["dropped_dashers"]:
            st.write("New:", d["new_dashers"] or "none", " · Dropped:", d["dropped_dashers"] or "none")
        ai_panel("AI briefing", run["briefing"], run["briefing_error"])
