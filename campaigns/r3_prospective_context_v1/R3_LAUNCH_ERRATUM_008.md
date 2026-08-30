# R3 Launch Erratum 008 — Spot Duplicate Outside UM Ranking Scope

Date: 2026-08-30 KST

Independent re-audit confirms that the duplicate-timestamp finding cited in
Erratum 006 was in the Spot archive
`spot/klines/UMAUSDT/1d/UMAUSDT-1d-2026-07.zip` (32 rows, 31 unique opens,
`DUPLICATE_TIMESTAMP`, checksum `656cb8ae...`). It is not in the USD-M archive.

The R3 universe contract is explicitly USD-M. The corresponding UM archive has
31 rows, 31 unique opens, no `validate_klines(..., "1d")` issues, and verified
published/computed SHA256
`8e91dac17daac13d1f8701d533c7e5de67dc5751977cdda6445e340311695f17`.

Erratum 006 remains historically valid for the then-overly-broad mixed-market
verifier, but it is superseded as an R3 scientific blocker. The ranking
qualification is being repaired to discover and validate UM archives only;
Spot data is neither repaired nor deduplicated by this campaign.
