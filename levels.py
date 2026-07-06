"""
Çoklu direnç/destek seviyesi tespiti ve "ölçülü hareket" (measured move)
yöntemiyle kırılma hedefi hesaplama.

Yöntem: Bir direnç kırıldığında, kırılma öncesi trading range'in yüksekliği
(direnç - altındaki en yakın destek) kırılma noktasından yukarı doğru
projekte edilir: hedef = direnç + (direnç - destek). Bu, teknik analizde
yaygın kullanılan, açıklanabilir bir tahmindir — kesinlik iddiası taşımaz.
"""

import pandas as pd


def find_swing_points(df: pd.DataFrame, order: int = 5):
    highs = df["High"].values
    lows = df["Low"].values
    n = len(df)
    resistance_points = []
    support_points = []

    if n - 2 * order <= 0:
        return resistance_points, support_points

    for i in range(order, n - order):
        window_high = highs[i - order : i + order + 1]
        if highs[i] == window_high.max():
            resistance_points.append(float(highs[i]))
        window_low = lows[i - order : i + order + 1]
        if lows[i] == window_low.min():
            support_points.append(float(lows[i]))

    return resistance_points, support_points


def cluster_levels(prices: list, tolerance_pct: float = 0.015) -> list:
    if not prices:
        return []
    sorted_prices = sorted(set(round(p, 2) for p in prices))
    clusters = [[sorted_prices[0]]]
    for p in sorted_prices[1:]:
        if p <= clusters[-1][-1] * (1 + tolerance_pct):
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [sum(c) / len(c) for c in clusters]


def compute_levels(df: pd.DataFrame, current_price: float, order: int = 5, max_levels: int = 3) -> dict:
    resistance_points, support_points = find_swing_points(df, order=order)
    resistance_prices = cluster_levels(resistance_points)
    support_prices = cluster_levels(support_points)

    above = sorted([r for r in resistance_prices if r > current_price])[:max_levels]
    resistance_levels = []
    for r in above:
        supports_below = [s for s in support_prices if s < r]
        nearest_support = max(supports_below) if supports_below else current_price * 0.95
        range_height = r - nearest_support
        breakout_target = r + range_height
        resistance_levels.append(
            {
                "level": round(r, 4),
                "nearest_support": round(nearest_support, 4),
                "breakout_target": round(breakout_target, 4),
            }
        )

    below = sorted([s for s in support_prices if s < current_price], reverse=True)[:max_levels]
    support_levels = []
    for s in below:
        resistances_above = [r for r in resistance_prices if r > s]
        nearest_resistance = min(resistances_above) if resistances_above else current_price * 1.05
        range_height = nearest_resistance - s
        breakdown_target = s - range_height
        support_levels.append(
            {
                "level": round(s, 4),
                "nearest_resistance": round(nearest_resistance, 4),
                "breakdown_target": round(breakdown_target, 4),
            }
        )

    return {"resistance_levels": resistance_levels, "support_levels": support_levels}
