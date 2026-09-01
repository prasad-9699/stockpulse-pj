"""
schemas.py — Pydantic v2 schemas for request/response serialization.
Every endpoint uses these schemas; no raw dicts leak into the API surface.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models import CategoryEnum, ProductStatus, SuggestionStatus, DirectionEnum, TriggerReason


# ──────────────────── Product Schemas ────────────────────

class ProductCreate(BaseModel):
    """Schema for creating a new product via POST /products."""
    sku: str
    name: str
    category: CategoryEnum
    current_price: float = Field(gt=0)
    stock_level: int = Field(ge=0)
    reorder_threshold: int = Field(ge=0, default=10)
    demand_velocity: int = Field(ge=0, default=0)
    cost_price: Optional[float] = None
    supplier_id: Optional[str] = None


class StockUpdate(BaseModel):
    """Schema for PATCH /products/{id}/stock — update inventory level."""
    stock_level: int = Field(ge=0)


class OrderSimulation(BaseModel):
    """Schema for POST /products/{id}/orders — simulate a sale."""
    qty: int = Field(ge=1, default=1)


class PricingSuggestionOut(BaseModel):
    """Read-only schema for a pricing suggestion returned in API responses."""
    id: int
    product_id: int
    current_price: float
    recommended_price: float
    direction: DirectionEnum
    confidence: float
    reasoning: Optional[str] = None
    status: SuggestionStatus
    trigger_reason: TriggerReason
    strategy_used: Optional[str] = None
    fallback_used: Optional[bool] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReorderSuggestionOut(BaseModel):
    """Read-only schema for a reorder suggestion returned in API responses."""
    id: int
    product_id: int
    current_stock: int
    recommended_quantity: int
    lead_time_days: int
    
    # Engine Calculation Details
    demand_velocity: int
    safety_stock_days: int
    expected_lead_time_demand: int
    safety_stock: int
    target_inventory: int
    guardrail_applied: bool
    
    confidence: float
    reasoning: Optional[str] = None
    status: SuggestionStatus
    trigger_reason: TriggerReason
    strategy_used: Optional[str] = None
    fallback_used: Optional[bool] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    """Read-only schema for a product, including its pending suggestions."""
    id: int
    sku: str
    name: str
    category: CategoryEnum
    current_price: float
    stock_level: int
    reorder_threshold: int
    demand_velocity: int
    status: ProductStatus
    cost_price: Optional[float] = None
    supplier_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    pricing_suggestions: List[PricingSuggestionOut] = []
    reorder_suggestions: List[ReorderSuggestionOut] = []

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    """Read-only schema for the product list with computed risk/stockout fields."""
    id: int
    sku: str
    name: str
    category: CategoryEnum
    current_price: float
    stock_level: int
    reorder_threshold: int
    demand_velocity: int
    status: ProductStatus
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    risk_factors: Optional[List[str]] = None
    estimated_stockout_days: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────── Suggestion Update Schemas ────────────────────

class SuggestionStatusUpdate(BaseModel):
    """Schema for PATCH /pricing-suggestions/{id} and /reorder-suggestions/{id}."""
    status: SuggestionStatus


# ──────────────────── SSE Event Schema ────────────────────

class AgentEvent(BaseModel):
    """Schema for a single event in the Agent Activity Feed SSE stream."""
    event_type: str  # e.g. "detection", "calling_ai", "suggestion_queued"
    message: str
    product_id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ──────────────────── Demand Spike Simulator ────────────────────

class DemandSpikeRequest(BaseModel):
    """Schema for POST /products/{id}/simulate-demand-spike."""
    multiplier: int = Field(ge=2, default=3, description="Multiply demand_velocity by this factor")


class DemandSpikeResponse(BaseModel):
    """Response after simulating a demand spike."""
    message: str
    product_id: int
    previous_velocity: int
    new_velocity: int
    triggered: bool


# ──────────────────── Strategy Settings ────────────────────

class StrategySettingsOut(BaseModel):
    """Current active strategy setting."""
    strategy: str  # "AI" or "RULE_BASED"


class StrategySettingsUpdate(BaseModel):
    """Schema for PATCH /settings/strategy."""
    strategy: str = Field(description="AI or RULE_BASED")


# ──────────────────── What-If Simulator ────────────────────

class WhatIfRequest(BaseModel):
    """Schema for POST /products/{id}/what-if."""
    stock_level: int = Field(ge=0)
    demand_velocity: int = Field(ge=0)
