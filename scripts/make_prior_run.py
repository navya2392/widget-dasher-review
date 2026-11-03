"""Make demo/prior_scorecard.csv: a clearly labelled, perturbed copy of the real scorecard so the briefing's
run-over-run diff has something to diff against. DEMO ONLY — every row carries the label in its `note` column.

Perturbations (deterministic):
  - Doorlanta: Ash +2.5, Hersh -1.5  -> Ash crosses into Tier 1, Hersh drops to Tier 2
  - Dashattan: Bret +20.5, Bill -0.5 -> Bret crosses into Tier 1, Bill drops to Tier 2
  - six other gate-passers nudged by a seeded N(0, 0.6)
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
BOUNDARY_MOVES = {("Doorlanta", "Ash"): 2.5, ("Doorlanta", "Hersh"): -1.5, ("Dashattan", "Bret"): 20.5, ("Dashattan", "Bill"): -0.5}


def main():
    sc = pipeline.run(ROOT / "data" / "2026_Platform_Ops_Widget_Data.xlsx")["scorecard"].copy()
    key = list(zip(sc["MARKET_NAME"], sc["DASHER"]))
    for k, delta in BOUNDARY_MOVES.items():
        sc.loc[[x == k for x in key], "selection_score"] += delta
    rng = np.random.default_rng(0)
    others = sc[sc["passes_gates"] & ~sc.set_index(pipeline.KEYS).index.isin(list(BOUNDARY_MOVES))].sample(6, random_state=0).index
    sc.loc[others, "selection_score"] += rng.normal(0, 0.6, size=len(others)).round(2)
    sc = pipeline.assign_tiers(sc)
    sc["note"] = LABEL
    out = ROOT / "demo" / "prior_scorecard.csv"
    out.parent.mkdir(exist_ok=True)
    sc.to_csv(out, index=False)
    real = pipeline.run(ROOT / "data" / "2026_Platform_Ops_Widget_Data.xlsx")["scorecard"]
    d = pipeline.diff(real, sc)
    print(f"wrote {out} ({len(sc)} rows, label: {LABEL!r})")
    print("tier changes vs real:", [(c["market"], c["dasher"], c["prior_tier"], "->", c["current_tier"]) for c in d["tier_changes"]])


if __name__ == "__main__":
    main()
