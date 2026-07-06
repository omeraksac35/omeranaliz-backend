"""
Yahoo Finance çağrılarını tek noktadan yöneten yardımcı katman.

Render gibi paylaşılan/datacenter IP'lerinden yapılan istekler Yahoo
tarafından zaman zaman "Too Many Requests" ile geçici olarak
kısıtlanıyor. Bunu azaltmak için iki şey yapılır:
  1. Kısa süreli bellek-içi önbellek: aynı sembol art arda sorgulandığında
     (kullanıcı hata alıp hemen tekrar denediğinde ya da farklı ekranlar
     aynı sembolü ayrı ayrı çektiğinde) gerçek bir HTTP isteği tekrar
     atılmaz.
  2. Kısa bir bekleme ile otomatik yeniden deneme: rate-limit hatası
     genelde birkaç saniye içinde geçici olduğu için 1-2 tekrar çoğu
     zaman isteği kurtarır.
"""

import time

import yfinance as yf

HISTORY_TTL_SECONDS = 180
INFO_TTL_SECONDS = 1800
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

_history_cache: dict[tuple[str, str, str], tuple[float, object]] = {}
_info_cache: dict[str, tuple[float, dict]] = {}


def _with_retry(fn):
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise last_exc


def get_history(ticker: str, period: str, interval: str):
    key = (ticker, period, interval)
    cached = _history_cache.get(key)
    now = time.time()
    if cached and now - cached[0] < HISTORY_TTL_SECONDS:
        return cached[1]

    df = _with_retry(lambda: yf.Ticker(ticker).history(period=period, interval=interval))
    _history_cache[key] = (now, df)
    return df


def get_info(ticker: str) -> dict:
    cached = _info_cache.get(ticker)
    now = time.time()
    if cached and now - cached[0] < INFO_TTL_SECONDS:
        return cached[1]

    info = _with_retry(lambda: yf.Ticker(ticker).info)
    _info_cache[ticker] = (now, info)
    return info
