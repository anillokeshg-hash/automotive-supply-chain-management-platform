"""Synthetic data for an automotive plant: suppliers, parts, vehicle models (BOM), history."""
import numpy as np
import pandas as pd

rng = np.random.default_rng(11)
TODAY = pd.Timestamp.today().normalize()

SUPPLIERS = pd.DataFrame(
    [
        (1, "Apex Castings", "Germany", 10, 0.94, 180),
        (2, "NovaBrake Systems", "India", 7, 0.88, 420),
        (3, "SiliconEdge Micro", "Taiwan", 30, 0.78, 90),
        (4, "GripTyre Co", "Japan", 14, 0.96, 250),
        (5, "ComfortSeat Ltd", "Mexico", 9, 0.85, 600),
        (6, "VoltCell Energy", "China", 21, 0.72, 350),
        (7, "SteelForge", "India", 5, 0.91, 300),
    ],
    columns=["supplier_id", "name", "country", "lead_time_days", "on_time_rate", "defect_ppm"],
).set_index("supplier_id")

PARTS = pd.DataFrame(
    [
        (1, "Engine Block", 1, 1800.0, 4000),
        (2, "Brake Kit", 2, 120.0, 6000),
        (3, "ECU Chip", 3, 85.0, 9000),
        (4, "Tyre Set", 4, 220.0, 9000),
        (5, "Seat Set", 5, 310.0, 3000),
        (6, "Battery Pack", 6, 6500.0, 600),
        (7, "Chassis Frame", 7, 900.0, 10000),
        (8, "Wiring Harness", 7, 150.0, 5000),
    ],
    columns=["part_id", "name", "supplier_id", "unit_cost", "stock"],
).set_index("part_id")

# Vehicle models: average daily output and bill of materials {part_id: qty per vehicle}
MODELS = {
    "Sedan": dict(base=120, bom={1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 7: 1, 8: 1}),
    "SUV": dict(base=90, bom={1: 1, 2: 1, 3: 2, 4: 1, 5: 1, 7: 1, 8: 1}),
    "EV": dict(base=50, bom={6: 1, 2: 1, 3: 3, 4: 1, 5: 1, 7: 1, 8: 1}),
}


def generate_demand_history(days: int = 90) -> pd.DataFrame:
    """Daily vehicles built/ordered per model (weekday pattern + growth + noise)."""
    dates = pd.date_range(end=TODAY - pd.Timedelta(days=1), periods=days)
    dow_factor = {0: 1.0, 1: 1.05, 2: 1.05, 3: 1.0, 4: 0.95, 5: 0.5, 6: 0.2}
    rows = []
    for m, cfg in MODELS.items():
        for i, d in enumerate(dates):
            units = cfg["base"] * dow_factor[d.dayofweek] * (1 + 0.002 * i) * rng.normal(1, 0.06)
            rows.append((d, m, int(max(units, 0))))
    return pd.DataFrame(rows, columns=["date", "model", "units"])


def generate_delivery_history(per_supplier: int = 40) -> pd.DataFrame:
    """Past inbound deliveries: delay_days = actual - promised (0 means on time)."""
    rows = []
    for sid, s in SUPPLIERS.iterrows():
        for _ in range(per_supplier):
            late = rng.random() > s.on_time_rate
            rows.append((sid, int(rng.integers(1, 11)) if late else 0))
    return pd.DataFrame(rows, columns=["supplier_id", "delay_days"])


def generate_open_shipments() -> list[dict]:
    """One open purchase order per part. The ECU shipment is delayed to demo risk alerts."""
    out = []
    for pid, p in PARTS.iterrows():
        lt = int(SUPPLIERS.loc[p.supplier_id, "lead_time_days"])
        ordered = TODAY - pd.Timedelta(days=int(rng.integers(1, max(2, lt - 1))))
        promised = ordered + pd.Timedelta(days=lt)
        delay = 6 if pid == 3 else (int(rng.integers(1, 5)) if rng.random() > SUPPLIERS.loc[p.supplier_id, "on_time_rate"] else 0)
        out.append({"part_id": int(pid), "qty": int(rng.integers(2, 6) * 500 if pid != 6 else 300),
                    "ordered": ordered, "promised": promised,
                    "eta": promised + pd.Timedelta(days=delay)})
    return out
