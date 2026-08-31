# R3 v5 boundary-timing clarification (append-only)

Recorded 2026-08-31 UTC before the August close.

`engineering_shadow_august_v5_retry` remains valid and unchanged as an
architecture/path qualification. It used real Binance REST requests, the
persistent collector implementation, a persistent `forceOrder` WebSocket
worker, and absolute logical 15-minute boundaries. However, its four target
boundaries were deliberately supplied in the past with
`wait_for_boundary=False`. The cycles therefore ran back-to-back rather than
being separated by four consecutive wall-clock 15-minute waits.

This distinction does not invalidate v5; it defines its evidence precisely.
The v6 root is the separate real wall-clock burn-in and must not reuse v5
evidence files or manifest-chain state.

For preservation checking, the v5 retry root tree SHA256 at clarification time
is `afee8d871c734a1df3574a96e00fb7b6c7c495ee646aa7f7b51f9a33332803d8`.

This clarification is metadata only; it does not alter the v5 root, receipt,
manifest chain, roster, or any scientific/outcome artifact.
