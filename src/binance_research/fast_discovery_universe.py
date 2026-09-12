"""Point-in-time Top50 universe construction for Fast Discovery V2."""
from __future__ import annotations

import hashlib

import pandas as pd

from .panel import select_verified_causal_liquidity_universe


def _hash_frame(frame: pd.DataFrame) -> str:
    ordered = frame.reindex(columns=sorted(frame.columns)).reset_index(drop=True)
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=True).values.tobytes()).hexdigest()


def build_point_in_time_top50(
    monthly_volume: pd.DataFrame,
    *,
    minimum_coverage_ratio: float = 1.0,
) -> pd.DataFrame:
    """Build deterministic market/month Top50 membership from prior-month data only.

    ``monthly_volume`` must contain verified prior-month quote volume and the
    first archive observation. The underlying validator rejects a non-adjacent
    volume month, incomplete prior-month coverage, and symbols first observed
    on/after the volume month. No bar or outcome columns are consumed.
    """
    result = select_verified_causal_liquidity_universe(
        monthly_volume,
        top_n=50,
        minimum_coverage_ratio=minimum_coverage_ratio,
    )
    if result.duplicated(["market", "universe_month", "symbol"]).any():
        raise ValueError("Top50 membership is not unique by market/month/symbol")
    selected_counts = result.groupby(["market", "universe_month"], sort=False)["selected_top50"].sum()
    if selected_counts.empty or (selected_counts > 50).any():
        raise ValueError("invalid Top50 count")
    result.attrs["membership_sha256"] = _hash_frame(result)
    result.attrs["selection_rule"] = "prior_month_quote_volume; complete prior month; first_observed before volume month"
    result.attrs["holdout_status"] = "UNTOUCHED"
    return result


def attach_point_in_time_top50(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    market: str,
) -> pd.DataFrame:
    """Attach frozen Top50 membership to bars without cross-market leakage."""
    required_bars = {"open_time", "symbol"}
    if missing := required_bars - set(bars.columns):
        raise ValueError(f"bars missing columns: {', '.join(sorted(missing))}")
    required_membership = {"market", "universe_month", "symbol", "selected_top50"}
    if missing := required_membership - set(membership.columns):
        raise ValueError(f"membership missing columns: {', '.join(sorted(missing))}")
    frame = bars.copy()
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True, errors="raise")
    frame["symbol"] = frame["symbol"].astype(str)
    frame["universe_month"] = frame["open_time"].dt.strftime("%Y-%m")
    cohort = membership.copy()
    cohort["market"] = cohort["market"].astype(str)
    cohort["symbol"] = cohort["symbol"].astype(str)
    cohort["universe_month"] = pd.to_datetime(cohort["universe_month"], utc=True, errors="raise").dt.strftime("%Y-%m")
    cohort = cohort.loc[cohort["market"].eq(str(market))]
    if cohort.duplicated(["universe_month", "symbol"]).any():
        raise ValueError("membership contains duplicate rows for requested market")
    joined = frame.merge(
        cohort[["universe_month", "symbol", "selected_top50"]],
        on=["universe_month", "symbol"],
        how="left",
        validate="many_to_one",
    )
    if joined["selected_top50"].isna().any():
        raise ValueError("bar month/symbol has no point-in-time membership record")
    joined["selected_top50"] = joined["selected_top50"].astype(bool)
    if not joined["selected_top50"].all():
        raise ValueError("bars include symbols outside the frozen Top50 cohort")
    joined["market"] = str(market)
    joined.attrs["membership_sha256"] = _hash_frame(cohort)
    joined.attrs["holdout_status"] = "UNTOUCHED"
    return joined
