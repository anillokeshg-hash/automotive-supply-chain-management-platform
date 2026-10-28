"""Supply chain engine: demand forecast, MRP, supplier risk, shipments, alerts."""
import math

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

import data

SAFETY_DAYS = 3
FORECAST_HORIZON = 45


def _features(dates: pd.DatetimeIndex, start: pd.Timestamp) -> np.ndarray:
    t = ((dates - start).days.values).reshape(-1, 1) / 100.0
    return np.hstack([t, np.eye(7)[dates.dayofweek.values]])


class SupplyChain:
    def __init__(self):
        self.suppliers = data.SUPPLIERS.copy()
        self.parts = data.PARTS.copy()
        self.demand_hist = data.generate_demand_history()
        self.delivery_hist = data.generate_delivery_history()
        self.shipments: list[dict] = []
        for s in data.generate_open_shipments():
            self._add_shipment(s["part_id"], s["qty"], s["ordered"], s["promised"], s["eta"])
        self._cache_forecasts()

    # ---------- shipments ----------
    def _add_shipment(self, part_id, qty, ordered, promised, eta) -> dict:
        sh = {"shipment_id": len(self.shipments) + 1, "part_id": int(part_id),
              "part": self.parts.loc[part_id, "name"],
              "supplier": self.suppliers.loc[self.parts.loc[part_id, "supplier_id"], "name"],
              "supplier_id": int(self.parts.loc[part_id, "supplier_id"]),
              "qty": int(qty), "ordered": ordered.strftime("%Y-%m-%d"),
              "promised": promised.strftime("%Y-%m-%d"), "eta": eta.strftime("%Y-%m-%d"),
              "status": "IN_TRANSIT"}
        self.shipments.append(sh)
        return sh

    def _open(self):
        return [s for s in self.shipments if s["status"] == "IN_TRANSIT"]

    def shipment_list(self) -> list[dict]:
        out = []
        for s in self.shipments:
            delay = (pd.Timestamp(s["eta"]) - pd.Timestamp(s["promised"])).days
            out.append({**s, "delay_days": delay,
                        "days_to_arrival": (pd.Timestamp(s["eta"]) - data.TODAY).days})
        return out

    def receive_shipment(self, shipment_id: int):
        for s in self.shipments:
            if s["shipment_id"] == shipment_id and s["status"] == "IN_TRANSIT":
                self.parts.loc[s["part_id"], "stock"] += s["qty"]
                s["status"] = "RECEIVED"
                return s
        return None

    def disrupt_supplier(self, supplier_id: int, delay_days: int) -> int:
        """Simulate a disruption (port strike, factory fire...) delaying all open shipments."""
        n = 0
        for s in self._open():
            if s["supplier_id"] == supplier_id:
                s["eta"] = (pd.Timestamp(s["eta"]) + pd.Timedelta(days=delay_days)).strftime("%Y-%m-%d")
                n += 1
        return n

    # ---------- 1. Demand forecasting ----------
    def _cache_forecasts(self):
        self.model_fc = {}
        for m in data.MODELS:
            h = self.demand_hist[self.demand_hist.model == m].sort_values("date")
            start = h.date.min()
            reg = Ridge(alpha=0.1).fit(_features(pd.DatetimeIndex(h.date), start), h.units.values)
            future = pd.date_range(data.TODAY, periods=FORECAST_HORIZON)
            self.model_fc[m] = (future, np.clip(reg.predict(_features(future, start)), 0, None))

    def forecast(self, model: str, days: int = 14) -> list[dict]:
        future, pred = self.model_fc[model]
        return [{"date": d.strftime("%Y-%m-%d"), "predicted_units": round(float(v), 1)}
                for d, v in list(zip(future, pred))[:days]]

    def part_demand(self) -> dict[int, np.ndarray]:
        """Daily part demand for the forecast horizon, derived from vehicle forecasts x BOM."""
        totals = {pid: np.zeros(FORECAST_HORIZON) for pid in self.parts.index}
        for m, cfg in data.MODELS.items():
            _, pred = self.model_fc[m]
            for pid, qty in cfg["bom"].items():
                totals[pid] += pred * qty
        return totals

    # ---------- 2. MRP / replenishment ----------
    def mrp(self) -> list[dict]:
        demand = self.part_demand()
        rows = []
        for pid, p in self.parts.iterrows():
            sup = self.suppliers.loc[p.supplier_id]
            lt = int(sup.lead_time_days)
            horizon = lt + SAFETY_DAYS
            d = demand[pid]
            avg_daily = float(d[:14].mean())
            cover = p.stock / avg_daily if avg_daily else 999.0
            inbound = sum(s["qty"] for s in self._open() if s["part_id"] == pid
                          and (pd.Timestamp(s["eta"]) - data.TODAY).days <= horizon)
            need = d[:horizon].sum() + avg_daily * SAFETY_DAYS - p.stock - inbound
            qty = int(math.ceil(need / 10) * 10) if need > 0 else 0
            status = "CRITICAL" if cover < lt else "WARNING" if cover < lt * 1.5 else "OK"
            rows.append({"part_id": int(pid), "part": p["name"], "supplier": sup["name"],
                         "stock": int(p.stock), "avg_daily_demand": round(avg_daily, 1),
                         "days_of_cover": round(cover, 1), "lead_time_days": lt,
                         "inbound_qty": int(inbound), "order_qty": qty, "status": status,
                         "stockout_date": (data.TODAY + pd.Timedelta(days=int(cover))).strftime("%Y-%m-%d")})
        return rows

    def auto_order(self) -> list[dict]:
        """Create purchase orders (in-transit shipments) for every part that needs one."""
        placed = []
        for r in self.mrp():
            if r["order_qty"] > 0:
                promised = data.TODAY + pd.Timedelta(days=r["lead_time_days"])
                placed.append(self._add_shipment(r["part_id"], r["order_qty"], data.TODAY, promised, promised))
        return placed

    # ---------- 3. Supplier risk ----------
    def supplier_scores(self) -> list[dict]:
        out = []
        for sid, s in self.suppliers.iterrows():
            h = self.delivery_hist[self.delivery_hist.supplier_id == sid]
            on_time = float((h.delay_days == 0).mean())
            late = h[h.delay_days > 0].delay_days
            avg_delay = float(late.mean()) if len(late) else 0.0
            risk = 100 * (0.5 * min((1 - on_time) / 0.3, 1) + 0.3 * min(avg_delay / 8, 1)
                          + 0.2 * min(s.defect_ppm / 2000, 1))
            open_delayed = sum(1 for x in self._open() if x["supplier_id"] == sid
                               and x["eta"] > x["promised"])
            out.append({"supplier_id": int(sid), "name": s["name"], "country": s.country,
                        "lead_time_days": int(s.lead_time_days),
                        "on_time_pct": round(on_time * 100, 1), "avg_delay_days": round(avg_delay, 1),
                        "defect_ppm": int(s.defect_ppm), "open_delayed": open_delayed,
                        "risk_score": round(risk, 1),
                        "risk_level": "HIGH" if risk >= 55 else "MEDIUM" if risk >= 30 else "LOW"})
        return sorted(out, key=lambda x: -x["risk_score"])

    # ---------- 4. Production impact ----------
    def production_impact(self) -> list[dict]:
        out = []
        for m, cfg in data.MODELS.items():
            _, pred = self.model_fc[m]
            limits = {pid: self.parts.loc[pid, "stock"] / q for pid, q in cfg["bom"].items()}
            bottleneck = min(limits, key=limits.get)
            buildable = limits[bottleneck]
            daily = float(pred[:14].mean())
            out.append({"model": m, "avg_daily_plan": round(daily, 1),
                        "vehicles_buildable_from_stock": int(buildable),
                        "days_of_production": round(buildable / daily, 1),
                        "bottleneck_part": self.parts.loc[bottleneck, "name"]})
        return out

    # ---------- 5. Alerts ----------
    def alerts(self) -> list[dict]:
        out = []
        mrp = {r["part_id"]: r for r in self.mrp()}
        for s in self.shipment_list():
            if s["status"] != "IN_TRANSIT":
                continue
            r = mrp[s["part_id"]]
            gap = s["days_to_arrival"] - r["days_of_cover"]
            if gap > 0:
                out.append({"severity": "critical", "message":
                            f"{s['part']}: stock-out expected ~{gap:.0f} day(s) before shipment #{s['shipment_id']} "
                            f"from {s['supplier']} arrives ({s['eta']})."})
            if s["delay_days"] > 0:
                out.append({"severity": "warning", "message":
                            f"Shipment #{s['shipment_id']} ({s['part']}) is {s['delay_days']} day(s) late."})
        for r in mrp.values():
            if r["order_qty"] > 0:
                out.append({"severity": "warning", "message":
                            f"{r['part']}: order {r['order_qty']} units now to cover lead time + safety stock."})
        for sc in self.supplier_scores():
            if sc["risk_level"] == "HIGH":
                out.append({"severity": "info", "message":
                            f"Supplier {sc['name']} is HIGH risk (score {sc['risk_score']}); consider a backup source."})
        order = {"critical": 0, "warning": 1, "info": 2}
        return sorted(out, key=lambda a: order[a["severity"]])
