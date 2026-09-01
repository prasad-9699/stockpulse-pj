"""
products.py — Product CRUD, action endpoints, and advanced feature routes.

Handles product creation, listing, detail retrieval, stock updates,
sale simulation, demand spike simulation, strategy toggle, analytics,
what-if simulation, and recommendation history. Stock updates and sales
fire the agentic loop as a background task when thresholds are crossed.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from app.database import get_db
from app.models import (
    Product, ProductStatus, CategoryEnum, TriggerReason,
    AppSettings, PricingSuggestion, ReorderSuggestion, SuggestionStatus,
)
from app.schemas import (
    ProductCreate, ProductOut, ProductListOut, StockUpdate, OrderSimulation,
    DemandSpikeRequest, DemandSpikeResponse,
    StrategySettingsOut, StrategySettingsUpdate,
    WhatIfRequest,
    PricingSuggestionOut, ReorderSuggestionOut,
)
from app.agentic_loop import run_agentic_loop, get_category_avg_velocity
from app.services.risk_service import calculate_risk_score
from app.services.analytics_service import get_analytics_overview
from app.services.what_if_service import run_what_if

router = APIRouter(prefix="/products", tags=["Products"])


# ──────────────────────── Product CRUD ────────────────────────


@router.post("", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    """
    Create a new product with initial stock/price.
    Sets status to OUT_OF_STOCK if stock_level is 0, otherwise ACTIVE.
    """
    product = Product(**payload.model_dump())
    if product.stock_level == 0:
        product.status = ProductStatus.OUT_OF_STOCK
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("", response_model=List[ProductListOut])
def list_products(
    status: Optional[str] = Query(None, description="Filter by product status"),
    category: Optional[str] = Query(None, description="Filter by product category"),
    db: Session = Depends(get_db),
):
    """
    List all products with optional status and category filters.
    Now computes risk_score, risk_level, risk_factors, and estimated_stockout_days
    for every product using the risk_service.
    """
    query = db.query(Product)
    if status:
        query = query.filter(Product.status == status)
    if category:
        query = query.filter(Product.category == category)
    products = query.order_by(Product.id).all()

    # Enrich each product with computed risk data
    result = []
    for p in products:
        status_val = p.status.value if hasattr(p.status, 'value') else p.status
        assessment = calculate_risk_score(
            p.stock_level, p.reorder_threshold, p.demand_velocity, status_val
        )
        # Build a dict from ORM object + computed fields
        product_dict = {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "current_price": p.current_price,
            "stock_level": p.stock_level,
            "reorder_threshold": p.reorder_threshold,
            "demand_velocity": p.demand_velocity,
            "status": p.status,
            "risk_score": assessment.risk_score,
            "risk_level": assessment.risk_level,
            "risk_factors": assessment.risk_factors,
            "estimated_stockout_days": assessment.estimated_stockout_days,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        result.append(product_dict)
    return result


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """
    Get a single product with its pending pricing and reorder suggestions embedded.
    Used by the frontend detail view and suggestion panels.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}/stock", response_model=ProductOut)
def update_stock(
    product_id: int,
    payload: StockUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Update a product's stock level directly.
    Fires the agentic loop as a background task if stock drops below reorder threshold.
    Sets status to OUT_OF_STOCK if stock reaches 0.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.stock_level = payload.stock_level

    # Update status based on new stock level
    if product.stock_level == 0:
        product.status = ProductStatus.OUT_OF_STOCK
    elif product.status == ProductStatus.OUT_OF_STOCK and product.stock_level > 0:
        product.status = ProductStatus.ACTIVE

    db.commit()
    db.refresh(product)

    # Fire agentic loop if stock is below reorder threshold
    if product.stock_level < product.reorder_threshold and product.stock_level > 0:
        background_tasks.add_task(run_agentic_loop, product.id, TriggerReason.INVENTORY_LOW.value)

    return product


@router.post("/{product_id}/orders", response_model=ProductOut)
def simulate_order(
    product_id: int,
    payload: OrderSimulation = OrderSimulation(),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """
    Simulate a sale: decrement stock by qty, bump demand_velocity.
    This is the primary demo trigger — click "Simulate Sale" in the UI.
    Fires the agentic loop on low-stock or demand-spike conditions.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock_level < payload.qty:
        raise HTTPException(status_code=400, detail=f"Insufficient stock ({product.stock_level}) for order qty ({payload.qty})")

    # Decrement stock and bump demand velocity
    product.stock_level -= payload.qty
    product.demand_velocity += payload.qty

    # Update status based on new stock level
    if product.stock_level == 0:
        product.status = ProductStatus.OUT_OF_STOCK

    db.commit()
    db.refresh(product)

    # Check triggers and fire agentic loop
    trigger = None
    category_avg = get_category_avg_velocity(db, product.category)

    if product.stock_level > 0 and product.stock_level < product.reorder_threshold:
        trigger = TriggerReason.INVENTORY_LOW.value
    elif category_avg > 0 and product.demand_velocity > 3 * category_avg:
        trigger = TriggerReason.DEMAND_SPIKE.value

    if trigger and background_tasks:
        background_tasks.add_task(run_agentic_loop, product.id, trigger)

    return product


# ──────────────────────── Demand Spike Simulator ────────────────────────


@router.post("/{product_id}/simulate-demand-spike", response_model=DemandSpikeResponse)
def simulate_demand_spike(
    product_id: int,
    payload: DemandSpikeRequest = DemandSpikeRequest(),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """
    Simulate a demand spike by multiplying the product's demand_velocity.
    Fires the agentic loop if the new velocity exceeds 3x category average.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    previous_velocity = product.demand_velocity
    product.demand_velocity = max(product.demand_velocity, 1) * payload.multiplier

    db.commit()
    db.refresh(product)

    # Check if spike triggers the agentic loop
    category_avg = get_category_avg_velocity(db, product.category)
    triggered = False
    if category_avg > 0 and product.demand_velocity > 3 * category_avg:
        triggered = True
        if background_tasks:
            background_tasks.add_task(run_agentic_loop, product.id, TriggerReason.DEMAND_SPIKE.value)

    return DemandSpikeResponse(
        message=f"Demand spike simulated for {product.name}",
        product_id=product.id,
        previous_velocity=previous_velocity,
        new_velocity=product.demand_velocity,
        triggered=triggered,
    )


# ──────────────────────── What-If Simulator ────────────────────────


@router.post("/{product_id}/what-if")
def what_if_simulation(
    product_id: int,
    payload: WhatIfRequest,
    db: Session = Depends(get_db),
):
    """
    Run a what-if simulation without modifying the database.
    Returns current vs simulated state with recommendations.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return run_what_if(db, product, payload.stock_level, payload.demand_velocity)
