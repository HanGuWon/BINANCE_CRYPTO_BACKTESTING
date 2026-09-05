# Cost Model (frozen)

- Spot: 10 bps taker fee + 5 bps slippage per side.
- UM: 5 bps taker fee + 5 bps slippage per side.
- Funding: every funding event crossed between entry fill and exit fill is
  charged at the signed event rate against LONG positions (negative rate =
  long receives). Events come from the same verified funding archives used
  in R1 materialization; no averaging or interpolation.
- Entry/exit always at executable open prices; no mid-price fills.
- Costs are applied identically across trials and cohorts.
