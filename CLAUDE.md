# CLAUDE.md — Analysis Handoff: DoorDash Widget Case

You are assisting with a take-home case analysis. Your job is the **mechanics** — cleaning,
computation, reconciliation, chart generation, exports. The **judgment** — metric design,
thresholds, recommendations — is already decided and specified below. Do not change it.
Where something is ambiguous, STOP and ask; never resolve a judgment call silently.

## Operating contract

1. Work ONE phase at a time (phases below). At the end of each phase, STOP and report:
   what was computed, what reconciled, what didn't, and wait for approval before continuing.
2. Never proceed past an unreconciled number. If your result differs from
   `reference/KEY_NUMBERS.md`, diagnose the definition difference and report it — do not
   silently adopt either number.
3. Never invent, estimate, or fill a number you did not compute from `data/`.
4. Commit at each phase boundary with the message format given per phase.
5. All work goes in `analysis.ipynb` with markdown narration: each section starts with a
   markdown cell saying what it does and what decision it feeds. No dead/exploratory cells
   left behind.
6. The human will verify and must be able to defend every line in an interview. Prefer
   simple, readable pandas over clever one-liners.

## Repo layout

```
data/2026_Platform_Ops_Widget_Data.xlsx   ← raw input (never modify)
reference/KEY_NUMBERS.md                  ← reconciliation answer key
reference/dasher_scorecard.csv            ← scoring answer key
reference/Case_Study_Prompt.docx          ← original ask (context only)
reference/Widget_Delivery_Case_Deck.pdf   ← current deliverable (context only)
analysis.ipynb                            ← all analysis work
export_01..04_*.xlsx                      ← staged Excel exports (generated; gitignored)
```

## Dataset facts you need

- 1,200 valid deliveries (600 per city: Dashattan = market 4001, Doorlanta = 4050),
  June 1–13. 6 junk trailing rows (no MARKET_NAME; one holds a stray COMPOSITE_SCORE=34.5)
  and one phantom column `Unnamed: 38` must be dropped first.
- ALL `*_DURATION` columns are **seconds**. Convert to minutes before use.
- Timestamps are ISO8601; parse with `pd.to_datetime(col, format='ISO8601')`. UTC columns
  for arithmetic between timestamps; `*_GALAXY_A` columns (UTC−4 local) for any
  hour-of-day analysis; `ACTIVE_DATE` for daily counts.
- SUBTOTAL is in cents.
- Lifetime columns (NUM_DELIVERIES, COMPOSITE_STAR_RATING, NUM_FIVE_STARS,
  NUM_ON_TIME_DELIVERIES) are constant per Dasher — aggregate with `.last()`, never mean.
- EXCLUDED by design (do not use in any metric): COMPOSITE_SCORE (undocumented, r≈0.05
  vs ratings), NUM_ON_TIME_DELIVERIES (41% missing, internally inconsistent),
  DASHER_TO_STORE_TIME_CATEGORY (27% missing, unknown bucketing). CANCELLED_AT is 100%
  empty. One Dasher (Lauran, Doorlanta) has two vehicles across deliveries — vehicle is
  per-delivery.

## Metric definitions (exact; do not vary)

Row-level, in order:
1. `late_min = (ACTUAL_DELIVERY_TIME − QUOTED_DELIVERY_TIME)` in minutes. Late = `late_min > 0`
   (strict). Quoted, never estimated.
2. `wait_min = DASHER_WAIT_DURATION / 60`. Missing (~16%) stays NaN — never impute.
3. `excess_wait = max(wait_min − 10, 0)` with NaN wait → 0 (the one permitted fillna:
   missing wait means zero forgiveness).
4. `late_min_adj = late_min − excess_wait`; `is_late_adj = late_min_adj > 0`.
5. `severe = late_min_adj > 15` (on the adjusted number).
6. `assign_lag_min = (DASHER_ASSIGNED_TIME − CREATED_AT)` minutes; meaningful for ASAP only.
7. `buffer_min = (QUOTED − ESTIMATED)` minutes. Expect 0 scheduled, ~17 mean ASAP.
8. `late_vs_estimate = ACTUAL_DELIVERY > ESTIMATED`; ASAP mean ≈ 56%.
9. `hour_local = ACTUAL_DELIVERY_TIME_GALAXY_A.dt.hour`.
10. `arrival_logged = DASHER_AT_STORE_TIME.notna()`.

Dasher-level (filter `ASAP == 1` FIRST, then group by [MARKET_NAME, DASHER]):
- `ontime_adj = 1 − mean(is_late_adj)`; also compute `ontime_raw` the same way.
- `severe_rate = mean(severe)`; `asap_n` = group size.
- Lifetime profile via `.last()` per Dasher.
- `shrunk_rating = (n·star + 200·market_mean) / (n + 200)` where n = lifetime deliveries
  and market_mean = mean of lifetime star over the DEDUPLICATED Dasher table per market.
- `arrival_share` = mean of arrival_logged per Dasher over ALL orders (not ASAP-only).
- Score (0–100): `50·ontime_adj + 30·shrunk_rating/5 + 10·max(0, 1 − severe_rate/0.30)
  + 10·arrival_share`.
- Gates: vehicle set contains car or motorcycle · lifetime ≥ 100 (Dashattan) / 300
  (Doorlanta) · asap_n ≥ 5 / 10 · fraud flags > 0 → tag `fraud_review` (never exclude).
  Strategy note (changes no computation): the vehicle gate is a CONDITIONAL capability
  gate — cars presumed satchel-ready; bicycles conditional on a cargo-satchel fit pilot
  at onboarding. All metrics, gates, and tiers compute exactly as specified above; the
  conditional reading is a selection layer on top of the same scorecard.
- Tiers among gate-passers per market: Tier 1 = top 4 (Dashattan) / top 10 (Doorlanta)
  by score; remainder Tier 2 (activation floor 75 — display only).

Market-level (Q3 baselines):
- Adjusted late rate: ASAP-only per city (expect ~14% / 12%).
- Long-hold share: share of ALL deliveries with wait_min > 10 (expect ~30% both).
- Low-rating share: `(rating ≤ 3).sum() / rating.notna().sum()` — denominator is RATED
  deliveries only.

## Phases

### Phase 1 — Clean & derive
Load raw xlsx. Drop junk rows and phantom column. Parse timestamps. Build row-level
metrics 1–10. Maintain a markdown "cleaning log" cell recording each decision.
Hand-check row DELIVERY_NAME=930 against the spreadsheet (scheduled, missing wait,
quoted==estimated) and show the check in the notebook.
**Export:** `export_01_cleaned.xlsx`, sheet `cleaned_deliveries` (all columns + derived).
Strip tz before writing: `df[c] = df[c].dt.tz_localize(None)` on every parsed timestamp.
**Acceptance:** 1,200 rows; no `Unnamed` columns; the 10 derived fields present.
**Commit:** `phase 1: cleaning + derived fields`

### Phase 2 — Reconcile
Recompute every statistic in `reference/KEY_NUMBERS.md`. Produce a reconciliation table
in the notebook: metric | expected | computed | match. For any mismatch, diagnose the
definition difference and REPORT it; do not adjust definitions without approval.
**Export:** `export_02_reconciled.xlsx` adds sheet `city_summary`.
**Acceptance:** every KEY_NUMBERS stat matched or explicitly flagged with diagnosis, AND
the notebook's pre-scoring sections (Cleaning, Verification, Market comparison,
Measurement) are complete, narrated, and run clean top-to-bottom (Restart & Run All).
**HARD GATE:** this stop is the human's pre-scoring review of the full notebook. Present
a short reading guide (which cells show the cleaning log, the row-930 check, the
reconciliation table, the market/measurement analysis). Do not begin Phase 3 until the
human explicitly confirms they have reviewed the notebook.
**Commit:** `phase 2: reconciliation vs KEY_NUMBERS`

### Phase 3 — Scoring
Implement the Dasher-level spec above from THIS FILE (do not port other code). Diff the
result against `reference/dasher_scorecard.csv` on: gate pass/fail, each component,
score (±0.1), tier. Write a small assert-based test cell that re-checks the diff, so
later changes can't silently alter scores. Show KC, Josh, and Bret traced end-to-end.
Also in Phase 3:
- Conditional bike cohort view cell: Dashers failing ONLY the vehicle gate (bicycle)
  but meeting their market's lifetime and asap_n thresholds, ranked by score, top 4
  highlighted. Expect Ron, Zak, Bunje, Rojan (scores ~91–97). Display-only; the
  reference diff is unaffected.
- Uniform-strict reconciliation (moved here from Phase 2; the registry omitted the
  definition): widget-capable vehicle AND lifetime ≥ 300 AND asap_n ≥ 10 AND
  severe-late rate ≤ 10% AND adjusted on-time ≥ 85%, with missing severe-late treated
  as fail and missing on-time as 0. Expect 1 (Dashattan) / 8 (Doorlanta).
**Export:** `export_03_scorecard.xlsx` adds sheet `dasher_scorecard`.
**Acceptance:** scorecard diff clean; test cell passes; conditional cohort shown;
uniform-strict reconciles to 1/8 or is flagged with diagnosis.
**Commit:** `phase 3: scoring matches reference scorecard`

### Phase 4 — Exploratory sweep (timeboxed)
Run items 14–33 from the plan doc (subtotal bands vs lateness/rating; item count vs
wait; subtotal by city; day-of-week; daily trend; late rate by hour; assign lag by hour;
bike-vs-car speed within Dashattan; Dasher utilization; half-window consistency;
confirm-speed tail; rating response bias; rating vs minutes-late; rating vs wait; manual
assignments; fraud-row profile; estimate-error distribution incl. p80; vehicle
consistency; IS_FIRST exclusion check; correlation sweep |r|>0.2).
For EACH: compute, show one small table or plot, write ONE markdown line — "nothing" or
"candidate: <why>". No chart polishing. End with a findings summary cell listing
candidates for promotion. STOP for human review of candidates.
**Export (optional):** `export_04_explore.xlsx` with any sweep table worth pivoting.
**Commit:** `phase 4: exploratory sweep + findings log`

### Phase 5 — Sensitivity
Re-run Tier-1 selection under: wait threshold 5/10/15 · weights (60,20,10,10) and
(40,40,10,10) · k = 100/400 · scheduled orders included with a synthetic 17-min buffer.
Report overlap vs baseline Tier 1 per market. Expected: identical or one swap at margin.
**Acceptance:** results table matching (or correcting) the Appendix B claims.
**Commit:** `phase 5: sensitivity`

### Phase 6 — Polish
Clean the notebook (dead cells removed, narration complete, runs top-to-bottom via
Restart & Run All without errors). Final cell: summary of every slide stat with the
cell reference that produced it.
**Commit:** `phase 6: notebook final`

## Prohibitions

- Do not change metric definitions, weights, thresholds, gates, or tier sizes.
- Do not use the excluded columns in any computation.
- Do not add analyses beyond the listed phases without asking.
- Do not touch `data/` or `reference/` files.
- The deck and prompt in `reference/` are context only: never source a number from the
  deck — every figure must be computed from `data/` and reconciled via KEY_NUMBERS.md,
  the only answer key. The deck is the thing being validated, not a source.
- Do not write any narrative claiming a recommendation — recommendations live in the
  deck and belong to the human.

### Phase 7 — Pipeline refactor (after Phase 5; ask before starting)
Extract the notebook's logic into modules, no logic changes:
```
pipeline/cleaning.py   ← junk rows, phantom column, timestamps, derived fields 1–10
pipeline/qa.py         ← deterministic profiling (nulls, ranges, schema vs expected)
pipeline/scoring.py    ← dasher aggregates, gates, components, score, tiers
pipeline/briefing.py   ← run-over-run diff computation
run_pipeline.py        ← CLI: python run_pipeline.py <xlsx> → outputs/ (QA report,
                         scorecard.csv, tiers, briefing.md, excel export)
```
**Lock:** pipeline/scoring.py output must pass the same assert-vs-reference test as §5.
Add tests/test_scoring.py running that check standalone.
**AI stages:** qa.py and briefing.py each end with one Anthropic API call (model:
claude-sonnet, key from .env via python-dotenv), system prompts loaded from
prompts/qa_system.md and prompts/briefing_system.md — never inline. Hard constraints
in those files are non-negotiable: QA never invents statistics not in the profile;
briefing reports only numbers present in its input. Both calls wrapped in try/except —
on API failure, write the deterministic outputs and an "AI summary unavailable" note;
the pipeline never fails because the AI call did.
**Demo prior run:** scripts/make_prior_run.py creates a labelled, perturbed copy of the
scorecard ("simulated prior week — demo only") so the briefing's diff has something
to diff against.
**Acceptance:** one command produces all outputs on the case xlsx; lock test passes;
pipeline runs to completion with no API key present (degraded mode).
**Commit:** `phase 7: pipeline refactor + AI stages`

### Phase 8 — Streamlit demo (after Phase 7)
app.py imports pipeline/ (no logic in the app). Single page, four blocks:
upload xlsx → run; QA report (AI text + the profile table); scorecard (sortable,
fraud_review and tier visible, conditional bike cohort shown separately); briefing +
an "Approve tier changes" button that writes approved_tiers.csv with a timestamp —
the human gate, visible. Run instructions in README. No styling beyond defaults.
**Acceptance:** `streamlit run app.py` works from a fresh venv per README.
**Commit:** `phase 8: streamlit review app`