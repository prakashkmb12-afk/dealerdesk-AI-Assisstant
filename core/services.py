import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone
from .models import Product, Dealer, Order, OrderItem, DailyOrderSequence
from .exceptions import ContractAPIException

GST_RATE = Decimal("0.18")
TWOPLACES = Decimal("0.01")


def round_paisa(amount: Decimal) -> Decimal:
    """Rounds monetary value to 2 decimal places using ROUND_HALF_UP."""
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def calculate_line_finances(unit_price: Decimal, quantity: int):
    """Calculates subtotal, 18% GST (rounded per line ROUND_HALF_UP), and total."""
    subtotal = round_paisa(unit_price * Decimal(quantity))
    tax = round_paisa(subtotal * GST_RATE)
    total = round_paisa(subtotal + tax)
    return subtotal, tax, total


def generate_order_number() -> str:
    """Generates unique, atomic ORD-YYYYMMDD-NNNN order number in Asia/Kolkata timezone."""
    kolkata_now = timezone.localtime(timezone.now())
    today = kolkata_now.date()

    with transaction.atomic():
        seq_obj, _ = DailyOrderSequence.objects.select_for_update().get_or_create(
            order_date=today,
            defaults={"last_seq": 0}
        )
        seq_obj.last_seq += 1
        seq_obj.save(update_fields=["last_seq"])
        date_str = today.strftime("%Y%m%d")
        return f"ORD-{date_str}-{seq_obj.last_seq:04d}"


def create_draft_order(dealer_id, items_data, idempotency_key=None, raw_body=None):
    """Creates a DRAFT order with full contract validation and pricing rules."""
    # 1. Dealer existence
    try:
        dealer = Dealer.objects.get(id=dealer_id)
    except Dealer.DoesNotExist:
        raise ContractAPIException(
            code="VALIDATION_ERROR",
            message=f"Dealer with id {dealer_id} does not exist.",
            status_code=400,
        )

    # 2. Items validation
    if not items_data or not isinstance(items_data, list):
        raise ContractAPIException(
            code="VALIDATION_ERROR",
            message="Order must contain at least one item.",
            status_code=400,
        )

    seen_skus = set()
    sku_list = []
    for idx, item in enumerate(items_data):
        if not isinstance(item, dict):
            raise ContractAPIException(code="VALIDATION_ERROR", message="Invalid item format.")
        sku = item.get("sku")
        qty = item.get("quantity")
        if not sku:
            raise ContractAPIException(code="VALIDATION_ERROR", message=f"Item {idx} missing sku.")
        if qty is None or not isinstance(qty, int) or qty < 1:
            raise ContractAPIException(
                code="VALIDATION_ERROR",
                message=f"Item {sku} quantity must be an integer >= 1.",
            )
        if sku in seen_skus:
            raise ContractAPIException(
                code="VALIDATION_ERROR",
                message=f"Duplicate SKU {sku} in order items.",
            )
        seen_skus.add(sku)
        sku_list.append(sku)

    # 3. Check SKUs in database
    products = {p.sku: p for p in Product.objects.filter(sku__in=sku_list)}
    missing_skus = [sku for sku in sku_list if sku not in products]
    if missing_skus:
        raise ContractAPIException(
            code="VALIDATION_ERROR",
            message=f"Unknown SKU(s): {', '.join(missing_skus)}",
            status_code=400,
        )

    # 4. Idempotency handling
    request_hash = None
    if idempotency_key:
        if raw_body is not None:
            if isinstance(raw_body, (dict, list)):
                raw_str = json.dumps(raw_body, sort_keys=True)
            else:
                raw_str = str(raw_body)
            request_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

        existing_order = Order.objects.filter(idempotency_key=idempotency_key).first()
        if existing_order:
            if existing_order.request_hash and request_hash and existing_order.request_hash != request_hash:
                raise ContractAPIException(
                    code="IDEMPOTENCY_CONFLICT",
                    message="Idempotency-Key already used with a different request payload.",
                    status_code=409,
                )
            return existing_order, False

    # 5. Create Order atomically
    with transaction.atomic():
        order_no = generate_order_number()
        order = Order.objects.create(
            order_number=order_no,
            dealer=dealer,
            status=Order.STATUS_DRAFT,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )

        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")

        order_items = []
        for item in items_data:
            sku = item["sku"]
            qty = item["quantity"]
            product = products[sku]
            unit_price = product.price
            l_subtotal, l_tax, l_total = calculate_line_finances(unit_price, qty)
            subtotal += l_subtotal
            tax_total += l_tax

            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    sku=sku,
                    name=product.name,
                    quantity=qty,
                    unit_price=unit_price,
                    line_subtotal=l_subtotal,
                    line_tax=l_tax,
                    line_total=l_total,
                )
            )

        OrderItem.objects.bulk_create(order_items)
        order.subtotal = subtotal
        order.tax_total = tax_total
        order.grand_total = subtotal + tax_total
        order.save(update_fields=["subtotal", "tax_total", "grand_total"])

    return order, True


def update_draft_order(order: Order, items_data):
    """Replaces all items in a DRAFT order. Rejects if order is not DRAFT."""
    if order.status != Order.STATUS_DRAFT:
        raise ContractAPIException(
            code="ORDER_LOCKED",
            message=f"Cannot edit order {order.order_number} in {order.status} status.",
            status_code=409,
        )

    if not items_data or not isinstance(items_data, list):
        raise ContractAPIException(
            code="VALIDATION_ERROR",
            message="Order must contain at least one item.",
            status_code=400,
        )

    seen_skus = set()
    sku_list = []
    for item in items_data:
        sku = item.get("sku")
        qty = item.get("quantity")
        if not sku or qty is None or not isinstance(qty, int) or qty < 1:
            raise ContractAPIException(code="VALIDATION_ERROR", message="Invalid item SKU or quantity.")
        if sku in seen_skus:
            raise ContractAPIException(code="VALIDATION_ERROR", message=f"Duplicate SKU {sku}.")
        seen_skus.add(sku)
        sku_list.append(sku)

    products = {p.sku: p for p in Product.objects.filter(sku__in=sku_list)}
    missing = [s for s in sku_list if s not in products]
    if missing:
        raise ContractAPIException(code="VALIDATION_ERROR", message=f"Unknown SKU(s): {', '.join(missing)}")

    with transaction.atomic():
        order.items.all().delete()
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        new_items = []
        for item in items_data:
            sku = item["sku"]
            qty = item["quantity"]
            product = products[sku]
            unit_price = product.price
            l_subtotal, l_tax, l_total = calculate_line_finances(unit_price, qty)
            subtotal += l_subtotal
            tax_total += l_tax
            new_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    sku=sku,
                    name=product.name,
                    quantity=qty,
                    unit_price=unit_price,
                    line_subtotal=l_subtotal,
                    line_tax=l_tax,
                    line_total=l_total,
                )
            )
        OrderItem.objects.bulk_create(new_items)
        order.subtotal = subtotal
        order.tax_total = tax_total
        order.grand_total = subtotal + tax_total
        order.save(update_fields=["subtotal", "tax_total", "grand_total", "updated_at"])

    return order


def confirm_order(order: Order):
    """Transitions DRAFT -> CONFIRMED, atomically verifying and deducting stock."""
    if order.status != Order.STATUS_DRAFT:
        raise ContractAPIException(
            code="INVALID_TRANSITION",
            message=f"Cannot confirm order in {order.status} status.",
            status_code=409,
        )

    with transaction.atomic():
        # Lock products to prevent concurrent overselling
        items = list(order.items.select_related("product").all())
        sku_to_qty = {item.sku: item.quantity for item in items}
        locked_products = {
            p.sku: p
            for p in Product.objects.filter(sku__in=sku_to_qty.keys()).select_for_update()
        }

        short_lines = []
        message_parts = []
        for item in items:
            product = locked_products.get(item.sku)
            requested = item.quantity
            available = product.stock if product else 0
            if available < requested:
                short_lines.append(
                    {"sku": item.sku, "requested": requested, "available": available}
                )
                prod_name = product.name if product else item.name
                message_parts.append(
                    f"Insufficient stock for {prod_name}. Available: {available}, Requested: {requested}"
                )

        if short_lines:
            raise ContractAPIException(
                code="INSUFFICIENT_STOCK",
                message=" ".join(message_parts),
                details=short_lines,
                status_code=409,
            )

        # Deduct stock and lock prices
        for item in items:
            product = locked_products[item.sku]
            product.stock -= item.quantity
            product.save(update_fields=["stock"])

        order.status = Order.STATUS_CONFIRMED
        order.save(update_fields=["status", "updated_at"])

    return order


def cancel_order(order: Order):
    """Transitions DRAFT or CONFIRMED -> CANCELLED, restoring stock exactly once if CONFIRMED."""
    if order.status not in (Order.STATUS_DRAFT, Order.STATUS_CONFIRMED):
        raise ContractAPIException(
            code="INVALID_TRANSITION",
            message=f"Cannot cancel order in {order.status} status.",
            status_code=409,
        )

    with transaction.atomic():
        if order.status == Order.STATUS_CONFIRMED:
            items = list(order.items.select_related("product").all())
            locked_products = {
                p.sku: p
                for p in Product.objects.filter(sku__in=[it.sku for it in items]).select_for_update()
            }
            for item in items:
                if item.sku in locked_products:
                    product = locked_products[item.sku]
                    product.stock += item.quantity
                    product.save(update_fields=["stock"])

        order.status = Order.STATUS_CANCELLED
        order.save(update_fields=["status", "updated_at"])

    return order


def dispatch_order(order: Order):
    """Transitions CONFIRMED -> DISPATCHED."""
    if order.status != Order.STATUS_CONFIRMED:
        raise ContractAPIException(
            code="INVALID_TRANSITION",
            message=f"Cannot dispatch order in {order.status} status.",
            status_code=409,
        )
    order.status = Order.STATUS_DISPATCHED
    order.save(update_fields=["status", "updated_at"])
    return order


def deliver_order(order: Order):
    """Transitions DISPATCHED -> DELIVERED."""
    if order.status != Order.STATUS_DISPATCHED:
        raise ContractAPIException(
            code="INVALID_TRANSITION",
            message=f"Cannot deliver order in {order.status} status.",
            status_code=409,
        )
    order.status = Order.STATUS_DELIVERED
    order.save(update_fields=["status", "updated_at"])
    return order
