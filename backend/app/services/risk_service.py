"""
risk_service.py — Inventory risk scoring service.

Calculates a deterministic risk score (0-100) for products based on:
- Stock level relative to reorder threshold
- Demand velocity
- Estimated days until stockout
- Out-of-stock state

Reusable across product API, analytics, and what-if simulator.
"""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class RiskAssessment:
    """Complete risk assessment for a single product."""
    risk_score: int  # 0-100
    risk_level: str  # LOW, MODERATE, HIGH, CRITICAL
    risk_factors: List[str]
    estimated_stockout_days: Optional[float]


def calculate_stockout_days(stock_level: int, demand_velocity: int) -> Optional[float]:
    """
    Calculate estimated days until stockout.
    Returns None if demand_velocity <= 0 (no active demand).
    Never divides by zero.
    """
    if demand_velocity <= 0:
        return None
    return round(stock_level / demand_velocity, 2)


def calculate_risk_score(
    stock_level: int,
    reorder_threshold: int,
    demand_velocity: int,
    status: str,
) -> RiskAssessment:
    """
    Calculate a deterministic inventory risk score (0-100).

    Scoring algorithm:
    - 40 points max from stock-to-threshold ratio
    - 25 points max from demand velocity intensity
    - 25 points max from stockout proximity
    - 10 points if currently OUT_OF_STOCK
    """
    score = 0
    factors: List[str] = []

    # Factor 1: Stock level vs reorder threshold (0-40 points)
    if reorder_threshold > 0:
        ratio = stock_level / reorder_threshold
        if ratio <= 0:
            score += 40
            factors.append("Stock is completely depleted")
        elif ratio < 0.5:
            score += 35
            factors.append("Stock is critically below reorder threshold")
        elif ratio < 1.0:
            score += 25
            factors.append("Stock is below reorder threshold")
        elif ratio < 1.5:
            score += 10
            factors.append("Stock is approaching reorder threshold")
        # else: healthy stock, no points added
    elif stock_level == 0:
        score += 40
        factors.append("Stock is completely depleted")

    # Factor 2: Demand velocity intensity (0-25 points)
    if demand_velocity >= 20:
        score += 25
        factors.append("Extremely high demand velocity")
    elif demand_velocity >= 10:
        score += 18
        factors.append("High demand velocity")
    elif demand_velocity >= 5:
        score += 10
        factors.append("Moderate demand velocity")
    elif demand_velocity >= 2:
        score += 5
        factors.append("Low-moderate demand velocity")

    # Factor 3: Stockout proximity (0-25 points)
    stockout_days = calculate_stockout_days(stock_level, demand_velocity)
    if stockout_days is not None:
        if stockout_days <= 1:
            score += 25
            factors.append("Estimated stockout within 1 day")
        elif stockout_days <= 2:
            score += 20
            factors.append("Estimated stockout within 2 days")
        elif stockout_days <= 5:
            score += 12
            factors.append("Estimated stockout within 5 days")
        elif stockout_days <= 10:
            score += 5
            factors.append("Estimated stockout within 10 days")

    # Factor 4: Already out of stock (0-10 points)
    if status == "OUT_OF_STOCK":
        score += 10
        factors.append("Product is currently out of stock")

    # Clamp to 0-100
    score = min(100, max(0, score))

    # Determine risk level
    if score >= 76:
        risk_level = "CRITICAL"
    elif score >= 51:
        risk_level = "HIGH"
    elif score >= 26:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    return RiskAssessment(
        risk_score=score,
        risk_level=risk_level,
        risk_factors=factors,
        estimated_stockout_days=stockout_days,
    )
