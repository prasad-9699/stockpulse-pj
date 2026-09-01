"""
analytics_service.py — Analytics data aggregation service.

Computes dashboard metrics and chart data from actual product
and suggestion records. No fake data — everything comes from the DB.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import (
    Product, PricingSuggestion, ReorderSuggestion,
    ProductStatus, SuggestionStatus, TriggerReason,
)
from app.services.risk_service import calculate_risk_score


def get_analytics_overview(db: Session) -> dict:
    """
    Aggregate real product and suggestion data for the analytics dashboard.
    Returns summary metrics, inventory health distribution, and chart data.
    """
    products = db.query(Product).all()
    total = len(products)

    # Calculate risk for every product
    risk_data = []
    for p in products:
        status_val = p.status.value if hasattr(p.status, 'value') else p.status
        assessment = calculate_risk_score(
            p.stock_level, p.reorder_threshold, p.demand_velocity, status_val
        )
        risk_data.append({
            "product_id": p.id,
            "name": p.name,
            "sku": p.sku,
            "category": p.category.value if hasattr(p.category, 'value') else p.category,
            "stock_level": p.stock_level,
            "demand_velocity": p.demand_velocity,
            "current_price": p.current_price,
            "risk_score": assessment.risk_score,
            "risk_level": assessment.risk_level,
            "estimated_stockout_days": assessment.estimated_stockout_days,
        })

    # Summary metrics
    out_of_stock = sum(1 for p in products if p.status == ProductStatus.OUT_OF_STOCK)
    critical = sum(1 for r in risk_data if r["risk_level"] == "CRITICAL")
    at_risk = sum(1 for r in risk_data if r["risk_level"] in ("HIGH", "CRITICAL"))
    avg_risk = round(sum(r["risk_score"] for r in risk_data) / total, 1) if total > 0 else 0

    # Pending suggestions count
    pending_pricing = db.query(PricingSuggestion).filter(
        PricingSuggestion.status == SuggestionStatus.PENDING
    ).count()
    pending_reorder = db.query(ReorderSuggestion).filter(
        ReorderSuggestion.status == SuggestionStatus.PENDING
    ).count()

    # Inventory health distribution
    healthy = sum(1 for r in risk_data if r["risk_level"] == "LOW")
    moderate = sum(1 for r in risk_data if r["risk_level"] == "MODERATE")
    high = sum(1 for r in risk_data if r["risk_level"] == "HIGH")

    # Recommendation distribution by trigger
    trigger_counts = {}
    for trigger in [TriggerReason.INVENTORY_LOW, TriggerReason.DEMAND_SPIKE, TriggerReason.MANUAL]:
        count = db.query(PricingSuggestion).filter(
            PricingSuggestion.trigger_reason == trigger
        ).count() + db.query(ReorderSuggestion).filter(
            ReorderSuggestion.trigger_reason == trigger
        ).count()
        trigger_counts[trigger.value] = count

    return {
        "summary": {
            "total_products": total,
            "products_at_risk": at_risk,
            "critical_products": critical,
            "out_of_stock": out_of_stock,
            "pending_recommendations": pending_pricing + pending_reorder,
            "average_risk_score": avg_risk,
        },
        "inventory_health": {
            "healthy": healthy,
            "moderate": moderate,
            "high": high,
            "critical": critical,
            "out_of_stock": out_of_stock,
        },
        "trigger_distribution": trigger_counts,
        "products": risk_data,
    }
