# Phase 6 — governance commit, immutable report, and collection-only handoff

## Scope and hard stop

Commit and push only governance/operations documentation and receipts needed
to close the adversarial V2 contract. Do not change scientific source files,
the D-backed scientific root, the collector, the response/return layers, or
any holdout/R2B2 artifact. Do not run an evaluation or inspect performance.

## Required evidence

1. Produce a new timestamped immutable final V2 report (never overwrite prior
   reports) that states the branch, frozen scientific implementation
   and source-tree identities, registry and horizon-map hashes, V1/V2 amendment
   hashes, dependency/inventory hashes, forceOrder identity contract, roster
   and gap accounting, per-horizon minima, global calendar gates, checker and
   qualification receipts, collector identity/watch results, and the exact
   collection-only final state.
2. Explicitly preserve the concurrent append-only collector caveat: a firewall
   audit may report `root_stable_during_audit=false` when the live collector
   appends bytes, while identity, writer, chain, seal, and outcome-blind
   predicates remain independently verified.
3. Verify the scientific scope (`scripts`, `src`, `tests`, `configs`) is clean;
   do not stage unrelated historical/untracked artifacts or `.codexclaw`.
4. Commit the report and plan as governance-only changes and push the branch
   with a non-force `git push`. Record both the unchanged frozen scientific
   implementation commit and the new governance commit separately, together
   with remote alignment and final Git scientific-content status.

## Exit condition

The phase exits only after the report is committed and pushed, the collector
remains running, final holdout and R2B2 remain untouched/not started, and the
repository is explicitly reported as
`R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`.
