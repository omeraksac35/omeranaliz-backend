from yf_client import get_info


def fetch_fundamentals(ticker: str) -> dict:
    try:
        info = get_info(ticker)
    except Exception:
        info = {}
    return {
        "sector": info.get("sector"),
        "long_name": info.get("longName"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "pb_ratio": info.get("priceToBook"),
        "debt_to_equity": info.get("debtToEquity"),
        "roe": info.get("returnOnEquity"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "dividend_yield": info.get("dividendYield"),
        "current_ratio": info.get("currentRatio"),
    }


def evaluate_fundamentals(f: dict) -> tuple[str, list]:
    """
    Basit kural tabanlı bir bilanço/oran değerlendirmesi. Banka gibi
    sektörlerde bazı oranlar (debt_to_equity, current_ratio) mevcut
    olmayabilir; eksik veriler değerlendirmeden atlanır.
    """
    red_flags = []
    green_flags = []

    profit_margin = f.get("profit_margin")
    if profit_margin is not None:
        if profit_margin < 0:
            red_flags.append("şirket zarar ediyor (negatif kâr marjı)")
        elif profit_margin > 0.10:
            green_flags.append(f"sağlıklı kâr marjı (%{profit_margin*100:.1f})")

    revenue_growth = f.get("revenue_growth")
    if revenue_growth is not None:
        if revenue_growth < 0:
            red_flags.append(f"ciro daralıyor (%{revenue_growth*100:.1f})")
        elif revenue_growth > 0.10:
            green_flags.append(f"ciro büyüyor (%{revenue_growth*100:.1f})")

    roe = f.get("roe")
    if roe is not None:
        if roe < 0:
            red_flags.append("özkaynak kârlılığı negatif (ROE)")
        elif roe > 0.15:
            green_flags.append(f"güçlü özkaynak kârlılığı (ROE %{roe*100:.1f})")

    debt_to_equity = f.get("debt_to_equity")
    if debt_to_equity is not None:
        if debt_to_equity > 200:
            red_flags.append(f"yüksek borç/özkaynak oranı ({debt_to_equity:.0f})")
        elif debt_to_equity < 50:
            green_flags.append(f"düşük borç/özkaynak oranı ({debt_to_equity:.0f})")

    pe_ratio = f.get("pe_ratio")
    if pe_ratio is not None:
        if pe_ratio < 0:
            red_flags.append("negatif F/K (şirket zarar ediyor)")
        elif pe_ratio > 60:
            red_flags.append(f"F/K oranı çok yüksek ({pe_ratio:.1f}) — pahalı olabilir")

    dividend_yield = f.get("dividend_yield")
    if dividend_yield is not None and dividend_yield > 0:
        green_flags.append(f"temettü ödüyor (verim %{dividend_yield:.2f})")

    if len(red_flags) >= 2:
        verdict = "ZAYIF"
    elif red_flags and not green_flags:
        verdict = "ZAYIF"
    elif len(green_flags) >= 2 and not red_flags:
        verdict = "GÜÇLÜ"
    else:
        verdict = "KARIŞIK/NÖTR"

    notes = [f"+ {g}" for g in green_flags] + [f"- {r}" for r in red_flags]
    return verdict, notes
