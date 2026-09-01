"""
pricing_suggestions.py — Endpoints for pricing suggestion management.

Handles listing pending suggestions, on-demand suggestion generation,
and the accept/reject approval workflow. Accepting a suggestion atomically
updates the product's current_price.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models import (
    Product, PricingSuggestion,
    SuggestionStatus, TriggerReason, ProductStatus,
)
from app.schemas import PricingSuggestionOut, SuggestionStatusUpdate
from app.agentic_loop import _get_strategy, get_category_avg_velocity

router = APIRouter(tags=["Pricing Suggestions"])


@router.get("/pricing-suggestions", response_model=List[PricingSuggestionOut])
def list_pricing_suggestions(
    status: Optional[str] = Query(None, description="Filter by suggestion status (PENDING, ACCEPTED, REJECTED)"),
    db: Session = Depends(get_db),
):
    """
    List all pricing suggestions, optionally filtered by status.
    The frontend uses status=PENDING to populate the suggestions panel.
    """
    query = db.query(PricingSuggestion)
    if status:
        query = query.filter(PricingSuggestion.status == status)
    return query.order_by(PricingSuggestion.created_at.desc()).all()


@router.post("/products/{product_id}/suggest-pricing", response_model=PricingSuggestionOut)
def suggest_pricing(product_id: int, db: Session = Depends(get_db)):
    """
    On-demand pricing suggestion (trigger_reason=MANUAL).
    Uses the same strategy interface as the agentic loop — no duplicated logic.
    Calls the active pricing strategy (rule or AI based on env var).
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    category_avg = get_category_avg_velocity(db, product.category)
    strategy = _get_strategy("pricing")
    rec = strategy.recommend_pricing(product, TriggerReason.MANUAL.value, category_avg)

    suggestion = PricingSuggestion(
        product_id=product_id,
        current_price=product.current_price,
        recommended_price=rec.recommended_price,
        direction=rec.direction,
        confidence=rec.confidence,
        reasoning=rec.reasoning,
        status=SuggestionStatus.PENDING,
        trigger_reason=TriggerReason.MANUAL,
    )
    db.add(suggestion)
    product.status = ProductStatus.PRICE_REVIEW_PENDING
    db.commit()
    db.refresh(suggestion)
    return suggestion


@router.patch("/pricing-suggestions/{suggestion_id}", response_model=PricingSuggestionOut)
def update_pricing_suggestion(
    suggestion_id: int,
    payload: SuggestionStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Accept or reject a pricing suggestion.
    ACCEPT: atomically updates Product.current_price to the recommended price.
    Resets product status to ACTIVE if no other pending suggestions remain.
    """
    suggestion = db.query(PricingSuggestion).filter(PricingSuggestion.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Pricing suggestion not found")

    if suggestion.status != SuggestionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Suggestion is not in PENDING status")

    suggestion.status = payload.status

    if payload.status == SuggestionStatus.ACCEPTED:
        # Atomically update the product's price
        product = db.query(Product).filter(Product.id == suggestion.product_id).first()
        if product:
            product.current_price = suggestion.recommended_price
            # Reset status to ACTIVE if no other pending pricing suggestions
            other_pending = db.query(PricingSuggestion).filter(
                PricingSuggestion.product_id == product.id,
                PricingSuggestion.id != suggestion_id,
                PricingSuggestion.status == SuggestionStatus.PENDING,
            ).count()
            if other_pending == 0:
                product.status = ProductStatus.ACTIVE

    elif payload.status == SuggestionStatus.REJECTED:
        # Reset product status if no other pending suggestions
        product = db.query(Product).filter(Product.id == suggestion.product_id).first()
        if product:
            other_pending = db.query(PricingSuggestion).filter(
                PricingSuggestion.product_id == product.id,
                PricingSuggestion.id != suggestion_id,
                PricingSuggestion.status == SuggestionStatus.PENDING,
            ).count()
            if other_pending == 0:
                product.status = ProductStatus.ACTIVE

    db.commit()
    db.refresh(suggestion)
    return suggestion
