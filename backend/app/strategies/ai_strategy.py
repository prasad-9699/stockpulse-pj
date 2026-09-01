"""
ai_strategy.py — AI-powered strategies that call the LLM gateway.

Uses two distinct prompts (inventory-low and demand-spike) for clearer
context and independent fallback. On ANY failure (API error, bad JSON,
out-of-bounds values), silently falls back to the rule-based strategy
and logs the reason — never crashes a demo.
"""

import json
import logging
from app.strategies.base import (
    PricingStrategy, ReorderStrategy,
    PricingRecommendation, ReorderRecommendation,
)
from app.strategies.rule_based import RuleBasedPricingStrategy, RuleBasedReorderStrategy
from app.llm_gateway import call_llm

logger = logging.getLogger("stockpulse.ai_strategy")

# Keep fallback instances ready
_rule_pricing = RuleBasedPricingStrategy()
_rule_reorder = RuleBasedReorderStrategy()


def _extract_json(text: str) -> dict:
    """
    Extract JSON from LLM response text, stripping markdown fences if present.
    Raises ValueError if no valid JSON found.
    """
    text = text.strip()
    # Strip markdown code fences that some models wrap around JSON
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (the fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


class AIPricingStrategy(PricingStrategy):
    """
    Calls the LLM for pricing recommendations using context-specific prompts.
    Falls back to rule-based on any failure.
    """

    def recommend_pricing(
        self, product, trigger_reason: str, category_avg_velocity: float
    ) -> PricingRecommendation:
        """
        Build a context-rich prompt based on trigger_reason, call the LLM,
        parse/validate the response, and return a PricingRecommendation.
        Falls back to rule-based strategy on any error.
        """
        try:
            prompt = self._build_prompt(product, trigger_reason, category_avg_velocity)
            raw = call_llm(prompt)
            data = _extract_json(raw)
            return self._validate_and_build(data, product)
        except Exception as e:
            logger.warning(f"AI pricing failed for product {product.id}, falling back to rule-based: {e}")
            return _rule_pricing.recommend_pricing(product, trigger_reason, category_avg_velocity)

    def _build_prompt(self, product, trigger_reason: str, category_avg_velocity: float) -> str:
        """Build the appropriate pricing prompt based on the trigger reason."""
        if trigger_reason in ("INVENTORY_LOW", "INITIAL"):
            # Inventory-low prompt — distinct from demand-spike for clearer AI reasoning
            return (
                f"You are an AI commerce pricing advisor for ShopStream.\n\n"
                f"Product: {product.name}\n"
                f"Category: {product.category.value if hasattr(product.category, 'value') else product.category}\n"
                f"Current Price: ${product.current_price:.2f}\n"
                f"Stock Level: {product.stock_level} units\n"
                f"Reorder Threshold: {product.reorder_threshold} units\n"
                f"Demand Velocity (orders/24h): {product.demand_velocity}\n\n"
                f"The stock level ({product.stock_level}) has dropped below the reorder threshold "
                f"({product.reorder_threshold}). Analyze whether we should:\n"
                f"- RAISE the price to protect scarce remaining stock and maximize revenue per unit\n"
                f"- RUN a clearance discount to move slow-selling units before they become dead stock\n"
                f"- HOLD the current price if neither action is warranted\n\n"
                f"Explain your reasoning in plain English, then give your recommendation.\n\n"
                f"Respond in STRICT JSON only (no markdown, no extra text):\n"
                f'{{"recommendedPrice": 29.99, "direction": "INCREASE", "confidence": 0.82, "reasoning": "..."}}\n'
                f"direction must be INCREASE, DECREASE, or HOLD."
            )
        else:
            # Demand-spike prompt — frames the question around capitalizing on viral demand
            return (
                f"You are an AI commerce pricing advisor for ShopStream.\n\n"
                f"Product: {product.name}\n"
                f"Category: {product.category.value if hasattr(product.category, 'value') else product.category}\n"
                f"Current Price: ${product.current_price:.2f}\n"
                f"Demand Velocity (orders/24h): {product.demand_velocity}\n"
                f"Category Average Velocity: {category_avg_velocity:.1f}\n"
                f"Stock Level: {product.stock_level} units\n\n"
                f"This product is experiencing a demand spike — velocity ({product.demand_velocity}) is "
                f"significantly above the category average ({category_avg_velocity:.1f}).\n\n"
                f"Should we capitalize on this viral spike with a modest price increase? "
                f"How much of an increase is justified without driving customers away? "
                f"Consider the risk of overpricing vs. leaving money on the table.\n\n"
                f"Respond in STRICT JSON only (no markdown, no extra text):\n"
                f'{{"recommendedPrice": 29.99, "direction": "INCREASE", "confidence": 0.82, "reasoning": "..."}}\n'
                f"direction must be INCREASE, DECREASE, or HOLD."
            )

    def _validate_and_build(self, data: dict, product) -> PricingRecommendation:
        """
        Validate LLM response fields: price must be positive.
        Applies configurable guardrails to prevent extreme price changes.
        """
        price = float(data["recommendedPrice"])
        direction = data["direction"].upper()
        confidence = float(data.get("confidence", 0.7))
        reasoning = data.get("reasoning", "AI-generated recommendation")

        if price <= 0:
            raise ValueError(f"Invalid recommended price: {price}")
            
        if direction not in ("INCREASE", "DECREASE", "HOLD"):
            raise ValueError(f"Invalid direction: {direction}")

        # Pricing Guardrails (Limit to +/- 20% change max)
        max_price = product.current_price * 1.20
        min_price = product.current_price * 0.80
        
        if price > max_price:
            reasoning += f" [Guardrail Applied: Price capped at +20% (${max_price:.2f}) to prevent extreme increase]"
            price = max_price
        elif price < min_price:
            reasoning += f" [Guardrail Applied: Price floored at -20% (${min_price:.2f}) to prevent extreme discount]"
            price = min_price

        return PricingRecommendation(
            recommended_price=round(price, 2),
            direction=direction,
            confidence=min(max(confidence, 0.0), 1.0),
            reasoning=reasoning,
        )


from app.services.reorder_calculation_service import calculate_reorder

class AIReorderStrategy(ReorderStrategy):
    """
    Calls the LLM for reorder recommendations with demand-aware prompts.
    Falls back to rule-based on any failure.
    Validates the LLM-generated quantity against the ReorderCalculationService
    to prevent hallucinations.
    """

    def recommend_reorder(
        self, product, trigger_reason: str
    ) -> ReorderRecommendation:
        """
        Build a reorder prompt, call the LLM, parse/validate the response,
        and return a ReorderRecommendation. Falls back on any error.
        """
        try:
            prompt = self._build_prompt(product, trigger_reason)
            raw = call_llm(prompt)
            data = _extract_json(raw)
            return self._validate_and_build(data, product)
        except Exception as e:
            logger.warning(f"AI reorder failed for product {product.id}, falling back to rule-based: {e}")
            self._last_fallback = True
            return _rule_reorder.recommend_reorder(product, trigger_reason)

    def _build_prompt(self, product, trigger_reason: str) -> str:
        """Build the reorder prompt with inventory and demand context."""
        if trigger_reason in ("INVENTORY_LOW", "INITIAL"):
            return (
                f"You are an AI inventory advisor for ShopStream.\n\n"
                f"Product: {product.name}\n"
                f"Category: {product.category.value if hasattr(product.category, 'value') else product.category}\n"
                f"Current Stock: {product.stock_level} units\n"
                f"Reorder Threshold: {product.reorder_threshold} units\n"
                f"Demand Velocity (orders/24h): {product.demand_velocity}\n"
                f"Current Price: ${product.current_price:.2f}\n\n"
                f"Stock has fallen below the reorder threshold. How many units should we reorder "
                f"to meet expected demand without overstocking? Consider current demand velocity "
                f"and the risk of stockout vs. carrying costs.\n\n"
                f"Respond in STRICT JSON only (no markdown, no extra text):\n"
                f'{{"recommendedQuantity": 150, "confidence": 0.78, "reasoning": "..."}}\n'
                f"recommendedQuantity must be a positive integer."
            )
        else:
            return (
                f"You are an AI inventory advisor for ShopStream.\n\n"
                f"Product: {product.name}\n"
                f"Category: {product.category.value if hasattr(product.category, 'value') else product.category}\n"
                f"Current Stock: {product.stock_level} units\n"
                f"Reorder Threshold: {product.reorder_threshold} units\n"
                f"Demand Velocity (orders/24h): {product.demand_velocity}\n"
                f"Current Price: ${product.current_price:.2f}\n\n"
                f"This product is experiencing a demand surge. How much extra stock should we "
                f"reorder to meet the surge without being caught with excess if demand normalizes? "
                f"Factor in the viral demand spike and the risk of stockout during peak.\n\n"
                f"Respond in STRICT JSON only (no markdown, no extra text):\n"
                f'{{"recommendedQuantity": 150, "confidence": 0.78, "reasoning": "..."}}\n'
                f"recommendedQuantity must be a positive integer."
            )

    def _validate_and_build(self, data: dict, product) -> ReorderRecommendation:
        """
        Validate LLM response: quantity must be a positive integer.
        Also clamps the quantity if it deviates too much from the deterministic baseline.
        """
        self._last_fallback = False
        ai_qty = int(data["recommendedQuantity"])
        confidence = float(data.get("confidence", 0.7))
        reasoning = data.get("reasoning", "AI-generated reorder recommendation")

        if ai_qty < 0:
            raise ValueError(f"Invalid recommended quantity: {ai_qty}")

        # Guardrails: Validate against the deterministic calculation engine
        calc = calculate_reorder(product)
        baseline_qty = calc["recommended_quantity"]
        
        guardrail_applied = False
        final_qty = ai_qty
        
        # If AI proposes 0 but baseline says we need stock, or AI proposes a crazy high amount
        # Let's say AI shouldn't propose > 2x the deterministic baseline if baseline > 0
        if baseline_qty > 0 and ai_qty > baseline_qty * 2:
            final_qty = baseline_qty
            guardrail_applied = True
            reasoning += f" [Guardrail: clamped from {ai_qty} to {baseline_qty} to prevent extreme overstocking]"
        elif baseline_qty == 0 and ai_qty > product.reorder_threshold:
            # We don't really need stock, but AI wants to buy a lot
            final_qty = 0
            guardrail_applied = True
            reasoning += f" [Guardrail: clamped from {ai_qty} to 0 because target inventory is already met]"

        return ReorderRecommendation(
            recommended_quantity=final_qty,
            lead_time_days=calc["lead_time_days"],
            demand_velocity=calc["demand_velocity"],
            safety_stock_days=calc["safety_stock_days"],
            expected_lead_time_demand=calc["expected_lead_time_demand"],
            safety_stock=calc["safety_stock"],
            target_inventory=calc["target_inventory"],
            guardrail_applied=guardrail_applied,
            confidence=min(max(confidence, 0.0), 1.0),
            reasoning=reasoning,
        )
