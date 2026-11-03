**Summary**
- This is 1,200 deliveries from two cities (Dashattan, Doorlanta), and the structure matches what we expect.
- It is fit for scoring. Every issue found is either a design decision you have already accepted or a minor side note.
- Two things worth knowing: the two cities cover different date windows, and one derived field (assign_lag_min) has an extreme maximum.

**Anomalies**

- **NOTE** — Schema: 38 of 38 columns present, none missing or unexpected. Drift check is clean.
- **NOTE** — Duplicates: zero duplicate DELIVERY_NAME values, so no double-counted deliveries.
- **NOTE** — DELIVERY_RATING missing (51.3%): accepted. Unrated deliveries stay out of rating denominators, so rating-based scores rest on about half the rows.
- **NOTE** — DASHER_WAIT_DURATION missing (15.9%, 191 rows; 124 no arrival logged, 67 arrival after pickup): accepted. Kept NaN and given zero wait forgiveness, so affected Dashers get no credit for waits we cannot measure.
- **NOTE** — Rows 200, 873, 1339 timestamp inversions: accepted. No in-scope metric uses the affected fields.
- **NOTE** — 8 rows with store arrival before confirmation, plus DASHER_TO_RESTAURANT_DURATION blank (132 rows, 11.0%): accepted. The field is unused.
- **NOTE** — IS_FIRST_DELIVERY unreliable (7 flagged rows): accepted. Nothing uses it.
- **NOTE** — Standing exclusions (COMPOSITE_SCORE, NUM_ON_TIME_DELIVERIES, DASHER_TO_STORE_TIME_CATEGORY, CANCELLED_AT): excluded by design, and the profile's excluded_columns list matches exactly. CANCELLED_AT is 100% null, consistent with this.
- **NOTE** — Date windows differ: Dashattan runs 13 days, Doorlanta 8. Accepted. Cross-city comparisons should use rates, not totals.
- **NOTE** — Lauran uses two vehicles: accepted. Vehicle is treated per delivery.
- **NOTE** — 9 FRAUDULENT-flagged rows: accepted. They route to manual review (fraud_review) and are not dropped.
- **NOTE** — assign_lag_min has a max of 5,666.78 minutes (about 3.9 days) against a median of 4.64. This is not on the accepted list. It cannot be a real assignment delay within a 13-day window. It is a derived field and the profile does not show how many rows are affected, so I cannot size it. Worth a quick look if assign_lag_min feeds any scored metric.
- **NOTE** — RESTAURANT_TO_CUSTOMER_DURATION is missing on 1 row (0.1%). This is negligible, but the profile does not say whether any in-scope metric uses it.

VERDICT: PROCEED
