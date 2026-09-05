# R2B holdout guard

The R2B acquisition cutoff is archive month `2024-01`; the panel cutoff is
`2024-02-10T00:00:00Z`. No materializer or future executor may open a raw,
panel, or checkpoint path containing final-holdout data. Every decision,
entry, and exit timestamp must be strictly earlier than the timeframe-specific
holdout boundary. `final_holdout_accessed` remains `false` until an explicitly
authorized future study.

