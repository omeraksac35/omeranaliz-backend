"""
Mevcut analiz motorunu (saatlik+günlük birleşik AL/SAT önerisi) tüm
taranan hisselere uygulayıp, yükselme potansiyeli en yüksek görünenleri
listeler.

ÖNEMLİ: Bu bir yatırım tavsiyesi değildir. "Olasılık", hissenin kendi
geçmiş fiyat hareketlerinde benzer büyüklükteki değişimlerin ne sıklıkla
gerçekleştiğine dayanan TARİHSEL bir sıklık ölçüsüdür — gelecek için bir
garanti ya da kesin tahmin İÇERMEZ.

Tüm hisseleri her istekte yeniden hesaplamak hem yavaş hem Yahoo Finance
rate-limit riskini artıracağı için sonuçlar bellek-içi önbellekte tutulur
ve en fazla saatte bir yeniden hesaplanır.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from analysis import analyze
from risky_stocks import CURATED_TICKERS

CACHE_TTL_SECONDS = 3600

_cache: dict = {"timestamp": 0.0, "picks": []}


def _evaluate_pick(base_symbol: str) -> Optional[dict]:
    try:
        result = analyze(base_symbol)
    except Exception:
        return None

    gt = result.get("genel_tavsiye")
    if not gt or not gt.get("is_buy_signal") or not gt.get("target") or not gt.get("probability"):
        return None

    return {
        "ticker": result["ticker"],
        "price": result["price"],
        "signal": gt["signal"],
        "reason": gt["reason"],
        "target_level": gt["target"]["level"],
        "target_pct": gt["target"]["target_pct"],
        "probability_pct": gt["probability"]["probability_pct"],
        "volatility_pct": gt["volatility_pct"],
        "is_speculative": gt["is_speculative"],
    }


def _compute_all_picks() -> list:
    picks = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_evaluate_pick, sym): sym for sym in CURATED_TICKERS}
        for future in as_completed(futures):
            pick = future.result()
            if pick is not None:
                picks.append(pick)

    picks.sort(key=lambda p: (p["probability_pct"], p["target_pct"]), reverse=True)
    return picks


def get_top_picks(top_n: int = 10, force_refresh: bool = False) -> dict:
    now = time.time()
    is_stale = force_refresh or (now - _cache["timestamp"] >= CACHE_TTL_SECONDS) or not _cache["picks"]

    if is_stale:
        _cache["picks"] = _compute_all_picks()
        _cache["timestamp"] = now

    return {
        "picks": _cache["picks"][:top_n],
        "scanned_count": len(CURATED_TICKERS),
        "matched_count": len(_cache["picks"]),
        "last_updated_unix": _cache["timestamp"],
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "note": (
            "Bu liste, saatlik ve günlük teknik sinyali birlikte AL yönünde "
            "olan ve tespit edilebilir bir direnç hedefi bulunan hisseleri, "
            "bu hedefe ulaşmanın geçmişte ne sıklıkla gerçekleştiğine "
            "(tarihsel sıklık) göre sıralar. Bu bir yatırım tavsiyesi ya da "
            "gelecek garantisi DEĞİLDİR. Tüm BIST değil, seçilmiş "
            f"{len(CURATED_TICKERS)} hisselik bir örneklem taranmıştır. "
            "Sonuçlar en fazla saatte bir yeniden hesaplanır."
        ),
    }
