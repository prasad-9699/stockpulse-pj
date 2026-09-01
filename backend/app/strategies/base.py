"""
base.py — Abstract base classes for the pluggable commerce engine.

These interfaces define the contract that both rule-based and AI strategies
must implement. The agentic loop and on-demand endpoints call strategies
exclusively through these interfaces — no duplicated logic.

Sprint-2 extensions (competitor pricing, margin floors, supplier catalog)
would plug in here by extending the method signatures or adding new
strategy types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PricingRecommendation:
    """Data object returned by any PricingStrategy implementation."""
    recommended_price: float
    direction: str  # INCREASE | DECREASE | HOLD
    confidence: float
    reasoning: str


@dataclass
class ReorderRecommendation:
    """Data object returned by any ReorderStrategy implementation."""
    recommended_quantity: int
    lead_time_days: int
    confidence: float
    reasoning: str
    
    # Engine Calculation Details
    demand_velocity: int = 0
    safety_stock_days: int = 3
    expected_lead_time_demand: int = 0
    safety_stock: int = 0
    target_inventory: int = 0
    guardrail_applied: bool = False


class PricingStrategy(ABC):
    """
    Abstract interface for pricing recommendation engines.
    Implementations: rule_based.RuleBasedPricingStrategy, ai_strategy.AIPricingStrategy
    """

    @abstractmethod
    def recommend_pricing(
        self, product, trigger_reason: str, category_avg_velocity: float
    ) -> PricingRecommendation:
        """Generate a pricing recommendation for the given product and trigger context."""
        ...


class ReorderStrategy(ABC):
    """
    Abstract interface for reorder recommendation engines.
    Implementations: rule_based.RuleBasedReorderStrategy, ai_strategy.AIReorderStrategy
    """

    @abstractmethod
    def recommend_reorder(
        self, product, trigger_reason: str
    ) -> ReorderRecommendation:
        """Generate a reorder recommendation for the given product and trigger context."""
        ...
