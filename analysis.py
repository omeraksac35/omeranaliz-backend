"""
BIST hissesi için çoklu zaman dilimli (kısa vadeli=günlük, uzun vadeli=haftalık)
teknik + temel analiz mantığı. Her iki vade için ayrı ayrı EMA/RSI/MACD sinyali,
"kriter uyum yüzdesi" bazlı güven skoru ve (AL durumunda) giriş/stop-loss/
take-profit seviyeleri üretir; ayrıca iki vadenin birbiriyle tutarlı olup
olmadığına dair kısa bir not ekler.

ÖNEMLİ: Güven yüzdesi istatistiksel bir olasılık DEĞİLDİR — sadece kaç teknik/
temel kriterin mevcut sinyali desteklediğinin basit bir oranıdır. Geçmiş işlem
sonuçlarıyla kalibre edilmemiştir, kâr garantisi vermez. Belirli bir tarihte
belirli bir fiyata ulaşacağına dair bir tahmin İÇERMEZ — böyle bir tahmin
teknik analizle güvenilir şekilde yapılamaz.
"""

from typing import Optional

import pandas as pd

from fundamentals import evaluate_fundamentals, fetch_fundamentals
from indicators import ema, macd, rsi, support_resistance
from levels import compute_levels
from yf_client import get_history

RISK_REWARD_RATIO = 2.0
STOP_LOSS_BUFFER_PCT = 0.02
SPECULATIVE_VOLATILITY_THRESHOLD_PCT = 40.0
PROBABILITY_WINDOW_TRADING_DAYS = 10

TIMEFRAMES = {
    "saatlik": {"label": "Saatlik", "period": "60d", "interval": "1h", "history_points": 120, "is_intraday": True},
    "kisa_vadeli": {"label": "Kısa Vadeli (Günlük)", "period": "1y", "interval": "1d", "history_points": 120, "is_intraday": False},
    "uzun_vadeli": {"label": "Uzun Vadeli (Haftalık)", "period": "3y", "interval": "1wk", "history_points": 104, "is_intraday": False},
}


def normalize_ticker(raw: str) -> str:
    raw = raw.strip().upper()
    if not raw:
        raise ValueError("Boş sembol.")
    if "." not in raw:
        raw = f"{raw}.IS"
    return raw


def fetch_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    df = get_history(ticker, period, interval)
    df = df[df["Close"].notna()]
    if df.empty:
        raise ValueError(f"{ticker} için veri bulunamadı. Sembolü kontrol et (örn. THYAO, GARAN).")
    return df


def compute_timeframe(
    df: pd.DataFrame, fund_verdict: str, label: str, history_points: int, is_intraday: bool = False
) -> dict:
    close = df["Close"]
    df = df.copy()
    df["ema9"] = ema(close, 9)
    df["ema21"] = ema(close, 21)
    df["ema50"] = ema(close, 50)
    df["rsi14"] = rsi(close, 14)
    macd_line, signal_line, _ = macd(close)
    df["macd"] = macd_line
    df["macd_signal"] = signal_line

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last["Close"])
    long_term_trend_up = bool(price > last["ema50"]) if pd.notna(last["ema50"]) else False
    bull_cross = bool(prev["ema9"] <= prev["ema21"] and last["ema9"] > last["ema21"])
    bear_cross = bool(prev["ema9"] >= prev["ema21"] and last["ema9"] < last["ema21"])
    momentum_up = bool(last["ema9"] > last["ema21"])

    rsi_value = float(last["rsi14"])
    macd_bullish = bool(last["macd"] > last["macd_signal"])

    support, resistance = support_resistance(df, lookback=min(20, len(df) - 2))

    lookback_vol = min(20, len(df) - 1)
    avg_volume = float(df["Volume"].iloc[-(lookback_vol + 1):-1].mean())
    last_volume = float(last["Volume"])
    volume_above_avg = last_volume > avg_volume

    if bull_cross and rsi_value < 70 and long_term_trend_up:
        technical_signal = "AL"
        reason = f"{label}: EMA yukarı kesişimi + RSI aşırı alımda değil + trend yukarı"
    elif momentum_up and rsi_value < 70 and long_term_trend_up and macd_bullish:
        technical_signal = "AL"
        reason = f"{label}: EMA9>EMA21, MACD pozitif, trend yukarı, RSI aşırı alımda değil"
    elif bear_cross or rsi_value >= 70 or not long_term_trend_up:
        technical_signal = "SAT"
        reason_parts = []
        if bear_cross:
            reason_parts.append("EMA aşağı kesişimi")
        if rsi_value >= 70:
            reason_parts.append("RSI aşırı alım bölgesinde")
        if not long_term_trend_up:
            reason_parts.append("trend aşağı")
        reason = f"{label}: " + " + ".join(reason_parts)
    else:
        technical_signal = "BEKLE"
        reason = f"{label}: net bir teknik sinyal yok"

    if technical_signal == "AL" and fund_verdict == "ZAYIF":
        final_signal = "DİKKATLİ AL"
    else:
        final_signal = technical_signal

    criteria = [
        ("Momentum yukarı (EMA9>EMA21)", momentum_up),
        ("Trend yukarı (Fiyat>EMA50)", long_term_trend_up),
        ("RSI aşırı alımda değil", rsi_value < 70),
        ("MACD pozitif", macd_bullish),
        ("Hacim ortalamanın üzerinde", volume_above_avg),
        ("Bilanço zayıf değil", fund_verdict != "ZAYIF"),
    ]
    bullish_count = sum(1 for _, ok in criteria if ok)
    bullish_pct = round(bullish_count / len(criteria) * 100)

    is_buy_signal = final_signal in ("AL", "DİKKATLİ AL")
    confidence_pct = (100 - bullish_pct) if final_signal == "SAT" else bullish_pct

    stop_loss = support * (1 - STOP_LOSS_BUFFER_PCT)
    risk = price - stop_loss
    take_profit = price + risk * RISK_REWARD_RATIO if risk > 0 else resistance

    history_window = df.iloc[-history_points:]
    date_format = "%Y-%m-%d %H:%M" if is_intraday else "%Y-%m-%d"
    history = [
        {
            "date": idx.strftime(date_format),
            "close": round(float(row["Close"]), 4),
            "ema9": round(float(row["ema9"]), 4),
            "ema21": round(float(row["ema21"]), 4),
            "ema50": round(float(row["ema50"]), 4) if pd.notna(row["ema50"]) else None,
        }
        for idx, row in history_window.iterrows()
    ]

    return {
        "label": label,
        "price": round(price, 4),
        "signal": final_signal,
        "technical_signal": technical_signal,
        "reason": reason,
        "confidence_pct": confidence_pct,
        "criteria": [{"label": lbl, "positive": ok} for lbl, ok in criteria],
        "rsi": round(rsi_value, 1),
        "macd_bullish": macd_bullish,
        "support": round(support, 4),
        "resistance": round(resistance, 4),
        "volume_above_avg": volume_above_avg,
        "is_buy_signal": is_buy_signal,
        "entry_point": round(price, 4) if is_buy_signal else None,
        "stop_loss": round(stop_loss, 4) if is_buy_signal else None,
        "take_profit": round(take_profit, 4) if is_buy_signal else None,
        "history": history,
    }


def build_consistency_note(kisa: dict, uzun: dict) -> str:
    k, u = kisa["signal"], uzun["signal"]
    k_buy, u_buy = kisa["is_buy_signal"], uzun["is_buy_signal"]

    if k_buy and u_buy:
        return "Kısa ve uzun vadeli görünüm uyumlu: ikisi de AL yönünde."
    if k == "SAT" and u == "SAT":
        return "Kısa ve uzun vadeli görünüm uyumlu: ikisi de SAT yönünde."
    if k_buy and u == "SAT":
        return "ÇELİŞKİLİ: Kısa vadede AL görünse de uzun vadeli trend aşağı — kısa vadeli bir tepki hareketi olabilir, temkinli ol."
    if k == "SAT" and u_buy:
        return "ÇELİŞKİLİ: Uzun vadeli trend yukarı ama kısa vadede SAT/düzeltme sinyali var — uzun vadeli görüş bozulmadan kısa vadeli bir düzeltme olabilir."
    return "Kısa ve uzun vadeli görünüm arasında net bir çelişki yok, ancak net bir uyum da yok (BEKLE ağırlıklı)."


def estimate_move_probability(
    daily_close: pd.Series, current_price: float, target_price: float, window: int = PROBABILITY_WINDOW_TRADING_DAYS
) -> Optional[dict]:
    """
    "Bu seviyeye ulaşma ihtimali" için TAHMİNİ bir gelecek olasılığı değil,
    hissenin kendi geçmiş verisinden TARİHSEL SIKLIK hesaplar: son 1 yılda
    her `window` işlem günlük dönemde fiyat en az bu kadar hareket etmiş mi,
    kaç kere etmiş. Bu bir garanti veya istatistiksel kesinlik iddiası
    DEĞİLDİR — sadece "geçmişte bu büyüklükte hareketler ne sıklıkla oldu"
    sorusuna cevap verir.
    """
    required_pct = (target_price - current_price) / current_price * 100
    returns = daily_close.pct_change(window).dropna() * 100
    total = len(returns)
    if total < 30:
        return None

    if required_pct >= 0:
        hits = int((returns >= required_pct).sum())
    else:
        hits = int((returns <= required_pct).sum())

    return {
        "window_trading_days": window,
        "required_move_pct": round(required_pct, 1),
        "probability_pct": round(hits / total * 100, 1),
        "sample_size": total,
    }


def build_overall_recommendation(
    saatlik: dict, gunluk: dict, volatility_pct: float, levels: dict, price: float, daily_close: pd.Series
) -> dict:
    """
    Saatlik + günlük teknik sinyalleri birleştirip tek bir AL/SAT/BEKLE
    önerisi üretir (haftalık vade dahil değildir — bu daha çok kısa vadeli,
    "şimdi alırsam ne olur" bakış açısıyla ilgilidir).
    """
    s_signal, g_signal = saatlik["signal"], gunluk["signal"]
    s_buy, g_buy = saatlik["is_buy_signal"], gunluk["is_buy_signal"]

    if s_buy and g_buy:
        final_signal = "DİKKATLİ AL" if "DİKKATLİ AL" in (s_signal, g_signal) else "AL"
        direction = "yukarı"
        reason = f"Saatlik ({s_signal}) ve günlük ({g_signal}) sinyaller birlikte yukarı yönü destekliyor."
    elif s_signal == "SAT" and g_signal == "SAT":
        final_signal = "SAT"
        direction = "aşağı"
        reason = "Saatlik ve günlük sinyaller birlikte aşağı yönü destekliyor."
    else:
        final_signal = "BEKLE"
        direction = None
        reason = (
            f"Saatlik ({s_signal}) ve günlük ({g_signal}) sinyaller birbiriyle çelişiyor — "
            "net bir yön için henüz erken, temkinli olunmalı."
        )

    is_speculative = volatility_pct >= SPECULATIVE_VOLATILITY_THRESHOLD_PCT

    target = None
    probability = None
    if direction == "yukarı" and levels["resistance_levels"]:
        r = levels["resistance_levels"][0]
        target = {
            "level": r["level"],
            "type": "direnç",
            "target_pct": round((r["level"] - price) / price * 100, 1),
        }
        probability = estimate_move_probability(daily_close, price, r["level"])
    elif direction == "aşağı" and levels["support_levels"]:
        s = levels["support_levels"][0]
        target = {
            "level": s["level"],
            "type": "destek",
            "target_pct": round((s["level"] - price) / price * 100, 1),
        }
        probability = estimate_move_probability(daily_close, price, s["level"])

    return {
        "signal": final_signal,
        "is_buy_signal": final_signal in ("AL", "DİKKATLİ AL"),
        "reason": reason,
        "volatility_pct": round(volatility_pct, 1),
        "is_speculative": is_speculative,
        "target": target,
        "probability": probability,
        "note": (
            "Bu bir yatırım tavsiyesi değildir. Olasılık yüzdesi bir GELECEK "
            "GARANTİSİ değildir — hissenin son 1 yıllık geçmiş fiyat "
            "hareketlerinde benzer büyüklükteki değişimlerin kaç kez "
            "gerçekleştiğinin (tarihsel sıklık) oranıdır. Geçmişte sık "
            "görülmesi gelecekte de aynı sıklıkla olacağı anlamına gelmez. "
            "Yüksek oynaklık (spekülatif) hem büyük kazanç hem büyük kayıp "
            "riski taşır."
        ),
    }


def analyze(raw_symbol: str) -> dict:
    ticker = normalize_ticker(raw_symbol)

    fundamentals = fetch_fundamentals(ticker)
    fund_verdict, fund_notes = evaluate_fundamentals(fundamentals)

    timeframes = {}
    daily_df = None
    for key, cfg in TIMEFRAMES.items():
        df = fetch_data(ticker, cfg["period"], cfg["interval"])
        timeframes[key] = compute_timeframe(
            df, fund_verdict, cfg["label"], cfg["history_points"], cfg["is_intraday"]
        )
        if key == "kisa_vadeli":
            daily_df = df

    consistency_note = build_consistency_note(timeframes["kisa_vadeli"], timeframes["uzun_vadeli"])

    price = timeframes["kisa_vadeli"]["price"]
    daily_close = daily_df["Close"]
    daily_returns = daily_close.pct_change().dropna()
    volatility_pct = float(daily_returns.std()) * (252 ** 0.5) * 100
    levels = compute_levels(daily_df, price)

    genel_tavsiye = build_overall_recommendation(
        timeframes["saatlik"], timeframes["kisa_vadeli"], volatility_pct, levels, price, daily_close
    )

    return {
        "ticker": ticker,
        "price": price,
        "saatlik": timeframes["saatlik"],
        "kisa_vadeli": timeframes["kisa_vadeli"],
        "uzun_vadeli": timeframes["uzun_vadeli"],
        "consistency_note": consistency_note,
        "genel_tavsiye": genel_tavsiye,
        "fundamentals": fundamentals,
        "fund_verdict": fund_verdict,
        "fund_notes": fund_notes,
        "disclaimer": (
            "Bu bir yatırım tavsiyesi değildir, kâr garantisi vermez. Güven "
            "yüzdesi istatistiksel bir olasılık değildir, sadece kaç kriterin "
            "sinyali desteklediğinin oranıdır. Belirli bir tarihte belirli bir "
            "fiyata ulaşacağına dair bir tahmin içermez. Güncel haber/KAP "
            "açıklaması değerlendirmesi içermez."
        ),
    }
