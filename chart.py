"""
Serbest zaman dilimi seçimiyle (saatlik/günlük/haftalık/yıllık) mum grafiği
verisi + çoklu direnç/destek + kırılma hedefi. `analysis.py`'deki sabit
kısa/uzun vadeli AL/SAT sinyalinden bağımsızdır — sadece görselleştirme ve
seviye keşfi içindir.
"""

import pandas as pd

from analysis import fetch_data, normalize_ticker
from indicators import ema
from levels import compute_levels

CHART_TIMEFRAMES = {
    "saatlik": {"label": "Saatlik", "interval": "1h", "period": "60d"},
    "gunluk": {"label": "Günlük", "interval": "1d", "period": "1y"},
    "haftalik": {"label": "Haftalık", "interval": "1wk", "period": "3y"},
    "yillik": {"label": "Yıllık", "interval": "1mo", "period": "10y"},
}

MAX_CANDLES = 180


def get_chart(raw_symbol: str, timeframe_key: str) -> dict:
    cfg = CHART_TIMEFRAMES.get(timeframe_key)
    if cfg is None:
        valid = ", ".join(CHART_TIMEFRAMES.keys())
        raise ValueError(f"Geçersiz zaman dilimi: {timeframe_key}. Geçerli değerler: {valid}")

    ticker = normalize_ticker(raw_symbol)
    df = fetch_data(ticker, cfg["period"], cfg["interval"])

    close = df["Close"]
    df = df.copy()
    df["ema9"] = ema(close, 9)
    df["ema21"] = ema(close, 21)
    df["ema50"] = ema(close, 50)

    current_price = float(close.iloc[-1])
    levels = compute_levels(df, current_price)

    is_intraday = cfg["interval"] in ("1h", "30m", "15m")
    candle_window = df.iloc[-MAX_CANDLES:]
    candles = [
        {
            "date": idx.strftime("%Y-%m-%d %H:%M") if is_intraday else idx.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "ema9": round(float(row["ema9"]), 4) if pd.notna(row["ema9"]) else None,
            "ema21": round(float(row["ema21"]), 4) if pd.notna(row["ema21"]) else None,
            "ema50": round(float(row["ema50"]), 4) if pd.notna(row["ema50"]) else None,
        }
        for idx, row in candle_window.iterrows()
    ]

    return {
        "ticker": ticker,
        "timeframe": timeframe_key,
        "label": cfg["label"],
        "current_price": round(current_price, 4),
        "candles": candles,
        "resistance_levels": levels["resistance_levels"],
        "support_levels": levels["support_levels"],
        "note": (
            "Kırılma hedefleri 'ölçülü hareket' (measured move) yöntemiyle "
            "hesaplanır: hedef = direnç + (direnç - altındaki destek). Bu bir "
            "kesinlik iddiası değildir, yaygın kullanılan açıklanabilir bir "
            "projeksiyondur."
        ),
    }
