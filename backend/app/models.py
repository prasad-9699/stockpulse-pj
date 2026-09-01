"""
models.py — SQLAlchemy ORM models for the StockPulse domain.
Tables: products, pricing_suggestions, reorder_suggestions, app_settings.
"""

import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


# ──────────────────────────── Enums ────────────────────────────

class CategoryEnum(str, enum.Enum):
    """Product categories sold by ShopStream."""
    ELECTRONICS = "ELECTRONICS"
    APPAREL = "APPAREL"
    HOME = "HOME"


class ProductStatus(str, enum.Enum):
    """Lifecycle status of a product."""
    ACTIVE = "ACTIVE"
    PRICE_REVIEW_PENDING = "PRICE_REVIEW_PENDING"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class SuggestionStatus(str, enum.Enum):
    """Approval workflow status for any suggestion."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class DirectionEnum(str, enum.Enum):
    """Price movement direction."""
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    HOLD = "HOLD"


class TriggerReason(str, enum.Enum):
    """What triggered the suggestion generation."""
    INITIAL = "INITIAL"
    INVENTORY_LOW = "INVENTORY_LOW"
    DEMAND_SPIKE = "DEMAND_SPIKE"
    MANUAL = "MANUAL"


# ──────────────────────────── Models ────────────────────────────

class Product(Base):
    """
    Represents a ShopStream product with inventory tracking fields.
    Extension placeholders (cost_price, supplier_id) are nullable for future use.
    """
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(SAEnum(CategoryEnum), nullable=False)
    current_price = Column(Float, nullable=False)
    stock_level = Column(Integer, nullable=False, default=0)
    reorder_threshold = Column(Integer, nullable=False, default=10)
    demand_velocity = Column(Integer, nullable=False, default=0)  # orders in last 24h
    status = Column(SAEnum(ProductStatus), nullable=False, default=ProductStatus.ACTIVE)

    # Sprint-2 extension placeholders
    cost_price = Column(Float, nullable=True)
    supplier_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    pricing_suggestions = relationship("PricingSuggestion", back_populates="product", lazy="selectin")
    reorder_suggestions = relationship("ReorderSuggestion", back_populates="product", lazy="selectin")


class PricingSuggestion(Base):
    """
    An AI- or rule-generated pricing recommendation awaiting human approval.
    Accepting it atomically updates the product's current_price.
    """
    __tablename__ = "pricing_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    current_price = Column(Float, nullable=False)
    recommended_price = Column(Float, nullable=False)
    direction = Column(SAEnum(DirectionEnum), nullable=False)
    confidence = Column(Float, nullable=False, default=0.5)
    reasoning = Column(Text, nullable=True)
    status = Column(SAEnum(SuggestionStatus), nullable=False, default=SuggestionStatus.PENDING)
    trigger_reason = Column(SAEnum(TriggerReason), nullable=False, default=TriggerReason.MANUAL)
    # Explainability: track which strategy produced this suggestion
    strategy_used = Column(String, nullable=True)  # "AI" or "RULE_BASED"
    fallback_used = Column(Boolean, nullable=True, default=False)  # True if AI fell back to rule-based
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="pricing_suggestions")


class ReorderSuggestion(Base):
    """
    An AI- or rule-generated reorder recommendation awaiting human approval.
    Accepting it atomically increments the product's stock_level (simulated inbound shipment).
    """
    __tablename__ = "reorder_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    current_stock = Column(Integer, nullable=False)
    recommended_quantity = Column(Integer, nullable=False)
    lead_time_days = Column(Integer, nullable=False, default=3)
    
    # Engine Calculation Details
    demand_velocity = Column(Integer, nullable=False, default=0)
    safety_stock_days = Column(Integer, nullable=False, default=3)
    expected_lead_time_demand = Column(Integer, nullable=False, default=0)
    safety_stock = Column(Integer, nullable=False, default=0)
    target_inventory = Column(Integer, nullable=False, default=0)
    guardrail_applied = Column(Boolean, nullable=False, default=False)
    
    confidence = Column(Float, nullable=False, default=0.5)
    reasoning = Column(Text, nullable=True)
    status = Column(SAEnum(SuggestionStatus), nullable=False, default=SuggestionStatus.PENDING)
    trigger_reason = Column(SAEnum(TriggerReason), nullable=False, default=TriggerReason.MANUAL)
    # Explainability: track which strategy produced this suggestion
    strategy_used = Column(String, nullable=True)  # "AI" or "RULE_BASED"
    fallback_used = Column(Boolean, nullable=True, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="reorder_suggestions")


class AppSettings(Base):
    """
    Persistent application settings for runtime configuration.
    Stores the active strategy so it survives restarts and doesn't need env vars.
    """
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, default=1)
    active_strategy = Column(String, nullable=False, default="RULE_BASED")  # "AI" or "RULE_BASED"
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
