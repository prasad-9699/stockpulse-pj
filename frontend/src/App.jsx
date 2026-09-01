/**
 * App.jsx — StockPulse Merchandising Console.
 *
 * Full dashboard with: product table (risk scores, stockout prediction),
 * suggestion panels (explainability), agent activity feed (improved timeline),
 * demand spike simulator, strategy toggle, analytics dashboard,
 * what-if simulator, and recommendation history.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  fetchProducts,
  fetchPricingSuggestions,
  fetchReorderSuggestions,
  simulateOrder,
  simulateDemandSpike,
  updatePricingSuggestion,
  updateReorderSuggestion,
  fetchStrategy,
  updateStrategy,
  fetchAnalytics,
  runWhatIf,
  fetchRecommendationHistory,
  SSE_URL,
} from './api.js';

// ──────────────────── Helpers ────────────────────

function buildProductMap(products) {
  const map = {};
  products.forEach(p => { map[p.id] = p; });
  return map;
}

function statusBadgeClass(status) {
  switch (status) {
    case 'ACTIVE': return 'badge-active';
    case 'PRICE_REVIEW_PENDING': return 'badge-pending';
    case 'OUT_OF_STOCK': return 'badge-out-of-stock';
    default: return '';
  }
}

function triggerBadgeClass(trigger) {
  switch (trigger) {
    case 'INVENTORY_LOW': return 'badge-inventory-low';
    case 'DEMAND_SPIKE': return 'badge-demand-spike';
    case 'MANUAL': return 'badge-manual';
    default: return 'badge-manual';
  }
}

function stockClass(stock, threshold) {
  if (stock === 0) return 'critical';
  if (stock < threshold) return 'low';
  return 'ok';
}

function riskLevelClass(level) {
  switch (level) {
    case 'CRITICAL': return 'risk-critical';
    case 'HIGH': return 'risk-high';
    case 'MODERATE': return 'risk-moderate';
    case 'LOW': return 'risk-low';
    default: return '';
  }
}

/** Map SSE event types to icons and colors for improved timeline. */
function eventTypeInfo(eventType) {
  switch (eventType) {
    case 'detection': return { icon: '🔍', cls: 'event-detection' };
    case 'strategy_selected': return { icon: '🧠', cls: 'event-strategy' };
    case 'calling_ai': return { icon: '⚙️', cls: 'event-calling' };
    case 'suggestion_queued': return { icon: '💡', cls: 'event-queued' };
    case 'checkpoint': return { icon: '⏳', cls: 'event-checkpoint' };
    case 'skipped': return { icon: '⏭️', cls: 'event-skipped' };
    default: return { icon: '📌', cls: 'event-default' };
  }
}

const CATEGORIES = ['ALL', 'ELECTRONICS', 'APPAREL', 'HOME'];
const TABS = ['inventory', 'analytics', 'history', 'whatif'];

export default function App() {
  // ── Core State ──
  const [products, setProducts] = useState([]);
  const [pricingSuggestions, setPricingSuggestions] = useState([]);
  const [reorderSuggestions, setReorderSuggestions] = useState([]);
  const [activityLog, setActivityLog] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [actionLoading, setActionLoading] = useState({});
  const [activeTab, setActiveTab] = useState('inventory');

  // ── Strategy State ──
  const [activeStrategy, setActiveStrategy] = useState('RULE_BASED');

  // ── Analytics State ──
  const [analytics, setAnalytics] = useState(null);

  // ── History State ──
  const [history, setHistory] = useState([]);
  const [historyFilter, setHistoryFilter] = useState('ALL');
  const [historyTypeFilter, setHistoryTypeFilter] = useState('ALL');

  // ── What-If State ──
  const [whatIfProduct, setWhatIfProduct] = useState(null);
  const [whatIfStock, setWhatIfStock] = useState(0);
  const [whatIfVelocity, setWhatIfVelocity] = useState(0);
  const [whatIfResult, setWhatIfResult] = useState(null);
  const [whatIfLoading, setWhatIfLoading] = useState(false);

  const activityRef = useRef(null);
  const toastIdRef = useRef(0);

  // ── Toast helper ──
  const showToast = useCallback((message, type = 'success') => {
    const id = ++toastIdRef.current;
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3500);
  }, []);

  // ── Data fetching ──
  const loadData = useCallback(async () => {
    try {
      const [prods, pricing, reorder] = await Promise.all([
        fetchProducts(null, categoryFilter === 'ALL' ? null : categoryFilter),
        fetchPricingSuggestions('PENDING'),
        fetchReorderSuggestions('PENDING'),
      ]);
      setProducts(prods);
      setPricingSuggestions(pricing);
      setReorderSuggestions(reorder);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [categoryFilter]);

  // Load strategy on mount
  useEffect(() => {
    fetchStrategy()
      .then(data => setActiveStrategy(data.strategy))
      .catch(() => {}); // Silently fall back to default
  }, []);

  // Initial load + polling every 4 seconds
  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 4000);
    return () => clearInterval(interval);
  }, [loadData]);

  // ── SSE connection for Agent Activity Feed ──
  useEffect(() => {
    let eventSource;
    try {
      eventSource = new EventSource(SSE_URL);
      eventSource.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data);
          setActivityLog(prev => {
            const next = [event, ...prev];
            return next.slice(0, 100);
          });
          if (event.event_type === 'suggestion_queued') {
            loadData();
          }
        } catch { /* ignore parse errors from keepalives */ }
      };
      eventSource.onerror = () => {};
    } catch {}
    return () => { if (eventSource) eventSource.close(); };
  }, [loadData]);

  // Auto-scroll activity feed
  useEffect(() => {
    if (activityRef.current) {
      activityRef.current.scrollTop = 0;
    }
  }, [activityLog]);

  // Load analytics when tab switches
  useEffect(() => {
    if (activeTab === 'analytics') {
      fetchAnalytics().then(setAnalytics).catch(() => {});
    }
  }, [activeTab]);

  // Load history when tab switches
  useEffect(() => {
    if (activeTab === 'history') {
      const statusParam = historyFilter === 'ALL' ? null : historyFilter;
      const typeParam = historyTypeFilter === 'ALL' ? null : historyTypeFilter;
      fetchRecommendationHistory(statusParam, typeParam).then(setHistory).catch(() => {});
    }
  }, [activeTab, historyFilter, historyTypeFilter]);

  // ── Actions ──

  const handleRequestPricing = async (productId) => {
    setActionLoading(prev => ({ ...prev, [`reqprice-${productId}`]: true }));
    try {
      await requestPricingSuggestion(productId);
      showToast('Pricing suggestion requested!', 'info');
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`reqprice-${productId}`]: false }));
    }
  };

  const handleRequestReorder = async (productId) => {
    setActionLoading(prev => ({ ...prev, [`reqreorder-${productId}`]: true }));
    try {
      await requestReorderSuggestion(productId);
      showToast('Reorder suggestion requested!', 'info');
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`reqreorder-${productId}`]: false }));
    }
  };

  const handleSimulateSale = async (productId) => {
    setActionLoading(prev => ({ ...prev, [`sale-${productId}`]: true }));
    try {
      await simulateOrder(productId);
      showToast('Sale simulated! Watch the Agent Activity Feed 👀', 'info');
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`sale-${productId}`]: false }));
    }
  };

  const handleDemandSpike = async (productId) => {
    setActionLoading(prev => ({ ...prev, [`spike-${productId}`]: true }));
    try {
      const result = await simulateDemandSpike(productId, 3);
      showToast(
        result.triggered
          ? `⚡ Demand spike! Velocity ${result.previous_velocity} → ${result.new_velocity}. Agent triggered!`
          : `⚡ Velocity ${result.previous_velocity} → ${result.new_velocity}`,
        result.triggered ? 'info' : 'success'
      );
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`spike-${productId}`]: false }));
    }
  };

  const handleAcceptPricing = async (id) => {
    setActionLoading(prev => ({ ...prev, [`pricing-${id}`]: true }));
    try {
      await updatePricingSuggestion(id, 'ACCEPTED');
      showToast('Pricing suggestion accepted! Price updated ✅');
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`pricing-${id}`]: false }));
    }
  };

  const handleRejectPricing = async (id) => {
    setActionLoading(prev => ({ ...prev, [`pricing-${id}`]: true }));
    try {
      await updatePricingSuggestion(id, 'REJECTED');
      showToast('Pricing suggestion rejected');
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`pricing-${id}`]: false }));
    }
  };

  const handleAcceptReorder = async (id) => {
    setActionLoading(prev => ({ ...prev, [`reorder-${id}`]: true }));
    try {
      await updateReorderSuggestion(id, 'ACCEPTED');
      showToast('Reorder accepted! Stock updated ✅');
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`reorder-${id}`]: false }));
    }
  };

  const handleRejectReorder = async (id) => {
    setActionLoading(prev => ({ ...prev, [`reorder-${id}`]: true }));
    try {
      await updateReorderSuggestion(id, 'REJECTED');
      showToast('Reorder suggestion rejected');
      await loadData();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [`reorder-${id}`]: false }));
    }
  };

  const handleStrategyToggle = async () => {
    const newStrategy = activeStrategy === 'AI' ? 'RULE_BASED' : 'AI';
    try {
      const result = await updateStrategy(newStrategy);
      setActiveStrategy(result.strategy);
      showToast(`Strategy switched to ${result.strategy === 'AI' ? '🤖 AI' : '📏 Rule-Based'}`, 'info');
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  const handleRunWhatIf = async () => {
    if (!whatIfProduct) return;
    setWhatIfLoading(true);
    try {
      const result = await runWhatIf(whatIfProduct.id, whatIfStock, whatIfVelocity);
      setWhatIfResult(result);
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setWhatIfLoading(false);
    }
  };

  const openWhatIf = (product) => {
    setWhatIfProduct(product);
    setWhatIfStock(product.stock_level);
    setWhatIfVelocity(product.demand_velocity);
    setWhatIfResult(null);
    setActiveTab('whatif');
  };

  const productMap = buildProductMap(products);

  // ── Render ──
  return (
    <div className="app-container">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-logo">
          <div className="app-logo-icon">⚡</div>
          <div>
            <h1>StockPulse</h1>
            <p>Merchandising Console</p>
          </div>
        </div>
        <div className="app-header-right">
          <button
            className={`strategy-toggle ${activeStrategy === 'AI' ? 'strategy-ai' : 'strategy-rule'}`}
            onClick={handleStrategyToggle}
            title="Click to switch strategy"
          >
            {activeStrategy === 'AI' ? '🤖 AI Strategy' : '📏 Rule-Based'}
            <span className="toggle-hint">click to switch</span>
          </button>
        </div>
      </header>

      {/* ── Tab Navigation ── */}
      <nav className="tab-nav">
        <button className={`tab-btn ${activeTab === 'inventory' ? 'active' : ''}`} onClick={() => setActiveTab('inventory')}>
          📦 Inventory
        </button>
        <button className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`} onClick={() => setActiveTab('analytics')}>
          📊 Analytics
        </button>
        <button className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`} onClick={() => setActiveTab('history')}>
          📜 History
        </button>
        <button className={`tab-btn ${activeTab === 'whatif' ? 'active' : ''}`} onClick={() => setActiveTab('whatif')}>
          🔮 What-If
        </button>
      </nav>

      {/* ══════════════ INVENTORY TAB ══════════════ */}
      {activeTab === 'inventory' && (
        <div className="main-grid">
          {/* ── Left Column: Product Table ── */}
          <div>
            <div className="card">
              <div className="card-header">
                <h2>📦 Product Inventory <span className="count-badge">{products.length}</span></h2>
              </div>

              {/* Category Filter Tabs */}
              <div className="filter-tabs">
                {CATEGORIES.map(cat => (
                  <button
                    key={cat}
                    className={`filter-tab ${categoryFilter === cat ? 'active' : ''}`}
                    onClick={() => setCategoryFilter(cat)}
                  >
                    {cat === 'ALL' ? '🏷️ All' : cat === 'ELECTRONICS' ? '💻 Electronics' : cat === 'APPAREL' ? '👕 Apparel' : '🏠 Home'}
                  </button>
                ))}
              </div>

              <div className="card-body-flush">
                {loading ? (
                  <div className="loading-spinner">
                    <div className="spinner"></div>
                    Loading products...
                  </div>
                ) : error ? (
                  <div className="error-message">⚠️ {error}</div>
                ) : products.length === 0 ? (
                  <div className="empty-state">No products found</div>
                ) : (
                  <table className="product-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Category</th>
                        <th>Price</th>
                        <th>Stock</th>
                        <th>Velocity</th>
                        <th>Risk</th>
                        <th>Stockout</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {products.map(product => (
                        <tr key={product.id}>
                          <td>
                            <div className="product-name">{product.name}</div>
                            <div className="product-sku">{product.sku}</div>
                          </td>
                          <td>
                            <span className="badge badge-manual">
                              {product.category === 'ELECTRONICS' ? '💻' : product.category === 'APPAREL' ? '👕' : '🏠'} {product.category}
                            </span>
                          </td>
                          <td>
                            <span className="product-price">${product.current_price.toFixed(2)}</span>
                          </td>
                          <td>
                            <span className={`stock-level ${stockClass(product.stock_level, product.reorder_threshold)}`}>
                              {product.stock_level}
                              <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> / {product.reorder_threshold}</span>
                            </span>
                          </td>
                          <td>
                            <div className="velocity-bar">
                              <div className="bar" style={{ width: `${Math.min(product.demand_velocity * 4, 60)}px` }}></div>
                              <span>{product.demand_velocity}</span>
                            </div>
                          </td>
                          <td>
                            {product.risk_score != null && (
                              <div className={`risk-indicator ${riskLevelClass(product.risk_level)}`}>
                                <div className="risk-score-value">{product.risk_score}</div>
                                <div className="risk-bar-mini">
                                  <div className="risk-fill" style={{ width: `${product.risk_score}%` }}></div>
                                </div>
                                <div className="risk-label">{product.risk_level}</div>
                              </div>
                            )}
                          </td>
                          <td>
                            {product.estimated_stockout_days != null ? (
                              <span className={`stockout-days ${product.estimated_stockout_days <= 2 ? 'stockout-urgent' : product.estimated_stockout_days <= 5 ? 'stockout-warning' : ''}`}>
                                {product.estimated_stockout_days.toFixed(1)}d
                              </span>
                            ) : (
                              <span className="stockout-safe">—</span>
                            )}
                          </td>
                          <td>
                            <span className={`badge ${statusBadgeClass(product.status)}`}>
                              {product.status === 'PRICE_REVIEW_PENDING' ? '⏳ REVIEW' : product.status === 'OUT_OF_STOCK' ? '🚫 OOS' : '✅ ACTIVE'}
                            </span>
                          </td>
                          <td>
                            <div className="btn-group">
                              <button
                                className="btn btn-simulate"
                                onClick={() => handleSimulateSale(product.id)}
                                disabled={product.stock_level === 0 || actionLoading[`sale-${product.id}`]}
                                title="Simulate a sale"
                              >
                                {actionLoading[`sale-${product.id}`] ? '...' : '🛒 Sell'}
                              </button>
                              <button
                                className="btn btn-spike"
                                onClick={() => handleDemandSpike(product.id)}
                                disabled={actionLoading[`spike-${product.id}`]}
                                title="Simulate demand spike (3x velocity)"
                              >
                                {actionLoading[`spike-${product.id}`] ? '...' : '⚡'}
                              </button>
                                <button
                                  className="btn btn-whatif"
                                  onClick={() => openWhatIf(product)}
                                  title="What-if simulator"
                                >
                                  🔮
                                </button>
                                <button
                                  className="btn btn-simulate"
                                  onClick={() => handleRequestPricing(product.id)}
                                  disabled={actionLoading[`reqprice-${product.id}`]}
                                  title="Request Pricing Suggestion"
                                  style={{ padding: "6px" }}
                                >
                                  {actionLoading[`reqprice-${product.id}`] ? '...' : '💰'}
                                </button>
                                <button
                                  className="btn btn-simulate"
                                  onClick={() => handleRequestReorder(product.id)}
                                  disabled={actionLoading[`reqreorder-${product.id}`]}
                                  title="Request Reorder Suggestion"
                                  style={{ padding: "6px" }}
                                >
                                  {actionLoading[`reqreorder-${product.id}`] ? '...' : '📦'}
                                </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>

          {/* ── Right Column: Sidebar ── */}
          <div className="sidebar">
            {/* Agent Activity Feed */}
            <div className="card">
              <div className="card-header">
                <h2>🔴 Agent Activity <span className="count-badge">{activityLog.length}</span></h2>
              </div>
              <div className="card-body-flush">
                <div className="activity-feed" ref={activityRef}>
                  {activityLog.length === 0 ? (
                    <div className="activity-empty">
                      <div className="icon">🤖</div>
                      <div>Waiting for agent activity...</div>
                      <div style={{ fontSize: '0.72rem', marginTop: 4 }}>Click "Sell" or "⚡" on a product to trigger the loop</div>
                    </div>
                  ) : (
                    activityLog.map((event, i) => {
                      const info = eventTypeInfo(event.event_type);
                      return (
                        <div className={`activity-item ${info.cls}`} key={`${event.timestamp}-${i}`}>
                          <span className="event-icon">{info.icon}</span>
                          <div className="event-content">
                            <span className="timestamp">
                              {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                            <span className="message">{event.message}</span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>

            {/* Pricing Suggestions */}
            <div className="card">
              <div className="card-header">
                <h2>💰 Pricing Suggestions <span className="count-badge">{pricingSuggestions.length}</span></h2>
              </div>
              <div className="card-body-flush">
                {pricingSuggestions.length === 0 ? (
                  <div className="empty-state">No pending pricing suggestions</div>
                ) : (
                  <div className="suggestion-list">
                    {pricingSuggestions.map(s => {
                      const prod = productMap[s.product_id];
                      return (
                        <div className="suggestion-item" key={s.id}>
                          <div className="suggestion-header">
                            <span className="suggestion-product-name">{prod?.name || `Product #${s.product_id}`}</span>
                            <span className={`badge ${triggerBadgeClass(s.trigger_reason)}`}>{s.trigger_reason}</span>
                          </div>
                          <div className="suggestion-price-change">
                            <span className="old-price">${s.current_price.toFixed(2)}</span>
                            <span className="arrow">→</span>
                            <span className={`new-price ${s.direction === 'DECREASE' ? 'decrease' : ''}`}>${s.recommended_price.toFixed(2)}</span>
                            <span className={`badge badge-${s.direction.toLowerCase()}`}>{s.direction}</span>
                          </div>
                          <div className="confidence-bar">
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Confidence</span>
                            <div className="track">
                              <div className="fill" style={{ width: `${s.confidence * 100}%` }}></div>
                            </div>
                            <span className="value">{(s.confidence * 100).toFixed(0)}%</span>
                          </div>
                          {/* Explainability: strategy + fallback info */}
                          {s.strategy_used && (
                            <div className="explainability-badge">
                              <span className={`strategy-tag ${s.strategy_used === 'AI' ? 'tag-ai' : 'tag-rule'}`}>
                                {s.strategy_used === 'AI' ? '🤖 AI' : '📏 Rule-Based'}
                              </span>
                              {s.fallback_used && (
                                <span className="fallback-tag">⚠️ AI failed → Rule-Based fallback</span>
                              )}
                            </div>
                          )}
                          {s.reasoning && <div className="suggestion-reasoning">{s.reasoning}</div>}
                          <div className="suggestion-actions">
                            <button className="btn btn-accept" onClick={() => handleAcceptPricing(s.id)} disabled={actionLoading[`pricing-${s.id}`]}>✅ Accept</button>
                            <button className="btn btn-reject" onClick={() => handleRejectPricing(s.id)} disabled={actionLoading[`pricing-${s.id}`]}>❌ Reject</button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Reorder Suggestions */}
            <div className="card">
              <div className="card-header">
                <h2>📦 Reorder Suggestions <span className="count-badge">{reorderSuggestions.length}</span></h2>
              </div>
              <div className="card-body-flush">
                {reorderSuggestions.length === 0 ? (
                  <div className="empty-state">No pending reorder suggestions</div>
                ) : (
                  <div className="suggestion-list">
                    {reorderSuggestions.map(s => {
                      const prod = productMap[s.product_id];
                      return (
                        <div className="suggestion-item" key={s.id}>
                          <div className="suggestion-header">
                            <span className="suggestion-product-name">{prod?.name || `Product #${s.product_id}`}</span>
                            <span className={`badge ${triggerBadgeClass(s.trigger_reason)}`}>{s.trigger_reason}</span>
                          </div>
                          <div className="suggestion-price-change">
                            <span style={{ color: 'var(--text-secondary)' }}>Current stock: {s.current_stock}</span>
                            <span className="arrow">→</span>
                            <span className="new-price">+{s.recommended_quantity} units</span>
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 6 }}>
                            Lead time: {s.lead_time_days} days
                          </div>
                          <div className="confidence-bar">
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Confidence</span>
                            <div className="track">
                              <div className="fill" style={{ width: `${s.confidence * 100}%` }}></div>
                            </div>
                            <span className="value">{(s.confidence * 100).toFixed(0)}%</span>
                          </div>
                          {/* Explainability Badge */}
                          {s.strategy_used && (
                            <div className="explainability-badge">
                              <span className={`strategy-tag ${s.strategy_used === 'AI' ? 'tag-ai' : 'tag-rule'}`}>
                                {s.strategy_used === 'AI' ? '🤖 AI' : '📏 Rule-Based'}
                              </span>
                              {s.fallback_used && (
                                <span className="fallback-tag">⚠️ AI failed → Rule-Based fallback</span>
                              )}
                              {s.guardrail_applied && (
                                <span className="fallback-tag">🛡️ Guardrail Applied</span>
                              )}
                            </div>
                          )}

                          {/* Reorder Engine Explainability Breakdown */}
                          <div className="suggestion-reasoning">
                            <div style={{ marginBottom: '8px', fontWeight: 'bold' }}>Why this reorder?</div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.72rem' }}>
                              <div>Current Stock: <strong>{s.current_stock} units</strong></div>
                              <div>Demand Velocity: <strong>{s.demand_velocity} units/day</strong></div>
                              <div>Lead Time: <strong>{s.lead_time_days} days</strong></div>
                              <div>Lead Time Demand: <strong>{s.expected_lead_time_demand} units</strong></div>
                              <div>Safety Stock: <strong>{s.safety_stock} units</strong></div>
                              <div>Target Inventory: <strong>{s.target_inventory} units</strong></div>
                            </div>
                            <div style={{ marginTop: '8px', padding: '6px', background: 'rgba(0,0,0,0.2)', borderRadius: '4px' }}>
                              Final Recommendation: <strong>Reorder +{s.recommended_quantity} units</strong>
                            </div>
                            {s.reasoning && (
                              <div style={{ marginTop: '8px', fontStyle: 'italic' }}>
                                {s.reasoning}
                              </div>
                            )}
                          </div>
                          <div className="suggestion-actions">
                            <button className="btn btn-accept" onClick={() => handleAcceptReorder(s.id)} disabled={actionLoading[`reorder-${s.id}`]}>✅ Accept</button>
                            <button className="btn btn-reject" onClick={() => handleRejectReorder(s.id)} disabled={actionLoading[`reorder-${s.id}`]}>❌ Reject</button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════ ANALYTICS TAB ══════════════ */}
      {activeTab === 'analytics' && (
        <div className="analytics-container">
          {!analytics ? (
            <div className="loading-spinner"><div className="spinner"></div> Loading analytics...</div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="analytics-grid">
                <div className="analytics-card card-total">
                  <div className="analytics-card-value">{analytics.summary.total_products}</div>
                  <div className="analytics-card-label">Total Products</div>
                </div>
                <div className="analytics-card card-risk">
                  <div className="analytics-card-value">{analytics.summary.products_at_risk}</div>
                  <div className="analytics-card-label">At Risk</div>
                </div>
                <div className="analytics-card card-critical">
                  <div className="analytics-card-value">{analytics.summary.critical_products}</div>
                  <div className="analytics-card-label">Critical</div>
                </div>
                <div className="analytics-card card-oos">
                  <div className="analytics-card-value">{analytics.summary.out_of_stock}</div>
                  <div className="analytics-card-label">Out of Stock</div>
                </div>
                <div className="analytics-card card-pending">
                  <div className="analytics-card-value">{analytics.summary.pending_recommendations}</div>
                  <div className="analytics-card-label">Pending Actions</div>
                </div>
                <div className="analytics-card card-avg-risk">
                  <div className="analytics-card-value">{analytics.summary.average_risk_score}</div>
                  <div className="analytics-card-label">Avg Risk Score</div>
                </div>
              </div>

              {/* Inventory Health Distribution */}
              <div className="analytics-row">
                <div className="card">
                  <div className="card-header"><h2>🏥 Inventory Health</h2></div>
                  <div className="card-body">
                    <div className="health-bars">
                      {[
                        { label: 'Healthy', value: analytics.inventory_health.healthy, color: 'var(--accent-emerald)', total: analytics.summary.total_products },
                        { label: 'Moderate', value: analytics.inventory_health.moderate, color: 'var(--accent-amber)', total: analytics.summary.total_products },
                        { label: 'High Risk', value: analytics.inventory_health.high, color: '#f97316', total: analytics.summary.total_products },
                        { label: 'Critical', value: analytics.inventory_health.critical, color: 'var(--accent-rose)', total: analytics.summary.total_products },
                        { label: 'Out of Stock', value: analytics.inventory_health.out_of_stock, color: '#6b7280', total: analytics.summary.total_products },
                      ].map(h => (
                        <div key={h.label} className="health-bar-row">
                          <span className="health-label">{h.label}</span>
                          <div className="health-track">
                            <div className="health-fill" style={{ width: `${h.total > 0 ? (h.value / h.total) * 100 : 0}%`, background: h.color }}></div>
                          </div>
                          <span className="health-count">{h.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="card">
                  <div className="card-header"><h2>🎯 Trigger Distribution</h2></div>
                  <div className="card-body">
                    <div className="trigger-grid">
                      {Object.entries(analytics.trigger_distribution).map(([trigger, count]) => (
                        <div key={trigger} className="trigger-item">
                          <span className={`badge ${triggerBadgeClass(trigger)}`}>{trigger}</span>
                          <span className="trigger-count">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Product Risk Table */}
              <div className="card">
                <div className="card-header"><h2>📋 Product Risk Overview</h2></div>
                <div className="card-body-flush">
                  <table className="product-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Category</th>
                        <th>Stock</th>
                        <th>Velocity</th>
                        <th>Price</th>
                        <th>Risk Score</th>
                        <th>Risk Level</th>
                        <th>Stockout ETA</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.products
                        .sort((a, b) => b.risk_score - a.risk_score)
                        .map(p => (
                          <tr key={p.product_id}>
                            <td>
                              <div className="product-name">{p.name}</div>
                              <div className="product-sku">{p.sku}</div>
                            </td>
                            <td><span className="badge badge-manual">{p.category}</span></td>
                            <td>{p.stock_level}</td>
                            <td>{p.demand_velocity}</td>
                            <td><span className="product-price">${p.current_price.toFixed(2)}</span></td>
                            <td>
                              <div className={`risk-indicator ${riskLevelClass(p.risk_level)}`}>
                                <div className="risk-score-value">{p.risk_score}</div>
                                <div className="risk-bar-mini">
                                  <div className="risk-fill" style={{ width: `${p.risk_score}%` }}></div>
                                </div>
                              </div>
                            </td>
                            <td><span className={`badge ${riskLevelClass(p.risk_level)}`}>{p.risk_level}</span></td>
                            <td>{p.estimated_stockout_days != null ? `${p.estimated_stockout_days.toFixed(1)} days` : '—'}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ══════════════ HISTORY TAB ══════════════ */}
      {activeTab === 'history' && (
        <div className="history-container">
          <div className="card">
            <div className="card-header">
              <h2>📜 Recommendation History <span className="count-badge">{history.length}</span></h2>
            </div>
            <div className="filter-tabs">
              {['ALL', 'PENDING', 'ACCEPTED', 'REJECTED'].map(f => (
                <button key={f} className={`filter-tab ${historyFilter === f ? 'active' : ''}`} onClick={() => setHistoryFilter(f)}>
                  {f === 'ALL' ? '📋 All' : f === 'PENDING' ? '⏳ Pending' : f === 'ACCEPTED' ? '✅ Accepted' : '❌ Rejected'}
                </button>
              ))}
              <span className="filter-divider">|</span>
              {['ALL', 'pricing', 'reorder'].map(f => (
                <button key={f} className={`filter-tab ${historyTypeFilter === f ? 'active' : ''}`} onClick={() => setHistoryTypeFilter(f)}>
                  {f === 'ALL' ? '🔄 All Types' : f === 'pricing' ? '💰 Pricing' : '📦 Reorder'}
                </button>
              ))}
            </div>
            <div className="card-body-flush">
              {history.length === 0 ? (
                <div className="empty-state">No recommendations found</div>
              ) : (
                <div className="history-list">
                  {history.map((item, i) => {
                    const prod = productMap[item.product_id];
                    return (
                      <div className="history-item" key={`${item.type}-${item.id}-${i}`}>
                        <div className="history-header">
                          <div className="history-left">
                            <span className={`badge ${item.type === 'pricing' ? 'badge-increase' : 'badge-manual'}`}>
                              {item.type === 'pricing' ? '💰 PRICING' : '📦 REORDER'}
                            </span>
                            <span className="history-product">{prod?.name || `Product #${item.product_id}`}</span>
                          </div>
                          <div className="history-right">
                            <span className={`badge ${item.status === 'ACCEPTED' ? 'badge-active' : item.status === 'REJECTED' ? 'badge-out-of-stock' : 'badge-pending'}`}>
                              {item.status}
                            </span>
                            <span className={`badge ${triggerBadgeClass(item.trigger_reason)}`}>{item.trigger_reason}</span>
                          </div>
                        </div>
                        <div className="history-details">
                          {item.type === 'pricing' ? (
                            <span>${item.current_price?.toFixed(2)} → <strong>${item.recommended_price?.toFixed(2)}</strong> ({item.direction})</span>
                          ) : (
                            <span>+<strong>{item.recommended_quantity}</strong> units (lead: {item.lead_time_days}d)</span>
                          )}
                          <span className="history-confidence">Confidence: {(item.confidence * 100).toFixed(0)}%</span>
                        </div>
                        {/* Explainability */}
                        {item.strategy_used && (
                          <div className="explainability-badge">
                            <span className={`strategy-tag ${item.strategy_used === 'AI' ? 'tag-ai' : 'tag-rule'}`}>
                              {item.strategy_used === 'AI' ? '🤖 AI' : '📏 Rule-Based'}
                            </span>
                            {item.fallback_used && <span className="fallback-tag">⚠️ Fallback</span>}
                          </div>
                        )}
                        {item.reasoning && <div className="suggestion-reasoning">{item.reasoning}</div>}
                        <div className="history-timestamp">{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════ WHAT-IF TAB ══════════════ */}
      {activeTab === 'whatif' && (
        <div className="whatif-container">
          <div className="card">
            <div className="card-header">
              <h2>🔮 What-If Simulator</h2>
            </div>
            <div className="card-body">
              {/* Product selector */}
              <div className="whatif-selector">
                <label>Select Product:</label>
                <select
                  value={whatIfProduct?.id || ''}
                  onChange={e => {
                    const p = products.find(p => p.id === Number(e.target.value));
                    if (p) {
                      setWhatIfProduct(p);
                      setWhatIfStock(p.stock_level);
                      setWhatIfVelocity(p.demand_velocity);
                      setWhatIfResult(null);
                    }
                  }}
                  className="whatif-select"
                >
                  <option value="">-- Choose a product --</option>
                  {products.map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>
                  ))}
                </select>
              </div>

              {whatIfProduct && (
                <>
                  <div className="whatif-inputs">
                    <div className="whatif-field">
                      <label>Simulated Stock Level</label>
                      <input type="number" min="0" value={whatIfStock} onChange={e => setWhatIfStock(Number(e.target.value))} className="whatif-input" />
                      <span className="whatif-current">Current: {whatIfProduct.stock_level}</span>
                    </div>
                    <div className="whatif-field">
                      <label>Simulated Demand Velocity</label>
                      <input type="number" min="0" value={whatIfVelocity} onChange={e => setWhatIfVelocity(Number(e.target.value))} className="whatif-input" />
                      <span className="whatif-current">Current: {whatIfProduct.demand_velocity}</span>
                    </div>
                    <button className="btn btn-simulate whatif-run" onClick={handleRunWhatIf} disabled={whatIfLoading}>
                      {whatIfLoading ? '⏳ Simulating...' : '🔮 Run Simulation'}
                    </button>
                  </div>
                  <p className="whatif-note">⚠️ This simulation does NOT modify the database.</p>

                  {whatIfResult && (
                    <div className="whatif-results">
                      {/* Current vs Simulated */}
                      <div className="whatif-comparison">
                        <div className="whatif-state">
                          <h3>Current State</h3>
                          <div className="whatif-metric"><span>Stock:</span> <strong>{whatIfResult.current_state.stock_level}</strong></div>
                          <div className="whatif-metric"><span>Velocity:</span> <strong>{whatIfResult.current_state.demand_velocity}</strong></div>
                          <div className="whatif-metric"><span>Risk:</span> <strong className={riskLevelClass(whatIfResult.current_state.risk_level)}>{whatIfResult.current_state.risk_score} ({whatIfResult.current_state.risk_level})</strong></div>
                          <div className="whatif-metric"><span>Stockout:</span> <strong>{whatIfResult.current_state.estimated_stockout_days != null ? `${whatIfResult.current_state.estimated_stockout_days}d` : '—'}</strong></div>
                        </div>
                        <div className="whatif-arrow">→</div>
                        <div className="whatif-state whatif-simulated">
                          <h3>Simulated State</h3>
                          <div className="whatif-metric"><span>Stock:</span> <strong>{whatIfResult.simulated_state.stock_level}</strong></div>
                          <div className="whatif-metric"><span>Velocity:</span> <strong>{whatIfResult.simulated_state.demand_velocity}</strong></div>
                          <div className="whatif-metric"><span>Risk:</span> <strong className={riskLevelClass(whatIfResult.simulated_state.risk_level)}>{whatIfResult.simulated_state.risk_score} ({whatIfResult.simulated_state.risk_level})</strong></div>
                          <div className="whatif-metric"><span>Stockout:</span> <strong>{whatIfResult.simulated_state.estimated_stockout_days != null ? `${whatIfResult.simulated_state.estimated_stockout_days}d` : '—'}</strong></div>
                          {whatIfResult.simulated_state.risk_factors?.length > 0 && (
                            <div className="whatif-risk-factors">
                              {whatIfResult.simulated_state.risk_factors.map((f, i) => (
                                <span key={i} className="risk-factor-tag">⚠️ {f}</span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Recommendations */}
                      <div className="whatif-recommendations">
                        <div className="whatif-rec">
                          <h3>💰 Pricing Recommendation</h3>
                          <div className="whatif-metric"><span>Price:</span> <strong className="product-price">${whatIfResult.pricing_recommendation.recommended_price.toFixed(2)}</strong></div>
                          <div className="whatif-metric"><span>Direction:</span> <span className={`badge badge-${whatIfResult.pricing_recommendation.direction.toLowerCase()}`}>{whatIfResult.pricing_recommendation.direction}</span></div>
                          <div className="whatif-metric"><span>Confidence:</span> <strong>{(whatIfResult.pricing_recommendation.confidence * 100).toFixed(0)}%</strong></div>
                          <div className="suggestion-reasoning">{whatIfResult.pricing_recommendation.reasoning}</div>
                        </div>
                        <div className="whatif-rec">
                          <h3>📦 Reorder Recommendation</h3>
                          <div className="whatif-metric"><span>Quantity:</span> <strong>+{whatIfResult.reorder_recommendation.recommended_quantity} units</strong></div>
                          <div className="whatif-metric"><span>Lead Time:</span> <strong>{whatIfResult.reorder_recommendation.lead_time_days} days</strong></div>
                          <div className="whatif-metric"><span>Confidence:</span> <strong>{(whatIfResult.reorder_recommendation.confidence * 100).toFixed(0)}%</strong></div>
                          <div className="suggestion-reasoning">{whatIfResult.reorder_recommendation.reasoning}</div>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Toast Notifications ── */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}
