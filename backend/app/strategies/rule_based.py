"""
rule_based.py — Deterministic rule-based strategies for pricing and reorder.

These serve as both the primary strategy when PRICING_STRATEGY=rule / REORDER_STRATEGY=rule
AND the silent fallback when the AI strategy fails (bad API key, timeout, invalid JSON).
"""

from app.strategies.base import (
    PricingStrategy, ReorderStrategy,
    PricingRecommendation, ReorderRecommendation,
)


class RuleBasedPricingStrategy(PricingStrategy):
    """
    Deterministic pricing rules:
    - stock < threshold → +10% (protect scarce inventory)
    - demand > 2x category avg → +5% (capitalize on demand)
    - otherwise → HOLD with moderate confidence
    """

    def recommend_pricing(
        self, product, trigger_reason: str, category_avg_velocity: float
    ) -> PricingRecommendation:
        """Apply simple heuristic rules to generate a pricing recommendation."""
        price = product.current_price

        if product.stock_level < product.reorder_threshold:
            # Protect scarce remaining stock with a price increase
            new_price = round(price * 1.10, 2)
            return PricingRecommendation(
                recommended_price=new_price,
                direction="INCREASE",
                confidence=0.72,
                reasoning=(
                    f"Stock ({product.stock_level}) is below reorder threshold "
                    f"({product.reorder_threshold}). Recommending a 10% price increase "
                    f"from ${price:.2f} to ${new_price:.2f} to protect scarce inventory."
                ),
            )
        elif category_avg_velocity > 0 and product.demand_velocity > 2 * category_avg_velocity:
            # Capitalize on above-average demand
            new_price = round(price * 1.05, 2)
            return PricingRecommendation(
                recommended_price=new_price,
                direction="INCREASE",
                confidence=0.65,
                reasoning=(
                    f"Demand velocity ({product.demand_velocity}) exceeds 2x the category "
                    f"average ({category_avg_velocity:.1f}). Recommending a modest 5% increase "
                    f"from ${price:.2f} to ${new_price:.2f}."
                ),
            )
        else:
            # No strong signal — hold current price
            return PricingRecommendation(
                recommended_price=price,
                direction="HOLD",
                confidence=0.50,
                reasoning=(
                    f"No strong pricing signal detected. Stock ({product.stock_level}) is above "
                    f"threshold ({product.reorder_threshold}) and demand velocity "
                    f"({product.demand_velocity}) is within normal range. Holding at ${price:.2f}."
                ),
            )


from app.services.reorder_calculation_service import calculate_reorder

class RuleBasedReorderStrategy(ReorderStrategy):
    """
    Rule-based reorder formula uses the generalized inventory calculation engine.
    """

    def recommend_reorder(
        self, product, trigger_reason: str
    ) -> ReorderRecommendation:
        """Calculate reorder quantity using the dynamic ReorderCalculationService."""
        calc = calculate_reorder(product)
        qty = calc["recommended_quantity"]
        
        return ReorderRecommendation(
            recommended_quantity=qty,
            lead_time_days=calc["lead_time_days"],
            demand_velocity=calc["demand_velocity"],
            safety_stock_days=calc["safety_stock_days"],
            expected_lead_time_demand=calc["expected_lead_time_demand"],
            safety_stock=calc["safety_stock"],
            target_inventory=calc["target_inventory"],
            guardrail_applied=False,
            confidence=0.70,
            reasoning=(
                f"Computed target inventory is {calc['target_inventory']} units "
                f"(expected lead time demand: {calc['expected_lead_time_demand']}, "
                f"safety stock: {calc['safety_stock']}). "
                f"With current stock at {product.stock_level}, recommending a reorder of {qty} units."
            ),
        )
