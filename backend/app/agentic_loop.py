"""
agentic_loop.py — Trigger detection + background suggestion generation.

This is the core reactive engine. It runs AFTER the HTTP response has been
sent (via BackgroundTasks) so it never blocks the API. The loop follows the
Observe -> Reason -> Act -> Checkpoint pattern:

1. Observe: detect inventory-low or demand-spike signals
2. Reason: call the active strategy (rule-based or AI) for recommendations
3. Act: queue PricingSuggestion + ReorderSuggestion records
4. Checkpoint: human accepts or rejects (handled by separate endpoints)

Idempotency: skips if a PENDING suggestion already exists for the same
(product_id, trigger_reason, suggestion_type).
"""

import os
import logging
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models import (
    Product, PricingSuggestion, ReorderSuggestion, AppSettings,
    SuggestionStatus, TriggerReason, ProductStatus, CategoryEnum,
)
from app.strategies.base import PricingStrategy, ReorderStrategy
from app import event_bus

logger = logging.getLogger("stockpulse.agentic_loop")


def _get_active_strategy_name(db: Session = None) -> str:
    """
    Resolve the active strategy name from AppSettings (DB-persisted)
    with env var fallback. Returns 'AI' or 'RULE_BASED'.
    """
    # First check DB-persisted setting
    if db:
        try:
            settings = db.query(AppSettings).first()
            if settings and settings.active_strategy:
                return settings.active_strategy.upper()
        except Exception:
            pass  # Table might not exist yet during startup
    # Fallback to env var
    env_val = os.getenv("PRICING_STRATEGY", "rule").lower()
    return "AI" if env_val == "ai" else "RULE_BASED"


def _get_strategy(strategy_type: str, db: Session = None):
    """
    Factory function that resolves the active strategy implementation.
    Checks DB-persisted AppSettings first, then env vars as fallback.
    No restart needed to switch.

    strategy_type: 'pricing' or 'reorder'
    Returns an instance of the appropriate strategy.
    """
    active = _get_active_strategy_name(db)

    if strategy_type == "pricing":
        if active == "AI":
            from app.strategies.ai_strategy import AIPricingStrategy
            return AIPricingStrategy()
        else:
            from app.strategies.rule_based import RuleBasedPricingStrategy
            return RuleBasedPricingStrategy()
    elif strategy_type == "reorder":
        if active == "AI":
            from app.strategies.ai_strategy import AIReorderStrategy
            return AIReorderStrategy()
        else:
            from app.strategies.rule_based import RuleBasedReorderStrategy
            return RuleBasedReorderStrategy()
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")


def get_category_avg_velocity(db: Session, category) -> float:
    """
    Calculate the average demand velocity for all products in a category.
    Used to detect demand spikes relative to category peers.
    """
    result = db.query(func.avg(Product.demand_velocity)).filter(
        Product.category == category
    ).scalar()
    return float(result) if result else 0.0


def _has_pending_suggestion(db: Session, product_id: int, trigger_reason: str, suggestion_type: str) -> bool:
    """
    Idempotency check: returns True if a PENDING suggestion already exists
    for the same (product_id, trigger_reason, type) combination.
    Prevents duplicate suggestions from repeated triggers.
    """
    if suggestion_type == "pricing":
        return db.query(PricingSuggestion).filter(
            PricingSuggestion.product_id == product_id,
            PricingSuggestion.trigger_reason == trigger_reason,
            PricingSuggestion.status == SuggestionStatus.PENDING,
        ).first() is not None
    else:
        return db.query(ReorderSuggestion).filter(
            ReorderSuggestion.product_id == product_id,
            ReorderSuggestion.trigger_reason == trigger_reason,
            ReorderSuggestion.status == SuggestionStatus.PENDING,
        ).first() is not None


async def run_agentic_loop(product_id: int, trigger_reason: str):
    """
    Main entry point for the background agentic loop.
    Called via BackgroundTasks from stock-update and order endpoints.

    Generates both a PricingSuggestion and a ReorderSuggestion for the
    given product and trigger, publishing SSE events at each stage.
    Runs blocking DB/strategy work in a thread to avoid blocking the event loop.
    """
    await asyncio.to_thread(_run_agentic_loop_sync, product_id, trigger_reason)


def _run_agentic_loop_sync(product_id: int, trigger_reason: str):
    """
    Synchronous implementation of the agentic loop.
    Creates its own DB session since BackgroundTasks run outside the request lifecycle.
    Uses publish_sync for thread-safe SSE event broadcasting.
    Now tracks strategy_used and fallback_used for explainability.
    """
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"Agentic loop: product {product_id} not found")
            return

        category_avg = get_category_avg_velocity(db, product.category)
        active_strategy = _get_active_strategy_name(db)

        # -- Stage 1: OBSERVE -- publish detection event
        if trigger_reason == TriggerReason.INVENTORY_LOW.value:
            msg = (
                f"[DETECT] {product.sku} stock ({product.stock_level}) "
                f"< threshold ({product.reorder_threshold}) -- INVENTORY_LOW"
            )
        else:
            msg = (
                f"[DETECT] {product.sku} demand velocity ({product.demand_velocity}) "
                f"> 3x category avg ({category_avg:.1f}) -- DEMAND_SPIKE"
            )
        event_bus.publish_sync("detection", msg, product_id)

        # -- Stage 1b: STRATEGY -- publish selected strategy
        strategy_label = "AI Strategy" if active_strategy == "AI" else "Rule-Based Strategy"
        event_bus.publish_sync("strategy_selected", f"[STRATEGY] Using {strategy_label} for {product.sku}", product_id)

        # -- Stage 2: REASON -- call pricing strategy
        if not _has_pending_suggestion(db, product_id, trigger_reason, "pricing"):
            event_bus.publish_sync(
                "calling_ai",
                f"[ANALYZE] Generating pricing recommendation for {product.sku}...",
                product_id,
            )

            pricing_strategy = _get_strategy("pricing", db)
            pricing_rec = pricing_strategy.recommend_pricing(product, trigger_reason, category_avg)

            # Detect if fallback occurred (AI strategy returns rule-based result on failure)
            fallback = False
            if active_strategy == "AI":
                from app.strategies.ai_strategy import AIPricingStrategy
                if isinstance(pricing_strategy, AIPricingStrategy):
                    fallback = getattr(pricing_strategy, '_last_fallback', False)

            # -- Stage 3: ACT -- queue pricing suggestion
            suggestion = PricingSuggestion(
                product_id=product_id,
                current_price=product.current_price,
                recommended_price=pricing_rec.recommended_price,
                direction=pricing_rec.direction,
                confidence=pricing_rec.confidence,
                reasoning=pricing_rec.reasoning,
                status=SuggestionStatus.PENDING,
                trigger_reason=trigger_reason,
                strategy_used=active_strategy,
                fallback_used=fallback,
            )
            db.add(suggestion)

            # Set product status to PRICE_REVIEW_PENDING
            product.status = ProductStatus.PRICE_REVIEW_PENDING
            db.commit()

            event_bus.publish_sync(
                "suggestion_queued",
                f"[PRICING] {product.sku}: {pricing_rec.direction} "
                f"to ${pricing_rec.recommended_price:.2f} (confidence {pricing_rec.confidence:.0%})",
                product_id,
            )
        else:
            event_bus.publish_sync(
                "skipped",
                f"[SKIP] Pending pricing suggestion already exists for {product.sku}",
                product_id,
            )

        # -- Stage 2b: REASON -- call reorder strategy
        if not _has_pending_suggestion(db, product_id, trigger_reason, "reorder"):
            event_bus.publish_sync(
                "calling_ai",
                f"[ANALYZE] Generating reorder recommendation for {product.sku}...",
                product_id,
            )

            reorder_strategy = _get_strategy("reorder", db)
            reorder_rec = reorder_strategy.recommend_reorder(product, trigger_reason)

            fallback = False
            if active_strategy == "AI":
                from app.strategies.ai_strategy import AIReorderStrategy
                if isinstance(reorder_strategy, AIReorderStrategy):
                    fallback = getattr(reorder_strategy, '_last_fallback', False)

            # -- Stage 3b: ACT -- queue reorder suggestion
            reorder = ReorderSuggestion(
                product_id=product_id,
                current_stock=product.stock_level,
                recommended_quantity=reorder_rec.recommended_quantity,
                lead_time_days=reorder_rec.lead_time_days,
                
                # Engine Calculation Details
                demand_velocity=reorder_rec.demand_velocity,
                safety_stock_days=reorder_rec.safety_stock_days,
                expected_lead_time_demand=reorder_rec.expected_lead_time_demand,
                safety_stock=reorder_rec.safety_stock,
                target_inventory=reorder_rec.target_inventory,
                guardrail_applied=reorder_rec.guardrail_applied,
                
                confidence=reorder_rec.confidence,
                reasoning=reorder_rec.reasoning,
                status=SuggestionStatus.PENDING,
                trigger_reason=trigger_reason,
                strategy_used=active_strategy,
                fallback_used=fallback,
            )
            db.add(reorder)
            db.commit()

            event_bus.publish_sync(
                "suggestion_queued",
                f"[REORDER] {product.sku}: +{reorder_rec.recommended_quantity} units "
                f"(confidence {reorder_rec.confidence:.0%})",
                product_id,
            )
        else:
            event_bus.publish_sync(
                "skipped",
                f"[SKIP] Pending reorder suggestion already exists for {product.sku}",
                product_id,
            )

        # -- Stage 4: CHECKPOINT -- waiting for human approval
        event_bus.publish_sync(
            "checkpoint",
            f"[WAITING] Recommendations for {product.sku} awaiting human approval",
            product_id,
        )

    except Exception as e:
        logger.exception(f"Agentic loop failed for product {product_id}: {e}")
    finally:
        db.close()
