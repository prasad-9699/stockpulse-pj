"""
settings.py — Strategy toggle, analytics, and recommendation history endpoints.

These are top-level routes for app-wide settings and cross-product views
that don't belong under the /products prefix.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models import (
    AppSettings, PricingSuggestion, ReorderSuggestion, SuggestionStatus,
)
from app.schemas import (
    StrategySettingsOut, StrategySettingsUpdate,
    PricingSuggestionOut, ReorderSuggestionOut,
)
from app.services.analytics_service import get_analytics_overview

router = APIRouter(tags=["Settings & Analytics"])


# ──────────────────────── Strategy Toggle ────────────────────────


@router.get("/settings/strategy", response_model=StrategySettingsOut)
def get_strategy(db: Session = Depends(get_db)):
    """
    Get the currently active recommendation strategy.
    Returns 'AI' or 'RULE_BASED'. Creates default settings if none exist.
    """
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings(id=1, active_strategy="RULE_BASED")
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return StrategySettingsOut(strategy=settings.active_strategy)


@router.patch("/settings/strategy", response_model=StrategySettingsOut)
def update_strategy(
    payload: StrategySettingsUpdate,
    db: Session = Depends(get_db),
):
    """
    Switch between AI and Rule-Based strategies at runtime.
    Persists to DB so it survives server restarts. No restart needed.
    """
    strategy = payload.strategy.upper()
    if strategy not in ("AI", "RULE_BASED"):
        raise HTTPException(status_code=400, detail="Strategy must be 'AI' or 'RULE_BASED'")

    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings(id=1, active_strategy=strategy)
        db.add(settings)
    else:
        settings.active_strategy = strategy

    db.commit()
    db.refresh(settings)
    return StrategySettingsOut(strategy=settings.active_strategy)


# ──────────────────────── Analytics ────────────────────────


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """
    Get analytics overview with real database data.
    Returns summary metrics, inventory health distribution,
    trigger distribution, and per-product risk data.
    """
    return get_analytics_overview(db)


# ──────────────────────── Recommendation History ────────────────────────


@router.get("/recommendations/history")
def get_recommendation_history(
    status: Optional[str] = Query(None, description="Filter by status: PENDING, ACCEPTED, REJECTED"),
    suggestion_type: Optional[str] = Query(None, description="Filter by type: pricing, reorder"),
    db: Session = Depends(get_db),
):
    """
    Get all recommendations (pricing + reorder) with optional filters.
    Returns a unified list sorted by creation date descending.
    Unlike the suggestion endpoints which default to PENDING, this returns all statuses.
    """
    results = []

    if suggestion_type is None or suggestion_type == "pricing":
        query = db.query(PricingSuggestion)
        if status:
            query = query.filter(PricingSuggestion.status == status)
        for s in query.order_by(PricingSuggestion.created_at.desc()).all():
            results.append({
                "id": s.id,
                "type": "pricing",
                "product_id": s.product_id,
                "status": s.status.value if hasattr(s.status, 'value') else s.status,
                "trigger_reason": s.trigger_reason.value if hasattr(s.trigger_reason, 'value') else s.trigger_reason,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
                "strategy_used": s.strategy_used,
                "fallback_used": s.fallback_used,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                # Pricing-specific fields
                "current_price": s.current_price,
                "recommended_price": s.recommended_price,
                "direction": s.direction.value if hasattr(s.direction, 'value') else s.direction,
            })

    if suggestion_type is None or suggestion_type == "reorder":
        query = db.query(ReorderSuggestion)
        if status:
            query = query.filter(ReorderSuggestion.status == status)
        for s in query.order_by(ReorderSuggestion.created_at.desc()).all():
            results.append({
                "id": s.id,
                "type": "reorder",
                "product_id": s.product_id,
                "status": s.status.value if hasattr(s.status, 'value') else s.status,
                "trigger_reason": s.trigger_reason.value if hasattr(s.trigger_reason, 'value') else s.trigger_reason,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
                "strategy_used": s.strategy_used,
                "fallback_used": s.fallback_used,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                # Reorder-specific fields
                "current_stock": s.current_stock,
                "recommended_quantity": s.recommended_quantity,
                "lead_time_days": s.lead_time_days,
            })

    # Sort unified list by created_at descending
    results.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return results
