from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from core.models import Product, Dealer, Order, OrderItem


class BackendCoreTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.product = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set - Bajaj Pulsar 150",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1459.50"),
            stock=50,
            description="Genuine brake pad set.",
        )
        self.dealer = Dealer.objects.create(
            dealer_code="DLR-001",
            name="Test Dealer",
            city="Bengaluru",
            phone="9876543210",
            credit_limit=Decimal("50000.00"),
        )

    def test_health(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_products_list_and_filter(self):
        resp = self.client.get("/api/products/?search=pulsar")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["sku"], "BRK-1044")
        self.assertEqual(data["results"][0]["price"], "1459.50")
        self.assertIsInstance(data["results"][0]["stock"], int)

    def test_product_detail_and_404(self):
        resp = self.client.get("/api/products/BRK-1044/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["sku"], "BRK-1044")

        resp_404 = self.client.get("/api/products/NOPE-9999/")
        self.assertEqual(resp_404.status_code, 404)
        self.assertEqual(resp_404.json()["error"]["code"], "NOT_FOUND")

    def test_product_duplicate_409(self):
        payload = {
            "sku": "BRK-1044",
            "name": "Duplicate Product",
            "category": "Brakes",
            "brand": "Endurance",
            "vehicle_fitment": "Universal",
            "price": "999.00",
        }
        resp = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "DUPLICATE")

    def test_inventory_update(self):
        resp = self.client.put("/api/inventory/BRK-1044/", {"quantity": 85, "reason": "audit"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"sku": "BRK-1044", "quantity": 85})

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 85)

    def test_order_creation_draft(self):
        payload = {
            "dealer_id": self.dealer.id,
            "items": [{"sku": "BRK-1044", "quantity": 2}],
        }
        resp = self.client.post("/api/orders/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], "DRAFT")
        self.assertEqual(data["items"][0]["sku"], "BRK-1044")
        self.assertEqual(data["items"][0]["unit_price"], "1459.50")
        self.assertEqual(data["items"][0]["line_subtotal"], "2919.00")
        self.assertEqual(data["items"][0]["line_tax"], "525.42")
        self.assertEqual(data["items"][0]["line_total"], "3444.42")
        self.assertEqual(data["subtotal"], "2919.00")
        self.assertEqual(data["tax_total"], "525.42")
        self.assertEqual(data["grand_total"], "3444.42")
        self.assertTrue(data["order_number"].startswith("ORD-"))

    def test_order_confirm_and_cancel_lifecycle(self):
        payload = {
            "dealer_id": self.dealer.id,
            "items": [{"sku": "BRK-1044", "quantity": 5}],
        }
        create_resp = self.client.post("/api/orders/", payload, format="json")
        order_no = create_resp.json()["order_number"]

        # Confirm order
        confirm_resp = self.client.post(f"/api/orders/{order_no}/confirm/")
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertEqual(confirm_resp.json()["status"], "CONFIRMED")

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 45)  # 50 - 5 = 45

        # Cancel order
        cancel_resp = self.client.post(f"/api/orders/{order_no}/cancel/")
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()["status"], "CANCELLED")

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 50)  # Restored to 50
