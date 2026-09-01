"""
reorder_calculation_service.py — Generalized Reorder Engine.

Provides deterministic, inventory-based calculations for recommended reorder quantities.
Works for all products based on their current telemetry (stock, velocity, etc.)
and configurable supply chain defaults.
"""

from typing import Dict, Any

# Configurable defaults (can be moved to env vars/settings later)
DEFAULT_LEAD_TIME_DAYS = 7
DEFAULT_SAFETY_STOCK_DAYS = 3

def calculate_reorder(product) -> Dict[str, Any]:
    """
    Calculate the recommended reorder quantity dynamically based on standard
    inventory formulas.

    Formulas:
    If demand > 0:
      expected_lead_time_demand = demand_velocity * lead_time_days
      safety_stock = demand_velocity * safety_stock_days
      target_inventory = expected_lead_time_demand + safety_stock
    If demand <= 0:
      target_inventory = max(reorder_threshold, current_stock)

    recommended_reorder = max(0, target_inventory - current_stock)

    Returns a dictionary with the full calculation breakdown.
    """
    demand_velocity = max(0, product.demand_velocity)
    current_stock = max(0, product.stock_level)
    reorder_threshold = max(0, product.reorder_threshold)
    
    # Use defaults or product-specific if available (future extension)
    lead_time_days = getattr(product, "lead_time_days", DEFAULT_LEAD_TIME_DAYS)
    safety_stock_days = getattr(product, "safety_stock_days", DEFAULT_SAFETY_STOCK_DAYS)

    if demand_velocity > 0:
        expected_lead_time_demand = demand_velocity * lead_time_days
        safety_stock = demand_velocity * safety_stock_days
        target_inventory = expected_lead_time_demand + safety_stock
    else:
        # Zero demand handling: ensure we maintain at least the reorder threshold
        expected_lead_time_demand = 0
        safety_stock = reorder_threshold
        target_inventory = max(reorder_threshold, current_stock + 1)

    recommended_quantity = max(0, target_inventory - current_stock)

    return {
        "recommended_quantity": recommended_quantity,
        "current_stock": current_stock,
        "demand_velocity": demand_velocity,
        "lead_time_days": lead_time_days,
        "safety_stock_days": safety_stock_days,
        "expected_lead_time_demand": expected_lead_time_demand,
        "safety_stock": safety_stock,
        "target_inventory": target_inventory,
        "guardrail_applied": False, # Updated by the caller if AI hallucinates
    }
