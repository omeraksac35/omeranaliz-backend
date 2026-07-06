"""
Yüksek oynaklık (volatilite) gösteren BIST hisselerini tarar.

ÖNEMLİ: "Riskli" burada SADECE fiyat oynaklığı anlamına gelir — ne yönde
(yukarı ya da aşağı) hareket edeceğine dair bir tahmin İÇERMEZ. Yüksek
oynaklık hem büyük kazanç hem büyük kayıp potansiyeli taşır. Bu bir kâr
garantisi veya öneri değildir.

Kapsam notu: Tüm BIST hisseleri değil, çeşitli sektör/piyasa değerlerinden
seçilmiş ~30 hisselik bir örneklem taranır (performans nedeniyle).
"""

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import yfinance as yf

from analysis import compute_timeframe, fetch_data, normalize_ticker
from levels import compute_levels

CURATED_TICKERS = [
    "THYAO", "GARAN", "ASELS", "BIMAS", "EREGL", "KCHOL", "SISE", "TUPRS",
    "AKBNK", "ISCTR", "SASA", "PETKM", "TOASO", "FROTO",
    "PGSUS", "TAVHL", "MGROS", "ULKER", "VESTL", "ARCLK", "ENJSA", "EKGYO",
    "ODAS", "MANAS", "ASTOR", "TABGD", "AEFES", "DOAS",
]


def _compute_metrics(base_symbol: str) -> Optional[dict]:
    ticker = f"{base_symbol}.IS"
    try:
        df = yf.Ticker(ticker).history(period="3mo", interval="1d")
        if df.empty or len(df) < 20:
            return None

        close = df["Close"]
        returns = close.pct_change().dropna()
        daily_std = float(returns.std())
        annualized_volatility_pct = daily_std * math.sqrt(252) * 100

        price = float(close.iloc[-1])
        price_30d_ago = float(close.iloc[-21]) if len(close) >= 21 else float(close.iloc[0])
        return_30d_pct = (price - price_30d_ago) / price_30d_ago * 100

        info = yf.Ticker(ticker).info
        beta = info.get("beta")

        return {
            "ticker": ticker,
            "price": round(price, 4),
            "volatility_pct": round(annualized_volatility_pct, 1),
            "return_30d_pct": round(return_30d_pct, 1),
            "beta": round(beta, 2) if beta is not None else None,
        }
    except Exception:
        return None


def get_risky_stocks(top_n: int = 15) -> dict:
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_compute_metrics, sym): sym for sym in CURATED_TICKERS}
        for future in as_completed(futures):
            metrics = future.result()
            if metrics is not None:
                results.append(metrics)

    results.sort(key=lambda r: r["volatility_pct"], reverse=True)

    return {
        "stocks": results[:top_n],
        "scanned_count": len(CURATED_TICKERS),
        "note": (
            "Bu liste SADECE fiyat oynaklığına (yıllıklandırılmış standart "
            "sapma) göre sıralanmıştır — hangi yönde hareket edeceğine dair "
            "bir tahmin içermez. Yüksek oynaklık hem büyük kazanç hem büyük "
            "kayıp riski taşır. Bu bir öneri veya kâr garantisi değildir. "
            f"Tüm BIST değil, seçilmiş {len(CURATED_TICKERS)} hisselik bir "
            "örneklem taranmıştır."
        ),
    }


def _trend_summary(df, label: str) -> dict:
    """
    Saf teknik trend özeti (EMA/RSI/MACD) — bilanço ile birleştirilmemiştir,
    bu yüzden fund_verdict için nötr bir değer geçilir (Bilanço kriteri
    değerlendirmeye katılmaz). Sadece "şu an hangi trendde" sorusuna cevap
    verir; kâr garantisi veya kesin yön tahmini değildir.
    """
    result = compute_timeframe(df, fund_verdict="KARIŞIK/NÖTR", label=label, history_points=1)
    return {
        "label": label,
        "signal": result["technical_signal"],
        "reason": result["reason"],
        "rsi": result["rsi"],
        "macd_bullish": result["macd_bullish"],
    }


def get_risk_profile(raw_symbol: str) -> dict:
    """
    Tek bir hisse için risk odaklı profil: oynaklık + trend yönü + giriş
    noktası + en yakın direnç (kırılırsa yukarı hedef) + en yakın destek
    (kırılırsa aşağı hedef). Yön tahmini kesin değildir — sadece geçmiş
    fiyat verisinden hesaplanan trend/seviye/mesafeleri gösterir.
    """
    ticker = normalize_ticker(raw_symbol)
    df = fetch_data(ticker, period="1y", interval="1d")
    close = df["Close"]
    price = float(close.iloc[-1])

    kisa_vadeli_trend = _trend_summary(df, "Kısa Vadeli (Günlük)")
    try:
        df_weekly = fetch_data(ticker, period="3y", interval="1wk")
        uzun_vadeli_trend = _trend_summary(df_weekly, "Uzun Vadeli (Haftalık)")
    except Exception:
        uzun_vadeli_trend = None

    returns = close.pct_change().dropna()
    volatility_pct = float(returns.std()) * math.sqrt(252) * 100

    price_30d_ago = float(close.iloc[-21]) if len(close) >= 21 else float(close.iloc[0])
    return_30d_pct = (price - price_30d_ago) / price_30d_ago * 100

    try:
        beta = yf.Ticker(ticker).info.get("beta")
    except Exception:
        beta = None

    levels = compute_levels(df, price)
    resistance_levels = levels["resistance_levels"]
    support_levels = levels["support_levels"]

    nearest_resistance = None
    if resistance_levels:
        r = resistance_levels[0]
        nearest_resistance = {
            **r,
            "upside_to_level_pct": round((r["level"] - price) / price * 100, 1),
            "upside_to_target_pct": round((r["breakout_target"] - price) / price * 100, 1),
        }

    nearest_support = None
    if support_levels:
        s = support_levels[0]
        nearest_support = {
            **s,
            "downside_to_level_pct": round((price - s["level"]) / price * 100, 1),
            "downside_to_target_pct": round((price - s["breakdown_target"]) / price * 100, 1),
        }

    return {
        "ticker": ticker,
        "price": round(price, 4),
        "volatility_pct": round(volatility_pct, 1),
        "beta": round(beta, 2) if beta is not None else None,
        "return_30d_pct": round(return_30d_pct, 1),
        "entry_reference": round(price, 4),
        "kisa_vadeli_trend": kisa_vadeli_trend,
        "uzun_vadeli_trend": uzun_vadeli_trend,
        "nearest_resistance": nearest_resistance,
        "nearest_support": nearest_support,
        "all_resistance_levels": resistance_levels,
        "all_support_levels": support_levels,
        "note": (
            "Trend sinyalleri sadece teknik göstergelere (EMA/RSI/MACD) "
            "dayanır, bilanço dahil değildir. Giriş noktası olarak güncel "
            "fiyat referans alınmıştır. Direnç/destek kırılma hedefleri "
            "'ölçülü hareket' (measured move) yöntemiyle hesaplanır — "
            "kesinlik iddiası değildir. Yüksek oynaklık hem büyük kazanç "
            "hem büyük kayıp riski taşır."
        ),
    }
