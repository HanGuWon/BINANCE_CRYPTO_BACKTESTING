# Premium provenance audit supersession

The original \`premium_provenance_summary.json\` and \`premium_coverage_audit.csv\`
in this directory were generated with the historical R1 derivative anchor
manifest (\`data/census/r1_full_history_v1/derivative_archive_manifest.csv\`).
That input contains only the BTCUSDT/ETHUSDT anchor lineage (158 rows), so its
2-symbol result was not an audit of the R2B acquisition.

Those files are preserved as:

* \`premium_provenance_summary.stale_r1_anchor_20260827.json\`
* \`premium_coverage_audit.stale_r1_anchor_20260827.csv\`

The canonical replacements were generated read-only on 2026-08-27 from
\`campaigns/r2b_restricted_derivatives_v1/premium_archive_manifest.csv\`, which
is constrained by \`scripts/audit_r2b_premium_coverage.py\` to
\`dataset=premiumIndexKlines\`, \`market=um\`, \`interval=15m\`, all checksums PASS,
and a non-anchor multi-symbol lineage. The regenerated audit reports 189
acquired symbols and 5,647 verified manifest rows against the
\`r2b_restricted_derivatives_v1_repaired_v2_causal3\` root.
