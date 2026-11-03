**WEEKLY OPS BRIEFING — WIDGET DASHER PROGRAM**

**Summary**
This week: 20 Dashers passed gate across both markets (4 Dashattan, 16 Doorlanta, total 54 tracked). Four tier changes pending approval, one requiring urgent review. Data quality issue halts auto-approval; see QA note below.

**Tier Changes (Pending Approval)**

*Dashattan:*
- **Bill:** Tier 2 → Tier 1 (79.62 → 80.12, +0.5). Component breakdown not in this run's data.
- **Bret:** Tier 1 → Tier 2 (80.89 → 60.39, **-20.5**). Component breakdown not in this run's data. *Requires immediate review — see Flags.*

*Doorlanta:*
- **Hersh:** Tier 2 → Tier 1 (83.1 → 84.6, +1.5). Component breakdown not in this run's data.
- **Ash:** Tier 1 → Tier 2 (86.56 → 84.06, -2.5). Component breakdown not in this run's data.

**Flags Requiring Human Review**

*Fraud review queued (5 Dashers):*
- Dashattan: KC (92.5, Tier 1), Samm (84.6, Tier 1), Bret (60.4, Tier 2)
- Doorlanta: Hanna (90.7, Tier 1), Katelynn (90.5, Tier 1)

*Score drop > 5 points (1 Dasher):*
- Dashattan: **Bret** (80.89 → 60.39, -20.5). Now flagged for fraud review and tier demotion.

*Within 3 points of tier boundary (6 Dashers):*
- Dashattan: Carlee (80.4, within 0.3 of 80.1 cutoff)
- Doorlanta: Cate (86.6, within 2.5 of 84.6 cutoff and 2.5 of 84.1 cutoff), Hersh (84.6, at cutoff, within 0.5 of 84.1), Ash (84.1, at cutoff, within 0.5 of 84.6), Joe (84.0, within 0.6 of both cutoffs), Merissa (81.2, within 2.9 of 84.1 cutoff)

**Data Quality Note**
**VERDICT:** HALT_FOR_REVIEW: Three distinct rows (200, 873, 1339) exhibit timestamp/duration inversions that corrupt core lateness and transit-time metrics.