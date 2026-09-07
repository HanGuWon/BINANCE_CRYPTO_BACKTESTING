# Evidence Grading & Promotion Policy (frozen before any outcome run)

Grade A (STRONG): FDR q <= 0.05 AND HAC |t| >= 3 AND >= 75% positive-fold
sign consistency AND survives yearly + Top20/Top100 cohort cuts qualitatively.

Grade B (MODERATE): FDR q <= 0.10 AND HAC |t| >= 2 AND >= 60% fold
consistency.

Grade C (WEAK): nominal p < 0.05 but failing one Grade B condition.

Grade D (NO EVIDENCE): everything else.

Rules:

- Grades apply ONLY to pre-holdout (train+validation) evidence.
- Nothing is promoted into production or holdout testing by this policy.
- Any Grade A/B indicator becomes eligible for a SEPARATE future holdout
  campaign with its own preregistration; this document grants no such
  authorization.
- Performance claims beyond these grades are prohibited.
