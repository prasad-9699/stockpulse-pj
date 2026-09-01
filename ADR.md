# Architecture Decision Records — StockPulse

---

## ADR-1: Commerce Logic Lives in a Dedicated Strategy Layer, Not the Service/Router Layer

### Context
StockPulse needs pricing and reorder recommendation logic that can be invoked from two places: on-demand HTTP endpoints and the background agentic loop. Putting this logic directly in route handlers would create duplication and tight coupling.

### Options
1. **Inline in route handlers** — fastest to write, but duplicates logic between on-demand and agentic paths
2. **Service layer functions** — better, but still couples business rules to a specific implementation
3. **Strategy pattern with abstract interfaces** — most flexible, supports runtime switching

### Decision
We use the **Strategy pattern** with abstract base classes (`PricingStrategy`, `ReorderStrategy`) in `strategies/base.py`. Both the HTTP endpoints and the agentic loop call strategies through these interfaces. A factory function resolves the active implementation from env vars at runtime.

### Tradeoffs
- ✅ Single code path for both on-demand and reactive suggestions — no duplicated logic
- ✅ New strategies (e.g., competitor-aware pricing) plug in by implementing the interface
- ✅ Runtime switching without restart (`PRICING_STRATEGY=rule|ai` env var)
- ⚠️ Slightly more abstraction than a hackathon might warrant, but the payoff is immediate (AI fallback uses the same interface)

---

## ADR-2: Separate AI Prompts for Pricing and Reorder (Not a Single Combined Prompt)

### Context
When the AI strategy generates suggestions, it could use one prompt asking for both pricing and reorder recommendations simultaneously, or separate prompts for each.

### Options
1. **Single combined prompt** — one LLM call, lower latency, but harder to parse and more likely to produce malformed responses
2. **Separate prompts** — two LLM calls, but each is focused, easier to validate, and fails independently

### Decision
We use **separate, context-specific prompts**. The pricing prompt frames the question as "protect scarce stock vs. clearance discount" for inventory-low triggers, and "capitalize on viral demand" for demand-spike triggers. The reorder prompt focuses on quantity optimization.

### Tradeoffs
- ✅ Clearer prompts produce better, more focused AI reasoning
- ✅ Independent fallback — if the pricing call fails, the reorder call can still succeed
- ✅ Easier to validate and debug each response independently
- ⚠️ Two LLM calls instead of one (acceptable for ~200ms flash models)
- ⚠️ Slightly more code, but each prompt is self-contained and readable

---

## ADR-3: Runtime Strategy Switching via Environment Variables (Factory/Registry Pattern)

### Context
During a demo, we want to switch between rule-based and AI strategies without restarting the server. During development, we want rule-based to work with zero setup.

### Options
1. **Hardcoded imports** — simplest, but requires code change + restart to switch
2. **Config file** — more flexible, but still requires restart for most implementations
3. **Env var read on each call** — reads `PRICING_STRATEGY` and `REORDER_STRATEGY` fresh on every invocation

### Decision
The `_get_strategy()` factory function in `agentic_loop.py` reads env vars **on every call**. This means you can change the strategy by updating the env var and the next request uses the new strategy — no restart needed.

### Tradeoffs
- ✅ Hot-swap strategies during a live demo
- ✅ Default to `rule` so zero-setup demos work immediately
- ✅ Factory pattern is well-understood and easy to extend
- ⚠️ Env var read on every call has negligible overhead (os.getenv is fast)
- ⚠️ No validation of env var values at startup — typos silently default to rule-based

---

## ADR-4: LLM Failure Handling — Silent Fallback to Rule-Based

### Context
LLM calls can fail in many ways: missing API key, network timeout, rate limiting, malformed JSON response, or out-of-bounds values (e.g., negative prices). A hackathon demo must never crash because of a flaky API.

### Options
1. **Crash and surface the error** — transparent but breaks the demo
2. **Queue a failed suggestion with error details** — more work, confusing UX
3. **Silent fallback to rule-based strategy** — the show goes on, with a server-side log

### Decision
The AI strategy classes (`AIPricingStrategy`, `AIReorderStrategy`) wrap every LLM call in a try/except. On **any** failure — missing key, timeout, HTTP error, JSON parse error, or validation failure (price ≤ 0, price > 3x current, negative quantity) — the strategy logs the reason and returns the rule-based recommendation instead.

### Tradeoffs
- ✅ Demo never crashes due to LLM issues
- ✅ Rule-based fallback produces reasonable, deterministic results
- ✅ Server-side logging captures exactly what went wrong for debugging
- ⚠️ The frontend doesn't know if it got an AI or rule-based suggestion — acceptable for MVP
- ⚠️ Silent failures could mask persistent issues in production (add monitoring in sprint 2)

---

## ADR-5: Agentic Loop Decoupling — BackgroundTasks + Idempotency + SSE Events

### Context
When a stock update or sale triggers the agentic loop, the API must respond immediately — the user shouldn't wait for LLM calls to complete. The loop must also avoid creating duplicate suggestions if triggered multiple times for the same signal.

### Options
1. **Synchronous in-request** — simple but blocks the API response for 1-5 seconds
2. **Celery/Redis task queue** — production-grade but massive setup overhead for a hackathon
3. **FastAPI BackgroundTasks** — runs after the response is sent, zero infrastructure

### Decision
We use **FastAPI BackgroundTasks** to fire the agentic loop after the HTTP response is prepared. The loop runs in a background thread via `asyncio.to_thread()`. Before creating any suggestion, it checks for existing `PENDING` suggestions with the same `(product_id, trigger_reason, suggestion_type)` — this is the **idempotency guard**.

The loop publishes SSE events at each stage (detection, calling advisor, suggestion queued) via a thread-safe in-process event bus. Connected frontend clients see the loop fire in real-time.

### Tradeoffs
- ✅ API responses return instantly — no blocking on LLM calls
- ✅ Zero infrastructure — no Redis, no Celery, no message broker
- ✅ Idempotency prevents duplicate suggestions from rapid-fire triggers
- ✅ SSE events create the strongest demo moment (judges watch the loop react live)
- ⚠️ BackgroundTasks don't survive server restarts (acceptable for hackathon; use Celery in production)
- ⚠️ In-process pub/sub doesn't scale to multiple server instances (use Redis pub/sub in production)

---

## ADR-6: Deliberate Exclusions — What's Deferred to Sprint 2

### Context
Several features were considered but deliberately excluded to ship a working end-to-end demo within the time budget.

### Excluded Features and Where They'd Plug In

| Feature | Why Excluded | Where It Plugs In |
|---|---|---|
| **Competitor pricing** | Requires external data source + scraping infrastructure | New strategy implementation of `PricingStrategy` that combines internal signals with competitor data |
| **Margin floors** | Needs `cost_price` data which we don't have real values for | `Product.cost_price` field exists (nullable); strategies would check `recommended_price > cost_price * 1.1` |
| **Supplier catalog** | Needs supplier API integration | `Product.supplier_id` field exists (nullable); `ReorderStrategy` would query supplier for lead times and MOQs |
| **Price history tracking** | Useful for sparklines but not critical for MVP | Add a `PriceHistory` table, insert a row on every `ACCEPTED` pricing suggestion |
| **Demand velocity decay** | Velocity currently only goes up — no 24h rolling window | Add a periodic task that decays velocity, or track individual order timestamps |
| **Multi-instance SSE** | In-process event bus doesn't work across multiple server instances | Replace `event_bus.py` with Redis pub/sub |
| **Authentication** | No auth — anyone can access the console | Add FastAPI `Depends` with JWT or session-based auth |

### Decision
These are all acknowledged as sprint-2 items. The codebase is explicitly structured to accommodate them — the strategy interfaces, placeholder fields, and modular architecture make each addition a targeted change rather than a rewrite.
