/**
 * DealerDesk — Frontend Application Logic
 * Professional B2B Distribution, Inventory, Order Management & AI Assistant
 */

// Global State
const State = {
  activeTab: 'overview',
  dealers: [],
  selectedDealerId: 1,
  sessionId: 'session-' + Math.random().toString(36).substring(2, 9),
  products: [],
  productsCount: 0,
  currentPage: 1,
  pageSize: 20,
  orders: [],
  reorderItems: [],
  selectedForecastSku: 'BRK-1019',
  syncRunning: false,
  isAssistantLoading: false,
};

// Formatting Utilities
const fmtMoney = (val) => {
  if (val === null || val === undefined) return '₹0.00';
  const num = parseFloat(val);
  return '₹' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Unified API Client
async function api(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : `/api${endpoint}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.error?.message || data.detail || `Request failed with status ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

// Initialization on DOM Load
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupAssistant();
  setupCatalogue();
  setupOrders();
  setupForecast();
  setupSync();

  // Load initial backend state
  await loadDealers();
  await loadOverviewData();
});

// Navigation Handling
function setupNavigation() {
  const navButtons = document.querySelectorAll('.nav-item');
  navButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      switchTab(tab);
    });
  });
}

function switchTab(tabId) {
  State.activeTab = tabId;
  document.querySelectorAll('.nav-item').forEach((b) => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));

  const activeBtn = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
  const activePane = document.getElementById(`tab-${tabId}`);
  if (activeBtn) activeBtn.classList.add('active');
  if (activePane) activePane.classList.add('active');

  // Lazy-load data when switching to tabs
  if (tabId === 'overview') loadOverviewData();
  if (tabId === 'catalogue' && State.products.length === 0) loadProducts();
  if (tabId === 'orders') loadOrders();
  if (tabId === 'reorder') loadReorderSuggestions();
  if (tabId === 'forecast') loadForecastView();
  if (tabId === 'dealers') renderDealersDirectory();
}

// --------------------------------------------------------------------------
// Active Dealer & Overview Management
// --------------------------------------------------------------------------
async function loadDealers() {
  try {
    const data = await api('/dealers/?page_size=100');
    State.dealers = data.results || [];
    const select = document.getElementById('global-dealer-select');
    if (select) {
      select.innerHTML = State.dealers
        .map(
          (d) =>
            `<option value="${d.id}" ${d.id === State.selectedDealerId ? 'selected' : ''}>
              ${d.name} (${d.dealer_code} • ${d.city})
            </option>`
        )
        .join('');

      select.addEventListener('change', (e) => {
        State.selectedDealerId = parseInt(e.target.value);
        updateDealerContext();
      });
    }
    updateDealerContext();
  } catch (err) {
    console.error('Failed to load dealers:', err);
  }
}

function updateDealerContext() {
  const dealer = State.dealers.find((d) => d.id === State.selectedDealerId);
  if (!dealer) return;

  // Update Assistant Sidebar details
  const nameEl = document.getElementById('sidebar-dealer-name');
  const codeEl = document.getElementById('sidebar-dealer-code');
  const cityEl = document.getElementById('sidebar-dealer-city');
  const creditEl = document.getElementById('sidebar-dealer-credit');

  if (nameEl) nameEl.textContent = dealer.name;
  if (codeEl) codeEl.textContent = dealer.dealer_code;
  if (cityEl) cityEl.textContent = dealer.city;
  if (creditEl) creditEl.textContent = fmtMoney(dealer.credit_limit);
}

async function loadOverviewData() {
  try {
    // 1. Fetch metrics
    const [prods, ordersData, dealersData] = await Promise.all([
      api('/products/?page_size=1'),
      api('/orders/?page_size=5'),
      api('/dealers/?page_size=1'),
    ]);

    const valProds = document.getElementById('overview-val-products');
    const valOrders = document.getElementById('overview-val-orders');
    const valDealers = document.getElementById('overview-val-dealers');
    const badgeProds = document.getElementById('nav-badge-products');
    const badgeOrders = document.getElementById('nav-badge-orders');

    if (valProds) valProds.textContent = prods.count || 600;
    if (badgeProds) badgeProds.textContent = prods.count || 600;
    if (valOrders) valOrders.textContent = ordersData.count || 0;
    if (badgeOrders) badgeOrders.textContent = ordersData.count || 0;
    if (valDealers) valDealers.textContent = dealersData.count || 25;

    // 2. Render Recent Orders Table
    const recentOrders = ordersData.results || [];
    const recentBody = document.getElementById('overview-recent-orders-body');
    if (recentBody) {
      if (recentOrders.length === 0) {
        recentBody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--text-muted)">No orders placed yet.</td></tr>`;
      } else {
        recentBody.innerHTML = recentOrders
          .map((o) => {
            const d = State.dealers.find((dl) => dl.id === o.dealer_id) || { name: 'Dealer #' + o.dealer_id };
            return `
            <tr>
              <td><span class="sku-badge">${o.order_number}</span></td>
              <td>${d.name}</td>
              <td><span class="status-badge status-${o.status}">${o.status}</span></td>
              <td style="font-weight:600;color:var(--text-primary)">${fmtMoney(o.grand_total)}</td>
            </tr>
          `;
          })
          .join('');
      }
    }

    // 3. Render Low Stock Alerts from Reorder Suggestions
    const reorderData = await api('/reorder-suggestions/').catch(() => ({ results: [] }));
    const lowStockItems = (reorderData.results || []).filter((r) => r.reorder_qty > 0).slice(0, 5);
    const lowStockBody = document.getElementById('overview-low-stock-body');

    if (lowStockBody) {
      if (lowStockItems.length === 0) {
        lowStockBody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--success)">All items at optimal warehouse stock.</td></tr>`;
      } else {
        lowStockBody.innerHTML = lowStockItems
          .map(
            (item) => `
          <tr>
            <td><span class="sku-badge">${item.sku}</span></td>
            <td>ROP: ${item.reorder_point} units</td>
            <td><span class="status-badge low-stock">${item.current_stock} in stock</span></td>
            <td>
              <button class="btn-secondary btn-sm" onclick="quickReorderFromSku('${item.sku}', ${item.reorder_qty})">+ Draft (${item.reorder_qty})</button>
            </td>
          </tr>
        `
          )
          .join('');
      }
    }
  } catch (err) {
    console.error('Overview data error:', err);
  }
}

// --------------------------------------------------------------------------
// SECTION 4: AI Assistant
// --------------------------------------------------------------------------
function setupAssistant() {
  const sendBtn = document.getElementById('chat-send-btn');
  const inputEl = document.getElementById('chat-input');
  const resetBtn = document.getElementById('reset-chat-btn');
  const chips = document.querySelectorAll('.prompt-chip');

  if (sendBtn && inputEl) {
    sendBtn.addEventListener('click', () => sendAssistantMessage());
    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendAssistantMessage();
      }
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', () => resetAssistantSession());
  }

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      if (inputEl) {
        inputEl.value = chip.dataset.prompt;
        sendAssistantMessage();
      }
    });
  });
}

function resetAssistantSession() {
  State.sessionId = 'session-' + Math.random().toString(36).substring(2, 9);
  const messagesBox = document.getElementById('chat-messages');
  const promptsBox = document.getElementById('suggested-prompts-box');

  if (messagesBox) {
    messagesBox.innerHTML = `
      <div class="msg-row assistant">
        <div class="msg-avatar">AI</div>
        <div class="msg-bubble">
          Hello! I am your <strong>DealerDesk Parts Assistant</strong>. I am grounded in live catalogue and inventory data. 
          You can ask me to check parts compatibility, look up on-hand stock, or create draft orders for your active dealership.
        </div>
      </div>
    `;
  }

  if (promptsBox) promptsBox.style.display = 'block';
  hideAssistantLoading();
}

function getFriendlyLoadingText(message) {
  const m = message.toLowerCase();
  if (m.includes('stock') || m.includes('available') || m.includes('how many')) {
    return 'Checking current availability…';
  }
  if (m.includes('order') || m.includes('draft') || m.includes('buy') || m.includes('reserve')) {
    return 'Preparing your draft order…';
  }
  if (m.includes('reorder') || m.includes('re-order')) {
    return 'Evaluating inventory and reorder points…';
  }
  if (m.includes('find') || m.includes('search') || m.includes('looking for') || m.includes('pad') || m.includes('brake')) {
    return 'Searching the catalogue…';
  }
  return 'Working on your request…';
}

function showAssistantLoading(statusMessage) {
  State.isAssistantLoading = true;
  const statusBox = document.getElementById('assistant-status-box');
  const statusText = document.getElementById('assistant-status-text');
  const sendBtn = document.getElementById('chat-send-btn');
  const inputEl = document.getElementById('chat-input');

  if (statusText) statusText.textContent = statusMessage;
  if (statusBox) statusBox.style.display = 'block';
  if (sendBtn) sendBtn.disabled = true;
  if (inputEl) inputEl.disabled = true;
}

function hideAssistantLoading() {
  State.isAssistantLoading = false;
  const statusBox = document.getElementById('assistant-status-box');
  const sendBtn = document.getElementById('chat-send-btn');
  const inputEl = document.getElementById('chat-input');

  if (statusBox) statusBox.style.display = 'none';
  if (sendBtn) sendBtn.disabled = false;
  if (inputEl) {
    inputEl.disabled = false;
    inputEl.focus();
  }
}

async function sendAssistantMessage() {
  if (State.isAssistantLoading) return;
  const inputEl = document.getElementById('chat-input');
  const message = inputEl.value.trim();
  if (!message) return;

  // Clear input
  inputEl.value = '';

  // Hide suggested prompts after first message
  const promptsBox = document.getElementById('suggested-prompts-box');
  if (promptsBox) promptsBox.style.display = 'none';

  // Append user message immediately
  appendChatMessage('user', escapeHtml(message));

  // Determine friendly loading text and activate indicator
  const friendlyStatus = getFriendlyLoadingText(message);
  showAssistantLoading(friendlyStatus);

  try {
    const payload = {
      session_id: State.sessionId,
      dealer_id: State.selectedDealerId,
      message: message,
    };

    const res = await api('/assistant/chat/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    hideAssistantLoading();
    renderAssistantMessage(res);
  } catch (err) {
    hideAssistantLoading();
    appendChatMessage(
      'assistant',
      `<div style="color:var(--danger)">⚠️ We were unable to process your request. Please try again in a moment. (${escapeHtml(err.message)})</div>`
    );
  }
}

function appendChatMessage(role, contentHtml) {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  const row = document.createElement('div');
  row.className = `msg-row ${role}`;
  row.innerHTML = `
    <div class="msg-avatar">${role === 'user' ? 'You' : 'AI'}</div>
    <div class="msg-bubble">${contentHtml}</div>
  `;
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

function renderAssistantMessage(data) {
  let content = formatMarkdown(data.reply);

  // If a draft order was created in actions, render a clean draft order card
  const orderAction = (data.actions || []).find((a) => a.type === 'draft_order_created');
  if (orderAction) {
    content += `
      <div class="order-reference-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span class="order-ref-badge">✓ Draft Order Created</span>
          <span class="sku-badge">${orderAction.order_number}</span>
        </div>
        <div style="font-size:12.5px;color:var(--text-secondary)">
          Amount: <strong>${fmtMoney(orderAction.grand_total)}</strong> (including 18% GST).
        </div>
        <div style="font-size:11.5px;color:var(--text-muted);margin-top:4px;">
          Note: This is a draft order. Please confirm it from the <strong>Orders</strong> tab when ready to reserve inventory.
        </div>
      </div>
    `;
  }

  // If products were cited or returned, render structured product cards
  if (data.cited_skus && data.cited_skus.length > 0) {
    // Check if tools returned product details
    const foundItems = [];
    (data.tool_calls || []).forEach((tc) => {
      // In tool_calls we have arguments or tool outputs
    });

    content += `
      <div style="margin-top:12px;font-size:12px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;">Referenced Products:</div>
      <div style="display:flex;flex-direction:column;gap:8px;margin-top:6px;">
        ${data.cited_skus
          .map(
            (sku) => `
          <div class="product-reference-card">
            <div class="product-ref-header">
              <span class="sku-badge">${sku}</span>
              <div class="product-ref-actions">
                <button class="btn-secondary btn-sm" onclick="quickCheckStockInChat('${sku}')">Check Stock</button>
                <button class="btn-primary btn-sm" onclick="quickDraftOrderInChat('${sku}')">+ Order (1)</button>
              </div>
            </div>
          </div>
        `
          )
          .join('')}
      </div>
    `;
  }

  appendChatMessage('assistant', content);
}

window.quickCheckStockInChat = async function (sku) {
  const inputEl = document.getElementById('chat-input');
  if (inputEl) {
    inputEl.value = `Check stock for ${sku}`;
    sendAssistantMessage();
  }
};

window.quickDraftOrderInChat = async function (sku) {
  const inputEl = document.getElementById('chat-input');
  if (inputEl) {
    inputEl.value = `Create a draft order for 1 unit of ${sku}`;
    sendAssistantMessage();
  }
};

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

// --------------------------------------------------------------------------
// SECTION 2: Catalogue & Inventory
// --------------------------------------------------------------------------
function setupCatalogue() {
  const searchInput = document.getElementById('cat-search-input');
  const catSelect = document.getElementById('cat-category-select');
  const prevBtn = document.getElementById('cat-prev-btn');
  const nextBtn = document.getElementById('cat-next-btn');

  if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        State.currentPage = 1;
        loadProducts();
      }, 300);
    });
  }

  if (catSelect) {
    catSelect.addEventListener('change', () => {
      State.currentPage = 1;
      loadProducts();
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      if (State.currentPage > 1) {
        State.currentPage--;
        loadProducts();
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      State.currentPage++;
      loadProducts();
    });
  }
}

async function loadProducts() {
  const search = document.getElementById('cat-search-input')?.value.trim() || '';
  const category = document.getElementById('cat-category-select')?.value || '';

  let query = `/products/?page=${State.currentPage}&page_size=${State.pageSize}`;
  if (search) query += `&search=${encodeURIComponent(search)}`;
  if (category) query += `&category=${encodeURIComponent(category)}`;

  try {
    const data = await api(query);
    State.products = data.results || [];
    State.productsCount = data.count || 0;
    renderProductsTable();
  } catch (err) {
    console.error('Products load error:', err);
  }
}

function renderProductsTable() {
  const tbody = document.getElementById('products-table-body');
  const paginationInfo = document.getElementById('cat-pagination-info');
  if (!tbody) return;

  if (State.products.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:30px;color:var(--text-muted)">No products found matching filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = State.products
    .map((p) => {
      let badgeClass = 'in-stock';
      let badgeLabel = `${p.stock} in stock`;
      if (p.stock === 0) {
        badgeClass = 'out-of-stock';
        badgeLabel = 'Out of Stock';
      } else if (p.stock < 15) {
        badgeClass = 'low-stock';
        badgeLabel = `${p.stock} low stock`;
      }

      return `
      <tr>
        <td><span class="sku-badge">${p.sku}</span></td>
        <td>
          <div style="font-weight:600;color:var(--text-primary)">${p.name}</div>
          <div style="font-size:11.5px;color:var(--text-secondary)">${p.brand}</div>
        </td>
        <td><span style="font-size:12px;color:var(--text-secondary)">${p.category}</span></td>
        <td><span style="font-size:12px;color:var(--text-primary)">${p.vehicle_fitment}</span></td>
        <td style="font-weight:600;color:var(--text-primary)">${fmtMoney(p.price)}</td>
        <td><span class="status-badge ${badgeClass}">${badgeLabel}</span></td>
        <td>
          <div style="display:flex;gap:6px;">
            <button class="btn-secondary btn-sm" onclick="openInventoryModal('${p.sku}', ${p.stock})">Adjust</button>
            <button class="btn-secondary btn-sm" onclick="quickAddOrderFromSku('${p.sku}')">+ Order</button>
          </div>
        </td>
      </tr>
    `;
    })
    .join('');

  if (paginationInfo) {
    const totalPages = Math.ceil(State.productsCount / State.pageSize) || 1;
    paginationInfo.textContent = `Page ${State.currentPage} of ${totalPages} (${State.productsCount} total SKUs)`;
  }
}

window.openInventoryModal = function (sku, currentStock) {
  const modal = document.getElementById('inventory-modal');
  document.getElementById('inv-sku-display').textContent = sku;
  document.getElementById('inv-qty-input').value = currentStock;
  document.getElementById('inv-reason-input').value = 'Warehouse cycle count adjustment';
  modal.classList.add('active');
};

window.closeInventoryModal = function () {
  document.getElementById('inventory-modal').classList.remove('active');
};

window.submitInventoryUpdate = async function () {
  const sku = document.getElementById('inv-sku-display').textContent;
  const qty = parseInt(document.getElementById('inv-qty-input').value);
  const reason = document.getElementById('inv-reason-input').value;

  try {
    await api(`/inventory/${sku}/`, {
      method: 'PUT',
      body: JSON.stringify({ quantity: qty, reason: reason }),
    });
    closeInventoryModal();
    loadProducts();
    alert(`Inventory for ${sku} updated to ${qty} units.`);
  } catch (err) {
    alert(`Failed to update inventory: ${err.message}`);
  }
};

// --------------------------------------------------------------------------
// SECTION 3: Orders
// --------------------------------------------------------------------------
function setupOrders() {
  const createBtn = document.getElementById('btn-open-create-order');
  const addLineBtn = document.getElementById('btn-add-order-line');
  const statusFilter = document.getElementById('order-status-filter');

  if (createBtn) createBtn.addEventListener('click', () => openCreateOrderModal());
  if (addLineBtn) addLineBtn.addEventListener('click', () => addOrderLineItem());
  if (statusFilter) statusFilter.addEventListener('change', () => loadOrders());
}

async function loadOrders() {
  const status = document.getElementById('order-status-filter')?.value || '';
  let url = '/orders/?page_size=50';
  if (status) url += `&status=${status}`;

  try {
    const data = await api(url);
    State.orders = data.results || [];
    renderOrdersTable();
  } catch (err) {
    console.error('Orders error:', err);
  }
}

function renderOrdersTable() {
  const tbody = document.getElementById('orders-table-body');
  if (!tbody) return;

  if (State.orders.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:30px;color:var(--text-muted)">No orders found. Click "+ Create Draft Order" to start.</td></tr>`;
    return;
  }

  tbody.innerHTML = State.orders
    .map((o) => {
      const dealer = State.dealers.find((d) => d.id === o.dealer_id) || { name: 'Dealer #' + o.dealer_id, city: '' };
      return `
      <tr>
        <td><strong style="color:var(--text-primary);font-family:var(--font-mono)">${o.order_number}</strong></td>
        <td>
          <div style="font-weight:600;color:var(--text-primary)">${dealer.name}</div>
          <div style="font-size:11.5px;color:var(--text-secondary)">${dealer.city}</div>
        </td>
        <td><span class="status-badge status-${o.status}">${o.status}</span></td>
        <td>${fmtMoney(o.subtotal)}</td>
        <td style="color:var(--text-secondary)">${fmtMoney(o.tax_total)}</td>
        <td style="font-weight:600;color:var(--text-primary)">${fmtMoney(o.grand_total)}</td>
        <td>
          <div style="display:flex;gap:6px;">
            ${getOrderActionButtons(o)}
          </div>
        </td>
      </tr>
    `;
    })
    .join('');
}

function getOrderActionButtons(order) {
  let btns = `<button class="btn-secondary btn-sm" onclick="viewOrderDetails('${order.order_number}')">View</button>`;
  if (order.status === 'DRAFT') {
    btns += `<button class="btn-primary btn-sm" onclick="confirmOrder('${order.order_number}')">Confirm</button>`;
    btns += `<button class="btn-secondary btn-sm" style="color:var(--danger)" onclick="cancelOrder('${order.order_number}')">Cancel</button>`;
  } else if (order.status === 'CONFIRMED') {
    btns += `<button class="btn-secondary btn-sm" onclick="dispatchOrder('${order.order_number}')">Dispatch</button>`;
    btns += `<button class="btn-secondary btn-sm" style="color:var(--danger)" onclick="cancelOrder('${order.order_number}')">Cancel</button>`;
  } else if (order.status === 'DISPATCHED') {
    btns += `<button class="btn-secondary btn-sm" onclick="deliverOrder('${order.order_number}')">Deliver</button>`;
  }
  return btns;
}

window.confirmOrder = async function (orderNo) {
  if (!confirm(`Confirm order ${orderNo}? Stock will be atomically deducted.`)) return;
  try {
    await api(`/orders/${orderNo}/confirm/`, { method: 'POST' });
    loadOrders();
    alert(`Order ${orderNo} confirmed! Inventory reserved.`);
  } catch (err) {
    alert(`Confirmation failed: ${err.message}`);
  }
};

window.cancelOrder = async function (orderNo) {
  if (!confirm(`Cancel order ${orderNo}? Reserved stock will be restored.`)) return;
  try {
    await api(`/orders/${orderNo}/cancel/`, { method: 'POST' });
    loadOrders();
    alert(`Order ${orderNo} cancelled.`);
  } catch (err) {
    alert(`Cancellation failed: ${err.message}`);
  }
};

window.dispatchOrder = async function (orderNo) {
  try {
    await api(`/orders/${orderNo}/dispatch/`, { method: 'POST' });
    loadOrders();
  } catch (err) {
    alert(`Dispatch failed: ${err.message}`);
  }
};

window.deliverOrder = async function (orderNo) {
  try {
    await api(`/orders/${orderNo}/deliver/`, { method: 'POST' });
    loadOrders();
  } catch (err) {
    alert(`Delivery failed: ${err.message}`);
  }
};

window.viewOrderDetails = async function (orderNo) {
  try {
    const o = await api(`/orders/${orderNo}/`);
    const modal = document.getElementById('order-detail-modal');
    document.getElementById('detail-order-number').textContent = o.order_number;
    document.getElementById('detail-order-status').textContent = o.status;
    document.getElementById('detail-order-status').className = `status-badge status-${o.status}`;
    document.getElementById('detail-order-subtotal').textContent = fmtMoney(o.subtotal);
    document.getElementById('detail-order-tax').textContent = fmtMoney(o.tax_total);
    document.getElementById('detail-order-grand').textContent = fmtMoney(o.grand_total);

    const tbody = document.getElementById('detail-items-table-body');
    tbody.innerHTML = (o.items || [])
      .map(
        (it) => `
      <tr>
        <td><span class="sku-badge">${it.sku}</span></td>
        <td>${it.name}</td>
        <td>${it.quantity}</td>
        <td>${fmtMoney(it.unit_price)}</td>
        <td>${fmtMoney(it.line_subtotal)}</td>
        <td>${fmtMoney(it.line_tax)}</td>
        <td style="font-weight:600">${fmtMoney(it.line_total)}</td>
      </tr>
    `
      )
      .join('');

    modal.classList.add('active');
  } catch (err) {
    alert(`Failed to load order: ${err.message}`);
  }
};

window.closeOrderDetailModal = function () {
  document.getElementById('order-detail-modal').classList.remove('active');
};

// Order Creation Modal
window.openCreateOrderModal = function () {
  const select = document.getElementById('new-order-dealer-select');
  select.innerHTML = State.dealers
    .map(
      (d) =>
        `<option value="${d.id}" ${d.id === State.selectedDealerId ? 'selected' : ''}>
          ${d.name} (${d.dealer_code} • ${d.city})
        </option>`
    )
    .join('');

  const container = document.getElementById('order-lines-container');
  container.innerHTML = '';
  addOrderLineItem('BRK-1044', 2);
  document.getElementById('create-order-modal').classList.add('active');
};

window.closeCreateOrderModal = function () {
  document.getElementById('create-order-modal').classList.remove('active');
};

window.addOrderLineItem = function (sku = '', qty = 1) {
  const container = document.getElementById('order-lines-container');
  const div = document.createElement('div');
  div.className = 'order-line-item-row';
  div.style.cssText = 'display:flex;gap:8px;margin-bottom:8px;align-items:center;';
  div.innerHTML = `
    <input type="text" class="composer-input line-sku" placeholder="SKU (e.g. BRK-1044)" value="${sku}" style="flex:2;height:38px;" required>
    <input type="number" class="composer-input line-qty" placeholder="Quantity" value="${qty}" min="1" style="flex:1;height:38px;" required>
    <button type="button" class="btn-secondary btn-sm" onclick="this.closest('.order-line-item-row').remove()" style="color:var(--danger)">✕</button>
  `;
  container.appendChild(div);
};

window.submitNewOrder = async function () {
  const dealerId = parseInt(document.getElementById('new-order-dealer-select').value);
  const rows = document.querySelectorAll('.order-line-item-row');
  const items = [];

  rows.forEach((r) => {
    const sku = r.querySelector('.line-sku').value.trim();
    const qty = parseInt(r.querySelector('.line-qty').value);
    if (sku && qty > 0) items.push({ sku, quantity: qty });
  });

  if (items.length === 0) {
    alert('Please enter at least one line item with valid SKU and quantity.');
    return;
  }

  try {
    const res = await api('/orders/', {
      method: 'POST',
      body: JSON.stringify({ dealer_id: dealerId, items }),
    });
    closeCreateOrderModal();
    loadOrders();
    alert(`Draft order ${res.order_number} created successfully! Subtotal: ${fmtMoney(res.subtotal)}, GST 18%: ${fmtMoney(res.tax_total)}, Grand Total: ${fmtMoney(res.grand_total)}`);
  } catch (err) {
    alert(`Order creation failed: ${err.message}`);
  }
};

window.quickAddOrderFromSku = function (sku) {
  openCreateOrderModal();
  const container = document.getElementById('order-lines-container');
  container.innerHTML = '';
  addOrderLineItem(sku, 5);
};

// --------------------------------------------------------------------------
// SECTION 5: Demand Forecast
// --------------------------------------------------------------------------
function setupForecast() {
  const select = document.getElementById('forecast-sku-select');
  if (select) {
    select.addEventListener('change', (e) => {
      State.selectedForecastSku = e.target.value;
      loadSkuForecast(State.selectedForecastSku);
    });
  }
}

async function loadForecastView() {
  await loadReorderSuggestions();
  const select = document.getElementById('forecast-sku-select');
  if (select && select.options.length > 0) {
    State.selectedForecastSku = select.value;
    loadSkuForecast(State.selectedForecastSku);
  }
}

async function loadSkuForecast(sku) {
  try {
    const data = await api(`/forecast/${sku}/`);
    renderForecastCards(data.forecast || []);
  } catch (err) {
    console.error('Forecast detail error:', err);
  }
}

function renderForecastCards(weeks) {
  const container = document.getElementById('forecast-cards-container');
  if (!container) return;

  container.innerHTML = weeks
    .map(
      (w, idx) => `
    <div class="forecast-week-card">
      <div class="forecast-week-label">Week ${idx + 1} (${w.week_start})</div>
      <div class="forecast-week-units">${w.forecast_units}</div>
      <div style="font-size:11.5px;color:var(--text-secondary)">Predicted Units</div>
      ${idx === 2 ? `<div class="forecast-badge" style="margin-top:6px;">Diwali Peak</div>` : ''}
    </div>
  `
    )
    .join('');
}

// --------------------------------------------------------------------------
// SECTION 6: Reorder Suggestions
// --------------------------------------------------------------------------
async function loadReorderSuggestions() {
  try {
    const data = await api('/reorder-suggestions/');
    State.reorderItems = data.results || [];
    renderReorderTable(State.reorderItems);

    // Populate SKU select dropdown in Demand Forecast tab
    const select = document.getElementById('forecast-sku-select');
    if (select && select.options.length === 0) {
      select.innerHTML = State.reorderItems
        .map((r) => `<option value="${r.sku}">${r.sku} (Lead Time: ${r.lead_time_weeks}w)</option>`)
        .join('');
      if (State.reorderItems.length > 0) {
        State.selectedForecastSku = State.reorderItems[0].sku;
        loadSkuForecast(State.selectedForecastSku);
      }
    }
  } catch (err) {
    console.error('Reorder suggestions error:', err);
  }
}

function renderReorderTable(items) {
  const tbody = document.getElementById('reorder-table-body');
  if (!tbody) return;

  tbody.innerHTML = items
    .map((r) => {
      const needsReorder = r.reorder_qty > 0;
      return `
      <tr>
        <td><span class="sku-badge">${r.sku}</span></td>
        <td><span class="status-badge ${r.current_stock < r.reorder_point ? 'low-stock' : 'in-stock'}">${r.current_stock}</span></td>
        <td>${r.lead_time_weeks} weeks</td>
        <td>${r.lead_time_demand}</td>
        <td>${r.safety_stock}</td>
        <td><strong>${r.reorder_point}</strong></td>
        <td>
          <span style="font-weight:700;font-family:var(--font-mono);color:${needsReorder ? 'var(--danger)' : 'var(--success)'}">
            ${r.reorder_qty}
          </span>
        </td>
        <td>
          ${needsReorder ? `<span class="status-badge low-stock">Reorder Required</span>` : `<span class="status-badge in-stock">Stock Optimal</span>`}
        </td>
        <td>
          ${needsReorder ? `<button class="btn-primary btn-sm" onclick="quickReorderFromSku('${r.sku}', ${r.reorder_qty})">+ Draft Order</button>` : `<button class="btn-secondary btn-sm" onclick="quickReorderFromSku('${r.sku}', 10)">Draft</button>`}
        </td>
      </tr>
    `;
    })
    .join('');
}

window.quickReorderFromSku = function (sku, qty) {
  openCreateOrderModal();
  const container = document.getElementById('order-lines-container');
  container.innerHTML = '';
  addOrderLineItem(sku, Math.max(1, qty));
};

// --------------------------------------------------------------------------
// SECTION 7: Dealers Directory
// --------------------------------------------------------------------------
function renderDealersDirectory() {
  const container = document.getElementById('dealers-grid-container');
  if (!container) return;

  container.innerHTML = State.dealers
    .map((d) => {
      const isActive = d.id === State.selectedDealerId;
      return `
      <div class="card" style="margin-bottom:0;border-color:${isActive ? 'var(--primary)' : 'var(--border-light)'}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <span class="sku-badge">${d.dealer_code}</span>
          ${isActive ? `<span class="status-badge in-stock">Active Dealer</span>` : `<span style="font-size:12px;color:var(--text-secondary)">${d.city}</span>`}
        </div>
        <div style="font-family:var(--font-heading);font-size:15px;font-weight:600;color:var(--text-primary);margin-bottom:4px;">${d.name}</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">GSTIN: ${d.gstin || 'Unregistered'}</div>
        <div style="background:var(--bg-subtle);border:1px solid var(--border-light);border-radius:var(--radius-sm);padding:8px 12px;margin-bottom:12px;">
          <div style="font-size:11px;color:var(--text-secondary);font-weight:600;text-transform:uppercase;">Credit Limit</div>
          <div style="font-size:16px;font-weight:700;color:var(--text-primary);margin-top:2px;">${fmtMoney(d.credit_limit)}</div>
        </div>
        <button class="btn-secondary btn-sm" style="width:100%;justify-content:center;" onclick="setActiveDealerPersona(${d.id})">
          ${isActive ? 'Selected' : 'Select Active Dealer'}
        </button>
      </div>
    `;
    })
    .join('');
}

window.setActiveDealerPersona = function (id) {
  State.selectedDealerId = id;
  const select = document.getElementById('global-dealer-select');
  if (select) select.value = id;
  updateDealerContext();
  renderDealersDirectory();
};

// --------------------------------------------------------------------------
// SECTION 8: Supplier Sync Console
// --------------------------------------------------------------------------
function setupSync() {
  const syncBtn = document.getElementById('btn-run-supplier-sync');
  if (syncBtn) {
    syncBtn.addEventListener('click', () => runSupplierSync());
  }
}

async function runSupplierSync() {
  if (State.syncRunning) return;
  State.syncRunning = true;

  const btn = document.getElementById('btn-run-supplier-sync');
  const statusEl = document.getElementById('sync-status-indicator');
  btn.disabled = true;
  btn.textContent = 'Synchronizing...';
  if (statusEl) statusEl.textContent = 'Fetching supplier catalogue pages with rate-limit backoff…';

  try {
    const res = await api('/sync/supplier/', { method: 'POST' });
    document.getElementById('sync-stat-created').textContent = res.created;
    document.getElementById('sync-stat-updated').textContent = res.updated;
    document.getElementById('sync-stat-unchanged').textContent = res.unchanged;
    document.getElementById('sync-stat-rejected').textContent = (res.rejected || []).length;
    document.getElementById('sync-stat-pages').textContent = res.pages_fetched;
    document.getElementById('sync-stat-requests').textContent = res.requests_made;

    if (statusEl) {
      statusEl.textContent = `Sync completed: ${res.created} created, ${res.updated} updated, ${res.unchanged} unchanged across ${res.pages_fetched} pages.`;
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = `Sync failed: ${err.message}`;
  } finally {
    State.syncRunning = false;
    btn.disabled = false;
    btn.textContent = 'Run Supplier Sync';
  }
}
