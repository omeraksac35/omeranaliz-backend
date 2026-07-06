"""
Uygulamanın üstünde kayan görsel "ticker bandı" için hafif, hızlı veri.
BIST100 endeksi + birkaç büyük hissenin güncel fiyatı ve günlük değişim
yüzdesini döner. Salt görsel/bilgilendirme amaçlıdır, analiz veya sinyal
üretmez.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from yf_client import get_history

TICKER_TAPE_SYMBOLS = [
    {"symbol": "XU100", "label": "BIST100"},
    {"symbol": "THYAO", "label": "THYAO"},
    {"symbol": "GARAN", "label": "GARAN"},
    {"symbol": "ASELS", "label": "ASELS"},
    {"symbol": "BIMAS", "label": "BIMAS"},
    {"symbol": "EREGL", "label": "EREGL"},
    {"symbol": "AKBNK", "label": "AKBNK"},
    {"symbol": "SASA", "label": "SASA"},
]


def _fetch_one(item: dict) -> Optional[dict]:
    ticker = f"{item['symbol']}.IS"
    try:
        df = get_history(ticker, period="5d", interval="1d")
        if df.empty or len(df) < 2:
            return None
        close = df["Close"]
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change_pct = (price - prev) / prev * 100
        return {"label": item["label"], "price": round(price, 2), "change_pct": round(change_pct, 2)}
    except Exception:
        return None


def get_ticker_tape() -> dict:
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_one, item) for item in TICKER_TAPE_SYMBOLS]
        items = [f.result() for f in futures]
    return {"items": [i for i in items if i is not None]}
