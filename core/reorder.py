import csv
import math
from pathlib import Path
import pandas as pd
from django.conf import settings
from core.models import Product

FORECAST_WEEKS = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]


class ReorderService:
    """Computes exact contract-compliant reorder suggestions using committed forecasts and live inventory."""

    def __init__(self):
        self.base_dir = Path(settings.BASE_DIR)
        self.data_dir = settings.DATA_DIR
        self.forecast_path = self.base_dir / "ml" / "forecast.csv"
        self.lead_times_path = self.data_dir / "lead_times.csv"
        self.sales_history_path = self.data_dir / "sales_history.csv"

        self._forecast_data = None
        self._lead_times = None
        self._sigmas = None

    def load_forecast_data(self):
        """Loads ml/forecast.csv mapping sku -> list of {week_start, forecast_units}."""
        if not self.forecast_path.exists():
            return {}

        data = {}
        with open(self.forecast_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sku = row["sku"].strip()
                if sku not in data:
                    data[sku] = []
                data[sku].append({
                    "week_start": row["week_start"].strip(),
                    "forecast_units": float(row["forecast_units"].strip()),
                })

        # Ensure sorted by week_start
        for sku in data:
            data[sku].sort(key=lambda x: x["week_start"])

        return data

    def load_lead_times(self):
        """Loads data/lead_times.csv mapping sku -> lead_time_weeks."""
        if not self.lead_times_path.exists():
            return {}

        lead_times = {}
        with open(self.lead_times_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sku = row["sku"].strip()
                lead_times[sku] = int(row["lead_time_weeks"].strip())
        return lead_times

    def compute_12week_sigmas(self):
        """Computes sample standard deviation (n-1) of units_sold over most recent 12 weeks of sales_history.csv."""
        if not self.sales_history_path.exists():
            return {}

        df = pd.read_csv(self.sales_history_path)
        df["week_start"] = pd.to_datetime(df["week_start"])
        sigmas = {}

        for sku, group in df.groupby("sku"):
            sorted_sales = group.sort_values("week_start")["units_sold"].tail(12).values
            if len(sorted_sales) > 1:
                sigmas[sku] = float(pd.Series(sorted_sales).std(ddof=1))
            else:
                sigmas[sku] = 0.0

        return sigmas

    def get_sku_forecast(self, sku: str):
        """Returns forecast entries for a specific SKU or None if not a forecast SKU."""
        forecast_map = self.load_forecast_data()
        lead_times = self.load_lead_times()

        if sku not in lead_times or sku not in forecast_map:
            return None

        return forecast_map[sku]

    def get_reorder_suggestions(self):
        """Generates reorder suggestions for all 40 forecast SKUs with live database stock."""
        forecast_map = self.load_forecast_data()
        lead_times = self.load_lead_times()
        sigmas = self.compute_12week_sigmas()

        # Query live available stock from PostgreSQL
        live_products = {
            p.sku: p.stock
            for p in Product.objects.filter(sku__in=lead_times.keys())
        }

        results = []
        for sku, lead_time_weeks in lead_times.items():
            sku_forecast = forecast_map.get(sku, [])
            l = lead_time_weeks

            # lead_time_demand = sum of forecast_units for the first L forecast weeks
            ltd = sum(item["forecast_units"] for item in sku_forecast[:l])
            ltd = round(ltd, 1)

            # sigma over most recent 12 weeks
            sigma = sigmas.get(sku, 0.0)

            # safety_stock = ceil(1.65 * sigma * sqrt(L))
            safety_stock = math.ceil(1.65 * sigma * math.sqrt(l))

            # reorder_point = lead_time_demand + safety_stock
            reorder_point = round(ltd + safety_stock, 1)

            # current_stock from live DB (or 0 if missing)
            current_stock = live_products.get(sku, 0)

            # reorder_qty = max(0, ceil(reorder_point - current_stock))
            reorder_qty = max(0, math.ceil(reorder_point - current_stock))

            results.append({
                "sku": sku,
                "current_stock": current_stock,
                "lead_time_weeks": l,
                "lead_time_demand": ltd,
                "safety_stock": safety_stock,
                "reorder_point": reorder_point,
                "reorder_qty": reorder_qty,
            })

        return results
