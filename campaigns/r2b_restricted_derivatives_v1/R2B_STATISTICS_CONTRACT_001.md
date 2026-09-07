# R2B statistics contract 001

The primary unit is the time-indexed aggregate decision-time portfolio series,
with equal weights across simultaneous eligible active signals. Coins are not
treated as independent observations. Newey-West/HAC is applied to this series
with the repository's deterministic lag-selection implementation frozen before
outcomes. Calendar-block bootstrap preserves all symbols jointly, uses 1,000
samples, and seed 1729. Bootstrap blocks are calendar months.

The complete multiple-testing family is all 72 preregistered hypotheses.
Primary multiplicity control is Benjamini-Hochberg FDR at q=0.05; Bonferroni is
descriptive secondary only. The two polarity variants are structurally
dependent, and no independence claim is made.
