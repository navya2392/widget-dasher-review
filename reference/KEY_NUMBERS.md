# Key numbers for slides (all verified against cleaned data)

## Market overview (June 1–13, 600 deliveries/city)
- Dashers: 24 Dashattan / 30 Doorlanta
- Raw late rate (vs. quoted): 19% Dashattan / 16% Doorlanta
- Adjusted late rate (ASAP, merchant holds >10 min forgiven): 14% / 12%
- Median confirm-to-delivery: 32 min / 35 min; avg rating 4.55 / 4.56
- Median travel-to-customer: 12.1 min / 13.8 min; p90 ~23 min BOTH cities → one satchel spec (~30-min hold)

## Q1 — Selection
- Vehicle mix: Dashattan 62% bicycle; only 8 car Dashers; KC = 62% of Dashattan car deliveries; KC has 2 fraud flags (1.4% of his 143 observed)
- Lateness attribution: 40% of late deliveries had a merchant hold >10 min ("2 in 5"); slow dispatch compounds it (late rate 12%→26% from fastest to slowest assignment-lag quartile)
- Uniform strict criteria qualify: 1 Dashattan / 8 Doorlanta. City-calibrated gates: 5 / 15 (Tier 1 = top 4 / top 10 by score)
- Scoring: gates (vehicle, experience 100/300, sample 5/10, fraud review) → score /100 = Reliability 50 (adjusted on-time: late only if (actual−quoted)−max(wait−10m,0)>0, ASAP only) + Quality 30 (rating shrunk k=200) + Consistency 10 (1−severe-late/30%) + Professionalism 10 (arrival-logged share) → Tier 1 launch / Tier 2 bench (activation ≥75) + 20-order probation. Tier-1 cohort stable across thresholds & weights (≤1 swap).
- Wait adjustment proof: Josh (Doorlanta) 80%→95% on-time (rank 7→2); Merissa +21pt; Lauran/Matt barely move

## Q2 — Satchels
- Density: 90,909 vs. 3,731 residents/sq mi (24x) → hub pickup (Dashattan) vs. ship-to-home (Doorlanta)
- Sizing per 1,000 daily food orders: 350 widget orders → ÷6 per Dasher-day → ~58 Dashers → ×1.3 → ~76 satchels
- Demand peaks: lunch (11–14) & dinner (18–20) local → onboarding events 9–11am / 2–5pm

## Q3 — Measurement
- Scheduled orders: 27% late vs. 17% ASAP; quote buffer = 0 min scheduled vs. ~17 min ASAP → fix promise logic
- Batched late rate: 35% vs. 16% (Dashattan), 19% vs. 15% (Doorlanta) → no widget batching
- Proposed targets vs. baselines: adjusted late ≤5% (vs. 12–14%); long merchant holds ≤10% (vs. ~30%); low ratings ≤5% (vs. ~11–13%)

## Data quality (appendix)
- 6 junk trailing rows removed (one held the stray COMPOSITE_SCORE=34.5); phantom extra column dropped
- NUM_ON_TIME_DELIVERIES excluded (41% missing; implies impossible 1–77% lifetime on-time)
- COMPOSITE_SCORE excluded (undocumented; r≈0.05–0.09 vs. both rating columns)
- CANCELLED_AT 100% empty → completion rate unmeasurable, flagged as desired metric
- FRAUDULENT attribution unknown (customer vs. Dasher) → review trigger, not auto-exclusion
- Local-time (Galaxy A, UTC−4) columns used for all hour-of-day analysis

## Restructure notes (final deck flow)
- Flow: Exec → 2a Measurement (attribution + promise gap; implications → Q1 scoring & Q3 fixes) → 2b Markets (vehicle mix + concentration/variance/density-swell/batching callouts) → Q1 mechanism → Q2 satchels (hourly + sizing; density as callout) → Q3 framework + launch rules → AI slide · Appendix A–E
- 2a/2b are a shared evidence base feeding all three answers (1-1-1 on recommendation slides)
- Batching, ASAP-only: Dashattan 33% vs 16% late; Doorlanta 16% vs 15% (no penalty) → Dashattan-only launch rule
- Vs-estimate proof: ASAP orders would be 56% "late" against the raw estimate → quoted promise is the fair benchmark
- Scheduled orders: 6.2% of volume, median 2 per Dasher; with a synthetic 17-min buffer their late rate is ~1% → lateness is quote design. Robustness: including them leaves Tier 1 unchanged (Dash.) / 9 of 10 (Door.)
- Launch rules (Q3): no Dashattan widget batching · buffer scheduled widget quotes · priority dispatch for widgets (then track widget assignment lag vs food)
