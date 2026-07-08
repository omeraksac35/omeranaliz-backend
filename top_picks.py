"""
BIST100'e yakın kapsamda taranan tüm hisseler için "yükselme potansiyeli"
sıralaması üretir. AL/SAT filtrelemesi YAPMAZ — her hisse için teknik
durum (destek yakınlığı, önündeki direnç), geçmiş fiyat davranışına dayalı
tarihsel olasılık ve güncel kritik haberleri derleyip sıralar. En yüksek
potansiyelli hisse en üstte olacak şekilde HER ZAMAN bir liste döner.

ÖNEMLİ: "% olasılık", hissenin kendi geçmiş fiyat hareketlerinde benzer
büyüklükteki değişimlerin ne sıklıkla gerçekleştiğine dayanan TARİHSEL bir
sıklık ölçüsüdür — gelecek için garanti ya da kesin tahmin İÇERMEZ. Bu bir
yatırım tavsiyesi değildir.

Tüm hisseleri her istekte yeniden hesaplamak hem yavaş hem Yahoo Finance
rate-limit riskini artıracağı için sonuçlar bellek-içi önbellekte tutulur
ve en fazla saatte bir yeniden hesaplanır.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from analysis import estimate_move_probability, fetch_data, normalize_ticker
from levels import compute_levels
from news import get_news_for_symbol
from risky_stocks import CURATED_TICKERS

# CURATED_TICKERS (risky_stocks.py) ~28 hisseyle sınırlı. BIST100'e daha
# yakın bir kapsam için bilinen BIST100/BIST30 bileşenleriyle genişletiyoruz.
# NOT: TradingView gibi sitelerin canlı listesini otomatik kazımak
# (scraping) hem kullanım şartlarına aykırı olur hem kırılgan bir bağımlılık
# yaratır; bunun yerine bilinen BIST100/BIST30 hisselerinden oluşan sabit
# bir liste kullanılır. Sembol yanlış/pasif olsa bile analiz sessizce
# atlanır, bu yüzden listeye geniş yaklaşılabilir.
EXTRA_TICKERS = [
    "YKBNK", "HALKB", "VAKBN", "TSKB", "ALBRK",
    "SAHOL", "ALARK", "ENKAI", "TKFEN", "DOHOL", "AGHOL",
    "TTRAK", "OTKAR", "KARSN", "KRDMD", "ISDMR", "ASUZU", "EGEEN", "CEMTS",
    "SOKM", "CCOLA", "MAVI",
    "TCELL", "TTKOM", "LOGO", "NETAS", "INDES",
    "AKSEN", "ZOREN", "GWIND", "NTGAZ",
    "AKSA", "GUBRF", "HEKTS", "ALKIM", "BAGFS",
    "CIMSA", "OYAKC", "BRSAN", "BRISA", "KARTN", "IZMDC",
    "ISGYO", "YATAS", "GOLTS", "SNGYO", "TRGYO", "KLGYO", "PSGYO",
    "ANSGR", "TURSG", "SKBNK", "ISMEN", "GLYHO",
    "DEVA", "ECILC", "SELEC", "MPARK",
    # İkinci genişletme turu: BIST100 kapsamını daha da artırmak için
    "AKFYE", "AYDEM", "ALFAS", "CWENE", "BERA", "QUAGR", "QNBTR",
    "MIATK", "REEDR", "FONET", "OBASE", "PAPIL", "HTTBT",
    "ARENA", "DGATE", "LINK", "KFEIN",
    "VAKKO", "TMSN", "EGSER", "USAK", "KUTPO",
    "AKGRT", "RAYSG", "KONTR", "SUWEN", "KAYSE",
]

SCAN_TICKERS = list(dict.fromkeys(CURATED_TICKERS + EXTRA_TICKERS))

CACHE_TTL_SECONDS = 3600

_cache: dict = {"timestamp": 0.0, "picks": []}


def _evaluate_stock(base_symbol: str) -> Optional[dict]:
    try:
        ticker = normalize_ticker(base_symbol)
        df = fetch_data(ticker, period="1y", interval="1d")
    except Exception:
        return None

    price = float(df["Close"].iloc[-1])
    daily_close = df["Close"]
    returns = daily_close.pct_change().dropna()
    volatility_pct = float(returns.std()) * (252 ** 0.5) * 100 if len(returns) > 1 else 0.0

    levels = compute_levels(df, price)
    resistance_levels = levels["resistance_levels"]
    support_levels = levels["support_levels"]

    has_resistance_overhead = bool(resistance_levels)
    if resistance_levels:
        target_level = resistance_levels[0]["level"]
    else:
        year_high = float(df["High"].max())
        target_level = year_high if year_high > price * 1.01 else None

    probability = estimate_move_probability(daily_close, price, target_level) if target_level else None

    if support_levels:
        support_level = support_levels[0]["level"]
        support_distance_pct = round((price - support_level) / price * 100, 1)
        downside_probability = estimate_move_probability(daily_close, price, support_level)
    else:
        support_level = None
        support_distance_pct = None
        downside_probability = None

    target_pct = round((target_level - price) / price * 100, 1) if target_level is not None else None
    upside_prob_pct = probability["probability_pct"] if probability else None
    downside_prob_pct = downside_probability["probability_pct"] if downside_probability else None

    # Bu liste zaten "yükselme potansiyeli" üzerine kurulu — hedef seviye
    # tanımı gereği her zaman mevcut fiyatın üzerindedir. Bu yüzden ayrı bir
    # (bazen çelişkili görünen) SAT/BEKLE teknik sinyali yerine, yükselme
    # potansiyelinin büyüklüğüne, düşme olasılığına kıyasla yükselme
    # olasılığının gücüne göre tutarlı bir etiket kullanılır:
    #  - Hedef %1'in altındaysa (önemsiz hareket, gürültü): BEKLE
    #  - Düşme olasılığı yükselme olasılığından yüksekse (aşağı yönlü risk
    #    daha olası): AL önerilmez, SAT
    #  - Yükselme olasılığı %50'nin üzerindeyse: GÜÇLÜ AL
    #  - Diğer durumlarda: AL
    if target_pct is None or target_pct < 1.0:
        potential_label = "BEKLE"
    elif downside_prob_pct is not None and upside_prob_pct is not None and downside_prob_pct > upside_prob_pct:
        potential_label = "SAT"
    elif upside_prob_pct is not None and upside_prob_pct > 50:
        potential_label = "GÜÇLÜ AL"
    else:
        potential_label = "AL"

    critical_categories: list = []
    try:
        news = get_news_for_symbol(base_symbol)
        seen = set()
        for note in news["critical_notes"]:
            for c in note["categories"]:
                if c not in seen:
                    seen.add(c)
                    critical_categories.append(c)
    except Exception:
        pass

    return {
        "ticker": ticker,
        "price": round(price, 4),
        "potential_label": potential_label,
        "target_level": round(target_level, 4) if target_level is not None else None,
        "target_pct": target_pct,
        "probability_pct": upside_prob_pct,
        "has_resistance_overhead": has_resistance_overhead,
        "support_level": round(support_level, 4) if support_level is not None else None,
        "support_distance_pct": support_distance_pct,
        "downside_probability_pct": downside_prob_pct,
        "volatility_pct": round(volatility_pct, 1),
        "critical_news_categories": critical_categories,
    }


_LABEL_RANK = {"GÜÇLÜ AL": 3, "AL": 2, "BEKLE": 1, "SAT": 0}


def _sort_key(p: dict):
    """
    Önce etiket gücüne göre sıralanır (GÜÇLÜ AL en üstte, SAT en altta).
    Aynı etiket içinde "beklenen değer" (hedef % × olasılık %) kullanılır:
    sadece "en çok artabilecek" hisseyi öne çıkarmak yanıltıcı olur — %50
    hedefi olan ama tarihte neredeyse hiç gerçekleşmemiş (%1-2 olasılık)
    bir hareket, %5 hedefi olup makul sıklıkla (%40-50) gerçekleşen bir
    hareketten daha "değerli" değildir.
    """
    label_rank = _LABEL_RANK.get(p["potential_label"], 0)
    target_pct = p["target_pct"] if p["target_pct"] is not None else 0.0
    prob = p["probability_pct"] if p["probability_pct"] is not None else 0.0
    return (label_rank, target_pct * prob)


def _compute_all_picks() -> list:
    picks = []
    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = {executor.submit(_evaluate_stock, sym): sym for sym in SCAN_TICKERS}
        for future in as_completed(futures):
            pick = future.result()
            if pick is not None:
                picks.append(pick)

    picks.sort(key=_sort_key, reverse=True)
    return picks


def get_top_picks(top_n: int = 15, force_refresh: bool = False) -> dict:
    now = time.time()
    is_stale = force_refresh or (now - _cache["timestamp"] >= CACHE_TTL_SECONDS) or not _cache["picks"]

    if is_stale:
        _cache["picks"] = _compute_all_picks()
        _cache["timestamp"] = now

    return {
        "picks": _cache["picks"][:top_n],
        "scanned_count": len(SCAN_TICKERS),
        "matched_count": len(_cache["picks"]),
        "last_updated_unix": _cache["timestamp"],
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "note": (
            "Taranan tüm hisseler önce GÜÇLÜ AL/AL/BEKLE/SAT etiketine, "
            "sonra hedefe kadar ne kadar artabileceği (%) × bu seviyeye "
            "ulaşma olasılığına göre sıralanır. Hem yükselme hem düşme "
            "olasılığı hesaplanır (sırasıyla en yakın direnç ve destek "
            "seviyesine ulaşmanın son 1 yıldaki TARİHSEL sıklığı — gelecek "
            "garantisi DEĞİLDİR). Düşme olasılığı yükselme olasılığından "
            "yüksekse AL önerilmez (SAT). Yükselme olasılığı %50'nin "
            "üzerindeyse GÜÇLÜ AL, %1'in altındaki hedefler önemsiz kabul "
            "edilip BEKLE olarak işaretlenir. Hedef seviye önündeki en "
            "yakın dirençtir; direnç yoksa 1 yıllık zirve referans alınır. "
            "Destek seviyesi de benzer şekilde en yakın destektir. Kritik "
            "haberler basit anahtar kelime eşleştirmesiyle tespit edilir, "
            "duygu analizi değildir. Bu bir yatırım tavsiyesi değildir. "
            "Tüm BIST değil, bilinen BIST100/BIST30 hisselerinden oluşan "
            f"{len(SCAN_TICKERS)} hisselik bir örneklem taranmıştır. "
            "Sonuçlar en fazla saatte bir yeniden hesaplanır."
        ),
    }
