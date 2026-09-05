# R3 Stage-A erratum 001 — forceOrder market routing

Date: 2026-08-30 UTC

The immutable `engineering_shadow_august_v3` evidence proved REST+WebSocket
connectivity and `ENGINEERING_SHADOW` isolation. It also preserved one observed
forceOrder payload for `ZKCUSDT` whose market discriminator was nested at
`payload["o"]["st"] = 1`. The earlier router inspected only the top-level
discriminator and therefore stored this valid USD-M event under `unknown`.

The v3 raw files and manifest are not rewritten. The router is corrected in a
later implementation with nested-first precedence and contradiction rejection;
the repaired behavior is qualified by fixture tests and will be used only by a
fresh v4 shadow root.
