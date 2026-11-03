"""pipeline.py — deterministic logic lifted from analysis.ipynb (nothing is imported from the notebook).

Public functions
    clean(raw_df)                 -> (df, cleaning_log)   cleaning + the 12 derived row-level fields
    profile(df)                   -> dict                 data-quality facts for the QA stage
    score(df, **params)           -> scorecard_df         gates, components, 0–100 score, tiers (reference column names)
    bike_cohort(scorecard_df)     -> DataFrame            display-only: bicycle Dashers failing only the vehicle gate
    diff(scorecard_df, prior_df)  -> dict                 tier changes, score movers, new / dropped Dashers
    run(xlsx_path)                -> {"scorecard", "cleaning_log", "profile"}
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ============================================================================
# CONSTANTS — the only block to touch when a definition changes (CLAUDE.md)
# ============================================================================
WAIT_THRESHOLD_MIN = 10            # merchant wait beyond this is forgiven (metric 3); missing wait = zero forgiveness
SEVERE_LATE_MIN = 15               # adjusted lateness beyond this is "severe" (metric 5)
SEVERE_CAP = 0.30                  # consistency component falls linearly to zero at this severe-late rate
WEIGHTS = {"reliability": 50, "quality": 30, "consistency": 10, "professionalism": 10}   # score = sum = 100
K_SHRINK = 200                     # pseudo-deliveries pulling lifetime star toward the market mean
GATE_LIFETIME_MIN = {"Dashattan": 100, "Doorlanta": 300}   # lifetime deliveries gate, per city
GATE_ASAP_MIN = {"Dashattan": 5, "Doorlanta": 10}          # observed ASAP orders gate, per city
TIER1_SIZE = {"Dashattan": 4, "Doorlanta": 10}             # Tier 1 = top N gate-passers by score
WIDGET_VEHICLES = ("car", "motorcycle")                     # vehicle set must contain one of these
ACTIVATION_FLOOR = 75              # Tier 2 activation floor — display only, never gates
UNIFORM_STRICT = dict(lifetime_min=300, asap_min=10, severe_max=0.10, ontime_min=0.85)  # KEY_NUMBERS "uniform strict"
SYNTHETIC_BUFFER_MIN = 17          # Phase 5: quote buffer given to scheduled orders when they are included
PHANTOM_COLUMN = "Unnamed: 38"
UTC_COLS = ["CREATED_AT", "QUOTED_DELIVERY_TIME", "ESTIMATED_DELIVERY_TIME", "ACTUAL_PICKUP_TIME",
            "ACTUAL_DELIVERY_TIME", "DASHER_ASSIGNED_TIME", "DASHER_CONFIRMED_TIME", "DASHER_AT_STORE_TIME"]
LOCAL_COLS = ["ACTUAL_PICKUP_TIME_GALAXY_A", "ACTUAL_DELIVERY_TIME_GALAXY_A",
              "DASHER_ASSIGNED_TIME_GALAXY_A", "DASHER_AT_STORE_TIME_GALAXY_A"]
TIMESTAMP_COLS = UTC_COLS + LOCAL_COLS
EXCLUDED_COLUMNS = ["COMPOSITE_SCORE", "NUM_ON_TIME_DELIVERIES", "DASHER_TO_STORE_TIME_CATEGORY", "CANCELLED_AT"]
EXPECTED_COLUMNS = [  # the 38 raw columns after the phantom column is dropped; schema drift is reported against this
    "DELIVERY_NAME", "DELIVERY_RATING", "MARKET_NUMBER", "MARKET_NAME", "TIMEZONE", "DASHER", "IS_FIRST_DELIVERY", "VEHICLE",
    "CREATED_AT", "QUOTED_DELIVERY_TIME", "ESTIMATED_DELIVERY_TIME", "ASAP", "FRAUDULENT", "ACTUAL_PICKUP_TIME",
    "ACTUAL_DELIVERY_TIME", "DASHER_ASSIGNED_TIME", "MANUALLY_ASSIGNED", "DASHER_CONFIRMED_TIME", "DASHER_AT_STORE_TIME",
    "CANCELLED_AT", "ACTIVE_DATE", "COMPOSITE_SCORE", "SUBTOTAL", "CONFIRM_TO_DELIVER_DURATION",
    "DASHER_TO_RESTAURANT_DURATION", "DASHER_WAIT_DURATION", "RESTAURANT_TO_CUSTOMER_DURATION", "WAS_BATCHED",
    "TOTAL_ITEM_COUNT", "DASHER_TO_STORE_TIME_CATEGORY", "ACTUAL_PICKUP_TIME_GALAXY_A", "ACTUAL_DELIVERY_TIME_GALAXY_A",
    "DASHER_ASSIGNED_TIME_GALAXY_A", "DASHER_AT_STORE_TIME_GALAXY_A", "COMPOSITE_STAR_RATING", "NUM_FIVE_STARS",
    "NUM_DELIVERIES", "NUM_ON_TIME_DELIVERIES",
]
DERIVED_FIELDS = ["late_min", "is_late", "wait_min", "excess_wait", "late_min_adj", "is_late_adj", "severe",
                  "assign_lag_min", "buffer_min", "late_vs_estimate", "hour_local", "arrival_logged"]
RANGE_COLUMNS = ["DELIVERY_RATING", "SUBTOTAL", "TOTAL_ITEM_COUNT", "CONFIRM_TO_DELIVER_DURATION", "DASHER_WAIT_DURATION",
                 "RESTAURANT_TO_CUSTOMER_DURATION", "COMPOSITE_STAR_RATING", "NUM_DELIVERIES", "late_min", "assign_lag_min"]
KEYS = ["MARKET_NAME", "DASHER"]
SCORECARD_COLUMNS = [  # identical to reference/dasher_scorecard.csv
    "MARKET_NAME", "DASHER", "lifetime_deliveries", "lifetime_star", "sample_deliveries", "fraud_flags", "vehicles",
    "arrival_logged", "asap_n", "ontime_raw", "ontime_adj", "severe_late_rate", "shrunk_rating", "widget_capable",
    "pts_reliability", "pts_quality", "pts_consistency", "pts_professionalism", "selection_score", "passes_gates",
    "fraud_review", "tier", "selected_uniform_strict",
]
# ============================================================================


# ----------------------------------------------------------------------------- clean
def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Drop junk rows and the phantom column, parse timestamps, build the 12 derived fields. Returns (df, log)."""
    log: list[str] = []
    df = raw.copy()

    junk = df[df["MARKET_NAME"].isna()]
    stray = junk["COMPOSITE_SCORE"].dropna().round(2).tolist() if "COMPOSITE_SCORE" in junk else []
    df = df[df["MARKET_NAME"].notna()].copy()
    log.append(f"1. Dropped {len(junk)} trailing rows with no MARKET_NAME; their only data was COMPOSITE_SCORE {stray}.")
    if PHANTOM_COLUMN in df.columns:
        n_cells = int(raw[PHANTOM_COLUMN].notna().sum())
        df = df.drop(columns=[PHANTOM_COLUMN])
        log.append(f"2. Dropped headerless column '{PHANTOM_COLUMN}' ({n_cells} non-empty cell).")
    df = df.reset_index(drop=True)

    for col in TIMESTAMP_COLS:
        df[col] = pd.to_datetime(df[col], format="ISO8601")
    offsets = sorted({round(float(h), 2) for col in LOCAL_COLS
                      for h in ((df[col.replace("_GALAXY_A", "")] - df[col]).dt.total_seconds() / 3600).dropna().unique()})
    log.append(f"3. Parsed {len(TIMESTAMP_COLS)} ISO8601 timestamp columns. *_GALAXY_A columns sit {offsets} h behind UTC "
               "(local time; their Z suffix is a mislabel). UTC columns for arithmetic, local for hour-of-day.")
    log.append("4. All *_DURATION columns are seconds; derived fields convert to minutes, raw columns are left in seconds.")

    def minutes(start: str, end: str) -> pd.Series:
        return (df[end] - df[start]).dt.total_seconds() / 60

    df["late_min"] = minutes("QUOTED_DELIVERY_TIME", "ACTUAL_DELIVERY_TIME")
    df["is_late"] = df["late_min"] > 0
    df["wait_min"] = df["DASHER_WAIT_DURATION"] / 60
    df["excess_wait"] = (df["wait_min"] - WAIT_THRESHOLD_MIN).clip(lower=0).fillna(0)
    df["late_min_adj"] = df["late_min"] - df["excess_wait"]
    df["is_late_adj"] = df["late_min_adj"] > 0
    df["severe"] = df["late_min_adj"] > SEVERE_LATE_MIN
    df["assign_lag_min"] = minutes("CREATED_AT", "DASHER_ASSIGNED_TIME")
    df["buffer_min"] = minutes("ESTIMATED_DELIVERY_TIME", "QUOTED_DELIVERY_TIME")
    df["late_vs_estimate"] = df["ACTUAL_DELIVERY_TIME"] > df["ESTIMATED_DELIVERY_TIME"]
    df["hour_local"] = df["ACTUAL_DELIVERY_TIME_GALAXY_A"].dt.hour
    df["arrival_logged"] = df["DASHER_AT_STORE_TIME"].notna()

    wait_missing = df["wait_min"].isna()
    no_arrival = df["DASHER_AT_STORE_TIME"].isna()
    n_no_arrival = int((wait_missing & no_arrival).sum())
    n_after_pickup = int((wait_missing & ~no_arrival).sum())
    log.append(f"5. DASHER_WAIT_DURATION missing on {int(wait_missing.sum())} rows ({100 * wait_missing.mean():.1f}%): "
               f"{n_no_arrival} with no store arrival logged, {n_after_pickup} with the arrival stamped after pickup "
               "(source left the wait blank rather than negative). Kept NaN; never imputed.")
    log.append(f"6. excess_wait fills a missing wait with 0 (zero forgiveness) — the only fillna. The {n_after_pickup} "
               "late-logged arrivals still count as arrival_logged for Professionalism.")
    before_pickup = df.loc[df["ACTUAL_PICKUP_TIME"] > df["ACTUAL_DELIVERY_TIME"], "DELIVERY_NAME"].astype(int).tolist()
    est_after_quote = df.loc[df["ESTIMATED_DELIVERY_TIME"] > df["QUOTED_DELIVERY_TIME"], "DELIVERY_NAME"].astype(int).tolist()
    c2d_from_ts = (df["ACTUAL_DELIVERY_TIME"] - df["DASHER_CONFIRMED_TIME"]).dt.total_seconds()
    c2d_mismatch = df.loc[(df["CONFIRM_TO_DELIVER_DURATION"] - c2d_from_ts).abs() > 2, "DELIVERY_NAME"].astype(int).tolist()
    arrival_before_confirm = int((df["DASHER_CONFIRMED_TIME"] > df["DASHER_AT_STORE_TIME"]).sum())
    log.append(f"7–10. Kept, report only: delivered before pickup {before_pickup}; estimate later than quote {est_after_quote}; "
               f"CONFIRM_TO_DELIVER_DURATION disagrees with timestamps {c2d_mismatch}; store arrival before confirmation on "
               f"{arrival_before_confirm} rows (DASHER_TO_RESTAURANT_DURATION blank there).")
    first = df[df["IS_FIRST_DELIVERY"] == 1]
    log.append(f"11. IS_FIRST_DELIVERY = 1 on {len(first)} rows whose Dashers have {int(first['NUM_DELIVERIES'].min())}–"
               f"{int(first['NUM_DELIVERIES'].max())} lifetime deliveries; flag unreliable, excluded from nothing.")
    multi = df.groupby(KEYS)["VEHICLE"].nunique()
    multi = multi[multi > 1]
    log.append(f"12. Dashers with more than one vehicle: {[d for _, d in multi.index]}; vehicle is treated per delivery.")
    lifetime_cols = ["NUM_DELIVERIES", "COMPOSITE_STAR_RATING", "NUM_FIVE_STARS", "NUM_ON_TIME_DELIVERIES"]
    varies = int((df.groupby(KEYS)[lifetime_cols].nunique(dropna=False) > 1).sum().sum())
    log.append(f"13. Lifetime columns vary within a Dasher on {varies} Dasher-columns (0 = constant, so .last() is exact).")
    missing_pct = {c: round(100 * df[c].isna().mean(), 1) for c in EXCLUDED_COLUMNS if c in df.columns}
    log.append(f"14. Excluded by design, kept in exports, used in no metric: {missing_pct} (% missing).")
    log.append(f"15. DELIVERY_RATING missing on {int(df['DELIVERY_RATING'].isna().sum())} rows "
               f"({100 * df['DELIVERY_RATING'].isna().mean():.1f}%): unrated deliveries, left NaN; rated-only denominators.")
    log.append("16. assign_lag_min, buffer_min and late_vs_estimate are computed on all rows; filtering to ASAP happens at use.")
    years = sorted(df["ACTIVE_DATE"].dt.year.unique().tolist())
    log.append(f"17. All dates sit in {years} (fictional dataset); every metric is relative, so the year is immaterial.")
    windows = df.groupby("MARKET_NAME")["ACTIVE_DATE"].agg(["min", "max", "size"])
    log.append("18. Date window per city: " + "; ".join(
        f"{m} {r['min'].date()}–{r['max'].date()} ({int(r['size'])} orders)" for m, r in windows.iterrows()) + ".")
    return df, log


# ----------------------------------------------------------------------------- profile
def profile(df: pd.DataFrame) -> dict:
    """Data-quality facts for the QA stage. JSON-serialisable; numbers only — no interpretation."""
    wait_missing = df["wait_min"].isna()
    no_arrival = df["DASHER_AT_STORE_TIME"].isna()
    by_city = df.groupby("MARKET_NAME")
    c2d_from_ts = (df["ACTUAL_DELIVERY_TIME"] - df["DASHER_CONFIRMED_TIME"]).dt.total_seconds()
    missing = {c: {"n": int(df[c].isna().sum()), "pct": round(100 * df[c].isna().mean(), 1)}
               for c in df.columns if df[c].isna().any()}
    raw_cols = [c for c in df.columns if c not in DERIVED_FIELDS]
    return {
        "schema": {"expected_columns": len(EXPECTED_COLUMNS), "actual_raw_columns": len(raw_cols),
                   "missing_vs_expected": [c for c in EXPECTED_COLUMNS if c not in raw_cols],
                   "unexpected": [c for c in raw_cols if c not in EXPECTED_COLUMNS],
                   "derived_fields_present": [c for c in DERIVED_FIELDS if c in df.columns]},
        "duplicates": {"DELIVERY_NAME_duplicates": int(df["DELIVERY_NAME"].duplicated().sum())},
        "value_ranges": {c: {"min": round(float(df[c].min()), 2), "median": round(float(df[c].median()), 2),
                             "max": round(float(df[c].max()), 2)} for c in RANGE_COLUMNS if c in df.columns},
        "standing_exclusions": EXCLUDED_COLUMNS,
        "rows": int(len(df)),
        "rows_per_city": {m: int(n) for m, n in by_city.size().items()},
        "dashers_per_city": {m: int(n) for m, n in by_city["DASHER"].nunique().items()},
        "date_window_per_city": {m: {"first": str(g["ACTIVE_DATE"].min().date()), "last": str(g["ACTIVE_DATE"].max().date()),
                                     "days": int(g["ACTIVE_DATE"].nunique())} for m, g in by_city},
        "asap_rows": int((df["ASAP"] == 1).sum()),
        "scheduled_rows": int((df["ASAP"] == 0).sum()),
        "missing_wait": {"total": int(wait_missing.sum()), "no_arrival_logged": int((wait_missing & no_arrival).sum()),
                         "arrival_after_pickup": int((wait_missing & ~no_arrival).sum())},
        "missing_by_column": missing,
        "anomaly_rows": {
            "delivered_before_pickup": df.loc[df["ACTUAL_PICKUP_TIME"] > df["ACTUAL_DELIVERY_TIME"], "DELIVERY_NAME"].astype(int).tolist(),
            "estimate_after_quote": df.loc[df["ESTIMATED_DELIVERY_TIME"] > df["QUOTED_DELIVERY_TIME"], "DELIVERY_NAME"].astype(int).tolist(),
            "confirm_to_deliver_duration_mismatch": df.loc[(df["CONFIRM_TO_DELIVER_DURATION"] - c2d_from_ts).abs() > 2, "DELIVERY_NAME"].astype(int).tolist(),
            "arrival_before_confirmation_n": int((df["DASHER_CONFIRMED_TIME"] > df["DASHER_AT_STORE_TIME"]).sum()),
            "is_first_delivery_rows": int((df["IS_FIRST_DELIVERY"] == 1).sum()),
        },
        "multi_vehicle_dashers": [d for _, d in df.groupby(KEYS)["VEHICLE"].nunique().loc[lambda s: s > 1].index],
        "fraud_flagged_rows": int(df["FRAUDULENT"].sum()),
        "excluded_columns": EXCLUDED_COLUMNS,
        "derived_field_checks": {
            "wait_missing_pct": round(100 * wait_missing.mean(), 1),
            "buffer_min_mean_by_asap": {str(int(k)): round(v, 2) for k, v in df.groupby("ASAP")["buffer_min"].mean().items()},
            "late_vs_estimate_pct_asap": round(100 * df.loc[df["ASAP"] == 1, "late_vs_estimate"].mean(), 1),
        },
    }


# ----------------------------------------------------------------------------- score
def score(df: pd.DataFrame, wait_threshold: float = WAIT_THRESHOLD_MIN, weights: dict = WEIGHTS,
          k: float = K_SHRINK, include_scheduled: bool = False) -> pd.DataFrame:
    """Dasher scorecard. Defaults reproduce the notebook / reference exactly; the parameters are the Phase 5 knobs."""
    r = df[KEYS + ["ASAP", "late_min", "wait_min"]].copy()
    r["excess"] = (r["wait_min"] - wait_threshold).clip(lower=0).fillna(0)
    if include_scheduled:
        r.loc[r["ASAP"] == 0, "late_min"] = r.loc[r["ASAP"] == 0, "late_min"] - SYNTHETIC_BUFFER_MIN
    else:
        r = r[r["ASAP"] == 1]                       # filter to ASAP FIRST, then group
    r["late_adj"] = r["late_min"] - r["excess"]
    r["is_late_raw"] = r["late_min"] > 0
    r["is_late_adj"] = r["late_adj"] > 0
    r["severe"] = r["late_adj"] > SEVERE_LATE_MIN
    perf = r.groupby(KEYS).agg(asap_n=("is_late_adj", "size"),
                               ontime_raw=("is_late_raw", lambda s: 1 - s.mean()),
                               ontime_adj=("is_late_adj", lambda s: 1 - s.mean()),
                               severe_late_rate=("severe", "mean"))
    prof = df.groupby(KEYS).agg(lifetime_deliveries=("NUM_DELIVERIES", "last"),
                                lifetime_star=("COMPOSITE_STAR_RATING", "last"),
                                sample_deliveries=("DELIVERY_NAME", "size"),
                                fraud_flags=("FRAUDULENT", "sum"),
                                vehicles=("VEHICLE", lambda s: "/".join(sorted(set(s)))),
                                arrival_logged=("arrival_logged", "mean"))
    s = prof.join(perf, how="left")
    market_mean = s.groupby(level="MARKET_NAME")["lifetime_star"].mean()      # deduplicated Dasher table
    mk = s.index.get_level_values("MARKET_NAME")
    n = s["lifetime_deliveries"]
    s["shrunk_rating"] = (n * s["lifetime_star"] + k * mk.map(market_mean)) / (n + k)
    s["widget_capable"] = s["vehicles"].str.contains("|".join(WIDGET_VEHICLES))
    s["pts_reliability"] = weights["reliability"] * s["ontime_adj"]
    s["pts_quality"] = weights["quality"] * s["shrunk_rating"] / 5
    s["pts_consistency"] = weights["consistency"] * (1 - s["severe_late_rate"] / SEVERE_CAP).clip(lower=0)
    s["pts_professionalism"] = weights["professionalism"] * s["arrival_logged"]
    s["selection_score"] = s[["pts_reliability", "pts_quality", "pts_consistency", "pts_professionalism"]].sum(axis=1, min_count=4)
    s["passes_gates"] = (s["widget_capable"]
                         & (s["lifetime_deliveries"] >= mk.map(GATE_LIFETIME_MIN))
                         & (s["asap_n"].fillna(0) >= mk.map(GATE_ASAP_MIN)))
    s["fraud_review"] = s["fraud_flags"] > 0
    s = s.reset_index()
    s = assign_tiers(s)
    u = UNIFORM_STRICT
    s["selected_uniform_strict"] = (s["widget_capable"] & (s["lifetime_deliveries"] >= u["lifetime_min"])
                                    & (s["asap_n"].fillna(0) >= u["asap_min"])
                                    & (s["severe_late_rate"].fillna(1.0) <= u["severe_max"])
                                    & (s["ontime_adj"].fillna(0.0) >= u["ontime_min"]))
    return s[SCORECARD_COLUMNS]


def assign_tiers(s: pd.DataFrame) -> pd.DataFrame:
    """Tier 1 = top TIER1_SIZE gate-passers by selection_score per market; other passers Tier 2; non-passers None."""
    s = s.copy()
    s["tier"] = None
    for market, passers in s[s["passes_gates"]].groupby("MARKET_NAME"):
        ranked = passers["selection_score"].sort_values(ascending=False)
        s.loc[ranked.index, "tier"] = "Tier 2"
        s.loc[ranked.index[:TIER1_SIZE[market]], "tier"] = "Tier 1"
    return s


def bike_cohort(scorecard: pd.DataFrame) -> pd.DataFrame:
    """Display only: Dashers failing ONLY the vehicle gate, ranked by score, top 4 flagged. Changes nothing above."""
    mk = scorecard["MARKET_NAME"]
    cohort = scorecard[~scorecard["widget_capable"]
                       & (scorecard["lifetime_deliveries"] >= mk.map(GATE_LIFETIME_MIN))
                       & (scorecard["asap_n"].fillna(0) >= mk.map(GATE_ASAP_MIN))]
    cohort = cohort.sort_values("selection_score", ascending=False).reset_index(drop=True)
    cohort["top_4"] = cohort.index < 4
    return cohort


# ----------------------------------------------------------------------------- diff
def diff(scorecard: pd.DataFrame, prior: pd.DataFrame | None, movers: int = 5) -> dict:
    """Run-over-run comparison. Keyed by (MARKET_NAME, DASHER); prior=None gives the current state only."""
    cur = scorecard.set_index(KEYS)
    tiers_now = {m: sorted(scorecard.loc[(scorecard["MARKET_NAME"] == m) & (scorecard["tier"] == "Tier 1"), "DASHER"])
                 for m in TIER1_SIZE}
    out = {"dashers": int(len(cur)), "tier1_now": tiers_now,
           "gate_passers_now": {m: int(n) for m, n in scorecard.groupby("MARKET_NAME")["passes_gates"].sum().items()}}
    if prior is None:
        out.update({"prior": None, "tier_changes": [], "score_movers": [], "new_dashers": [], "dropped_dashers": []})
        return out
    pri = prior.set_index(KEYS)
    both = cur.index.intersection(pri.index)
    tier_now, tier_pri = cur.loc[both, "tier"].fillna(""), pri.loc[both, "tier"].fillna("")
    changed = both[(tier_now != tier_pri).values]
    out["prior"] = {"tier1": {m: sorted(prior.loc[(prior["MARKET_NAME"] == m) & (prior["tier"] == "Tier 1"), "DASHER"]) for m in TIER1_SIZE}}
    out["tier_changes"] = [{"market": m, "dasher": d, "prior_tier": tier_pri[(m, d)] or "none", "current_tier": tier_now[(m, d)] or "none",
                            "prior_score": round(float(pri.loc[(m, d), "selection_score"]), 2),
                            "current_score": round(float(cur.loc[(m, d), "selection_score"]), 2)} for m, d in changed]
    delta = (cur.loc[both, "selection_score"] - pri.loc[both, "selection_score"]).dropna()
    top = delta.abs().sort_values(ascending=False).head(movers).index
    out["score_movers"] = [{"market": m, "dasher": d, "prior_score": round(float(pri.loc[(m, d), "selection_score"]), 2),
                            "current_score": round(float(cur.loc[(m, d), "selection_score"]), 2), "change": round(float(delta[(m, d)]), 2)}
                           for m, d in top]
    out["new_dashers"] = [{"market": m, "dasher": d} for m, d in cur.index.difference(pri.index)]
    out["dropped_dashers"] = [{"market": m, "dasher": d} for m, d in pri.index.difference(cur.index)]
    return out


# ----------------------------------------------------------------------------- run
def run(xlsx_path: str) -> dict:
    """Raw workbook in, {"scorecard", "cleaning_log", "profile"} out. No AI, no side effects."""
    raw = pd.read_excel(xlsx_path)
    df, log = clean(raw)
    return {"scorecard": score(df), "cleaning_log": log, "profile": profile(df)}


if __name__ == "__main__":
    import sys
    result = run(sys.argv[1] if len(sys.argv) > 1 else "data/2026_Platform_Ops_Widget_Data.xlsx")
    print("\n".join(result["cleaning_log"]))
    sc = result["scorecard"]
    print(sc[sc["passes_gates"]].sort_values(["MARKET_NAME", "selection_score"], ascending=[True, False])
          [["MARKET_NAME", "DASHER", "selection_score", "tier", "fraud_review"]].to_string(index=False))
