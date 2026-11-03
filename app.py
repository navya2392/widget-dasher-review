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



COLUMN_HELP = {  # shown as a ? tooltip on each column header
    "Dasher": "Dasher name.",
    "Score": "0–100 selection score = 50 × adjusted on-time + 30 × shrunk rating / 5 + 10 × consistency (1 − severe-late rate / 30%) + 10 × arrival-logged share.",
    "Recommended": "Tier assigned by the pipeline: Tier 1 = top 4 (Dashattan) / top 10 (Doorlanta) gate-passers by score; others Tier 2.",
    "Override": "Operator's decision. Change it to override the recommended tier; every override is recorded on Approve.",
    "Review": "'review' = at least one fraud flag in this Dasher's deliveries → manual review. Never auto-excluded.",
    "Deliveries": "Deliveries observed in this data extract (June 1–13).",
    "ASAP n": "ASAP (on-demand) deliveries in the extract — the sample the on-time and severe-late rates are computed on.",
    "Lifetime deliv.": "Lifetime deliveries on the platform (NUM_DELIVERIES).",
    "Lifetime rating": "Lifetime star rating (COMPOSITE_STAR_RATING).",
    "Shrunk rating": "Lifetime rating pulled toward the market mean with k = 200 pseudo-deliveries: (n × star + 200 × market mean) / (n + 200). A high rating on few deliveries shrinks more.",
    "On-time adj %": "Share of ASAP deliveries on time versus the quoted time, after forgiving merchant waits beyond 10 minutes.",
    "Severe %": "Share of ASAP deliveries more than 15 minutes late after the wait adjustment.",
    "Logged %": "Share of all deliveries where the Dasher logged arrival at the store (app discipline).",
    "Vehicle": "Vehicle(s) used in the extract; car or motorcycle = widget-capable.",
    "Failed gate(s)": "Gate(s) missed: widget-capable vehicle · lifetime deliveries ≥ 100 (Dashattan) / 300 (Doorlanta) · ASAP deliveries ≥ 5 / 10.",
    "Reliability /50": "50 × adjusted on-time rate.",
    "Quality /30": "30 × shrunk rating / 5.",
    "Consistency /10": "10 × max(0, 1 − severe-late rate / 30%).",
    "Professionalism /10": "10 × arrival-logged share.",
}

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


SAVED_QA = Path("demo/e2e_qa.md")               # verified AI outputs of the demo run (2026-11-03); shipped with the app
SAVED_BRIEFING = Path("demo/e2e_briefing.md")
SAVED_NOTE = "_Saved from the verified demo run (2026-11-03) — no live model call. Uploaded files get a live read._"


@st.cache_data(show_spinner=False)
def cached_run(raw_bytes: bytes, prior_bytes: bytes | None, source: str, use_saved_ai: bool = False) -> dict:
    """One pipeline run plus at most one call per AI function, cached on the input bytes: the first session to
    run a given workbook pays once per server process; every later session (and every rerun) gets it instantly.
    use_saved_ai: the demo shows the saved, verified AI texts instead of calling the model (instant, no key needed)."""
    raw = pd.read_excel(io.BytesIO(raw_bytes))
    prior = pd.read_csv(io.BytesIO(prior_bytes)) if prior_bytes else None
    result = pipeline.run_raw(raw)
    diff = pipeline.diff(result["scorecard"], prior)
    if use_saved_ai and SAVED_QA.exists() and SAVED_BRIEFING.exists():
        qa = SAVED_NOTE + "\n\n" + SAVED_QA.read_text(encoding="utf-8")
        briefing = SAVED_NOTE + "\n\n" + SAVED_BRIEFING.read_text(encoding="utf-8") if prior is not None else None
        qa_error = briefing_error = None
    else:
        ensure_api_key()
        qa = ai.qa_summary(result["profile"])
        qa_error = ai.last_error
        briefing = briefing_error = None
        if prior is not None:
            verdict = [line for line in (qa or "").splitlines() if "VERDICT" in line]
            qa_note = verdict[-1] if verdict else ("QA report truncated before its verdict" if qa else None)
            briefing = ai.briefing(result["scorecard"], prior, qa_note=qa_note)
            briefing_error = ai.last_error
    return {**result, "prior": prior, "diff": diff, "qa": qa, "qa_error": qa_error,
            "briefing": briefing, "briefing_error": briefing_error, "source": source,
            "ran_at": dt.datetime.now().isoformat(timespec="seconds")}


def run_everything(raw_bytes: bytes, prior_bytes: bytes | None, source: str, use_saved_ai: bool = False) -> dict:
    """Session-side wrapper: resets any operator overrides, then returns the (cached) run."""
    for market in MARKETS:
        st.session_state.pop(f"tier_override_{market}", None)
        st.session_state.pop(f"edited_{market}", None)
    st.session_state.pop("approved", None)
    return cached_run(raw_bytes, prior_bytes, source, use_saved_ai)


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
        "": ["🟢" if t == "Tier 1" else "🟡" for t in passers["tier"]],
        "Dasher": passers["DASHER"].values,
        "Score": passers["selection_score"].round(1).values,
        "Recommended": passers["tier"].values,
        "Override": [overrides.get(d, t) for d, t in zip(passers["DASHER"], passers["tier"])],
        "Review": ["review" if f else "" for f in passers["fraud_review"]],
        "Deliveries": passers["sample_deliveries"].astype(int).values,
        "ASAP n": passers["asap_n"].fillna(0).astype(int).values,
        "Lifetime deliv.": passers["lifetime_deliveries"].astype(int).values,
        "Lifetime rating": passers["lifetime_star"].round(2).values,
        "Shrunk rating": passers["shrunk_rating"].round(2).values,
        "On-time adj %": (100 * passers["ontime_adj"]).round(1).values,
        "Severe %": (100 * passers["severe_late_rate"]).round(1).values,
        "Logged %": (100 * passers["arrival_logged"]).round(1).values,
        "Vehicle": passers["vehicles"].values,
    })
    if show_components:
        for label, col in COMPONENT_COLUMNS.items():
            view[label] = passers[col].round(1).values
    return view


def render_market(scorecard: pd.DataFrame, market: str) -> None:
    passers = scorecard[(scorecard["MARKET_NAME"] == market) & scorecard["passes_gates"]]
    m1, m2, m3 = st.columns(3)
    m1.metric("Gate-passers", int(len(passers)), delta=f"of {int((scorecard['MARKET_NAME'] == market).sum())} Dashers", delta_color="off")
    m2.metric("Tier 1", int((passers["tier"] == "Tier 1").sum()), delta=f"top {pipeline.TIER1_SIZE[market]} by score")
    m3.metric("Fraud reviews", int(passers["fraud_review"].sum()), delta="manual check, never excluded", delta_color="inverse")
    show = st.session_state.get(f"components_{market}", False)
    full_view = scorecard_view(scorecard, market, show)

    # filters: display only — Approve always covers every gate-passer, filtered in or out
    f1, f2, f3, f4 = st.columns(4)
    tiers = f1.multiselect("Tier", ["Tier 1", "Tier 2"], default=["Tier 1", "Tier 2"], key=f"f_tier_{market}")
    min_rating = f2.slider("Min lifetime rating", 3.5, 5.0, 3.5, 0.05, key=f"f_rating_{market}")
    max_life = int(full_view["Lifetime deliv."].max()) if len(full_view) else 1
    min_life = f3.slider("Min lifetime deliveries", 0, max_life, 0, 50, key=f"f_life_{market}")
    min_ontime = f4.slider("Min on-time rate %", 0, 100, 0, 5, key=f"f_ontime_{market}")
    mask = (full_view["Recommended"].isin(tiers) & (full_view["Lifetime rating"] >= min_rating)
            & (full_view["Lifetime deliv."] >= min_life) & (full_view["On-time adj %"] >= min_ontime))
    view = full_view[mask].reset_index(drop=True)
    st.caption(f"Showing {len(view)} of {len(full_view)} gate-passers · change **Override** to override, "
               "then Approve below")
    config = {
        "": st.column_config.TextColumn("", width="small"),
        "Dasher": st.column_config.TextColumn("Dasher", width=88),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f", width=112),
        "Recommended": st.column_config.TextColumn("Recommended", width=85, help="Pipeline tier (read-only)"),
        "Override": st.column_config.SelectboxColumn("Override", options=pipeline.TIER_OPTIONS, required=True,
                                                     width=90, help="Operator's decision — change to override"),
        "Review": st.column_config.TextColumn("Fraud review", width=95,
                                              help="⚠️ = fraud flag in sample → manual review, never auto-excluded"),
        "Vehicle": st.column_config.TextColumn("Vehicle", width=85),
    }
    # pixel widths + short labels so all columns fit a laptop screen; the data column names are unchanged
    for col, label, w in (("Deliveries", "Deliveries", 92), ("ASAP n", "ASAP deliveries", 118), ("Lifetime deliv.", "Lifetime deliveries", 132)):
        config[col] = st.column_config.NumberColumn(label, format="%d", width=w)
    for col, label in (("Lifetime rating", "Lifetime ★"), ("Shrunk rating", "Shrunk ★")):
        config[col] = st.column_config.NumberColumn(label, format="%.2f", width=78)
    for col, label in (("On-time adj %", "On-time %"), ("Severe %", "Severe %"), ("Logged %", "Logged %")):
        config[col] = st.column_config.NumberColumn(label, format="%.1f", width=78)
    for col in COMPONENT_COLUMNS:
        config[col] = st.column_config.NumberColumn(col, format="%.1f", width=85)
    for col, text in COLUMN_HELP.items():          # ? tooltip with the definition on every header
        if col in config:
            config[col]["help"] = text
    overrides = dict(st.session_state.get(f"tier_override_{market}", {}))
    for tier_label, colour in (("Tier 1", "red"), ("Tier 2", None)):         # Tier 1 red, Tier 2 black
        section = view[view["Recommended"] == tier_label].reset_index(drop=True)
        if section.empty:
            continue
        head = f":{colour}[● {tier_label} — recommended]" if colour else f"● {tier_label} — recommended"
        st.markdown(f"#### {head} &nbsp; <span style='color:gray;font-weight:normal'>"
                    f"{len(section)} Dasher{'s' if len(section) != 1 else ''}</span>", unsafe_allow_html=True)
        shown = section.drop(columns=["Recommended", ""])          # recommendation stays in the data for the approval log
        edited = st.data_editor(shown, column_config=config,
                                disabled=[c for c in shown.columns if c != "Override"],
                                hide_index=True, width="stretch",
                                height=35 * (len(section) + 1) + 3,     # show every visible row without an inner scrollbar
                                key=f"editor_{market}_{tier_label}_{'full' if show else 'compact'}_{abs(hash(tuple(section['Dasher'])))}")
        overrides.update(zip(edited["Dasher"], edited["Override"]))
    st.session_state[f"tier_override_{market}"] = overrides
    approval_frame = full_view[["Dasher", "Score", "Recommended"]].copy()
    approval_frame["Tier"] = [overrides.get(d, r) for d, r in zip(full_view["Dasher"], full_view["Recommended"])]
    approval_frame["Review"] = full_view["Review"].values
    st.session_state[f"edited_{market}"] = approval_frame.assign(MARKET_NAME=market)
    # read-only: Dashers who did not clear the gates (cannot be approved), with the gate(s) they failed
    non = scorecard[(scorecard["MARKET_NAME"] == market) & ~scorecard["passes_gates"]].sort_values("selection_score", ascending=False)
    if len(non):
        def failed_gates(r):
            out = []
            if not r["widget_capable"]: out.append("vehicle")
            if r["lifetime_deliveries"] < pipeline.GATE_LIFETIME_MIN[market]: out.append(f"lifetime < {pipeline.GATE_LIFETIME_MIN[market]}")
            if (r["asap_n"] if pd.notna(r["asap_n"]) else 0) < pipeline.GATE_ASAP_MIN[market]: out.append(f"ASAP < {pipeline.GATE_ASAP_MIN[market]}")
            return ", ".join(out)
        non_view = pd.DataFrame({
            "Dasher": non["DASHER"].values,
            "Score": non["selection_score"].round(1).values,
            "Failed gate(s)": [failed_gates(r) for _, r in non.iterrows()],
            "Review": ["review" if f else "" for f in non["fraud_review"]],
            "Deliveries": non["sample_deliveries"].astype(int).values,
            "ASAP n": non["asap_n"].fillna(0).astype(int).values,
            "Lifetime deliv.": non["lifetime_deliveries"].astype(int).values,
            "Lifetime rating": non["lifetime_star"].round(2).values,
            "Shrunk rating": non["shrunk_rating"].round(2).values,
            "On-time adj %": (100 * non["ontime_adj"]).round(1).values,
            "Severe %": (100 * non["severe_late_rate"]).round(1).values,
            "Logged %": (100 * non["arrival_logged"]).round(1).values,
            "Vehicle": non["vehicles"].values,
        })
        st.markdown(f"#### ○ Did not clear gates &nbsp; <span style='color:gray;font-weight:normal'>{len(non)} Dashers · "
                    "read-only, not eligible for approval</span>", unsafe_allow_html=True)
        non_config = dict(config); non_config["Failed gate(s)"] = st.column_config.TextColumn("Failed gate(s)", width=150, help=COLUMN_HELP["Failed gate(s)"])
        st.dataframe(non_view, column_config=non_config, hide_index=True, width="stretch", height=35 * (len(non_view) + 1) + 3)
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
st.set_page_config(page_title="Widget Dasher Review", page_icon="📦", layout="wide")
st.title("📦 Widget Dasher Review")
st.caption("AI interprets and explains; code computes; a human approves.")

# The uploader widgets render only on request: Streamlit Community Cloud intermittently answers HTTP 500 for the
# uploader's JavaScript chunk on first-time visits, which left error boxes where the uploaders should be. The demo
# button needs nothing from that chunk, so it is the front door.
col_demo, col_own = st.columns(2)
want_upload = col_own.toggle("Upload my own files", value=False)
upload = prior_upload = None
if want_upload:
    upload = st.file_uploader("Deliveries workbook (.xlsx)", type=["xlsx"])
    prior_upload = st.file_uploader("Prior run scorecard (.csv, optional)", type=["csv"])
col_run = st.container()
demo_prior_bytes = DEMO_PRIOR.read_bytes() if DEMO_PRIOR.exists() else None
if want_upload and col_run.button("Run", disabled=upload is None):
    prior_bytes = prior_upload.getvalue() if prior_upload is not None else demo_prior_bytes
    with st.spinner("Running pipeline and AI stages..."):
        st.session_state["run"] = run_everything(upload.getvalue(), prior_bytes, source=upload.name)
if col_demo.button("Run with demo data"):
    with st.spinner("Running the pipeline on the case data..."):
        st.session_state["run"] = run_everything(DEMO_XLSX.read_bytes(), demo_prior_bytes, source=f"demo: {DEMO_XLSX.name}",
                                                 use_saved_ai=True)

run = st.session_state.get("run")
if run is None:
    st.info("Upload a workbook and press Run, or press Run with demo data.")
    st.stop()

st.caption(f"Source: {run['source']} · ran {run['ran_at']}")
scorecard = run["scorecard"]
tab_score, tab_data, tab_changes = st.tabs(["📊 Scorecard", "🧪 Data check", "🔁 Changes vs prior run"])

# ----------------------------------------------------------------------------- scorecard (first)
with tab_score:
    CITY_COLOUR = {"Dashattan": "red", "Doorlanta": None}            # two colours only: red and (default) black
    city_tabs = st.tabs([f":red[**{m.upper()}**]" if CITY_COLOUR[m] else f"**{m.upper()}**" for m in MARKETS])
    for city_tab, market in zip(city_tabs, MARKETS):
        with city_tab:
            st.markdown(f"## :red[{market.upper()}]" if CITY_COLOUR[market] else f"## {market.upper()}")
            render_market(scorecard, market)
            cohort = pipeline.bike_cohort(scorecard)
            cohort = cohort[cohort["MARKET_NAME"] == market]
            if len(cohort):
                with st.expander(f"Conditional bike cohort — {market} (display only; fails only the vehicle gate)"):
                    st.dataframe(cohort[["DASHER", "vehicles", "lifetime_deliveries", "asap_n", "ontime_adj", "shrunk_rating",
                                         "selection_score", "fraud_review", "top_4"]].round(3), hide_index=True, width="stretch")
    st.write("")
    _, mid, _ = st.columns([2, 1, 2])
    if mid.button("Approve tier changes", width="stretch", type="primary"):
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
