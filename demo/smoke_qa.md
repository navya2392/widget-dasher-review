# Data-QA Review: Dasher Scoring Pipeline

## Anomalies

**BLOCKER** — Row 1339: `CONFIRM_TO_DELIVER_DURATION` mismatch indicates corrupted duration field, which directly drives late-min calculation and thus Dasher performance scores.

**BLOCKER** — Row 873: delivery timestamp precedes pickup timestamp, making transit-time computation negative and invalidating route-efficiency scoring.

**BLOCKER** — Row 200: estimated delivery time occurs after quoted delivery time, breaking the late/on-time determination logic.

**EXCLUDE_COLUMN** — `DELIVERY_RATING`: 51.3% missing exceeds typical thresholds and would bias customer-satisfaction component of composite scoring toward dashers with fewer rated orders.

**EXCLUDE_COLUMN** — `NUM_ON_TIME_DELIVERIES`: 40.9% missing prevents reliable historical on-time rate calculation for experience-weighted scoring.

**EXCLUDE_COLUMN** — `DASHER_TO_STORE_TIME_CATEGORY`: 26.8% missing (beyond the standing exclusion) confirms this field remains unreliable for travel-time bucketing.

**NOTE** — `DASHER_WAIT_DURATION`: 15.9% missing aligns with 10.3% missing `DASHER_AT_STORE_TIME` plus 67 arrival-after-pickup cases; wait-time scoring can proceed using available subset.

**NOTE** — `DASHER_TO_RESTAURANT_DURATION`: 11.0% missing is acceptable for optional pre-assignment routing analysis; core scoring uses confirm-to-deliver intervals.

**NOTE** — 8 arrivals logged before confirmation time suggest clock-sync issues but affect <1% of rows; non-blocking for aggregate Dasher metrics.

**NOTE** — Dasher "Lauran" logged multiple vehicle types; if vehicle consistency is a scoring input, flag this account for manual vehicle-type assignment.

**NOTE** — 9 fraud-flagged rows (0.75%) are within expected operational noise; exclude from scoring via existing `FRAUDULENT` filter.

**NOTE** — 7 first-delivery rows allow new-dasher cohort analysis but do not affect experienced-dasher scoring pipeline.

**NOTE** — Doorlanta date window (8 days) is 38% shorter than Dashattan (13 days); cross-city volume-per-dasher comparisons require normalization but within-city scoring remains valid.

---

**VERDICT:** HALT_FOR_REVIEW: Three distinct rows (200, 873, 1339) exhibit timestamp/duration inversions that corrupt core lateness and transit-time metrics.