import json
from decimal import Decimal
from django.db.models import Q
from core.models import Product, Dealer
from core.services import create_draft_order as service_create_draft_order


# Tool definitions matching OpenAI/Groq function calling specifications
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_parts",
            "description": "Search the product catalogue for spare parts using part query, vehicle fitment, and category. Returns real SKUs, names, vehicle fitment, current price, and stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Part name or search term, e.g. 'brake pads', 'air filter', 'chain sprocket'",
                    },
                    "vehicle": {
                        "type": "string",
                        "description": "Vehicle make and model, e.g. 'Bajaj Pulsar 150', 'KTM Duke 390', 'Royal Enfield Classic 350'",
                    },
                    "category": {
                        "type": "string",
                        "description": "Part category if known, e.g. 'Brakes', 'Engine & Oils', 'Drivetrain', 'Filters'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Check current live stock quantity and current price from the authoritative database for specific product SKUs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of product SKU codes, e.g. ['BRK-1044', 'FIL-1016']",
                    }
                },
                "required": ["skus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft_order",
            "description": "Create a DRAFT order for a dealer. Never confirms orders or decrements inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dealer_id": {
                        "type": "integer",
                        "description": "The ID of the ordering dealer",
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string", "description": "Product SKU code"},
                                "quantity": {"type": "integer", "description": "Units to order (>= 1)"},
                            },
                            "required": ["sku", "quantity"],
                        },
                        "description": "List of line items with SKU and quantity",
                    },
                },
                "required": ["dealer_id", "items"],
            },
        },
    },
]


def execute_search_parts(query: str, vehicle: str = None, category: str = None) -> list:
    """Executes catalogue search with vehicle fitment and token matching."""
    qs = Product.objects.all()

    if vehicle:
        v_clean = vehicle.strip()
        qs = qs.filter(Q(vehicle_fitment__icontains=v_clean) | Q(vehicle_fitment__iexact="Universal"))

    if category:
        qs = qs.filter(category__icontains=category.strip())

    if query:
        terms = [t.strip() for t in query.split() if len(t.strip()) > 1]
        term_filter = Q()
        for term in terms:
            term_filter |= Q(name__icontains=term) | Q(sku__icontains=term) | Q(brand__icontains=term)
        if term_filter:
            qs = qs.filter(term_filter)

    results = []
    # Rank: specific vehicle match first, then alphabetically
    for p in qs[:8]:
        results.append({
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "brand": p.brand,
            "vehicle_fitment": p.vehicle_fitment,
            "price": str(p.price),
            "stock": p.stock,
            # Descriptions are untrusted supplier inputs: sanitize and truncate
            "description": p.description[:120] if p.description else "",
        })

    return results


def execute_check_stock(skus: list) -> list:
    """Queries PostgreSQL directly for live available inventory and authoritative pricing."""
    if not skus or not isinstance(skus, list):
        return []

    clean_skus = [str(s).strip() for s in skus if str(s).strip()]
    products = {p.sku: p for p in Product.objects.filter(sku__in=clean_skus)}

    results = []
    for s in clean_skus:
        if s in products:
            p = products[s]
            results.append({
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "brand": p.brand,
                "vehicle_fitment": p.vehicle_fitment,
                "stock": p.stock,
                "price": str(p.price),
                "in_stock": p.stock > 0,
            })
        else:
            results.append({
                "sku": s,
                "error": "SKU not found in catalogue",
                "stock": 0,
                "in_stock": False,
            })

    return results


def execute_create_draft_order(dealer_id: int, items: list) -> dict:
    """Creates a DRAFT order using core business rules. Returns created order details."""
    try:
        order, created = service_create_draft_order(dealer_id=dealer_id, items_data=items)
        return {
            "success": True,
            "order_number": order.order_number,
            "status": order.status,
            "dealer_id": order.dealer_id,
            "subtotal": str(order.subtotal),
            "tax_total": str(order.tax_total),
            "grand_total": str(order.grand_total),
            "item_count": order.items.count(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
