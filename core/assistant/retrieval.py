import re
from django.db.models import Q
from core.models import Product


def sanitize_untrusted_text(text: str) -> str:
    """Sanitizes untrusted supplier description text to neutralize prompt injection tokens."""
    if not text:
        return ""
    # Strip potential prompt injection markers, instruction overrides, and delimiters
    cleaned = re.sub(r"(ignore\s+(all\s+)?previous\s+instructions|system\s+prompt|system:|developer:|<system>)", "[FILTERED]", text, flags=re.IGNORECASE)
    return cleaned[:150]


def retrieve_relevant_catalogue_items(query: str, vehicle: str = None, limit: int = 5) -> list:
    """Hybrid retrieval combining fitment constraints and token ranking."""
    qs = Product.objects.all()

    # Exact SKU search
    sku_match = re.search(r"\b[A-Z]{3}-\d{4}\b", query.upper())
    if sku_match:
        sku = sku_match.group(0)
        direct_prod = Product.objects.filter(sku=sku).first()
        if direct_prod:
            return [{
                "sku": direct_prod.sku,
                "name": direct_prod.name,
                "category": direct_prod.category,
                "brand": direct_prod.brand,
                "vehicle_fitment": direct_prod.vehicle_fitment,
                "price": str(direct_prod.price),
                "stock": direct_prod.stock,
                "description": sanitize_untrusted_text(direct_prod.description),
            }]

    if vehicle:
        v_clean = vehicle.strip()
        qs = qs.filter(Q(vehicle_fitment__icontains=v_clean) | Q(vehicle_fitment__iexact="Universal"))

    # Extract query terms
    terms = [w.strip() for w in re.findall(r"\w+", query) if len(w.strip()) > 2]
    filter_q = Q()
    for term in terms:
        filter_q |= Q(name__icontains=term) | Q(brand__icontains=term) | Q(category__icontains=term)

    if filter_q:
        qs = qs.filter(filter_q)

    results = []
    for p in qs[:limit]:
        results.append({
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "brand": p.brand,
            "vehicle_fitment": p.vehicle_fitment,
            "price": str(p.price),
            "stock": p.stock,
            "description": sanitize_untrusted_text(p.description),
        })

    return results
