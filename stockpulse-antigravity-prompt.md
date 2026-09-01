# StockPulse — Build Prompt for Antigravity

Paste everything below into Antigravity as a single build instruction.

---

## ROLE

You are building **StockPulse**, an AI-powered inventory & dynamic pricing
advisor, for a solo hackathon. I have **~2 hours** of build time left. Work
fast, favor working end-to-end functionality over polish, and don't ask me
clarifying questions — make a reasonable decision, note it as a one-line
comment, and keep moving. Generate the **entire project** (backend +
frontend + docs) in one pass, then run it to confirm it boots.

## THE PROBLEM (context for your decisions)

ShopStream sells electronics, apparel, and home goods. Prices are set
manually and reviewed weekly, so when a product's stock runs critically low,
or demand suddenly spikes, nobody reacts until a human notices. StockPulse
closes that gap automatically:

> When inventory crosses a threshold OR demand velocity spikes, the system
> detects it, asks an AI advisor for a recommended price change AND a
> reorder quantity, and queues both for one-click human approval — no one
> has to ask for it.

This is a **reactive commerce advisor**, not a full storefront. No cart, no
checkout, no payments.

## TECH STACK (fixed — do not substitute)

- **Backend:** Python, FastAPI, SQLAlchemy ORM, Pydantic v2 for schemas, `uvicorn`
- **Database:** SQLite (file-based, `stockpulse.db`) via SQLAlchemy — use a
  `DATABASE_URL` env var so switching to Postgres later is a one-line change.
  Do NOT require Docker or a running Postgres service; SQLite must work
  out of the box with zero setup.
- **Frontend:** React 18 + Vite, plain fetch/axios (no heavy state library needed)
- **AI:** One `llm_gateway.py` module that calls an LLM provider based on
  env vars (see "LLM Gateway" section below)
- **Async/background work:** FastAPI `BackgroundTasks` (or `asyncio.create_task`)
  for the agentic loop — do NOT block the HTTP response while the AI call runs
- **CORS:** allow `http://localhost:5173`

Repo layout:
```
/backend
  /app
    main.py
    models.py         # SQLAlchemy models
    schemas.py         # Pydantic schemas
    database.py         # engine/session, SQLite by default
    strategies/
      base.py             # abstract PricingStrategy / ReorderStrategy interfaces
      rule_based.py
      ai_strategy.py
    llm_gateway.py
    agentic_loop.py     # trigger detection + background suggestion generation
    routers/
      products.py
      pricing_suggestions.py
      reorder_suggestions.py
      stream.py            # SSE endpoints
    seed.py
  requirements.txt
  .env.example
/frontend
  (Vite React app)
README.md
ADR.md
```

## DOMAIN MODEL

**Product**
- `id`, `sku`, `name`, `category` (`ELECTRONICS` | `APPAREL` | `HOME`)
- `current_price`, `stock_level`, `reorder_threshold`, `demand_velocity` (orders in last 24h)
- `status`: `ACTIVE → PRICE_REVIEW_PENDING → ACTIVE`, and `OUT_OF_STOCK` when stock = 0
- extension placeholders (nullable, unused for now): `cost_price`, `supplier_id`

**PricingSuggestion**
- `product_id`, `current_price`, `recommended_price`
- `direction`: `INCREASE` | `DECREASE` | `HOLD`
- `confidence` (0.0–1.0), `reasoning` (text)
- `status`: `PENDING → ACCEPTED | REJECTED`
- `trigger_reason`: `INITIAL` | `INVENTORY_LOW` | `DEMAND_SPIKE` | `MANUAL`
- `created_at`

**ReorderSuggestion**
- `product_id`, `current_stock`, `recommended_quantity`, `lead_time_days`
- `confidence`, `reasoning`
- `status`: `PENDING → ACCEPTED | REJECTED`
- `trigger_reason`: same enum as above
- `created_at`

## API ENDPOINTS

- `POST /products` — create product with initial stock/price
- `GET /products?status=&category=` — filterable list
- `GET /products/{id}` — single product with its pending suggestions embedded
- `PATCH /products/{id}/stock` — update stock; **fires agentic loop** if resulting stock < reorder_threshold
- `POST /products/{id}/orders` — simulate a sale: decrement stock by 1 (or `qty` in body), bump demand_velocity; **fires agentic loop** on low-stock or demand-spike
- `POST /products/{id}/suggest-pricing` — on-demand pricing suggestion (trigger_reason=MANUAL)
- `POST /products/{id}/suggest-reorder` — on-demand reorder suggestion (trigger_reason=MANUAL)
- `PATCH /pricing-suggestions/{id}` — body `{status: ACCEPTED|REJECTED}`; accept atomically updates `Product.current_price` and resets status to ACTIVE if no other pending suggestions
- `PATCH /reorder-suggestions/{id}` — accept atomically increments `Product.stock_level` (simulated inbound shipment)
- `GET /pricing-suggestions?status=PENDING` / `GET /reorder-suggestions?status=PENDING`
- `GET /events/stream` — **SSE endpoint** for the Agent Activity Feed (see New Feature below)
- `POST /products/{id}/suggest-pricing/stream` — SSE token stream of the AI's reasoning as it's generated (bonus feature, reuse the same streaming utility)

## PLUGGABLE COMMERCE ENGINE (strategy pattern)

Define abstract base classes in `strategies/base.py`:
```python
class PricingStrategy(ABC):
    def recommend_pricing(self, product, trigger_reason: str, category_avg_velocity: float) -> PricingRecommendation: ...

class ReorderStrategy(ABC):
    def recommend_reorder(self, product, trigger_reason: str) -> ReorderRecommendation: ...
```

**Rule-based pricing** (`rule_based.py`):
- if `stock_level < reorder_threshold` → recommend +10% price, direction=INCREASE
- elif `demand_velocity > 2 * category_avg_velocity` → recommend +5%, direction=INCREASE
- else → HOLD, confidence 0.5

**Rule-based reorder**:
- `recommended_quantity = max(1, reorder_threshold * 3 - stock_level)`

**AI strategy** (`ai_strategy.py`) implements the same interfaces, calling `llm_gateway.call_llm(prompt)`.

Active strategy is chosen at runtime from an env var `PRICING_STRATEGY=rule|ai` /
`REORDER_STRATEGY=rule|ai`, read fresh on each call (no restart needed) via a
small factory/registry function — not hardcoded imports.

Both the on-demand HTTP endpoints and the async agentic loop must call
strategies through the **same interface** — no duplicated logic.

## LLM GATEWAY (`llm_gateway.py`)

```python
# Config via environment variables (put a real key in backend/.env, gitignored):
#   LLM_PROVIDER=gemini | groq | ollama   (default: gemini)
#   LLM_API_KEY=<your key>                 (leave blank to force rule-based fallback)
#   LLM_MODEL=gemini-1.5-flash             (or llama-3.1-8b-instant for groq, etc.)
#   LLM_BASE_URL=https://generativelanguage.googleapis.com
```
- Implement `call_llm(prompt: str) -> str` supporting Gemini, Groq (OpenAI-compatible),
  and Ollama (local, OpenAI-compatible) via simple `if/elif` on `LLM_PROVIDER`.
- **If `LLM_API_KEY` is empty/unset, or the call raises/times out/returns
  unparseable JSON, the AI strategy must silently fall back to the
  rule-based strategy for that suggestion** — never let a broken API key
  crash a demo. Log the fallback reason server-side.
- Never hardcode a key in source. `.env` is in `.gitignore`. `.env.example`
  documents the variable names with placeholder values only.

### Two distinct prompts (do not reuse one prompt with a field swapped in)

**Inventory-low prompt** — include: product name/category, current price,
stock level vs reorder threshold, demand velocity, and explicitly ask the
model to weigh "raise price to protect scarce remaining stock" vs "run a
clearance discount to move slow units" and explain its reasoning in plain
English before giving numbers.

**Demand-spike prompt** — include: product name/category, current price,
demand velocity vs category average, and frame it as "should we capitalize
on a viral spike with a modest price increase, and how much extra stock
should we reorder to meet the surge?"

Both prompts must instruct the model to respond in **strict JSON only**:
```json
// pricing
{"recommendedPrice": 29.99, "direction": "INCREASE", "confidence": 0.82, "reasoning": "..."}
// reorder
{"recommendedQuantity": 150, "confidence": 0.78, "reasoning": "..."}
```
Validate: price > 0 and not more than 3x current price without flagging;
quantity is a positive integer. Reject and fall back to rule-based on
violation.

## AGENTIC LOOP (`agentic_loop.py`)

- Triggered from the stock-update and order endpoints, **after** the HTTP
  response has been prepared (use `BackgroundTasks`) — the request must
  return immediately.
- **Trigger A (inventory low):** resulting `stock_level < reorder_threshold`
  → generate PricingSuggestion + ReorderSuggestion with `trigger_reason=INVENTORY_LOW`,
  set product status to `PRICE_REVIEW_PENDING`.
- **Trigger B (demand spike):** `demand_velocity > 3 * category_avg_velocity`
  → generate both suggestion types with `trigger_reason=DEMAND_SPIKE`.
- **Idempotency:** before creating a new suggestion, skip if a `PENDING`
  suggestion already exists for the same `(product_id, trigger_reason, suggestion_type)`.
- Push an event onto the SSE queue at each stage (see below) so the frontend
  can show the loop firing live.
- Loop: Observe (signal) → Reason (call strategy) → Act (queue suggestion) → Checkpoint (human accepts/rejects). Never auto-publish a price.

## NEW FEATURE (beyond the brief) — Live Agent Activity Feed

This is the differentiator for the demo. Implement a simple in-process
pub/sub (a list of `asyncio.Queue` per connected client is fine) that the
agentic loop publishes to at each stage:
```
🔍 Detected: PRD-003 stock (7) < threshold (15) — INVENTORY_LOW
🤖 Calling AI advisor for pricing recommendation...
💡 Suggestion queued: DECREASE not chosen — recommend +12% (confidence 0.81)
🤖 Calling AI advisor for reorder recommendation...
💡 Reorder suggestion queued: +38 units (confidence 0.76)
```
Expose this over `GET /events/stream` (SSE, `text/event-stream`). In the
React UI, render it as a small scrolling "Agent Activity" panel so judges
can *watch* the agentic loop react to a simulated sale in real time —
this is your strongest demo moment.

## FRONTEND (React + Vite) — Merchandising Console

**Floor (must have):**
- Product table: SKU, name, category, stock, price, demand velocity, status badge
- "Simulate Sale" button per product (calls `POST /products/{id}/orders`) — this is
  the primary demo trigger, no curl needed
- Pending Suggestions panel: shows pricing + reorder suggestions with
  confidence %, AI reasoning text, and a colored badge for
  `INVENTORY_LOW` / `DEMAND_SPIKE` / `MANUAL`
- Accept / Reject buttons on each suggestion, wired to the PATCH endpoints
- Live Agent Activity Feed panel (SSE) described above
- Polling (every 3–5s) or refetch-on-action for the product list; loading
  and error states everywhere

**Ceiling (only if time remains):** category filter tabs, a simple margin
indicator, a tiny price-history sparkline per product.

Keep styling simple and clean (basic CSS or a lightweight utility like
plain CSS modules) — functionality over visual polish given the time budget.

## SEED DATA

On backend startup (or via `python -m app.seed`), insert these 8 products
so the demo path works immediately:

| SKU | Name | Category | Price | Stock | Threshold | Velocity | Status |
|---|---|---|---|---|---|---|---|
| SKU-ELEC-001 | Wireless Earbuds Pro | ELECTRONICS | 79.99 | 45 | 20 | 3 | ACTIVE |
| SKU-ELEC-002 | USB-C Hub 7-Port | ELECTRONICS | 34.99 | 120 | 30 | 1 | ACTIVE |
| SKU-APP-001 | Organic Cotton T-Shirt | APPAREL | 24.99 | 8 | 15 | 12 | PRICE_REVIEW_PENDING |
| SKU-APP-002 | Running Shorts — Navy | APPAREL | 39.99 | 55 | 20 | 2 | ACTIVE |
| SKU-HOME-001 | Ceramic Pour-Over Set | HOME | 49.99 | 22 | 10 | 4 | ACTIVE |
| SKU-HOME-002 | LED Desk Lamp — Dimmable | HOME | 59.99 | 0 | 15 | 0 | OUT_OF_STOCK |
| SKU-ELEC-003 | Portable Charger 20K | ELECTRONICS | 44.99 | 18 | 25 | 8 | ACTIVE |
| SKU-APP-003 | Hoodie — Heather Grey | APPAREL | 54.99 | 11 | 12 | 15 | ACTIVE |

Demo paths to keep in mind:
- **Inventory low:** simulate sales on the T-Shirt (PRD-003 equiv) until stock < threshold → auto pricing + reorder suggestions appear.
- **Demand spike:** simulate several sales on the Hoodie → velocity crosses threshold → spike-triggered suggestions.

## README.md (write this — must let a stranger run the app in under 5 minutes)

Include:
1. Prereqs (Python 3.10+, Node 18+)
2. `cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
3. `cp .env.example .env` and note that leaving `LLM_API_KEY` blank still works (rule-based fallback)
4. `uvicorn app.main:app --reload` (seeds DB automatically on first run)
5. `cd frontend && npm install && npm run dev`
6. URLs for backend (`http://localhost:8000/docs`) and frontend (`http://localhost:5173`)
7. A "Demo script" section: "Click Simulate Sale on the Hoodie 3 times → watch the Agent Activity Feed → see suggestions appear → Accept the pricing suggestion → price updates on the product row."

## ADR.md (write this — as important as the code)

Four to six entries, each in **Context → Options → Decision → Tradeoffs**
format, covering:
1. Where commerce logic lives (service layer vs dedicated advisor module)
2. Unified vs separate AI calls for pricing/reorder (you chose separate — explain why: clearer prompts, independent fallback)
3. Runtime strategy switching mechanism (env-var-read factory)
4. LLM failure handling (timeouts, bad JSON, out-of-bounds values → rule-based fallback)
5. Agentic loop decoupling (BackgroundTasks, idempotency check)
6. What you deliberately excluded (competitor pricing, margin floors, supplier catalog — sprint 2) and where in the code those would plug in (point to the strategy interface and the `cost_price`/`supplier_id` placeholder fields)

## BUILD ORDER (given ~2 hours)

1. Backend models + DB + seed script + basic CRUD endpoints (30 min)
2. Rule-based strategies wired to on-demand endpoints (20 min)
3. LLM gateway + AI strategy + both prompts + validation/fallback (30 min)
4. Agentic loop (BackgroundTasks, both triggers, idempotency, SSE feed) (25 min)
5. React console: product table, simulate sale, suggestions panel, accept/reject, activity feed (30 min)
6. README + ADR + final smoke test end-to-end (15 min)

If you run short on time: drop the price-history sparkline and margin
display first. Do NOT drop the agentic loop, the accept/reject checkpoint,
or the ADR — those carry the most evaluation weight.

---

Build the full project now, then run both servers to confirm the app boots
and the seed data loads correctly.
