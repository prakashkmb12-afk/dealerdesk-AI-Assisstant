from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from core.models import Product
from core.supplier_sync import sync_supplier_catalogue
from core.exceptions import ContractAPIException


class SupplierSyncTests(TestCase):
    def setUp(self):
        self.p1 = Product.objects.create(
            sku="BRK-1044",
            name="Old Name",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1400.00"),
            stock=50,
            description="Old description",
        )

    @patch("requests.get")
    def test_sync_successful(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "supplier_sku": "SUP-1",
                    "sku": "BRK-1044",
                    "name": "Updated Brake Pad Set",
                    "category": "Brakes",
                    "brand": "Endurance",
                    "vehicle_fitment": "Bajaj Pulsar 150",
                    "price": "1459.50",
                    "supplier_stock": 200,
                    "updated_at": "2026-10-10T10:00:00Z",
                },
                {
                    "supplier_sku": "SUP-2",
                    "sku": "NEW-9999",
                    "name": "Brand New Part",
                    "category": "Controls & Grips",
                    "brand": "Renthal",
                    "vehicle_fitment": "Universal",
                    "price": "850.00",
                    "supplier_stock": 100,
                    "updated_at": "2026-10-10T10:00:00Z",
                },
                {
                    "supplier_sku": "SUP-3",
                    "sku": "",  # invalid
                    "price": "100.00",
                },
            ],
            "next_cursor": None,
        }
        mock_get.return_value = mock_resp

        result = sync_supplier_catalogue()
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(len(result["rejected"]), 1)

        # Ensure our stock is NEVER changed by supplier_stock
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 50)
        self.assertEqual(self.p1.name, "Updated Brake Pad Set")
        self.assertEqual(self.p1.price, Decimal("1459.50"))

        new_prod = Product.objects.get(sku="NEW-9999")
        self.assertEqual(new_prod.stock, 0)
