"""
seed.py — Database seeder with 8 demo products.

Run as `python -m app.seed` or called automatically on first startup.
Seeds the DB only if the products table is empty, making it safe to
call repeatedly. The seed data is carefully chosen to enable two demo paths:
- Inventory low: T-Shirt (stock 8, threshold 15) → a few sales triggers the loop
- Demand spike: Hoodie (velocity 15) → a few more sales crosses the 3x threshold
"""

from app.database import engine, SessionLocal, Base
from app.models import Product, ProductStatus, CategoryEnum


SEED_PRODUCTS = [
    {
        "sku": "SKU-ELEC-001",
        "name": "Wireless Earbuds Pro",
        "category": CategoryEnum.ELECTRONICS,
        "current_price": 79.99,
        "stock_level": 45,
        "reorder_threshold": 20,
        "demand_velocity": 3,
        "status": ProductStatus.ACTIVE,
    },
    {
        "sku": "SKU-ELEC-002",
        "name": "USB-C Hub 7-Port",
        "category": CategoryEnum.ELECTRONICS,
        "current_price": 34.99,
        "stock_level": 120,
        "reorder_threshold": 30,
        "demand_velocity": 1,
        "status": ProductStatus.ACTIVE,
    },
    {
        "sku": "SKU-APP-001",
        "name": "Organic Cotton T-Shirt",
        "category": CategoryEnum.APPAREL,
        "current_price": 24.99,
        "stock_level": 8,
        "reorder_threshold": 15,
        "demand_velocity": 12,
        "status": ProductStatus.PRICE_REVIEW_PENDING,
    },
    {
        "sku": "SKU-APP-002",
        "name": "Running Shorts — Navy",
        "category": CategoryEnum.APPAREL,
        "current_price": 39.99,
        "stock_level": 55,
        "reorder_threshold": 20,
        "demand_velocity": 2,
        "status": ProductStatus.ACTIVE,
    },
    {
        "sku": "SKU-HOME-001",
        "name": "Ceramic Pour-Over Set",
        "category": CategoryEnum.HOME,
        "current_price": 49.99,
        "stock_level": 22,
        "reorder_threshold": 10,
        "demand_velocity": 4,
        "status": ProductStatus.ACTIVE,
    },
    {
        "sku": "SKU-HOME-002",
        "name": "LED Desk Lamp — Dimmable",
        "category": CategoryEnum.HOME,
        "current_price": 59.99,
        "stock_level": 0,
        "reorder_threshold": 15,
        "demand_velocity": 0,
        "status": ProductStatus.OUT_OF_STOCK,
    },
    {
        "sku": "SKU-ELEC-003",
        "name": "Portable Charger 20K",
        "category": CategoryEnum.ELECTRONICS,
        "current_price": 44.99,
        "stock_level": 18,
        "reorder_threshold": 25,
        "demand_velocity": 8,
        "status": ProductStatus.ACTIVE,
    },
    {
        "sku": "SKU-APP-003",
        "name": "Hoodie — Heather Grey",
        "category": CategoryEnum.APPAREL,
        "current_price": 54.99,
        "stock_level": 11,
        "reorder_threshold": 12,
        "demand_velocity": 15,
        "status": ProductStatus.ACTIVE,
    },
]


def seed_database():
    """
    Insert demo products if the products table is empty.
    Safe to call multiple times — only seeds on first run.
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Product).count() == 0:
            for product_data in SEED_PRODUCTS:
                db.add(Product(**product_data))
            db.commit()
            print(f"[OK] Seeded {len(SEED_PRODUCTS)} products")
        else:
            print("[INFO] Products already exist, skipping seed")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
