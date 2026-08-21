# R1 causal universe selection

At the beginning of each UTC calendar month, eligibility is evaluated using only
symbols observed strictly before that month. Quote volume is aggregated from the
immediately preceding completed month; no current-month or future-month volume is
allowed. Symbols are sorted by descending quote volume with symbol as a stable
tie-breaker. Top-20, Top-50, and Top-100 flags are diagnostics; Top-50 is frozen
and is not optimized. A missing prior month, negative volume, or a first observed
timestamp on/after the month start is ineligible and is recorded with an explicit
reason. Delisted symbols remain eligible in months before their observed end.

The current R1 branch contains the anchor-window implementation and metadata
contract. It does not turn today's exchange-info symbol list into historical
membership.
