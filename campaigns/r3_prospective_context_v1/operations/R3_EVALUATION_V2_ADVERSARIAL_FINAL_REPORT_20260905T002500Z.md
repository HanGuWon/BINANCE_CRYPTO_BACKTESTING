# R3 evaluation amendment V2 — final outcome-blind governance report

Recorded 2026-09-05T00:25:00Z (2026-09-05 KST). This is a new, timestamped
report; prior reports and receipts are preserved and were not overwritten.
The report closes the adversarial contract work only. It does not authorize an
evaluation, materialize a response, read a return/PnL/performance field, or
access the final holdout or R2B2.

## 37 required fields

1. **Starting HEAD/origin.** The work phase started from
   `388c3252ace9da571125e1fa8d812b0479ef69db` with origin at the same SHA.

2. **Final HEAD/origin.** The governance descendants were pushed non-force as
   `522f1b445be10d1dc82fc2af7549a5290d84b605`,
   `9dbd3eaf2de02accff2bef02abe0457970680ea7`, and
   `3dabdfb47f13fb05cc079bee8ccb7224004c8774`; the final receipt-citation
   commit is reported separately after this report update. The remote is kept
   synchronized and no scientific source commit is changed.

3. **Scientific source-tree.** Frozen SHA256
   `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`, with
   frozen scientific implementation
   `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`. `git status --short --
   scripts src tests configs` is empty. The full worktree is intentionally
   dirty from pre-existing governance/archive files and `.codexclaw`; this is
   not represented as a clean whole-tree claim.

4. **Registry SHA.** `trial_registry.csv` SHA256
   `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`;
   exactly six primary rows, `R3_H01`–`R3_H06`.

5. **V1 SHA.** `R3_EVALUATION_AMENDMENT_V1.md` SHA256
   `27276b4d3b66d25c987fadbac531df3cfd741dbd43625406fdc342e89c2f1c39`;
   preserved byte-for-byte.

6. **V2 SHA.** `R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md` SHA256
   `ac788de08e77a5eb87b7b5a6619ada104668df3dc00f6908491ee2e1afa79672`.

7. **Horizon-map SHA.** `R3_EVALUATION_HORIZON_MAP_V1.json` SHA256
   `7cd935a33ac7ed47d1b9c7e037d5033b3add694934730eca5ebadda48fbb98e5`.
   The superseded map remains at
   `R3_EVALUATION_HORIZON_MAP_V1_SUPERSEDED_20260905.json` with SHA256
   `86dafd9c69ec43eb37cd3fb37d505d7e534de53607c8a601a8c321500eda7798`.

8. **H01 response window.** `FWD_15M`, `[T_exec, next completed 15m close]`,
   `log(C[T_exec+15m]/C[T_exec])`.

9. **H02 response window.** `FWD_1H`, `[T_exec, T_exec+60m]`,
   `log(C[T_exec+60m]/C[T_exec])`, with four complete native 15m endpoints.

10. **H03 response window.** `LIQ_CONT_15M`, `[T_exec, T_exec+15m]`,
    `log(C[event_symbol,T_exec+15m]/C[event_symbol,T_exec])`.

11. **H04 response window.** `LIQ_REVERSION_15M_TO_1H`,
    `[T_exec+15m, T_exec+60m]`,
    `log(C[event_symbol,T_exec+60m]/C[event_symbol,T_exec+15m])`.

12. **H05 response window.** `FWD_1H`, `[T_exec, T_exec+60m]`,
    `log(C[T_exec+60m]/C[T_exec])`.

13. **H06 response window.** `FWD_1H`, `[T_exec, T_exec+60m]`,
    `log(C[T_exec+60m]/C[T_exec])`.

14. **H03/H04 non-redundancy.** Both use one deduplicated candidate identity
    universe, but H04 has an independent two-endpoint eligibility filter and
    starts at the H03 +15m endpoint. It is an incremental interval, not the
    algebraic negative of H03.

15. **Six primary scalar tests.** H01: 2-df Wald omnibus for
    `H0: beta_spread=beta_microprice=0` in
    `Y=alpha+gamma*D+beta_s*spread_bps+beta_m*microprice_displacement+error`.
    H02: 3-df saturated four-cell Wald equality test for
    `Q=(sign(Delta close),sign(Delta OI))` in fixed `(++),(+-),(-+),(--)`
    order. H03: studentized mean of `u_e*Y_H03`, alternative `E[u_eY]>0`.
    H04: studentized mean of `-u_e*Y_H04`, alternative `E[-u_eY]>0`.
    H05: 2-df Wald omnibus for `H0: beta_f=beta_p=0` in
    `b*Y=alpha+beta_f*f+beta_p*p+error`. H06: 1-df Wald test of
    `H0: beta_O=0` in `s_BTC*Y=alpha+beta_O*(s_BTC*B)+error`.
    All family p-values are two-sided, block-residual wild-bootstrap
    studentized, 10,000 draws, seed 1729, inclusive tail `(1+exceedances)/10001`.

16. **H01 omnibus rule.** Full nuisance rank and tested rank exactly two are
    required; component p-values are forbidden.

17. **H02 omnibus rule.** All four cells and rank four are required; one
    three-df equality omnibus is primary, with cell means/contrasts secondary.

18. **H05 omnibus rule.** Funding and completed premium are jointly tested in
    one rank-two Wald omnibus; component fishing and mark-price substitution
    are forbidden.

19. **H06 orientation.** `s_BTC=sign(r_BTC)` and `O=s_BTC*B`; zero/non-finite
    BTC or empty breadth is ineligible. The primary response is `s_BTC*Y` and
    divergence remains `O<0`.

20. **Raw/unique forceOrder event counts.** The frozen metadata-only scan at
    2026-09-05T00:26:15Z saw 49,541 liquidation envelopes: 49,174 UM and 367
    CM. Under the frozen UM validator, valid identities and unique keys were
    both 0; duplicates and collisions were 0; all 49,541 were invalid
    (`ps_ENUM_INVALID`: 49,174; `MARKET_TYPE_NOT_UM`: 367). The earlier
    pre-wp3 inventory snapshot reported 34,538 raw liquidation records but did
    not emit strict unique accounting and is not an executable qualification.
    No invalid record contributes to H03/H04 minima.

21. **ForceOrder deduplication key.**
    `forceorder:v2:<lowercase SHA256(UTF-8 compact sorted canonical identity tuple JSON)>`,
    with identity tuple `(market_type,symbol,E_ms,T_ms,t_trade_id,S,o,f,q,p,ap,X,l,z,ps,st)`.
    The disjoint invariant is `raw=unique+duplicate+collision+invalid` (and
    the same per endpoint).

22. **Actual roster-month count.** One verified month (`2026-09`, 50 symbols,
    roster SHA `bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79`);
    August is explicitly unverified because replay proof is missing. The
    two-month gate therefore fails.

23. **Gap-to-block mapping rule.** Every explicit UTC interval maps to every
    touched UTC-6-hour block; overlaps count once per scope, source gaps are
    not imputed/backfilled, and a gap resets state. The latest completed
    inventory snapshot had 25 explicit restart-gap records and seven excluded
    UTC-6 blocks (aggregate mapped exclusions 174).

24. **Usable blocks by H01–H06.** The latest available outcome-blind inventory
    snapshot (before the live append race) emitted eligible block maps of:
    H01 `{2026-09-02T12:00:00Z}`; H02 `{2026-09-02T12:00:00Z}`; H03
    `{2026-09-02T12:00:00Z}`; H04 `{2026-09-02T12:00:00Z}`; H05
    `{2026-09-02T12:00:00Z}`; H06
    `{2026-09-02T12:00:00Z, 2026-09-03T18:00:00Z}`. A concurrent append-only
    inventory attempt failed closed on health/incident reconciliation
    (`health=(30,30)`, observed `(32,32)`); it created no receipt.

25. **Per-H block minima.** At least 30 usable UTC-6 blocks for each H.

26. **Per-H day minima.** At least 30 usable UTC days for each H.

27. **Per-roster contribution requirement.** Every used verified roster SHA
    must contribute at least one complete record to every H; unused or
    unverified roster artifacts do not count.

28. **Global calendar/block minimum.** At least 30 independent UTC days and
    120 independent UTC-6 blocks, plus two verified roster months. The current
    metadata snapshot has 3 observed days, 9 raw blocks, and 2 effective blocks,
    so it cannot pass.

29. **Evaluation/confirmatory split.** Evaluation, if separately authorized in
    the future, is limited to eligible pre-holdout R3 cycles. The separately
    sealed post-boundary confirmatory holdout cannot satisfy any response,
    gap, minimum, or p-value requirement and remains inaccessible.

30. **Readiness-checker test result.** PASS for the synthetic/adversarial
    checker suite and metadata verifiers: 58 targeted tests in the wp4
    receipt; registry, horizon, inventory, and operations verifiers PASS.
    The strict inventory verifier reports `metadata_only=true` and
    `root_accessed=false`; no evaluation was run.

31. **Current cycle count.** The latest exact-v8 metadata watch observed 168
    completed cycles and 168 manifest entries. The live collector was safely
    resumed through the approved launcher after archiving a stale lock whose
    PID was absent.

32. **Collector writer count.** One authorized writer, zero duplicate writers,
    live lock PID 160284 at the post-resume watch. The collector session is
    left running.

33. **Chain/seal state.** Manifest chain verification `true`; launch seal
    `SEALED` with manifest SHA
    `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659` and
    seal SHA `ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85`.
    Watchdog is `YELLOW` only for the recorded restart/source gap; the prior
    firewall audit's `root_stable_during_audit=false` was an append-only write
    during observation, not an identity or chain failure.

34. **Outcomes.** `NOT_STARTED`; outcome values were not accessed.

35. **Final holdout.** `UNTOUCHED`.

36. **R2B2.** `NOT_STARTED`.

37. **Exact final state.** `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`.
    This state is intentionally not evaluation-ready: calendar, roster, and
    per-H minima are unmet, human authorization is false, and strict live
    forceOrder identity validation currently yields no admissible unique
    records.

## Receipts and provenance

- Full pytest receipt: `operations/R3_V2_FULL_PYTEST_RECEIPT_20260905.json`
  (331 passed, 1 warning in 121.27s, exit code 0); immutable cxc receipt copy
  `operations/R3_V2_CXC_TEST_RECEIPT_20260905T004218Z.json` has SHA256
  `d1e5a2f213ab4e8785fa0ad761a88082df4d8cc215c66bf1b1ae6c45993f4425`.
  Its global `dirty=true` is recorded honestly; scientific scope is clean.
- V2 reproducibility manifest SHA256
  `0cb2400f2ada8cc35882563d49af14f8e33e4148f21cc128ce02c8127849a104`.
- ForceOrder matrix SHA256
  `31802e1e09c6b1558cbb0a6938609fe36b15722bb4870ab0656e24ff09de77f6`;
  superseded V1 matrix SHA256
  `cedb4b0e8c41db89dbe38987f425f27fa0fe6b8d80a675880b870f767bb5ca58`.
- Exact-v8 identity pins: implementation `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`,
  source tree `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`,
  registry `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`,
  root `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`.

No R3 evaluation, response materialization, return/PnL/performance analysis,
final-holdout access, or R2B2 launch is permitted by this report.
