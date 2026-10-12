# VIKMO DealerDesk — AI/ML Intern Track

VIKMO DealerDesk is an AI-native distribution management platform for motorcycle and automotive parts distributors in South India. It provides a robust, contract-compliant backend with live inventory management, draft-order workflows, an intelligent GenAI parts assistant with tool calling and prompt injection defenses, and a validated demand forecasting engine that powers live reorder suggestions.

**Selected Track:** `aiml` (AI / ML Intern)  
**Walkthrough Video (5-minute demonstration):** [https://youtu.be/placeholder-video-url](https://youtu.be/placeholder-video-url)

---

## 1. Business Problem & Solution

Automotive spare parts distributors face four core operational challenges:
1. **Overselling & Pricing Inaccuracies:** Manual orders risk overselling scarce stock, and rounding discrepancies in 18% GST cause reconciliation delays. DealerDesk solves this with atomic database transactions, strict status flows, and line-level `ROUND_HALF_UP` paise calculations.
2. **Stale Supplier Catalogues:** Third-party supplier catalogues drift over time. DealerDesk incorporates a resilient, rate-limit-aware supplier synchronization engine (Bonus Part B).
3. **High Support Overhead:** Dealers frequently inquire about part fitments, stock, and draft orders. DealerDesk deploys an LLM Dealer Assistant with genuine tool calling grounded strictly in live PostgreSQL inventory.
4. **Demand Guesswork:** Stocking swings unpredictably around promotions and shifting festive dates (Diwali). DealerDesk features a machine-learning demand forecasting model (`HistGradientBoostingRegressor`) delivering a **20.64% WAPE** (outperforming baselines by >6%) and automated safety-stock calculations.

---

## 2. Technology Stack

- **Backend Framework:** Python 3.11+, Django 5.2, Django REST Framework 3.18
- **Relational Database:** PostgreSQL (strictly enforced, SQLite disabled)
- **Database Driver:** `psycopg[binary]` 3.3, `dj-database-url` 3.1
- **LLM Provider & Model:** **Groq** using `llama-3.3-70b-versatile` (with multi-provider fallback support for Google Gemini and OpenAI)
- **Machine Learning & Forecasting:** `scikit-learn` 1.8, `pandas` 3.0, `numpy` 2.4, `scipy` 1.17
- **Testing:** Django Test Suite, `requests`, `smoke_test.py`

---

## 3. Architecture & Data Flow

```
                           +------------------------+
                           |  Dealer / API Client   |
                           +------------------------+
                                       |
                   +-------------------+-------------------+
                   |                   |                   |
         +-----------------+   +----------------+  +------------------+
         | REST API Core   |   | GenAI Assistant|  | ML Reorder Engine|
         | Products/Orders |   | Tool Calling   |  | Safety Stock     |
         +-----------------+   +----------------+  +------------------+
                   |                   |                   |
                   |           +---------------+           |
                   |           |  Groq LLM     |           |
                   |           |  llama-3.3-70b|           |
                   |           +---------------+           |
                   |                   |                   |
                   +-------------------+-------------------+
                                       |
                           +------------------------+
                           | PostgreSQL Database    |
                           | Products, Orders,      |
                           | Dealers, Sessions      |
                           +------------------------+
```

---

## 4. Database Models & Schema

The schema is defined in [core/models.py](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/core/models.py):

- **`Product`:** Authoritative catalogue items (`sku` PK, `name`, `category`, `brand`, `vehicle_fitment`, `price` Decimal, `stock` Integer, `description` TextField).
- **`Dealer`:** Distributor dealer accounts (`id` PK, `dealer_code` unique, `name`, `city`, `phone`, `email`, `gstin`, `credit_limit` Decimal).
- **`Order`:** Aggregate order header (`order_number` PK `ORD-YYYYMMDD-NNNN`, `dealer` FK with `on_delete=PROTECT`, `status` DRAFT/CONFIRMED/DISPATCHED/DELIVERED/CANCELLED, `subtotal`, `tax_total`, `grand_total`, `idempotency_key`).
- **`OrderItem`:** Line items (`order` FK CASCADE, `product` FK PROTECT, `sku`, `name`, `quantity`, `unit_price`, `line_subtotal`, `line_tax`, `line_total`).
- **`DailyOrderSequence`:** Thread-safe PostgreSQL row-locked daily counter.
- **`ConversationMessage`:** Isolated session history for the AI Dealer Assistant (`session_id`, `role`, `content`, `tool_calls`).

Refer to [DECISIONS.md](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/DECISIONS.md#1-schema-design-relationships-and-on_delete-rationale) for the detailed explanation and justification of each foreign-key `on_delete` rule.

---

## 5. Setup & Running Instructions

### 5.1 Prerequisites
- Python 3.11 or newer
- PostgreSQL database running locally or hosted (e.g. Neon, Supabase, Docker)

### 5.2 Environment Configuration
Copy `.env.example` to `.env` and configure your credentials:

```bash
cp .env.example .env
```

Set the following variables in `.env`:
```ini
DATABASE_URL=postgres://postgres:postgres@localhost:5432/dealerdesk
SUPPLIER_API_URL=http://127.0.0.1:8099
SUPPLIER_API_KEY=dev-supplier-key
DJANGO_SECRET_KEY=your-secret-key-here
GROQ_API_KEY=your-groq-api-key-here
```

### 5.3 Installation & Seeding (Run Contract)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run migrations
python manage.py migrate --noinput

# 3. Seed database (idempotent: safe to run repeatedly)
python manage.py seed_data
python manage.py seed_data

# 4. Start the application
python manage.py runserver 0.0.0.0:8000 --noreload
```

---

## 6. API Endpoint Overview

All endpoints strictly follow [API_CONTRACT.md](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/API_CONTRACT.md) with exact JSON error shapes (`{"error": {"code": "...", "message": "...", "details": []}}`).

| Endpoint | Method | Description |
|---|---|---|
| `/api/health/` | `GET` | System health check (`{"status": "ok"}`) |
| `/api/products/` | `GET`, `POST` | List catalogue (paginated, filters: `search`, `category`, `vehicle`) or create product |
| `/api/products/{sku}/` | `GET`, `PATCH` | Retrieve product details or update catalogue fields |
| `/api/inventory/{sku}/` | `PUT` | Update available warehouse inventory |
| `/api/dealers/` | `GET`, `POST` | List dealers or register new dealer |
| `/api/dealers/{id}/` | `GET` | Retrieve dealer details |
| `/api/orders/` | `GET`, `POST` | List orders or create DRAFT order with GST calculation & idempotency |
| `/api/orders/{order_number}/` | `GET`, `PUT` | Retrieve order or replace items while in DRAFT status |
| `/api/orders/{order_number}/confirm/` | `POST` | Confirm order with atomic stock validation & deduction |
| `/api/orders/{order_number}/cancel/` | `POST` | Cancel order and restore stock (if confirmed) |
| `/api/orders/{order_number}/dispatch/` | `POST` | Mark order as dispatched |
| `/api/orders/{order_number}/deliver/` | `POST` | Mark order as delivered |
| `/api/assistant/chat/` | `POST` | AI Dealer Assistant multi-turn chat with tool calling |
| `/api/forecast/{sku}/` | `GET` | Retrieve 4-week demand predictions for target SKU |
| `/api/reorder-suggestions/` | `GET` | 40-SKU reorder recommendations using live inventory and lead times |
| `/api/sync/supplier/` | `POST` | Bonus Part B: Full supplier catalogue synchronization with retries |

---

## 7. AI Dealer Assistant

- **Provider:** Groq
- **Model:** `llama-3.3-70b-versatile`
- **Supported Tools:**
  1. `search_parts(query, vehicle, category)`: Fast hybrid catalogue search with fitment constraints.
  2. `check_stock(skus)`: Authoritative PostgreSQL lookup for live inventory and current price.
  3. `create_draft_order(dealer_id, items)`: Executes draft order creation via core services; never confirms orders or decrements inventory.
- **Safety & Injection Defense:** Supplier descriptions are untrusted external inputs. Descriptions are regex-sanitized to strip prompt-override tokens, strictly scoped inside data payload fences, and guarded by explicit system prompt constraints.
- **Ambiguity Clarification:** If a vehicle model is unspecified, the assistant prompts for make and model before citing parts or drafting an order.

---

## 8. Demand Forecasting & Reorder Engine

- **Target Forecast Horizon:** 4 weekly periods (2026-09-28, 2026-10-05, 2026-10-12, 2026-10-19) for the 40 target SKUs.
- **Forecast Output:** Committed to `ml/forecast.csv` (160 rows, columns: `sku,week_start,forecast_units`).
- **Validation Results (Rolling-Origin Backtest across 4 Folds):**
  - Seasonal Naive (52-week lag): WAPE 33.88%
  - Naive (Last Observed): WAPE 28.86%
  - Recent Average (SMA-4): WAPE 26.79%
  - **HistGradientBoostingRegressor (Selected):** **WAPE 20.64%**, MAE 7.15, RMSE 10.65
- **Reorder Formula Compliance:**
  - $L$ = `lead_time_weeks` from `data/lead_times.csv`
  - $\text{lead\_time\_demand} = \sum_{w=1}^L \text{forecast\_units}_w$
  - $\sigma$ = sample standard deviation ($n-1$) of `units_sold` over most recent 12 weeks of `sales_history.csv`
  - $\text{safety\_stock} = \lceil 1.65 \times \sigma \times \sqrt{L} \rceil$
  - $\text{reorder\_point} = \text{lead\_time\_demand} + \text{safety\_stock}$
  - $\text{reorder\_qty} = \max(0, \lceil \text{reorder\_point} - \text{current\_stock} \rceil)$
  - `current_stock` is queried live from PostgreSQL at runtime.

---

## 9. Testing & Verification

### 9.1 Running Django Automated Tests
```bash
python manage.py test core
```
*Output: 18 tests passing with 0 errors across backend core, assistant, forecasting, and supplier sync.*

### 9.2 Running the Smoke Test
```bash
python smoke_test.py --base-url http://localhost:8000 --track aiml
```
*Output: 10/10 checks passed on a freshly seeded database.*

---

## 10. Assumptions & Limitations

1. **Groq API Rate Limits:** In high-concurrency environments, Groq free-tier limits apply. The orchestrator includes a deterministic rule-based fallback ensuring zero downtime during testing.
2. **Historical Cutoff:** Sales data is strictly bounded to $\le \text{2026-09-21}$; no actual future demand data is observed or leaked during training.
