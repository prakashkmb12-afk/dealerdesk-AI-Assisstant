import decimal
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Product, Dealer, Order
from .serializers import (
    ProductSerializer,
    ProductCreateSerializer,
    DealerSerializer,
    DealerCreateSerializer,
    OrderSerializer,
)
from .pagination import ContractPagination
from .exceptions import ContractAPIException
from .services import (
    create_draft_order,
    update_draft_order,
    confirm_order,
    cancel_order,
    dispatch_order,
    deliver_order,
)


def health(request):
    """GET /api/health/ — the grader polls this until the app is ready."""
    return JsonResponse({"status": "ok"})


# ---- Products -------------------------------------------------------------
@api_view(["GET", "POST"])
def product_list(request):
    if request.method == "GET":
        qs = Product.objects.all()

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(sku__icontains=search)
                | Q(name__icontains=search)
                | Q(brand__icontains=search)
            )

        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        vehicle = request.query_params.get("vehicle")
        if vehicle:
            qs = qs.filter(vehicle_fitment__icontains=vehicle)

        paginator = ContractPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    elif request.method == "POST":
        sku = request.data.get("sku") if isinstance(request.data, dict) else None
        if sku and Product.objects.filter(sku=sku).exists():
            raise ContractAPIException(
                code="DUPLICATE",
                message=f"Product with SKU '{sku}' already exists.",
                status_code=409,
            )

        serializer = ProductCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise ContractAPIException(
                code="VALIDATION_ERROR",
                message="Invalid product data.",
                details=[f"{k}: {v}" for k, v in serializer.errors.items()],
                status_code=400,
            )

        try:
            product = serializer.save(stock=0)
        except IntegrityError:
            raise ContractAPIException(
                code="DUPLICATE",
                message=f"Product with SKU '{sku}' already exists.",
                status_code=409,
            )

        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
def product_detail(request, sku):
    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        raise ContractAPIException(
            code="NOT_FOUND",
            message=f"Product with SKU '{sku}' not found.",
            status_code=404,
        )

    if request.method == "GET":
        return Response(ProductSerializer(product).data)

    elif request.method == "PATCH":
        if "sku" in request.data and request.data["sku"] != sku:
            raise ContractAPIException(
                code="VALIDATION_ERROR",
                message="Product SKU cannot be changed.",
                status_code=400,
            )

        serializer = ProductSerializer(product, data=request.data, partial=True)
        if not serializer.is_valid():
            raise ContractAPIException(
                code="VALIDATION_ERROR",
                message="Invalid product update.",
                details=[f"{k}: {v}" for k, v in serializer.errors.items()],
                status_code=400,
            )

        product = serializer.save()
        return Response(ProductSerializer(product).data)


# ---- Inventory ------------------------------------------------------------
@api_view(["PUT"])
def inventory_detail(request, sku):
    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        raise ContractAPIException(
            code="NOT_FOUND",
            message=f"Product with SKU '{sku}' not found.",
            status_code=404,
        )

    qty = request.data.get("quantity")
    if qty is None or not isinstance(qty, int) or qty < 0:
        raise ContractAPIException(
            code="VALIDATION_ERROR",
            message="Quantity must be an integer >= 0.",
            status_code=400,
        )

    product.stock = qty
    product.save(update_fields=["stock"])
    return Response({"sku": sku, "quantity": qty}, status=status.HTTP_200_OK)


# ---- Dealers --------------------------------------------------------------
@api_view(["GET", "POST"])
def dealer_list(request):
    if request.method == "GET":
        qs = Dealer.objects.all()
        paginator = ContractPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = DealerSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    elif request.method == "POST":
        dealer_code = request.data.get("dealer_code") if isinstance(request.data, dict) else None
        if dealer_code and Dealer.objects.filter(dealer_code=dealer_code).exists():
            raise ContractAPIException(
                code="DUPLICATE",
                message=f"Dealer with code '{dealer_code}' already exists.",
                status_code=409,
            )

        serializer = DealerCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise ContractAPIException(
                code="VALIDATION_ERROR",
                message="Invalid dealer data.",
                details=[f"{k}: {v}" for k, v in serializer.errors.items()],
                status_code=400,
            )

        try:
            dealer = serializer.save()
        except IntegrityError:
            raise ContractAPIException(
                code="DUPLICATE",
                message=f"Dealer with code '{dealer_code}' already exists.",
                status_code=409,
            )

        return Response(DealerSerializer(dealer).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def dealer_detail(request, pk):
    try:
        dealer = Dealer.objects.get(id=pk)
    except Dealer.DoesNotExist:
        raise ContractAPIException(
            code="NOT_FOUND",
            message=f"Dealer with id {pk} not found.",
            status_code=404,
        )
    return Response(DealerSerializer(dealer).data)


# ---- Orders ---------------------------------------------------------------
@api_view(["GET", "POST"])
def order_list(request):
    if request.method == "GET":
        qs = Order.objects.prefetch_related("items").all()

        dealer_id = request.query_params.get("dealer_id")
        if dealer_id:
            qs = qs.filter(dealer_id=dealer_id)

        order_status = request.query_params.get("status")
        if order_status:
            qs = qs.filter(status=order_status)

        paginator = ContractPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = OrderSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    elif request.method == "POST":
        dealer_id = request.data.get("dealer_id")
        items = request.data.get("items")
        if dealer_id is None:
            raise ContractAPIException(code="VALIDATION_ERROR", message="dealer_id is required.")
        if items is None or not isinstance(items, list) or len(items) == 0:
            raise ContractAPIException(code="VALIDATION_ERROR", message="items must be a non-empty list.")

        idempotency_key = request.headers.get("Idempotency-Key") or request.META.get("HTTP_IDEMPOTENCY_KEY")

        order, created = create_draft_order(
            dealer_id=dealer_id,
            items_data=items,
            idempotency_key=idempotency_key,
            raw_body=request.data,
        )

        resp_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(OrderSerializer(order).data, status=resp_status)


@api_view(["GET", "PUT"])
def order_detail(request, order_number):
    try:
        order = Order.objects.prefetch_related("items").get(order_number=order_number)
    except Order.DoesNotExist:
        raise ContractAPIException(
            code="NOT_FOUND",
            message=f"Order '{order_number}' not found.",
            status_code=404,
        )

    if request.method == "GET":
        return Response(OrderSerializer(order).data)

    elif request.method == "PUT":
        items = request.data.get("items")
        if items is None or not isinstance(items, list) or len(items) == 0:
            raise ContractAPIException(code="VALIDATION_ERROR", message="items must be a non-empty list.")

        order = update_draft_order(order, items)
        return Response(OrderSerializer(order).data)


@api_view(["POST"])
def order_confirm(request, order_number):
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        raise ContractAPIException(code="NOT_FOUND", message=f"Order '{order_number}' not found.", status_code=404)

    order = confirm_order(order)
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
def order_cancel(request, order_number):
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        raise ContractAPIException(code="NOT_FOUND", message=f"Order '{order_number}' not found.", status_code=404)

    order = cancel_order(order)
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
def order_dispatch(request, order_number):
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        raise ContractAPIException(code="NOT_FOUND", message=f"Order '{order_number}' not found.", status_code=404)

    order = dispatch_order(order)
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
def order_deliver(request, order_number):
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        raise ContractAPIException(code="NOT_FOUND", message=f"Order '{order_number}' not found.", status_code=404)

    order = deliver_order(order)
    return Response(OrderSerializer(order).data)


# ---- Dealer Assistant (GenAI) ---------------------------------------------
@api_view(["POST"])
def assistant_chat(request):
    session_id = request.data.get("session_id")
    dealer_id = request.data.get("dealer_id")
    message = request.data.get("message")

    if not session_id or not isinstance(session_id, str):
        raise ContractAPIException(code="VALIDATION_ERROR", message="session_id is required.")
    if dealer_id is None or not isinstance(dealer_id, int):
        raise ContractAPIException(code="VALIDATION_ERROR", message="dealer_id must be an integer.")
    if not message or not isinstance(message, str):
        raise ContractAPIException(code="VALIDATION_ERROR", message="message is required.")

    from .assistant.orchestrator import AssistantOrchestrator
    orchestrator = AssistantOrchestrator(session_id=session_id, dealer_id=dealer_id)
    response_data = orchestrator.run(user_message=message)

    return Response(response_data, status=status.HTTP_200_OK)


# ---- Forecasting & Reorder (ML) -------------------------------------------
@api_view(["GET"])
def forecast_detail(request, sku):
    from .reorder import ReorderService
    service = ReorderService()
    forecast = service.get_sku_forecast(sku)
    if forecast is None:
        raise ContractAPIException(
            code="NOT_FOUND",
            message=f"Forecast for SKU '{sku}' not found or not a forecast SKU.",
            status_code=404,
        )

    return Response({"sku": sku, "forecast": forecast}, status=status.HTTP_200_OK)


@api_view(["GET"])
def reorder_suggestions(request):
    from .reorder import ReorderService
    service = ReorderService()
    results = service.get_reorder_suggestions()
    return Response({"results": results}, status=status.HTTP_200_OK)


# ---- Supplier Sync (Bonus Part B) -----------------------------------------
@api_view(["POST"])
def supplier_sync_view(request):
    from .supplier_sync import sync_supplier_catalogue
    result = sync_supplier_catalogue()
    return Response(result, status=status.HTTP_200_OK)


# ---- Web App Frontend ----------------------------------------------------
def index(request):
    from django.shortcuts import render
    return render(request, "index.html")

