Data-QA Report: Dasher Scoring Pipeline

Schema and structure

Schema: 38 of 38 expected columns present, none missing, none unexpected. NOTE: no drift, and the 12 derived fields are all present.
Duplicates: 0 duplicate DELIVERY_NAME values. NOTE: no double-counted deliveries.
Rows: 1,200 total, 600 per city, and the ASAP/scheduled split is 1,126/74. NOTE: balanced sample, so neither city dominates scoring.
City windows: Dashattan runs 13 days (Jun 1-13) and Doorlanta 8 days (Jun 1-8). NOTE: known and accepted extract design, but Doorlanta Dashers have fewer days of exposure when comparing volume-based metrics across cities.

Missing values

DELIVERY_RATING missing, 616 rows (51.3%): NOTE. Known and accepted: unrated deliveries stay out of rating denominators, so rating-based scores rest on about 584 rated deliveries.
DASHER_WAIT_DURATION and wait_min missing, 191 rows (15.9%): NOTE. Known and accepted: kept NaN with no forgiveness applied. The breakdown (124 no arrival logged, 67 arrival after pickup) sums to 191, consistent with the profile.
DASHER_AT_STORE_TIME and DASHER_AT_STORE_TIME_GALAXY_A missing, 124 rows (10.3%): NOTE. These match the 124 "no arrival logged" rows, so the gap is internally consistent.
DASHER_TO_RESTAURANT_DURATION missing, 132 rows (11.0%): NOTE. Covers the 124 no-arrival rows plus the 8 arrival-before-confirmation rows, and the field is unused.
RESTAURANT_TO_CUSTOMER_DURATION missing, 1 row (0.1%): NOTE. Negligible, but any metric using this field should skip that row.

Standing exclusions

COMPOSITE_SCORE, NUM_ON_TIME_DELIVERIES (40.9% missing), DASHER_TO_STORE_TIME_CATEGORY (26.8% missing) and CANCELLED_AT (100% missing): NOTE. Exclu

[truncated at max_tokens]
