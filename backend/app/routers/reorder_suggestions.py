"""
reorder_suggestions.py — Endpoints for reorder suggestion management.

Handles listing pending suggestions, on-demand suggestion generation,
and the accept/reject approval workflow. Accepting a suggestion atomically
increments the product's stock_level (simulated inbound shipment).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models import (
    Product, ReorderSuggestion,
    SuggestionStatus, TriggerReason, ProductStatus,
)
from app.schemas import ReorderSuggestionOut, SuggestionStatusUpdate
from app.agentic_loop import _get_strategy

router = APIRouter(tags=["Reorder Suggestions"])


@router.get("/reorder-suggestions", response_model=List[ReorderSuggestionOut])
def list_reorder_suggestions(
    status: Optional[str] = Query(None, description="Filter by suggestion status (PENDING, ACCEPTED, REJECTED)"),
    db: Session = Depends(get_db),
):
    """
    List all reorder suggestions, optionally filtered by status.
    The frontend uses status=PENDING to populate the suggestions panel.
    """
    query = db.query(ReorderSuggestion)
    if status:
        query = query.filter(ReorderSuggestion.status == status)
    return query.order_by(ReorderSuggestion.created_at.desc()).all()


@router.post("/products/{product_id}/suggest-reorder", response_model=ReorderSuggestionOut)
def suggest_reorder(product_id: int, db: Session = Depends(get_db)):
    """
    On-demand reorder suggestion (trigger_reason=MANUAL).
    Uses the same strategy interface as the agentic loop — no duplicated logic.
    Calls the active reorder strategy (rule or AI based on env var).
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    strategy = _get_strategy("reorder")
    rec = strategy.recommend_reorder(product, TriggerReason.MANUAL.value)

    suggestion = ReorderSuggestion(
        product_id=product_id,
        current_stock=product.stock_level,
        recommended_quantity=rec.recommended_quantity,
        lead_time_days=rec.lead_time_days,
        confidence=rec.confidence,
        reasoning=rec.reasoning,
        status=SuggestionStatus.PENDING,
        trigger_reason=TriggerReason.MANUAL,
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


@router.patch("/reorder-suggestions/{suggestion_id}", response_model=ReorderSuggestionOut)
def update_reorder_suggestion(
    suggestion_id: int,
    payload: SuggestionStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Accept or reject a reorder suggestion.
    ACCEPT: atomically increments Product.stock_level by recommended_quantity
    (simulated inbound shipment) and resets status to ACTIVE if appropriate.
    """
    suggestion = db.query(ReorderSuggestion).filter(ReorderSuggestion.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Reorder suggestion not found")

    if suggestion.status != SuggestionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Suggestion is not in PENDING status")

    suggestion.status = payload.status

    if payload.status == SuggestionStatus.ACCEPTED:
        # Atomically increment stock (simulated inbound shipment)
        product = db.query(Product).filter(Product.id == suggestion.product_id).first()
        if product:
            product.stock_level += suggestion.recommended_quantity
            # Restore to ACTIVE if was OUT_OF_STOCK
            if product.status == ProductStatus.OUT_OF_STOCK:
                product.status = ProductStatus.ACTIVE

    db.commit()
    db.refresh(suggestion)
    return suggestion
