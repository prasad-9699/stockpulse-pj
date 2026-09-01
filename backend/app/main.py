"""
main.py — FastAPI application entry point for StockPulse.

Bootstraps the app with CORS, includes all routers, creates DB tables,
and seeds demo data on first startup. Stores the event loop reference
for thread-safe SSE publishing. Run with:
    uvicorn app.main:app --reload
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env before anything else reads env vars
load_dotenv()

from app.database import engine, Base
from app.seed import seed_database
from app import event_bus
from app.routers import products, pricing_suggestions, reorder_suggestions, stream, settings

# Configure logging for the agentic loop and LLM gateway
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: create all DB tables, seed demo data, and store event loop reference.
    Shutdown: (no cleanup needed for SQLite)
    """
    # Store the event loop reference for thread-safe SSE publishing
    event_bus.set_event_loop(asyncio.get_event_loop())
    Base.metadata.create_all(bind=engine)
    seed_database()
    yield


app = FastAPI(
    title="StockPulse",
    description="AI-powered inventory & dynamic pricing advisor for ShopStream",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers — each router handles its own prefix and tags
app.include_router(products.router)
app.include_router(pricing_suggestions.router)
app.include_router(reorder_suggestions.router)
app.include_router(stream.router)
app.include_router(settings.router)


@app.get("/", tags=["Health"])
def health_check():
    """Simple health check endpoint to confirm the API is running."""
    return {"status": "ok", "app": "StockPulse", "version": "1.0.0"}
