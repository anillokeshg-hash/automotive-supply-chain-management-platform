# Automotive Supply Chain Management Platform

A simple base project showing how data and ML can manage an automotive manufacturer's supply chain.
All data is synthetic (see `data.py`), so it runs offline.

## What it models
- 7 suppliers (lead time, on-time rate, defect rate) and 8 parts (engine block, ECU chip, battery pack...)
- 3 vehicle models (Sedan, SUV, EV), each with a bill of materials (BOM)
- Open purchase orders / inbound shipments and delivery history

## Features
| Module | What it does | Method |
|---|---|---|
| Demand forecasting | Predicts daily vehicle output per model | Ridge regression (weekday + trend) |
| MRP / replenishment | Turns vehicle forecasts into part demand via the BOM; computes days of cover, stock-out date and order quantity | Lead time + safety stock logic |
| Auto purchase orders | Creates shipments for every part that needs ordering | Rule-based |
| Supplier risk | Scores each supplier LOW/MEDIUM/HIGH | Weighted on-time rate, delay length, defect ppm |
| Production impact | How many vehicles can be built from stock, and the bottleneck part | BOM min-ratio |
| Alerts | Stock-out before shipment arrives, late shipments, orders needed, risky suppliers | Rule-based |

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5002

Try it: click **Simulate disruption** to delay the ECU chip supplier, watch critical alerts and production
impact change, then click **Auto-create purchase orders**.

## API
- `GET  /api/forecast/<Sedan|SUV|EV>?days=14`
- `GET  /api/mrp`
- `POST /api/orders/auto`
- `GET  /api/shipments`
- `POST /api/shipments/<id>/receive` : adds stock
- `GET  /api/suppliers`
- `GET  /api/production-impact`
- `GET  /api/alerts`
- `POST /api/disruption` with `{"supplier_id": 3, "delay_days": 10}`

## Structure
```
app.py            Flask API + dashboard
scm.py            Forecasting, MRP, supplier risk, shipments, alerts
data.py           Synthetic suppliers, parts, BOM, history
requirements.txt
```

## Ideas to extend
Connect ERP/EDI data, add a database, multi-plant networks, GPS/IoT shipment tracking,
better forecasting (Prophet/XGBoost), supplier negotiation costs, and what-if scenario planning.
