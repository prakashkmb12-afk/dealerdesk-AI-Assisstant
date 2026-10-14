# DealerDesk — Distribution, Inventory & AI Ordering Platform

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Groq](https://img.shields.io/badge/Groq-Llama%203.3%20%7C%20Qwen-F55036)](https://groq.com/)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-1.8-F7931E?logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![Contract Test](https://img.shields.io/badge/Smoke%20Test-10%2F10%20Passed-22C55E)]()

**DealerDesk** is an enterprise-grade distribution management and automated ordering platform engineered for automotive and motorcycle spare parts distributors in South India. It provides a contract-compliant REST backend, live inventory tracking, draft-order lifecycles with exact 18% GST calculation, a grounded GenAI parts assistant with tool calling and security guardrails, an ML demand forecasting engine, and a professional white B2B single-page application.

---

### Key Information

| Attribute | Specification |
|---|---|
| **Candidate Track** | `aiml` (AI / ML Intern) |
| **Walkthrough Video** | [https://youtu.be/placeholder-video-url](https://drive.google.com/file/d/1lsFdHalIxYK213LeahWCJgoJr4jDGP_G/view?usp=sharing) |
| **Architecture Document** | [DECISIONS.md](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/DECISIONS.md) |
| **Contract Specifications** | [API_CONTRACT.md](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/API_CONTRACT.md) |
| **Primary Interface** | `http://localhost:8000/` |
| **REST API Base** | `http://localhost:8000/api/` |

---

## Table of Contents

1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [Core Platform Capabilities](#2-core-platform-capabilities)
3. [Technology Stack](#3-technology-stack)
4. [System Architecture](#4-system-architecture)
5. [Database Schema & Integrity](#5-database-schema--integrity)
6. [Quickstart & Installation](#6-quickstart--installation)
7. [API Reference & Endpoint Contracts](#7-api-reference--endpoint-contracts)
8. [AI Dealer Assistant Architecture](#8-ai-dealer-assistant-architecture)
9. [Demand Forecasting & Reorder Engine](#9-demand-forecasting--reorder-engine)
10. [Supplier Catalogue Synchronization](#10-supplier-catalogue-synchronization)
11. [Testing & Verification](#11-testing--verification)
12. [Architectural Decisions & FAQs](#12-architectural-decisions--faqs)

---

## 1. Executive Summary & Problem Statement

South Indian automotive parts distributors handle thousands of daily transactions across regional dealerships while facing four critical operational friction points:

1. **Overselling & Pricing Rounding Discrepancies:** Manual orders risk overselling scarce warehouse inventory during concurrent requests. Floating-point rounding inaccuracies in 18% GST cause reconciliation disputes with auditors. DealerDesk resolves this using PostgreSQL row-level locks (`select_for_update()`), atomic state machines, and Python `Decimal` with line-level `ROUND_HALF_UP` precision.
2. **Stale Supplier Catalogues:** Third-party vendor catalogues update continuously. Manual synchronization leads to stale prices and missing parts. DealerDesk incorporates a rate-limit-aware synchronization engine with cursor pagination, exponential backoff, and transactional batch commits.
3. **High Dealership Support Overhead:** Dealerships spend hours inquiring about vehicle fitments, availability, and draft holds. DealerDesk deploys a conversational AI Parts Assistant with multi-turn tool calling strictly grounded in live PostgreSQL data.
4. **Demand Guesswork & Stockouts:** Stocking swings unpredictably around regional promotions and festive periods (e.g. Diwali). DealerDesk features a `HistGradientBoostingRegressor` delivering **20.64% WAPE** across rolling-origin backtests, driving real-time safety stock and reorder point calculations.

---

## 2. Core Platform Capabilities

- **Overview Dashboard:** Live KPI cards for total catalogue products (600), active orders, registered dealers (25), and model validation accuracy, coupled with recent orders and low-stock alerts.
- **Catalogue & Inventory Management:** 600 SKUs searchable by part number, vehicle model, category, and brand, with real-time on-hand stock adjustments (`PUT /api/inventory/{sku}/`).
- **Orders Desk & Lifecycle Stepper:** DRAFT order creation with automatic 18% GST calculation, followed by atomic state transitions (`CONFIRMED` with stock deduction, `CANCELLED` with inventory restoration, `DISPATCHED`, `DELIVERED`).
- **AI Parts Assistant:** Grounded conversational agent with active-dealer persona persistence, dynamic task-oriented loading states, and direct draft order creation without requesting redundant dealer IDs.
- **Demand Forecasting:** 4-week forward prediction cards for 40 monitored SKUs with festive peak flags.
- **Reorder Radar:** Automated safety-stock and reorder quantity suggestions ($1.65 \times \sigma \times \sqrt{L}$) with one-click draft order drafting.
- **Dealers Directory:** Centralized directory for 25 South Indian dealers with credit limit tracking and active-persona switching.
- **Supplier Sync Console:** Live external synchronization monitoring with telemetry tracking for created, updated, unchanged, and rejected products.

---

## 3. Technology Stack

| Layer | Component | Version | Role |
|---|---|---|---|
| **Backend Framework** | Django | 5.2 | Web framework, ORM, migrations, static/template serving |
| **API Framework** | Django REST Framework | 3.18 | Serializers, exception handlers, REST views |
| **Database** | PostgreSQL | 16+ | Authoritative relational data store, row-level locking |
| **DB Driver & URL Parser** | `psycopg` & `dj-database-url` | 3.3 / 3.1 | Asynchronous/binary connection driver, resilient URI parser |
| **LLM Provider** | Groq API | — | Multi-turn tool calling via `llama-3.3-70b-versatile` / `qwen/qwen3.8-27b` |
| **Machine Learning** | `scikit-learn` | 1.8 | `HistGradientBoostingRegressor` demand forecasting |
| **Data Processing** | `pandas`, `numpy`, `scipy` | 3.0 / 2.4 / 1.17 | Lag features, rolling statistics, WAPE evaluation |
| **Frontend** | Vanilla JS, HTML5, CSS3 | — | Clean white B2B single-page application (zero build step) |
| **Testing** | Django Test Runner, `requests` | — | Unit tests, integration tests, contract smoke tests |

---

## 4. System Architecture

```
                                  +---------------------------+
                                  |   Dealer / Browser User   |
                                  |   http://localhost:8000/  |
                                  +---------------------------+
                                                |
                                      [HTTP REST / JSON]
                                                v
                     +-----------------------------------------------------+
                     |             Django Application Server               |
                     |             (Port 8000 / Development)               |
                     +-----------------------------------------------------+
                                 |              |              |
         +-----------------------+              |              +-----------------------+
         |                                      |                                      |
         v                                      v                                      v
+------------------+                 +----------------------+               +---------------------+
| REST API Engine  |                 | AI Assistant Service |               | ML Forecasting &    |
| • Products & Stock|                | • Groq Tool Calling  |               | Reorder Engine      |
| • Order Lifecycle|                 | • Fitment Grounding  |               | • 4-Week Horizon    |
| • 18% GST Logic  |                 | • Active Dealer Scope|               | • Safety Stock      |
+------------------+                 +----------------------+               +---------------------+
         |                                      |                                      |
         |         +----------------------------+                                      |
         |         | (Calls internal search/stock/order tools)                         |
         v         v                                                                   v
+-------------------------------------------------------------------------------------------------+
|                                   PostgreSQL Relational Database                                |
|   • Products (600)   • Dealers (25)   • Orders & Items   • Sequences   • Chat Transcripts       |
+-------------------------------------------------------------------------------------------------+
```

---

## 5. Database Schema & Integrity

Defined in [core/models.py](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/core/models.py):

- **`Product`:** Primary key `sku` (`CharField`), indexed by `category`, `brand`, and `vehicle_fitment`. Monetary fields use `DecimalField(max_digits=10, decimal_places=2)`.
- **`Dealer`:** Primary key `id` with unique `dealer_code`. Stores city, phone, email, GSTIN, and credit limit.
- **`Order`:** Aggregate header formatted as `ORD-YYYYMMDD-NNNN`. Foreign key to `Dealer` uses `on_delete=models.PROTECT` to safeguard audit integrity. Tracks idempotency keys to prevent duplicate order submissions.
- **`OrderItem`:** Line items with composite uniqueness (`order`, `sku`). Foreign key to `Order` uses `on_delete=models.CASCADE`, while foreign key to `Product` uses `on_delete=models.PROTECT`.
- **`DailyOrderSequence`:** Thread-safe daily counter locked using PostgreSQL `select_for_update()` to guarantee collision-free sequential order numbers.
- **`ConversationMessage`:** Multi-turn session history for the AI Dealer Assistant linked to sessions and optional dealers (`on_delete=models.SET_NULL`).

Refer to [DECISIONS.md §1](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/DECISIONS.md#1-schema-design-relationships-and-on_delete-rationale) for the mathematical and referential justifications.

---

## 6. Quickstart & Installation

### 6.1 Prerequisites

- Python 3.11 or higher
- PostgreSQL running locally or hosted (e.g., Neon, Supabase, Docker)

### 6.2 Environment Configuration

Create a `.env` file at the root of the repository (refer to `.env.example`):

```ini
DATABASE_URL=postgres://postgres:password@localhost:5432/dealerdesk
SUPPLIER_API_URL=http://127.0.0.1:8099
SUPPLIER_API_KEY=dev-supplier-key
DJANGO_SECRET_KEY=your-production-secret-key-here
GROQ_API_KEY=your-groq-api-key-here
```

> [!NOTE]
> Special characters like `#` in database passwords are automatically handled by the database configuration in `dealerdesk/settings.py`.

### 6.3 Run Contract Execution

The application strictly satisfies the evaluation run contract:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run migrations
python manage.py migrate --noinput

# 3. Seed catalogue and dealer data (idempotent: runs twice without duplicate errors)
python manage.py seed_data
python manage.py seed_data

# 4. Start the application
python manage.py runserver 0.0.0.0:8000 --noreload
```

Open [http://localhost:8000/](http://localhost:8000/) in your browser to access the DealerDesk interface.

---

## 7. API Reference & Endpoint Contracts

All endpoints return JSON and strictly adhere to [API_CONTRACT.md](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/API_CONTRACT.md) with standardized error envelopes:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable explanation",
    "details": []
  }
}
```

| Path | Method | Description | Error Codes |
|---|---|---|---|
| `/api/health/` | `GET` | Health check (`{"status": "ok"}`) | — |
| `/api/products/` | `GET`, `POST` | List catalogue (paginated, search, category) or add SKU | `VALIDATION_ERROR`, `CONFLICT` |
| `/api/products/{sku}/` | `GET`, `PATCH` | Retrieve or update product catalogue details | `NOT_FOUND` |
| `/api/inventory/{sku}/` | `PUT` | Adjust warehouse on-hand stock count | `NOT_FOUND`, `VALIDATION_ERROR` |
| `/api/dealers/` | `GET`, `POST` | List dealers or register new dealership account | `VALIDATION_ERROR`, `CONFLICT` |
| `/api/dealers/{id}/` | `GET` | Retrieve dealer account details | `NOT_FOUND` |
| `/api/orders/` | `GET`, `POST` | List orders or create DRAFT order with 18% GST calculation | `VALIDATION_ERROR`, `IDEMPOTENCY_CONFLICT` |
| `/api/orders/{order_number}/` | `GET`, `PUT` | Retrieve order breakdown or edit line items while in DRAFT | `NOT_FOUND`, `INVALID_TRANSITION` |
| `/api/orders/{order_number}/confirm/` | `POST` | Atomically reserve stock and confirm order | `INSUFFICIENT_STOCK`, `INVALID_TRANSITION` |
| `/api/orders/{order_number}/cancel/` | `POST` | Cancel order and restore reserved stock | `INVALID_TRANSITION` |
| `/api/orders/{order_number}/dispatch/` | `POST` | Mark confirmed order as dispatched | `INVALID_TRANSITION` |
| `/api/orders/{order_number}/deliver/` | `POST` | Mark dispatched order as delivered | `INVALID_TRANSITION` |
| `/api/assistant/chat/` | `POST` | Multi-turn AI Assistant chat with tool execution | `VALIDATION_ERROR` |
| `/api/forecast/{sku}/` | `GET` | Retrieve 4-week demand prediction for target SKU | `NOT_FOUND` |
| `/api/reorder-suggestions/` | `GET` | 40-SKU live reorder recommendations | — |
| `/api/sync/supplier/` | `POST` | Supplier catalogue sync with retry backoff | `BAD_GATEWAY` |

---

## 8. AI Dealer Assistant Architecture

- **LLM Provider:** Groq
- **Primary Model:** `llama-3.3-70b-versatile` (with dynamic discovery falling back to `qwen/qwen3.8-27b` or `openai/gpt-oss-120b`).
- **Grounded Tool Specifications:**
  1. `search_parts(query, vehicle, category)`: Fast hybrid catalogue search with fitment constraints.
  2. `check_stock(skus)`: Authoritative PostgreSQL lookup for live inventory and current price.
  3. `create_draft_order(dealer_id, items)`: Executes draft order creation via core services; never confirms orders or decrements inventory.
- **Active Dealer Scope:** Automatically binds the active dealership persona into the system prompt, allowing the agent to create draft orders without asking the user for their dealer ID.
- **Prompt Injection & Untrusted Data Defense:** Supplier descriptions are untrusted external inputs. Descriptions are regex-sanitized to strip prompt-override tokens, strictly scoped inside data payload fences, and guarded by explicit system prompt constraints.
- **Ambiguity Clarification:** If a vehicle model is unspecified for vehicle-specific parts, the assistant prompts for make and model before citing parts or drafting an order.

---

## 9. Demand Forecasting & Reorder Engine

### 9.1 Forecast Methodology & Validation

- **Target Horizon:** 4 weekly periods (`2026-09-28`, `2026-10-05`, `2026-10-12`, `2026-10-19`) for 40 target SKUs.
- **Output Artifact:** [ml/forecast.csv](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/ml/forecast.csv) (160 rows, schema: `sku,week_start,forecast_units`).
- **Model:** `HistGradientBoostingRegressor` evaluated with a 4-fold rolling-origin backtest:

| Model Strategy | WAPE (%) | MAE | RMSE | Status |
|---|---|---|---|---|
| Seasonal Naive (52-week lag) | 33.88% | 11.24 | 16.82 | Baseline |
| Naive (Last Observed) | 28.86% | 9.94 | 14.51 | Baseline |
| Recent Average (SMA-4) | 26.79% | 9.18 | 13.72 | Baseline |
| **HistGradientBoostingRegressor** | **20.64%** | **7.15** | **10.65** | **Selected Model** |

- **Leakage Prevention:** Training features strictly filter out all sales data beyond $\le \text{2026-09-21}$.

### 9.2 Reorder Formula Compliance

- $L = \text{lead\_time\_weeks}$ from `data/lead_times.csv`
- $\text{lead\_time\_demand} = \sum_{w=1}^L \text{forecast\_units}_w$
- $\sigma = \text{sample standard deviation } (n-1) \text{ of units sold over the last 12 weeks}$
- $\text{safety\_stock} = \lceil 1.65 \times \sigma \times \sqrt{L} \rceil$
- $\text{reorder\_point} = \text{lead\_time\_demand} + \text{safety\_stock}$
- $\text{reorder\_qty} = \max(0, \lceil \text{reorder\_point} - \text{current\_stock} \rceil)$

---

## 10. Supplier Catalogue Synchronization

Bonus Part B implements a resilient supplier catalogue synchronization service ([core/supplier_sync.py](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/core/supplier_sync.py)):

- **Cursor Pagination:** Traverses supplier catalogue pages using `cursor` tokens until exhaustion.
- **Rate Limit Handling:** Reads `Retry-After` headers on HTTP `429` responses and sleeps exponentially.
- **Transient Failure Recovery:** Retries transient `5xx` errors up to 3 times with exponential backoff.
- **Zero-Leakage Atomic Commit:** If any page permanently fails (e.g. HTTP 503 outage), the entire synchronization transaction rolls back, leaving PostgreSQL catalogue stock and prices unchanged.
- **Change Detection:** Classifies incoming supplier records into `created`, `updated`, `unchanged`, and `rejected` (for malformed monetary inputs or missing attributes).

---

## 11. Testing & Verification

### 11.1 Django Automated Test Suite

```bash
python manage.py test core
```
*Output: 18 tests passing with 0 errors across backend core, assistant, forecasting, and supplier sync.*

### 11.2 Contract Smoke Test

```bash
# 1. Start application server
python manage.py runserver 0.0.0.0:8000 --noreload

# 2. Run smoke test on a clean database
python smoke_test.py --base-url http://localhost:8000 --track aiml
```
*Output: 10/10 checks passed.*

```bash
# Optional: Run full check including supplier sync and order lifecycle
python smoke_test.py --base-url http://localhost:8000 --all
```
*Output: 12/12 checks passed.*

---

## 12. Architectural Decisions & FAQs

Detailed technical rationales answering all track evaluation questions are committed in [DECISIONS.md](file:///c:/Users/Balaji/Downloads/VIKMO%20DealerDesk%20Assignment/DECISIONS.md):

1. **Schema Design & `on_delete` Rationale:** Justification for `models.PROTECT` on `Order.dealer` and `OrderItem.product` vs `models.CASCADE` on `OrderItem.order`.
2. **Hybrid Retrieval Strategy:** Token-based inverted indexing + exact SKU resolution + vehicle fitment substring matching over dense embeddings.
3. **Tool-Calling Sequence:** Step-by-step walkthrough of `POST /api/assistant/chat/` through Groq function calling into database transactions.
4. **Authoritative Grounding:** Strict separation preventing the model from hallucinating unverified inventory or prices.
5. **Untrusted Input Protection:** Defenses against prompt injection inside supplier product descriptions.
6. **Forecast Backtesting:** Rolling-origin cross-validation methodology and leakage boundaries.
7. **Edge Cases in Demand:** Croston intermittent demand modeling, recency weighting for new SKUs, and Diwali festive multipliers.
8. **Weakest Part & Future Enhancements:** Plan for semantic cross-encoders and fine-tuned embeddings.
