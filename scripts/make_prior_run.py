"""Make demo/prior_scorecard.csv: a clearly labelled, perturbed copy of the real scorecard so the briefing's
run-over-run diff has something to diff against. DEMO ONLY — every row carries the label in its `note` column.

Perturbations are applied to a COMPONENT (so the briefing can name what drove a tier change), the underlying
rate is moved consistently, and selection_score is re-summed:
  - Doorlanta Ash    reliability +2.5  (adjusted on-time +0.05)  -> crosses into Tier 1
  - Doorlanta Hersh  consistency -1.5  (severe-late rate +0.045) -> drops to Tier 2
  - Dashattan Bret   reliability +20.5 (adjusted on-time +0.41)  -> crosses into Tier 1
  - Dashattan Bill   consistency -0.5  (severe-late rate +0.015) -> drops to Tier 2
  - six other gate-passers: quality nudged by a seeded N(0, 0.6), shrunk rating moved consistently
Tiers are re-derived with pipeline.assign_tiers so the prior file is internally consistent.

Run:  .venv\\Scripts\\python scripts/make_prior_run.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline  # noqa: E402

LABEL = "simulated prior week — demo only"
XLSX = ROOT / "data" / "2026_Platform_Ops_Widget_Data.xlsx"
COMPONENT_MOVES = {  # (market, dasher): (component column, points)
    ("Doorlanta", "Ash"): ("pts_reliability", 2.5),
    ("Doorlanta", "Hersh"): ("pts_consistency", -1.5),
    ("Dashattan", "Bret"): ("pts_reliability", 20.5),
    ("Dashattan", "Bill"): ("pts_consistency", -0.5),
}
PTS = ["pts_reliability", "pts_quality", "pts_consistency", "pts_professionalism"]
W = pipeline.WEIGHTS


def _sync_rates(sc):
    """Keep the rate columns consistent with the perturbed components."""
    sc["ontime_adj"] = sc["pts_reliability"] / W["reliability"]
    sc["severe_late_rate"] = (1 - sc["pts_consistency"] / W["consistency"]) * pipeline.SEVERE_CAP
    sc["shrunk_rating"] = sc["pts_quality"] / W["quality"] * 5
    sc["selection_score"] = sc[PTS].sum(axis=1)
    return sc


def main():
    real = pipeline.run(XLSX)["scorecard"]
    sc = real.copy()
    idx = sc.set_index(pipeline.KEYS).index
    for key, (col, pts) in COMPONENT_MOVES.items():
        sc.loc[idx == key, col] += pts
    rng = np.random.default_rng(0)
    others = sc[sc["passes_gates"] & ~idx.isin(list(COMPONENT_MOVES))].sample(6, random_state=0).index
    sc.loc[others, "pts_quality"] += rng.normal(0, 0.6, size=len(others)).round(2)
    sc = pipeline.assign_tiers(_sync_rates(sc))
    sc["note"] = LABEL
    out = ROOT / "demo" / "prior_scorecard.csv"
    out.parent.mkdir(exist_ok=True)
    sc.to_csv(out, index=False)
    d = pipeline.diff(real, sc)
    print(f"wrote {out} ({len(sc)} rows, label: {LABEL!r})")
    for c in d["tier_changes"]:
        print(f"  {c['market']} {c['dasher']}: prior {c['prior_tier']} ({c['prior_score']}) -> current {c['current_tier']} ({c['current_score']})")


if __name__ == "__main__":
    main()
