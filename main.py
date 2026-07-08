from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from analysis import analyze
from chart import get_chart
from news import get_news_for_symbol
from risky_stocks import get_risk_profile, get_risky_stocks
from ticker_tape import get_ticker_tape
from top_picks import get_top_picks

app = FastAPI(title="BIST Teknik+Temel Analiz API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/analyze/{symbol}")
def get_analysis(symbol: str):
    try:
        return analyze(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analiz sırasında hata: {exc}")


@app.get("/chart/{symbol}")
def get_chart_endpoint(symbol: str, timeframe: str = "gunluk"):
    try:
        return get_chart(symbol, timeframe)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Grafik verisi alınırken hata: {exc}")


@app.get("/news/{symbol}")
def get_news_endpoint(symbol: str):
    base_symbol = symbol.strip().upper().replace(".IS", "")
    try:
        return get_news_for_symbol(base_symbol)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Haberler alınırken hata: {exc}")


@app.get("/risky-stocks")
def get_risky_stocks_endpoint(top_n: int = 15):
    try:
        return get_risky_stocks(top_n)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Riskli hisseler alınırken hata: {exc}")


@app.get("/risk-profile/{symbol}")
def get_risk_profile_endpoint(symbol: str):
    try:
        return get_risk_profile(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Risk profili alınırken hata: {exc}")


@app.get("/ticker-tape")
def get_ticker_tape_endpoint():
    try:
        return get_ticker_tape()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ticker verisi alınırken hata: {exc}")


@app.get("/top-picks")
def get_top_picks_endpoint(top_n: int = 10, force_refresh: bool = False):
    try:
        return get_top_picks(top_n, force_refresh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Önerilen hisseler alınırken hata: {exc}")
