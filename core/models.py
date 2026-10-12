import decimal
from django.db import models
from django.utils import timezone


class Product(models.Model):
    """Authoritative catalogue product model. Stock represents live available quantity."""
    sku = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, db_index=True)
    brand = models.CharField(max_length=100, db_index=True)
    vehicle_fitment = models.CharField(max_length=255, db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "products"
        ordering = ["sku"]

    def __str__(self):
        return f"{self.sku} - {self.name}"


class Dealer(models.Model):
    """Dealer entity supplying automotive parts."""
    dealer_code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    gstin = models.CharField(max_length=50, blank=True, default="")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=decimal.Decimal("0.00"))

    class Meta:
        db_table = "dealers"
        ordering = ["id"]

    def __str__(self):
        return f"{self.dealer_code} - {self.name}"


class Order(models.Model):
    """Order aggregate with status workflow and exact financial totals."""
    STATUS_DRAFT = "DRAFT"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_DISPATCHED = "DISPATCHED"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "DRAFT"),
        (STATUS_CONFIRMED, "CONFIRMED"),
        (STATUS_DISPATCHED, "DISPATCHED"),
        (STATUS_DELIVERED, "DELIVERED"),
        (STATUS_CANCELLED, "CANCELLED"),
    ]

    order_number = models.CharField(max_length=64, primary_key=True)
    dealer = models.ForeignKey(Dealer, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=decimal.Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=decimal.Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=decimal.Decimal("0.00"))
    idempotency_key = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    request_hash = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_number} ({self.status})"


class OrderItem(models.Model):
    """Line items belonging to an order with exact GST calculations."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    line_tax = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "order_items"
        unique_together = [("order", "sku")]
        ordering = ["id"]

    def __str__(self):
        return f"{self.order_id} - {self.sku} x {self.quantity}"


class DailyOrderSequence(models.Model):
    """Row-lockable sequence tracking for unique ORD-YYYYMMDD-NNNN order numbers."""
    order_date = models.DateField(primary_key=True)
    last_seq = models.IntegerField(default=0)

    class Meta:
        db_table = "daily_order_sequences"


class ConversationMessage(models.Model):
    """Conversation history for dealer assistant sessions."""
    session_id = models.CharField(max_length=128, db_index=True)
    dealer = models.ForeignKey(Dealer, on_delete=models.SET_NULL, null=True, blank=True, related_name="chat_messages")
    role = models.CharField(max_length=32)  # 'user', 'assistant', 'system', 'tool'
    content = models.TextField(blank=True, default="")
    tool_calls = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_messages"
        ordering = ["created_at"]
