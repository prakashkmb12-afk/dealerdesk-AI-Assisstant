import time
import logging
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db import transaction
import requests
from core.models import Product
from core.exceptions import ContractAPIException

logger = logging.getLogger(__name__)


def sync_supplier_catalogue() -> dict:
    """Pulls supplier catalogue reliably with pagination, retry backoff, and atomic DB updates."""
    supplier_url = getattr(settings, "SUPPLIER_API_URL", "http://127.0.0.1:8099").rstrip("/")
    api_key = getattr(settings, "SUPPLIER_API_KEY", "")

    headers = {"X-Api-Key": api_key}
    cursor = None
    all_items = []
    rejected = []
    pages_fetched = 0
    requests_made = 0

    # 1. Fetch all pages with retry logic
    while True:
        url = f"{supplier_url}/v1/products"
        params = {"limit": 20}
        if cursor:
            params["cursor"] = cursor

        attempts = 0
        success = False
        data = None

        while attempts < 5:
            attempts += 1
            requests_made += 1
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    pages_fetched += 1
                    success = True
                    break
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2))
                    time.sleep(retry_after)
                elif resp.status_code in (401, 403):
                    raise ContractAPIException(
                        code="SUPPLIER_UNAVAILABLE",
                        message="Supplier rejected authentication credentials.",
                        status_code=502,
                    )
                elif resp.status_code >= 500:
                    time.sleep(1.0 * attempts)
                else:
                    time.sleep(1.0 * attempts)
            except requests.RequestException:
                time.sleep(1.0 * attempts)

        if not success:
            raise ContractAPIException(
                code="SUPPLIER_UNAVAILABLE",
                message=f"Failed to fetch supplier page after 5 attempts at cursor {cursor}.",
                status_code=502,
            )

        items = data.get("items", [])
        all_items.extend(items)
        cursor = data.get("next_cursor")
        if not cursor:
            break

    # 2. Filter invalid items and collect rejection reasons
    valid_items = []
    for it in all_items:
        supp_sku = it.get("supplier_sku", "")
        sku = it.get("sku")
        price_val = it.get("price")

        if not sku or not str(sku).strip():
            rejected.append({"supplier_sku": supp_sku, "reason": "missing or empty sku"})
            continue

        try:
            price_dec = Decimal(str(price_val))
            if price_dec <= 0 or price_dec.as_tuple().exponent < -2:
                rejected.append({"supplier_sku": supp_sku, "reason": "invalid price"})
                continue
        except (InvalidOperation, TypeError, ValueError):
            rejected.append({"supplier_sku": supp_sku, "reason": "invalid price"})
            continue

        valid_items.append(it)

    # 3. Deduplicate by SKU using latest updated_at
    latest_by_sku = {}
    for it in valid_items:
        sku = it["sku"].strip()
        updated_at = it.get("updated_at", "")
        if sku not in latest_by_sku:
            latest_by_sku[sku] = it
        else:
            if updated_at > latest_by_sku[sku].get("updated_at", ""):
                latest_by_sku[sku] = it

    # 4. Atomic database application
    created_count = 0
    updated_count = 0
    unchanged_count = 0

    with transaction.atomic():
        existing_products = {p.sku: p for p in Product.objects.filter(sku__in=latest_by_sku.keys())}

        for sku, it in latest_by_sku.items():
            price = Decimal(str(it["price"]))
            name = it.get("name", "").strip()
            category = it.get("category", "").strip()
            brand = it.get("brand", "").strip()
            vehicle_fitment = it.get("vehicle_fitment", "").strip()
            description = it.get("description", "").strip()

            if sku not in existing_products:
                Product.objects.create(
                    sku=sku,
                    name=name,
                    category=category,
                    brand=brand,
                    vehicle_fitment=vehicle_fitment,
                    price=price,
                    stock=0,  # Never use supplier_stock
                    description=description,
                )
                created_count += 1
            else:
                p = existing_products[sku]
                differs = (
                    p.name != name
                    or p.category != category
                    or p.brand != brand
                    or p.vehicle_fitment != vehicle_fitment
                    or p.description != description
                    or p.price != price
                )
                if differs:
                    p.name = name
                    p.category = category
                    p.brand = brand
                    p.vehicle_fitment = vehicle_fitment
                    p.description = description
                    p.price = price
                    p.save(update_fields=["name", "category", "brand", "vehicle_fitment", "description", "price"])
                    updated_count += 1
                else:
                    unchanged_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "rejected": rejected,
        "pages_fetched": pages_fetched,
        "requests_made": requests_made,
    }
