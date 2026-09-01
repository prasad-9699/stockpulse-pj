"""
what_if_service.py — What-If scenario simulator.

Runs pricing and reorder recommendations against a hypothetical product state
WITHOUT modifying the database. Uses the currently active strategy.
"""

from app.agentic_loop import _get_strategy, get_category_avg_velocity
from app.services.risk_service import calculate_risk_score, calculate_stockout_days
from sqlalchemy.orm import Session


class SimulatedProduct:
    """
    In-memory product-like object for what-if scenarios.
    Mimics the Product model interface so strategies can consume it directly.
    """
    def __init__(self, product, stock_override=None, velocity_override=None):
        self.id = product.id
        self.sku = product.sku
        self.name = product.name
        self.category = product.category
        self.current_price = product.current_price
        self.stock_level = stock_override if stock_override is not None else product.stock_level
        self.reorder_threshold = product.reorder_threshold
        self.demand_velocity = velocity_override if velocity_override is not None else product.demand_velocity
        self.status = product.status
        self.cost_price = product.cost_price
        self.supplier_id = product.supplier_id


def run_what_if(
    db: Session,
    product,
    simulated_stock: int,
    simulated_velocity: int,
) -> dict:
    """
    Run a what-if simulation without modifying the database.
    Creates an in-memory simulated product state and generates recommendations.

    Returns current state, simulated state, and both recommendation types.
    """
    # Current state assessment
    current_status = product.status.value if hasattr(product.status, 'value') else product.status
    current_risk = calculate_risk_score(
        product.stock_level, product.reorder_threshold,
        product.demand_velocity, current_status,
    )

    # Simulated state assessment
    sim_product = SimulatedProduct(product, simulated_stock, simulated_velocity)
    sim_risk = calculate_risk_score(
        simulated_stock, product.reorder_threshold,
        simulated_velocity, current_status,
    )

    # Determine trigger reason for simulation
    if simulated_stock < product.reorder_threshold:
        trigger = "INVENTORY_LOW"
    else:
        trigger = "DEMAND_SPIKE"

    # Get recommendations using active strategy
    category_avg = get_category_avg_velocity(db, product.category)

    pricing_strategy = _get_strategy("pricing")
    pricing_rec = pricing_strategy.recommend_pricing(sim_product, trigger, category_avg)

    reorder_strategy = _get_strategy("reorder")
    reorder_rec = reorder_strategy.recommend_reorder(sim_product, trigger)

    return {
        "current_state": {
            "stock_level": product.stock_level,
            "demand_velocity": product.demand_velocity,
            "risk_score": current_risk.risk_score,
            "risk_level": current_risk.risk_level,
            "estimated_stockout_days": current_risk.estimated_stockout_days,
        },
        "simulated_state": {
            "stock_level": simulated_stock,
            "demand_velocity": simulated_velocity,
            "risk_score": sim_risk.risk_score,
            "risk_level": sim_risk.risk_level,
            "risk_factors": sim_risk.risk_factors,
            "estimated_stockout_days": sim_risk.estimated_stockout_days,
        },
        "pricing_recommendation": {
            "recommended_price": pricing_rec.recommended_price,
            "direction": pricing_rec.direction,
            "confidence": pricing_rec.confidence,
            "reasoning": pricing_rec.reasoning,
        },
        "reorder_recommendation": {
            "recommended_quantity": reorder_rec.recommended_quantity,
            "lead_time_days": reorder_rec.lead_time_days,
            "confidence": reorder_rec.confidence,
            "reasoning": reorder_rec.reasoning,
        },
    }
