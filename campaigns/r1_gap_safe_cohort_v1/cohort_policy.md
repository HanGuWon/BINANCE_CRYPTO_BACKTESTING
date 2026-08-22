# R1.6 cohort policy

For universe month M, the ranking source is only the completed calendar month
M-1. A symbol must have existed before the beginning of M-1, have a complete
usable M-1 archive, and pass the frozen asset taxonomy. Partial months are
diagnostic exclusions, never silently filled.

Spot and UM are ranked independently. Ties are broken by lexical symbol order
only after identical quote volume. Top-20, Top-50, and Top-100 are persisted;
Top-50 is primary. Current-month and future-month observations cannot change
membership for M.

The all-USDT diagnostic cohort is retained separately and is never substituted
for the primary crypto cohort.
