Data-QA Report: Dasher Scoring Pipeline

Schema and structure

NOTE: Schema matches expected (38 of 38 columns, none missing, none unexpected), so the scoring logic reads the fields it expects.
NOTE: 0 duplicate DELIVERY_NAME values, so no delivery is double-counted in any Dasher's score.
NOTE: 1,200 rows split 600/600 across Dashattan and Doorlanta, so neither city dominates the comparison.
NOTE: Doorlanta's window is 8 days (ends June 8) vs. Dashattan's 13 (ends June 13); on the accepted list as an extract design choice, but per-city volumes are not like-for-like.

Missingness

NOTE: DELIVERY_RATING is missing on 616 rows (51.3%); accepted, as it means not rated, and rating metrics use rated-only denominators.
NOTE: DASHER_WAIT_DURATION is missing on 191 rows (15.9%; 124 no arrival logged, 67 arrival after pickup); accepted, kept NaN with no wait forgiveness and never imputed.
NOTE: DASHER_AT_STORE_TIME and DASHER_AT_STORE_TIME_GALAXY_A are each missing on 124 rows (10.3%), matching the 124 no-arrival rows above, so the pattern is consistent.
NOTE: DASHER_TO_RESTAURANT_DURATION is missing on 132 rows (11.0%), covering the 8 known arrival-before-confirmation rows; accepted and unused.
NOTE: RESTAURANT_TO_CUSTOMER_DURATION is missing on 1 row (0.1%); too small to move any Dasher's score.
NOTE: CANCELLED_AT (100% null), COMPOSITE_SCORE, NUM_ON_TIME_DELIVERIES (40.9% null) and DASHER_TO_STORE_TIME_CATEGORY (26.8% null) are standing exclusions and stay out of scoring.

Value ranges

NOTE: DELIVERY_RATING spans 1.0 to 5.0 and COMPOSITE_STAR_RATING 3.82 to 5.0; both are within valid star ranges.
NOTE: SUBTOTAL (400 to 7,500), TOTAL_ITEM_COUNT (1 to 47), CONFIRM_TO_DELIVER_DURATION (429 to 12,391) and RESTAURANT_TO_CUSTOMER_DURATION (7 to 10,987) show no negatives or impossible values in the profile. The long-tail maxes are worth a glance but not anomalous on their own.
NOTE: assign_lag_min runs from 0.04 to 5,666.78 minutes (about 3.9 days) against a median of 4.64; a few extreme assignment lags exist, so any metric using assign_lag_min should use a robust statistic (median or capped), not a mean. The profile does not say which rows these are.
NOTE: late_min ranges from -61.88 to 179.43 with a median of -14.81, so most deliveries arrive early and the tail is plausible.

Known anomaly rows (all on the accepted list)

NOTE: Rows 200 (estimate later than quote), 873 (delivered before pickup) and 1339 (CONFIRM_TO_DELIVER_DURATION off by 39 s) are known timestamp inversions; no in-scope metric uses the affected fields.
NOTE: 8 rows have store arrival stamped before confirmation; known, with DASHER_TO_RESTAURANT_DURATION blank there and unused.
NOTE: IS_FIRST_DELIVERY is unreliable on 7 flagged rows; used by nothing.
NOTE: 9 FRAUDULENT-flagged rows go to fraud_review, not exclusion.
NOTE: Lauran (Doorlanta) uses two vehicles; handled per delivery and accepted.

Derived fields

NOTE: All 12 derived fields are present; wait_min's 15.9% missing matches DASHER_WAIT_DURATION exactly.
NOTE: buffer_min averages 0.0 for non-ASAP rows and 17.38 for ASAP rows, a clean split that is plausible given 1,126 ASAP and 74

[truncated at max_tokens]
