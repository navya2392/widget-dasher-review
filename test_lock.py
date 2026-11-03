"""Lock test: pipeline.py must reproduce reference/dasher_scorecard.csv, and the Phase 5 sensitivity harness
must still reproduce the baseline and its two one-swap scenarios when pointed at pipeline.score().

Run:  .venv\\Scripts\\python -m pytest test_lock.py -v
"""
import pandas as pd
import pytest

import pipeline

XLSX = "data/2026_Platform_Ops_Widget_Data.xlsx"
REFERENCE = "reference/dasher_scorecard.csv"
KEYS = ["MARKET_NAME", "DASHER"]
RATE_COLS = ["arrival_logged", "ontime_raw", "ontime_adj", "severe_late_rate", "shrunk_rating",
             "pts_reliability", "pts_quality", "pts_consistency", "pts_professionalism", "selection_score"]
EXACT_COLS = ["lifetime_deliveries", "sample_deliveries", "fraud_flags", "asap_n", "vehicles",
              "widget_capable", "passes_gates", "fraud_review", "selected_uniform_strict"]


@pytest.fixture(scope="module")
def result():
    return pipeline.run(XLSX)


@pytest.fixture(scope="module")
def merged(result):
    ref = pd.read_csv(REFERENCE)
    m = result["scorecard"].merge(ref, on=KEYS, how="outer", suffixes=("", "_ref"), indicator=True)
    assert (m["_merge"] == "both").all(), "Dasher set differs from the reference"
    assert len(m) == 54
    return m


def test_columns_match_reference(result):
    assert list(result["scorecard"].columns) == list(pd.read_csv(REFERENCE).columns)


def test_gates_and_tiers_identical(merged):
    for col in EXACT_COLS:
        assert (merged[col].astype(str) == merged[f"{col}_ref"].astype(str)).all(), col
    assert (merged["tier"].fillna("") == merged["tier_ref"].fillna("")).all()
    assert (merged["lifetime_star"] - merged["lifetime_star_ref"]).abs().max() <= 0.001   # reference rounds to 3 dp


def test_scores_within_0_001(merged):
    for col in RATE_COLS:
        gap = (merged[col] - merged[f"{col}_ref"]).abs().max()
        assert gap <= 0.001, f"{col}: max diff {gap:.5f}"


def test_tier_sizes_and_uniform_strict(result):
    sc = result["scorecard"]
    assert {m: int(((sc["MARKET_NAME"] == m) & (sc["tier"] == "Tier 1")).sum()) for m in ("Dashattan", "Doorlanta")} == {"Dashattan": 4, "Doorlanta": 10}
    assert sc.groupby("MARKET_NAME")["selected_uniform_strict"].sum().to_dict() == {"Dashattan": 1, "Doorlanta": 8}


def test_profile_and_log_facts(result):
    p = result["profile"]
    assert p["rows"] == 1200 and p["rows_per_city"] == {"Dashattan": 600, "Doorlanta": 600}
    assert p["missing_wait"] == {"total": 191, "no_arrival_logged": 124, "arrival_after_pickup": 67}
    assert p["date_window_per_city"]["Doorlanta"]["last"] == "2055-06-08"
    log = "\n".join(result["cleaning_log"])
    for fact in ["Dropped 6 trailing rows", "missing on 191 rows", "124 with no store arrival", "67 with the arrival stamped after pickup",
                 "Doorlanta 2055-06-01–2055-06-08 (600 orders)", "Dashattan 2055-06-01–2055-06-13 (600 orders)"]:
        assert fact in log, fact


def test_bike_cohort_top4(result):
    cohort = pipeline.bike_cohort(result["scorecard"])
    assert cohort.loc[cohort["top_4"], "DASHER"].tolist() == ["Ron", "Zak", "Bunje", "Rojan"]


# ---- Phase 5 sensitivity harness against pipeline.score()
def _tier1(sc):
    return {m: set(sc.loc[(sc["MARKET_NAME"] == m) & (sc["tier"] == "Tier 1"), "DASHER"]) for m in ("Dashattan", "Doorlanta")}


@pytest.fixture(scope="module")
def df():
    return pipeline.clean(pd.read_excel(XLSX))[0]


def test_sensitivity_reproduces_phase5(df, result):
    base = _tier1(result["scorecard"])
    assert _tier1(pipeline.score(df)) == base
    identical = [dict(wait_threshold=15), dict(weights={"reliability": 60, "quality": 20, "consistency": 10, "professionalism": 10}),
                 dict(weights={"reliability": 40, "quality": 40, "consistency": 10, "professionalism": 10}), dict(k=100), dict(k=400)]
    for params in identical:
        assert _tier1(pipeline.score(df, **params)) == base, params
    wait5 = _tier1(pipeline.score(df, wait_threshold=5))
    assert wait5["Dashattan"] == base["Dashattan"] and base["Doorlanta"] - wait5["Doorlanta"] == {"Cate"} and wait5["Doorlanta"] - base["Doorlanta"] == {"Ash"}
    sched = _tier1(pipeline.score(df, include_scheduled=True))
    assert sched["Dashattan"] == base["Dashattan"] and base["Doorlanta"] - sched["Doorlanta"] == {"Hersh"} and sched["Doorlanta"] - base["Doorlanta"] == {"Ash"}
