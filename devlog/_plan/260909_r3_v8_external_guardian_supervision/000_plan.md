# R3 v8 external guardian supervision — execution plan

## Objective

Finalize exactly one OS-level external supervisor for the already-sealed September v8 collector. The supervisor is one-shot, operations-only, and may inspect state or archive proven stale locks, but it may launch only the canonical persistent guardian. It never launches the collector, mints child authorization, edits scientific data, runs Batch 002, reads outcomes, or accesses the final holdout.

## Frozen identity and prohibitions

Implementation ecebc49dff41eeec33af62c2c85a75c5a0bd2922; scientific source-tree SHA b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688; registry c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a; September roster bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79; standing policy SHA 6a23cf36e00b15ed5e5a46f1273052e946699a8e21a32b56588c4ae4f82e1e7c, expiry 2026-10-01T00:00:00Z. Batch 001 is immutable and scientifically verified. No Batch 002, outcomes, PnL, R2B2, backfill, October roster/transition, or holdout access.

## Work phases

- WP0: fresh census, live-state resolution, identity and firewall baseline.
- WP1: one-shot supervisor implementation and distinct lock; stale-lock evidence and guardian-only relaunch.
- WP2: synthetic qualification, one safe Task Scheduler registration attempt, privilege/credential audit, no-destructive-reboot proof.
- WP3: live NO_ACTION and repeated scheduler/no-duplication checks, append-only receipts, Batch 001/outcome firewall, closeout.

## Required artifacts

R3_V8_EXTERNAL_SUPERVISOR_CONTRACT_20260909.json, R3_V8_EXTERNAL_SUPERVISOR_QUALIFICATION_20260909.json, R3_V8_EXTERNAL_SUPERVISOR_INSTALLATION_20260909.json, R3_V8_EXTERNAL_SUPERVISOR_LIVE_NOOP_20260909.json, and R3_V8_EXTERNAL_SUPERVISION_CLOSEOUT_20260909.json, plus tests and source commits. Prior supervision decision remains untouched.

## Safety gates

Never stop a healthy process or intentionally kill/reboot. Any ambiguity returns BLOCK. Task Scheduler registration is attempted once only; permission denial becomes an explicit partial-hardening state and is not retried. The final report must distinguish mid-session, post-login, and pre-login coverage and leave the healthy guardian and collector running.