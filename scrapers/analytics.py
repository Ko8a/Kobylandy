"""
Analytics engine — scoring, ranking, and report generation.
"""

import logging
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)

# District prestige weights (Есиль > Алматинский > Байконур > Нура > others)
DISTRICT_SCORE = {
    "есиль": 1.0,
    "алматинский": 0.75,
    "байконур": 0.55,
    "нура": 0.45,
}

# Deadline scores — the sooner, the better
DEADLINE_SCORE = {
    "сдан": 1.0,
    "q1 2025": 1.0, "q2 2025": 1.0, "q3 2025": 1.0, "q4 2025": 0.95,
    "q1 2026": 0.85, "q2 2026": 0.80, "q3 2026": 0.75, "q4 2026": 0.70,
    "q1 2027": 0.60, "q2 2027": 0.55, "q3 2027": 0.50, "q4 2027": 0.45,
    "q1 2028": 0.35, "q2 2028": 0.30, "q3 2028": 0.25, "q4 2028": 0.20,
}

# Developer reliability (based on market presence and delivery history)
DEVELOPER_RELIABILITY = {
    "bi group": 0.95,
    "qazaqstroy": 0.90,
    "kusto home": 0.90,
    "bazis-a": 0.85,
    "svoy dom": 0.80,
    "gbg": 0.80,
    "sensata": 0.80,
    "tamos invest": 0.75,
    "rams": 0.70,
    "sat development": 0.70,
    "elita group": 0.65,
    "miras group": 0.65,
    "eurasia group": 0.60,
}

# Suspected promo / error price threshold (below this is suspicious)
SUSPICIOUS_PRICE_M2 = 270_000  # < 270K ₸/m² is very unusual for Astana

# Normal range for Astana
MIN_NORMAL_PRICE_M2 = 320_000
MAX_NORMAL_PRICE_M2 = 1_200_000


def _get_district_score(district: Optional[str]) -> float:
    if not district:
        return 0.4
    d = str(district).lower()
    for key, score in DISTRICT_SCORE.items():
        if key in d:
            return score
    return 0.4


def _get_deadline_score(deadline: Optional[str]) -> float:
    if not deadline:
        return 0.3
    d = str(deadline).lower().strip()
    if "сдан" in d or "готов" in d:
        return 1.0
    for key, score in DEADLINE_SCORE.items():
        if key in d:
            return score
    return 0.3


def _get_developer_score(developer: Optional[str]) -> float:
    if not developer:
        return 0.5
    d = str(developer).lower()
    for key, score in DEVELOPER_RELIABILITY.items():
        if key in d:
            return score
    return 0.5


def _has_financing(conditions: Optional[str]) -> float:
    if not conditions:
        return 0.0
    c = str(conditions).lower()
    return 1.0 if ("ипотека" in c or "рассрочка" in c) else 0.0


def compute_score(row: pd.Series) -> float:
    """
    score = 0.45 * price_m2_score
          + 0.25 * deadline_score
          + 0.15 * district_score
          + 0.10 * developer_score
          + 0.05 * financing_score
    """
    price_m2 = row.get("цена_за_м2_тг")
    if not price_m2 or price_m2 <= 0:
        return 0.0

    # Normalize: lower price → higher score; range 300K–900K ₸/m²
    p_min, p_max = 300_000, 900_000
    clamped = max(p_min, min(p_max, price_m2))
    price_score = (p_max - clamped) / (p_max - p_min)

    deadline_score = _get_deadline_score(row.get("срок_сдачи"))
    district_score = _get_district_score(row.get("район_адрес"))
    developer_score = _get_developer_score(row.get("застройщик"))
    financing_score = _has_financing(row.get("условия_покупки"))

    return (
        0.45 * price_score
        + 0.25 * deadline_score
        + 0.15 * district_score
        + 0.10 * developer_score
        + 0.05 * financing_score
    )


def flag_suspicious(df: pd.DataFrame) -> pd.DataFrame:
    """Flag apartments with suspiciously low price per m²."""
    has_price = df["цена_за_м2_тг"].notna() & (df["цена_за_м2_тг"] > 0)
    df["подозрительная_цена"] = has_price & (df["цена_за_м2_тг"] < SUSPICIOUS_PRICE_M2)
    return df


def build_analytics(df: pd.DataFrame) -> dict:
    """Run all analytics and return a dict of DataFrames."""
    results = {}

    # Filter to apartments with price data
    with_price = df[df["цена_полная_тг"].notna() & (df["цена_полная_тг"] > 0)].copy()
    with_price_m2 = df[df["цена_за_м2_тг"].notna() & (df["цена_за_м2_тг"] > 0)].copy()

    # 1. Top-20 cheapest by total price
    results["top20_cheap_total"] = (
        with_price.sort_values("цена_полная_тг").head(20)
        [["застройщик", "название_жк", "район_адрес", "комнат", "площадь_м2",
          "цена_полная_тг", "цена_за_м2_тг", "этаж", "срок_сдачи", "статус",
          "условия_покупки", "источник", "ссылка_квартира"]]
        .reset_index(drop=True)
    )

    # 2. Top-20 cheapest by price per m²
    results["top20_cheap_m2"] = (
        with_price_m2.sort_values("цена_за_м2_тг").head(20)
        [["застройщик", "название_жк", "район_адрес", "комнат", "площадь_м2",
          "цена_полная_тг", "цена_за_м2_тг", "этаж", "срок_сдачи", "статус",
          "условия_покупки", "источник", "ссылка_квартира"]]
        .reset_index(drop=True)
    )

    # 3–5. Top-10 by room count
    for rooms in [1, 2, 3]:
        subset = with_price_m2[with_price_m2["комнат"] == rooms].copy()
        results[f"top10_{rooms}k"] = (
            subset.sort_values("цена_за_м2_тг").head(10)
            [["застройщик", "название_жк", "район_адрес", "площадь_м2",
              "цена_полная_тг", "цена_за_м2_тг", "этаж", "срок_сдачи",
              "статус", "отделка", "условия_покупки", "источник", "ссылка_квартира"]]
            .reset_index(drop=True)
        )

    # 6. Best by composite score
    with_price_m2["score"] = with_price_m2.apply(compute_score, axis=1)
    results["top20_best_score"] = (
        with_price_m2.sort_values("score", ascending=False).head(20)
        [["застройщик", "название_жк", "район_адрес", "комнат", "площадь_м2",
          "цена_полная_тг", "цена_за_м2_тг", "срок_сдачи", "класс_жилья",
          "условия_покупки", "score", "источник", "ссылка_квартира"]]
        .reset_index(drop=True)
    )
    with_price_m2.drop(columns=["score"], inplace=True, errors="ignore")

    # 7. Suspicious prices
    df = flag_suspicious(df)
    results["suspicious"] = (
        df[df["подозрительная_цена"] == True]
        [["застройщик", "название_жк", "комнат", "площадь_м2",
          "цена_полная_тг", "цена_за_м2_тг", "статус",
          "условия_покупки", "источник", "ссылка_квартира"]]
        .sort_values("цена_за_м2_тг")
        .reset_index(drop=True)
    )

    # 9. No price — need to call sales office
    results["no_price"] = (
        df[df["цена_полная_тг"].isna() | (df["цена_полная_тг"] == 0)]
        [["застройщик", "название_жк", "комнат", "площадь_м2", "статус",
          "условия_покупки", "источник", "ссылка_жк"]]
        .reset_index(drop=True)
    )

    logger.info(f"Analytics complete. {len(results)} result tables generated.")
    return results
