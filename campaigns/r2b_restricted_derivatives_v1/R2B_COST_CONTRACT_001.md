# R2B cost and funding contract 001

UM taker fee is 5 bps per executed leg and slippage is 5 bps per executed leg.
The normal two-leg burden is therefore 20 bps before funding. These are frozen
research assumptions and are not replaced by current exchange fees.

For LONG direction `+1` and SHORT direction `-1`:

```text
funding_cashflow = -side_direction × sum(funding_rate for events in (entry_time, exit_time])
net_return = gross_return - 0.002 + funding_cashflow
```

No funding interpolation or synthetic grid is permitted; only actual crossed
events are included.
