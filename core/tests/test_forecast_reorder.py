import csv
import math
from pathlib import Path
from decimal import Decimal
from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient
from core.models import Product
from core.reorder import ReorderService, FORECAST_WEEKS


class ForecastAndReorderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.forecast_path = Path(settings.BASE_DIR) / "ml" / "forecast.csv"
        # Seed test product for reorder testing
        Product.objects.update_or_create(
            sku="FIL-1016",
            defaults={
                "name": "Oil Filter - KTM Duke 390",
                "category": "Filters",
                "brand": "Bosch",
                "vehicle_fitment": "KTM Duke 390",
                "price": Decimal("350.00"),
                "stock": 25,
            },
        )

    def test_forecast_file_integrity(self):
        self.assertTrue(self.forecast_path.exists(), "ml/forecast.csv must exist")
        with open(self.forecast_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        self.assertEqual(len(reader), 160, "ml/forecast.csv must contain exactly 160 rows")
        self.assertEqual(
            list(reader[0].keys())[:3],
            ["sku", "week_start", "forecast_units"],
            "Columns must be sku,week_start,forecast_units",
        )

        skus = {r["sku"] for r in reader}
        self.assertEqual(len(skus), 40, "Must cover exactly 40 SKUs")

        for r in reader:
            self.assertIn(r["week_start"], FORECAST_WEEKS)
            val = float(r["forecast_units"])
            self.assertGreaterEqual(val, 0.0, f"Forecast cannot be negative: {val}")

    def test_forecast_api_endpoint(self):
        resp = self.client.get("/api/forecast/FIL-1016/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["sku"], "FIL-1016")
        self.assertEqual(len(data["forecast"]), 4)
        weeks = [f["week_start"] for f in data["forecast"]]
        self.assertEqual(weeks, FORECAST_WEEKS)

        # 404 on unknown SKU
        resp_404 = self.client.get("/api/forecast/UNKNOWN-9999/")
        self.assertEqual(resp_404.status_code, 404)
        self.assertEqual(resp_404.json()["error"]["code"], "NOT_FOUND")

    def test_reorder_suggestions_endpoint(self):
        resp = self.client.get("/api/reorder-suggestions/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        results = data["results"]
        self.assertEqual(len(results), 40, "Must return suggestions for all 40 forecast SKUs")

        # Verify exact mathematical formula on first item
        item = [r for r in results if r["sku"] == "FIL-1016"][0]
        self.assertEqual(item["sku"], "FIL-1016")
        self.assertEqual(item["current_stock"], 25)

        l = item["lead_time_weeks"]
        ltd = item["lead_time_demand"]
        safety_stock = item["safety_stock"]
        reorder_point = item["reorder_point"]
        reorder_qty = item["reorder_qty"]

        # Formula checks:
        # reorder_point = ltd + safety_stock
        self.assertAlmostEqual(reorder_point, round(ltd + safety_stock, 1), places=1)
        # reorder_qty = max(0, ceil(reorder_point - current_stock))
        expected_qty = max(0, math.ceil(reorder_point - 25))
        self.assertEqual(reorder_qty, expected_qty)
