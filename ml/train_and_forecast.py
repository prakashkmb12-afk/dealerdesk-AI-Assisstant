import csv
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

FORECAST_WEEKS = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]


def train_and_generate_forecast():
    sales_file = DATA_DIR / "sales_history.csv"
    lead_file = DATA_DIR / "lead_times.csv"
    promo_file = DATA_DIR / "promo_calendar.csv"
    output_file = BASE_DIR / "ml" / "forecast.csv"

    sales_df = pd.read_csv(sales_file)
    sales_df["week_start"] = pd.to_datetime(sales_df["week_start"])
    sales_df = sales_df.sort_values(["sku", "week_start"]).reset_index(drop=True)

    lead_df = pd.read_csv(lead_file)
    target_skus = sorted(lead_df["sku"].unique())

    promo_df = pd.read_csv(promo_file)
    promo_lookup = {
        (row["sku"].strip(), str(row["week_start"]).strip()): int(row["promo_flag"])
        for _, row in promo_df.iterrows()
    }

    # Verify no future leakage: training data must be <= 2026-09-21
    max_train_date = sales_df["week_start"].max()
    assert max_train_date <= pd.to_datetime("2026-09-21"), f"Leakage detected! Training data includes {max_train_date}"

    # Build feature matrix from permitted historical data
    features = []
    targets = []

    for sku in target_skus:
        sdata = sales_df[sales_df["sku"] == sku].sort_values("week_start")
        if len(sdata) < 8:
            continue

        units = sdata["units_sold"].values
        promos = sdata["promo_flag"].values

        for i in range(8, len(sdata)):
            feat = {
                "sku": sku,
                "promo_flag": promos[i],
                "lag_1": units[i - 1],
                "lag_2": units[i - 2],
                "lag_3": units[i - 3],
                "lag_4": units[i - 4],
                "rolling_mean_4": np.mean(units[i - 4 : i]),
                "rolling_std_4": np.std(units[i - 4 : i]),
                "rolling_mean_8": np.mean(units[i - 8 : i]),
                "promo_rate": np.mean(promos[max(0, i - 12) : i]),
            }
            features.append(feat)
            targets.append(units[i])

    train_df = pd.DataFrame(features)
    train_df["sku"] = train_df["sku"].astype("category")

    # Fit HistGradientBoosting model
    hgb = HistGradientBoostingRegressor(
        categorical_features=["sku"],
        random_state=42,
        max_iter=100,
        min_samples_leaf=10,
        loss="squared_error",
    )
    hgb.fit(train_df, np.array(targets))

    # Multi-step recursive forecasting for the 4 forecast weeks
    sim_data = sales_df.copy()
    forecast_records = []

    for week_str in FORECAST_WEEKS:
        week_dt = pd.to_datetime(week_str)

        for sku in target_skus:
            promo_flag = promo_lookup.get((sku, week_str), 0)
            sdata = sim_data[sim_data["sku"] == sku].sort_values("week_start")
            units = sdata["units_sold"].values
            promos = sdata["promo_flag"].values

            # Determine SKU demand characteristics
            zero_rate = (units == 0).mean() if len(units) > 0 else 0.0
            is_new_sku = len(units) < 12
            is_intermittent = zero_rate > 0.40

            if is_new_sku:
                # New SKU fallback (CHN-1006, BRK-1105): Exponential recency weighted average + promo factor
                weights = np.exp(np.linspace(-0.5, 0, len(units)))
                weights /= weights.sum()
                base_demand = np.sum(units * weights)
                non_promo_mean = units[promos == 0].mean() if np.any(promos == 0) else base_demand
                promo_mean = units[promos == 1].mean() if np.any(promos == 1) else (non_promo_mean * 2.0)
                promo_mult = (promo_mean / non_promo_mean) if non_promo_mean > 0 else 2.0
                pred = (base_demand * promo_mult) if promo_flag == 1 else base_demand

            elif is_intermittent:
                # Intermittent SKU (ELE-1006, GRP-1043, BRK-1088): Croston method variant
                non_zero_units = units[units > 0]
                prob = len(non_zero_units) / len(units) if len(units) > 0 else 0.5
                avg_nz = np.mean(non_zero_units[-8:]) if len(non_zero_units) > 0 else 1.0
                base_demand = prob * avg_nz
                pred = (base_demand * 1.8) if promo_flag == 1 else base_demand

            else:
                # Regular SKU with sufficient history: HistGB feature prediction
                feat = pd.DataFrame([{
                    "sku": sku,
                    "promo_flag": promo_flag,
                    "lag_1": units[-1],
                    "lag_2": units[-2],
                    "lag_3": units[-3],
                    "lag_4": units[-4],
                    "rolling_mean_4": np.mean(units[-4:]),
                    "rolling_std_4": np.std(units[-4:]),
                    "rolling_mean_8": np.mean(units[-8:]),
                    "promo_rate": np.mean(promos[-12:]),
                }])
                feat["sku"] = pd.Categorical(feat["sku"], categories=train_df["sku"].cat.categories)
                raw_pred = hgb.predict(feat)[0]
                pred = max(0.0, raw_pred)

            final_units = round(float(max(0.0, pred)), 1)
            forecast_records.append({
                "sku": sku,
                "week_start": week_str,
                "forecast_units": final_units,
            })

            # Append prediction into sim_data for next step lag computation
            new_row = pd.DataFrame([{
                "week_start": week_dt,
                "sku": sku,
                "units_sold": final_units,
                "promo_flag": promo_flag,
            }])
            sim_data = pd.concat([sim_data, new_row], ignore_index=True)

    # Sort records by sku and week_start
    forecast_records.sort(key=lambda r: (r["sku"], r["week_start"]))

    # Write output to ml/forecast.csv
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sku", "week_start", "forecast_units"])
        writer.writeheader()
        writer.writerows(forecast_records)

    print(f"Successfully generated {len(forecast_records)} forecast rows to {output_file}")
    assert len(forecast_records) == 160, f"Expected 160 rows, got {len(forecast_records)}"
    return forecast_records


if __name__ == "__main__":
    train_and_generate_forecast()
