from __future__ import annotations

import numpy as np
import pandas as pd

from .data import INTERVAL_MS
from .models import FeatureSpec


def _gap_segments(bars: pd.DataFrame, expected_interval: str) -> tuple[str, pd.Series, pd.Series]:
    """Validate a declared grid and return timestamp column, segment ids, and timestamps."""
    if expected_interval not in INTERVAL_MS:
        raise ValueError(f"unsupported expected interval: {expected_interval}")
    timestamp_column = next((name for name in ("timestamp", "open_time", "close_time") if name in bars), None)
    if timestamp_column is None:
        raise ValueError("gap-safe feature computation requires timestamp/open_time/close_time")
    timestamps = pd.to_datetime(bars[timestamp_column], utc=True)
    if not timestamps.is_monotonic_increasing or timestamps.duplicated().any():
        raise ValueError("gap-safe feature computation requires strictly increasing unique timestamps")
    expected = pd.Timedelta(milliseconds=INTERVAL_MS[expected_interval])
    epoch_ns = timestamps.astype("datetime64[ns, UTC]").astype("int64")
    if ((epoch_ns % expected.value) != 0).any():
        raise ValueError("timestamps are not aligned to the canonical UTC interval boundary (OFF_GRID_PHASE)")
    deltas = timestamps.diff()
    finite = deltas.dropna()
    invalid = finite.lt(expected) | finite.mod(expected).ne(pd.Timedelta(0))
    if invalid.any():
        raise ValueError("timestamps are off the declared feature grid")
    return timestamp_column, deltas.fillna(expected).ne(expected).cumsum(), timestamps


def compute_gap_safe_features(engine, bars: pd.DataFrame, expected_interval: str) -> pd.DataFrame:
    """Compute features on contiguous time-grid segments only.

    Every missing-data gap starts a fresh feature segment, so rolling, EWM,
    momentum and cumulative transforms must earn their warm-up again. This is
    the required entry point for historical panels that may contain gaps.
    """
    timestamp_column, segment_id, timestamps = _gap_segments(bars, expected_interval)
    pieces = []
    for _, positions in bars.groupby(segment_id.to_numpy(), sort=False).groups.items():
        # Use positional selection: callers may legitimately provide a repeated
        # DataFrame index while timestamps themselves remain unique.
        piece = engine.compute(bars.iloc[list(positions)])
        pieces.append(piece)
    if not pieces:
        return pd.DataFrame(index=bars.index)
    output = pd.concat(pieces)
    output.index = bars.index
    output["segment_id"] = segment_id.to_numpy(dtype="int64")
    segment_values = segment_id.to_numpy(dtype="int64")
    output["segment_start"] = timestamps.groupby(segment_values, sort=False).transform("min").to_numpy()
    output["segment_end"] = timestamps.groupby(segment_values, sort=False).transform("max").to_numpy()
    gap_before = timestamps.diff().gt(pd.Timedelta(milliseconds=INTERVAL_MS[expected_interval]))
    output["gap_before"] = gap_before.to_numpy()
    output["gap_size_bars"] = timestamps.diff().div(pd.Timedelta(milliseconds=INTERVAL_MS[expected_interval])).sub(1).clip(lower=0).fillna(0).astype("int64").to_numpy()
    output["source_coverage_status"] = np.where(gap_before, "GAP_AFTER_PREVIOUS", "COMPLETE_CONTIGUOUS")
    return output


def _spec(
    feature_id: str,
    family: str,
    inputs: tuple[str, ...],
    parameters: dict[str, object],
    warmup: int,
    outputs: tuple[str, ...],
    signal: str | None = None,
    documentation: str = "",
) -> FeatureSpec:
    return FeatureSpec(
        feature_id, family, inputs, parameters, warmup, outputs,
        signal_column=signal,
        documentation=documentation or f"Causal trailing implementation of {feature_id}; available after the declared warmup.",
    )


CORE_FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    _spec("trend.ema_20_50_spread", "trend", ("close",), {"fast": 20, "slow": 50}, 50, ("ema20_50_spread",), "sig_ema20_50"),
    _spec("trend.ema_50_200_regime", "trend", ("close",), {"fast": 50, "slow": 200}, 200, ("ema50_200_spread", "ema50_200_regime"), "sig_ema50_200"),
    _spec("trend.ema_slope", "trend", ("close",), {"period": 20, "lag": 5}, 25, ("ema20_slope_5",), "sig_ema_slope"),
    _spec("trend.adx_dmi", "trend", ("high", "low", "close"), {"period": 14}, 28, ("adx14", "plus_di14", "minus_di14"), "sig_adx_dmi"),
    _spec("trend.kaufman_er", "trend", ("close",), {"period": 10}, 10, ("kaufman_er10",), "sig_kaufman_er"),
    _spec("trend.donchian", "trend", ("high", "low", "close"), {"period": 20}, 20, ("donchian_range_pos20", "donchian_breakout20"), "sig_donchian"),
    _spec("momentum.roc", "momentum", ("close",), {"short": 6, "medium": 24}, 24, ("roc6", "roc24"), "sig_roc"),
    _spec("momentum.rsi", "momentum", ("close",), {"period": 14}, 14, ("rsi14",), "sig_rsi"),
    _spec("volatility.atr_natr", "volatility", ("high", "low", "close"), {"period": 14}, 14, ("atr14", "natr14")),
    _spec("volatility.bollinger_bandwidth", "volatility", ("close",), {"period": 20, "std": 2.0}, 20, ("bb_bandwidth20",)),
    _spec("volatility.realized_percentile", "volatility", ("close",), {"rv_period": 20, "rank_period": 100}, 120, ("realized_vol20", "realized_vol_percentile100")),
    _spec("volume.rvol", "volume", ("volume",), {"period": 20}, 20, ("rvol20",)),
    _spec("volume.vwap_deviation", "volume", ("high", "low", "close", "volume"), {"period": 20}, 20, ("vwap20", "vwap_deviation20"), "sig_vwap_deviation"),
    _spec("orderflow.taker_ratio", "order_flow", ("volume", "taker_buy_volume"), {}, 1, ("aggressive_buy_volume", "aggressive_sell_volume", "taker_buy_sell_ratio"), "sig_taker_ratio"),
    _spec("orderflow.cvd", "order_flow", ("volume", "taker_buy_volume"), {"slope_period": 6}, 6, ("cvd", "cvd_slope6"), "sig_cvd"),
    _spec("microstructure.spread", "microstructure", ("bid_price", "ask_price"), {}, 1, ("spread_bps",)),
    _spec("microstructure.top_book_imbalance", "microstructure", ("bid_qty", "ask_qty"), {}, 1, ("top_book_imbalance", "microprice"), "sig_book_imbalance"),
    _spec("derivatives.oi_change", "derivatives", ("open_interest",), {"period": 1}, 2, ("oi_pct_change",)),
    _spec("derivatives.funding_zscore", "derivatives", ("funding_rate",), {"period": 90}, 90, ("funding_zscore90",)),
    _spec("derivatives.premium_zscore", "derivatives", ("premium",), {"period": 90}, 90, ("premium_zscore90",)),
    _spec("context.btc_regime", "market_context", ("btc_close",), {"ema": 200, "neutral_band": 0.005}, 200, ("btc_regime",), "sig_btc_regime"),
    _spec("context.market_breadth", "market_context", ("breadth_pct_above_ema",), {"bull": 0.6, "bear": 0.4}, 1, ("market_breadth",), "sig_market_breadth"),
)


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.div(denominator.replace(0, np.nan))


def _rolling_zscore(series: pd.Series, period: int) -> pd.Series:
    mean = series.rolling(period, min_periods=period).mean()
    std = series.rolling(period, min_periods=period).std(ddof=0)
    return _safe_divide(series - mean, std)


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _true_range(frame: pd.DataFrame) -> pd.Series:
    previous = frame["close"].shift(1)
    return pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = _wilder(gains, period)
    avg_loss = _wilder(losses, period)
    rs = _safe_divide(avg_gain, avg_loss)
    result = 100 - (100 / (1 + rs))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    return result.mask((avg_gain == 0) & (avg_loss == 0), 50.0)


def _adx(frame: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = frame["high"].diff()
    down = -frame["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=frame.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=frame.index)
    atr = _wilder(_true_range(frame), period)
    plus_di = 100 * _safe_divide(_wilder(plus_dm, period), atr)
    minus_di = 100 * _safe_divide(_wilder(minus_dm, period), atr)
    dx = 100 * _safe_divide((plus_di - minus_di).abs(), plus_di + minus_di)
    return _wilder(dx, period), plus_di, minus_di


def _rolling_last_percentile(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if len(finite) != len(values) or len(finite) == 0:
        return np.nan
    return float((finite <= finite[-1]).mean())


def _optional(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame:
        return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype=float)


class CoreFeatureEngine:
    """Compute the preregistered first-pass features with trailing-only transforms."""

    required_ohlcv = {"open", "high", "low", "close", "volume"}

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        missing = sorted(self.required_ohlcv - set(bars.columns))
        if missing:
            raise ValueError(f"missing OHLCV columns: {', '.join(missing)}")
        frame = bars.copy()
        for column in self.required_ohlcv | {"quote_volume", "taker_buy_volume", "taker_buy_quote_volume"}:
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        output = pd.DataFrame(index=frame.index)
        if "close_time" in frame:
            output["causal_timestamp"] = pd.to_datetime(frame["close_time"], utc=True)

        close = frame["close"]
        ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
        ema50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
        ema200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
        output["ema20_50_spread"] = _safe_divide(ema20 - ema50, close)
        output["ema50_200_spread"] = _safe_divide(ema50 - ema200, close)
        output["ema50_200_regime"] = np.sign(output["ema50_200_spread"])
        output["ema20_slope_5"] = _safe_divide(ema20 - ema20.shift(5), 5 * close)

        output["adx14"], output["plus_di14"], output["minus_di14"] = _adx(frame, 14)
        direction = close.diff(10).abs()
        path = close.diff().abs().rolling(10, min_periods=10).sum()
        output["kaufman_er10"] = _safe_divide(direction, path).clip(0, 1)

        prior_high = frame["high"].shift(1).rolling(20, min_periods=20).max()
        prior_low = frame["low"].shift(1).rolling(20, min_periods=20).min()
        output["donchian_range_pos20"] = _safe_divide(close - prior_low, prior_high - prior_low)
        output["donchian_breakout20"] = np.select([close > prior_high, close < prior_low], [1.0, -1.0], default=0.0)
        output.loc[prior_high.isna() | prior_low.isna(), "donchian_breakout20"] = np.nan

        output["roc6"] = close.pct_change(6, fill_method=None)
        output["roc24"] = close.pct_change(24, fill_method=None)
        output["rsi14"] = _rsi(close, 14)
        output["atr14"] = _wilder(_true_range(frame), 14)
        output["natr14"] = 100 * _safe_divide(output["atr14"], close)

        mean20 = close.rolling(20, min_periods=20).mean()
        std20 = close.rolling(20, min_periods=20).std(ddof=0)
        output["bb_bandwidth20"] = _safe_divide(4 * std20, mean20)
        log_return = np.log(close).diff()
        output["realized_vol20"] = log_return.rolling(20, min_periods=20).std(ddof=0) * np.sqrt(20)
        output["realized_vol_percentile100"] = output["realized_vol20"].rolling(100, min_periods=100).apply(_rolling_last_percentile, raw=True)

        volume_mean = frame["volume"].rolling(20, min_periods=20).mean()
        output["rvol20"] = _safe_divide(frame["volume"], volume_mean)
        typical_price = (frame["high"] + frame["low"] + close) / 3
        rolling_notional = (typical_price * frame["volume"]).rolling(20, min_periods=20).sum()
        rolling_volume = frame["volume"].rolling(20, min_periods=20).sum()
        output["vwap20"] = _safe_divide(rolling_notional, rolling_volume)
        output["vwap_deviation20"] = _safe_divide(close - output["vwap20"], output["vwap20"])

        taker_buy = _optional(frame, "taker_buy_volume")
        aggressive_sell = frame["volume"] - taker_buy
        output["aggressive_buy_volume"] = taker_buy
        output["aggressive_sell_volume"] = aggressive_sell
        output["taker_buy_sell_ratio"] = _safe_divide(taker_buy, aggressive_sell)
        delta_volume = taker_buy - aggressive_sell
        output["cvd"] = delta_volume.cumsum(skipna=False)
        output["cvd_slope6"] = output["cvd"].diff(6)

        bid = _optional(frame, "bid_price")
        ask = _optional(frame, "ask_price")
        bid_qty = _optional(frame, "bid_qty")
        ask_qty = _optional(frame, "ask_qty")
        midpoint = (bid + ask) / 2
        output["spread_bps"] = 10_000 * _safe_divide(ask - bid, midpoint)
        output["top_book_imbalance"] = _safe_divide(bid_qty - ask_qty, bid_qty + ask_qty)
        output["microprice"] = _safe_divide(ask * bid_qty + bid * ask_qty, bid_qty + ask_qty)

        output["oi_pct_change"] = _optional(frame, "open_interest").pct_change(fill_method=None)
        output["funding_zscore90"] = _rolling_zscore(_optional(frame, "funding_rate"), 90)
        output["premium_zscore90"] = _rolling_zscore(_optional(frame, "premium"), 90)
        btc_close = _optional(frame, "btc_close")
        btc_ema = btc_close.ewm(span=200, adjust=False, min_periods=200).mean()
        btc_distance = _safe_divide(btc_close - btc_ema, btc_ema)
        output["btc_regime"] = np.select([btc_distance > 0.005, btc_distance < -0.005], [1.0, -1.0], default=0.0)
        output.loc[btc_ema.isna(), "btc_regime"] = np.nan
        output["market_breadth"] = _optional(frame, "breadth_pct_above_ema")

        self._add_canonical_signals(output)
        return output

    @staticmethod
    def _add_canonical_signals(output: pd.DataFrame) -> None:
        output["sig_ema20_50"] = np.sign(output["ema20_50_spread"])
        output["sig_ema50_200"] = output["ema50_200_regime"]
        output["sig_ema_slope"] = np.sign(output["ema20_slope_5"])
        output["sig_adx_dmi"] = np.where(
            output["adx14"] >= 20,
            np.sign(output["plus_di14"] - output["minus_di14"]),
            0.0,
        )
        output.loc[output[["adx14", "plus_di14", "minus_di14"]].isna().any(axis=1), "sig_adx_dmi"] = np.nan
        output["sig_kaufman_er"] = np.where(output["kaufman_er10"] >= 0.3, np.sign(output["ema20_slope_5"]), 0.0)
        output.loc[output[["kaufman_er10", "ema20_slope_5"]].isna().any(axis=1), "sig_kaufman_er"] = np.nan
        output["sig_donchian"] = output["donchian_breakout20"]
        output["sig_roc"] = np.sign(output["roc24"])
        output["sig_rsi"] = np.select([output["rsi14"] <= 30, output["rsi14"] >= 70], [1.0, -1.0], default=0.0)
        output.loc[output["rsi14"].isna(), "sig_rsi"] = np.nan
        output["sig_vwap_deviation"] = -np.sign(output["vwap_deviation20"])
        output["sig_taker_ratio"] = np.sign(output["taker_buy_sell_ratio"] - 1)
        output["sig_cvd"] = np.sign(output["cvd_slope6"])
        output["sig_book_imbalance"] = np.sign(output["top_book_imbalance"])
        output["sig_btc_regime"] = output["btc_regime"]
        output["sig_market_breadth"] = np.select(
            [output["market_breadth"] >= 0.6, output["market_breadth"] <= 0.4],
            [1.0, -1.0], default=0.0,
        )
        output.loc[output["market_breadth"].isna(), "sig_market_breadth"] = np.nan


def build_market_breadth(
    panel: pd.DataFrame,
    timestamp_column: str = "close_time",
    symbol_column: str = "symbol",
    ema_period: int = 50,
) -> pd.DataFrame:
    """Create causal, lifecycle-aware cross-sectional breadth from observed rows."""
    required = {timestamp_column, symbol_column, "close"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"missing breadth columns: {', '.join(sorted(missing))}")
    ordered = panel.sort_values([symbol_column, timestamp_column]).copy()
    ema = ordered.groupby(symbol_column, sort=False)["close"].transform(
        lambda values: values.ewm(span=ema_period, adjust=False, min_periods=ema_period).mean()
    )
    ordered["above_ema"] = (ordered["close"] > ema).astype(float)
    ordered.loc[ema.isna(), "above_ema"] = np.nan
    breadth = ordered.groupby(timestamp_column, sort=True)["above_ema"].mean().rename("breadth_pct_above_ema")
    return ordered.merge(breadth, left_on=timestamp_column, right_index=True, how="left")


def build_cohort_aware_breadth(
    panel: pd.DataFrame,
    cohorts: pd.DataFrame,
    *,
    timeframe: str,
    timestamp_column: str = "timestamp",
    market_column: str = "market",
    symbol_column: str = "symbol",
    selected_column: str = "selected_top50",
    minimum_valid_fraction: float = 0.8,
    ema_period: int = 50,
) -> pd.DataFrame:
    """Compute breadth against only the frozen selected cohort denominator."""
    if timeframe not in INTERVAL_MS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    if not 0 < minimum_valid_fraction <= 1:
        raise ValueError("minimum_valid_fraction must be in (0, 1]")
    required_panel = {timestamp_column, market_column, symbol_column, "close"}
    required_cohort = {market_column, "universe_month", symbol_column, selected_column}
    if missing := required_panel - set(panel.columns):
        raise ValueError(f"missing breadth panel columns: {', '.join(sorted(missing))}")
    if missing := required_cohort - set(cohorts.columns):
        raise ValueError(f"missing breadth cohort columns: {', '.join(sorted(missing))}")
    frame = panel.copy()
    frame[timestamp_column] = pd.to_datetime(frame[timestamp_column], utc=True)
    frame["universe_month"] = frame[timestamp_column].dt.to_period("M").astype(str)
    frame["_close"] = pd.to_numeric(frame["close"], errors="coerce")
    expected = pd.Timedelta(milliseconds=INTERVAL_MS[timeframe])
    frame["_ema"] = np.nan
    for (market, symbol), indexes in frame.groupby([market_column, symbol_column], sort=False).groups.items():
        group = frame.loc[indexes].sort_values(timestamp_column)
        ts = group[timestamp_column]
        segments = ts.diff().fillna(expected).ne(expected).cumsum()
        for _, segment_indexes in group.groupby(segments, sort=False).groups.items():
            values = frame.loc[segment_indexes, "_close"]
            frame.loc[segment_indexes, "_ema"] = values.ewm(span=ema_period, adjust=False, min_periods=ema_period).mean().to_numpy()
    selected = cohorts[cohorts[selected_column].astype(bool)][[market_column, "universe_month", symbol_column]].drop_duplicates()
    frame = frame.merge(selected.assign(_selected=True), on=[market_column, "universe_month", symbol_column], how="left")
    frame["_selected"] = frame["_selected"].fillna(False)
    frame["_valid"] = frame["_selected"] & frame["_ema"].notna() & frame["_close"].notna()
    frame["_above"] = np.where(frame["_valid"], frame["_close"] > frame["_ema"], np.nan)
    group_keys = [market_column, timestamp_column]
    diagnostics = frame.groupby(group_keys, sort=True).agg(
        valid_count=("_valid", "sum"),
        selected_count=("_selected", "sum"),
        above_count=("_above", "sum"),
    ).reset_index()
    diagnostics["valid_fraction"] = diagnostics["valid_count"].div(diagnostics["selected_count"].replace(0, np.nan))
    diagnostics["breadth_pct_above_ema50"] = diagnostics["above_count"].div(diagnostics["valid_count"].replace(0, np.nan))
    diagnostics["coverage_status"] = np.where(
        diagnostics["valid_fraction"] >= minimum_valid_fraction,
        "AVAILABLE",
        "INSUFFICIENT_CROSS_SECTION",
    )
    diagnostics.loc[diagnostics["coverage_status"] != "AVAILABLE", "breadth_pct_above_ema50"] = np.nan
    diagnostics = diagnostics.drop(columns=["above_count"])
    return diagnostics


def classify_aggtrade_side(is_buyer_maker: pd.Series) -> pd.Series:
    """Binance m=true means seller was aggressive; false means buyer was aggressive."""
    mapped = is_buyer_maker.map({True: -1, False: 1})
    return mapped.astype("Int8")


def preregistered_rule_variants(bars: pd.DataFrame) -> pd.DataFrame:
    """Small coarse grid declared before testing; every returned column is one trial."""
    close = pd.to_numeric(bars["close"], errors="coerce")
    high = pd.to_numeric(bars["high"], errors="coerce")
    low = pd.to_numeric(bars["low"], errors="coerce")
    variants = pd.DataFrame(index=bars.index)
    for fast, slow in ((10, 30), (20, 50), (50, 200)):
        fast_ema = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
        slow_ema = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
        variants[f"ema_{fast}_{slow}"] = np.sign(fast_ema - slow_ema)
        variants.loc[slow_ema.isna(), f"ema_{fast}_{slow}"] = np.nan
    for period in (7, 14, 21):
        rsi = _rsi(close, period)
        variants[f"rsi_{period}_30_70"] = np.select([rsi <= 30, rsi >= 70], [1.0, -1.0], default=0.0)
        variants.loc[rsi.isna(), f"rsi_{period}_30_70"] = np.nan
    for period in (20, 48, 55):
        prior_high = high.shift(1).rolling(period, min_periods=period).max()
        prior_low = low.shift(1).rolling(period, min_periods=period).min()
        name = f"donchian_{period}"
        variants[name] = np.select([close > prior_high, close < prior_low], [1.0, -1.0], default=0.0)
        variants.loc[prior_high.isna() | prior_low.isna(), name] = np.nan
    for period in (6, 12, 24):
        roc = close.pct_change(period, fill_method=None)
        variants[f"roc_{period}"] = np.sign(roc)
    return variants
