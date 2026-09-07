"""Mechanical preregistration verification for the R2A trial registry."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from binance_research.audit import CLASSIFICATION_R2A_PRIMARY  # noqa: E402

LEGAL_SIDES = {"spot": {"LONG"}, "um": {"LONG", "SHORT"}}
NATIVE_TIMEFRAMES = ("15m", "1h", "4h")
HORIZON_BARS_24H = {"15m": 96, "1h": 24, "4h": 6}
KNOWN_VARIANTS = {
    "trend.ema_20_50_spread": {"ema_10_30", "ema_20_50", "ema_50_200"},
    "trend.ema_50_200_regime": {"ema_10_30", "ema_20_50", "ema_50_200"},
    "trend.ema_slope": {"default"},
    "trend.adx_dmi": {"adx14_threshold20"},
    "trend.kaufman_er": {"er10_threshold0.3"},
    "trend.donchian": {"donchian_20", "donchian_48", "donchian_55"},
    "momentum.roc": {"roc_6", "roc_12", "roc_24"},
    "momentum.rsi": {"rsi_7_30_70", "rsi_14_30_70", "rsi_21_30_70"},
    "volatility.atr_natr": {"natr14_filter"},
    "volatility.bollinger_bandwidth": {"bb20_2s_filter"},
    "volatility.realized_percentile": {"rv20_p100_filter"},
    "volume.rvol": {"rvol20_filter"},
    "volume.vwap_deviation": {"vwap_dev20_reversal"},
    "orderflow.taker_ratio": {"ratio_sign"},
    "orderflow.cvd": {"cvd_slope6_sign"},
    "context.btc_regime": {"regime_follow"},
    "context.market_breadth": {"breadth_0.4_0.6"},
    "derivatives.funding": {"funding_sign"},
    "derivatives.funding_zscore": {"z90_extreme"},
}
SIGNAL_SEMANTICS: dict[tuple[str, str], dict[str, Any]] = {
    # (feature_id, variant) -> deterministic signal rule applied to completed bars.
    ("trend.ema_20_50_spread", "ema_10_30"): {"rule": "sign(ema10-ema30)"},
    ("trend.ema_20_50_spread", "ema_20_50"): {"rule": "sign(ema20-ema50)"},
    ("trend.ema_20_50_spread", "ema_50_200"): {"rule": "sign(ema50-ema200)"},
    ("trend.ema_50_200_regime", "ema_50_200"): {"rule": "sign(ema50-ema200)"},
    ("trend.ema_50_200_regime", "ema_10_30"): {"rule": "sign(ema10-ema30) as regime proxy variant"},
    ("trend.ema_50_200_regime", "ema_20_50"): {"rule": "sign(ema20-ema50) as regime proxy variant"},
    ("trend.ema_slope", "default"): {"rule": "sign((ema20-ema20.shift5)/close)"},
    ("trend.adx_dmi", "adx14_threshold20"): {"rule": "+1 if adx14>=20 and +DI>-DI; -1 if adx14>=20 and -DI>+DI; else 0"},
    ("trend.kaufman_er", "er10_threshold0.3"): {"rule": "+1 if er10>=0.3 and slope>0; -1 if er10>=0.3 and slope<0; else 0"},
    ("trend.donchian", "donchian_20"): {"rule": "+1 close>prior_high20; -1 close<prior_low20; else 0"},
    ("trend.donchian", "donchian_48"): {"rule": "+1 close>prior_high48; -1 close<prior_low48; else 0"},
    ("trend.donchian", "donchian_55"): {"rule": "+1 close>prior_high55; -1 close<prior_low55; else 0"},
    ("momentum.roc", "roc_6"): {"rule": "sign(close/close.shift6-1)"},
    ("momentum.roc", "roc_12"): {"rule": "sign(close/close.shift12-1)"},
    ("momentum.roc", "roc_24"): {"rule": "sign(close/close.shift24-1)"},
    ("momentum.rsi", "rsi_7_30_70"): {"rule": "+1 rsi7<=30; -1 rsi7>=70; else 0"},
    ("momentum.rsi", "rsi_14_30_70"): {"rule": "+1 rsi14<=30; -1 rsi14>=70; else 0"},
    ("momentum.rsi", "rsi_21_30_70"): {"rule": "+1 rsi21<=30; -1 rsi21>=70; else 0"},
    ("volatility.atr_natr", "natr14_filter"): {"rule": "follow prior bar sign of return when natr14 in top tercile (deterministic expanding-rank), else 0"},
    ("volatility.bollinger_bandwidth", "bb20_2s_filter"): {"rule": "follow sign(bb_bandwidth20 z-rank expansion) deterministically: +1 when bandwidth expanding and return>0; -1 when expanding and return<0; else 0"},
    ("volatility.realized_percentile", "rv20_p100_filter"): {"rule": "+1 when rv_percentile>0.8 and roc6>0; -1 when >0.8 and roc6<0; else 0"},
    ("volume.rvol", "rvol20_filter"): {"rule": "+1 when rvol20>=2 and roc6>0; -1 when >=2 and roc6<0; else 0"},
    ("volume.vwap_deviation", "vwap_dev20_reversal"): {"rule": "-sign(vwap_deviation20)"},
    ("orderflow.taker_ratio", "ratio_sign"): {"rule": "sign(taker_buy_sell_ratio-1)"},
    ("orderflow.cvd", "cvd_slope6_sign"): {"rule": "sign(cvd.diff(6))"},
    ("context.btc_regime", "regime_follow"): {"rule": "btc_regime value as signal"},
    ("context.market_breadth", "breadth_0.4_0.6"): {"rule": "+1 breadth>=0.6; -1 breadth<=0.4; else 0"},
    ("derivatives.funding", "funding_sign"): {"rule": "-sign(funding_rate): short-crowded-long premium"},
    ("derivatives.funding_zscore", "z90_extreme"): {"rule": "-1 if z>=+3; +1 if z<=-3; else 0"},
}


def verify_registry(registry_path: Path, availability_path: Path) -> dict[str, object]:
    """Fail closed unless every trial is mechanically eligible."""
    registry = pd.read_csv(registry_path)
    availability = pd.read_csv(availability_path)
    primary = set(map(tuple, availability.loc[availability.classification == CLASSIFICATION_R2A_PRIMARY, ["feature", "market", "timeframe"]].values))
    errors: list[str] = []
    seen: set[str] = set()
    for row in registry.itertuples(index=False):
        key = (row.feature_id, row.market, row.timeframe)
        if key not in primary:
            errors.append(f"{row.trial_id}: feature not R2A_PRIMARY for market/timeframe: {key}")
        if row.side not in LEGAL_SIDES[row.market]:
            errors.append(f"{row.trial_id}: illegal side {row.side} for {row.market}")
        if row.timeframe not in NATIVE_TIMEFRAMES:
            errors.append(f"{row.trial_id}: non-native timeframe {row.timeframe}")
        if int(row.horizon_bars_24h) != HORIZON_BARS_24H[row.timeframe]:
            errors.append(f"{row.trial_id}: wrong horizon for {row.timeframe}")
        if row.cohort != "top50":
            errors.append(f"{row.trial_id}: cohort must be top50")
        if row.status != "REGISTERED":
            errors.append(f"{row.trial_id}: unexpected status {row.status}")
        variants = KNOWN_VARIANTS.get(row.feature_id)
        if variants is None or row.variant not in variants:
            errors.append(f"{row.trial_id}: unknown variant {row.feature_id}/{row.variant}")
        elif (row.feature_id, row.variant) not in SIGNAL_SEMANTICS:
            errors.append(f"{row.trial_id}: no deterministic signal semantics for {row.feature_id}/{row.variant}")
        dedupe = "|".join(str(getattr(row, c)) for c in ("feature_id", "variant", "market", "timeframe", "side"))
        if dedupe in seen:
            errors.append(f"{row.trial_id}: duplicate trial {dedupe}")
        seen.add(dedupe)
    expected_ids = [f"T{i:04d}" for i in range(1, len(registry) + 1)]
    if list(registry.trial_id) != expected_ids:
        errors.append("trial_id sequence is not deterministic T0001..Tnnnn")
    if any(errors):
        raise ValueError("; ".join(errors[:10]))
    families = registry.groupby(["market", "timeframe"]).size().to_dict()
    return {"trials": len(registry), "families": {f"{k[0]}|{k[1]}": int(v) for k, v in families.items()}}


def main() -> int:
    summary = verify_registry(
        ROOT / "campaigns" / "r2a_standalone_evidence_v1" / "trial_registry.csv",
        ROOT / "campaigns" / "r1_final_panel_v1" / "feature_availability_final.csv",
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
