"""Flask API + dashboard for the Automotive Supply Chain Management Platform."""
from flask import Flask, jsonify, request, render_template_string

from scm import SupplyChain

app = Flask(__name__)
scm = SupplyChain()

DASHBOARD = """
<!doctype html>
<title>Automotive SCM</title>
<style>
  body{font-family:system-ui,sans-serif;margin:2rem auto;max-width:1040px;padding:0 1rem;color:#222}
  section{margin:1.8rem 0} table{border-collapse:collapse;width:100%;font-size:14px}
  th,td{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}
  button{padding:8px 14px;border:0;border-radius:6px;background:#2563eb;color:#fff;cursor:pointer;margin-right:8px}
  button.warn{background:#dc2626}
  .critical,.CRITICAL,.HIGH{color:#b91c1c;font-weight:600}.warning,.WARNING,.MEDIUM{color:#b45309}
  .info,.OK,.LOW{color:#15803d}
</style>
<h1>Automotive Supply Chain Management Platform</h1>
<p><button onclick="act('/api/orders/auto')">Auto-create purchase orders</button>
   <button class="warn" onclick="disrupt()">Simulate disruption (SiliconEdge Micro +10 days)</button></p>

<section><h2>Alerts</h2><table id="alerts"></table></section>
<section><h2>Production impact</h2><table id="prod"></table></section>
<section><h2>Parts planning (MRP)</h2><table id="mrp"></table></section>
<section><h2>Shipments</h2><table id="ship"></table></section>
<section><h2>Supplier risk</h2><table id="sup"></table></section>

<script>
const J = async (u, o) => (await fetch(u, o)).json();
const CLS = ['severity','status','risk_level'];
const rows = (id, cols, data) => {
  document.getElementById(id).innerHTML = '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr>' +
    (data.length ? data.map(r => '<tr>' + cols.map(c => `<td class="${CLS.includes(c)?r[c]:''}">${r[c] ?? ''}</td>`).join('') + '</tr>').join('')
                 : `<tr><td colspan="${cols.length}">None</td></tr>`);
};
async function load(){
  rows('alerts', ['severity','message'], await J('/api/alerts'));
  rows('prod', ['model','avg_daily_plan','vehicles_buildable_from_stock','days_of_production','bottleneck_part'], await J('/api/production-impact'));
  rows('mrp', ['part','supplier','stock','avg_daily_demand','days_of_cover','lead_time_days','inbound_qty','order_qty','status','stockout_date'], await J('/api/mrp'));
  rows('ship', ['shipment_id','part','supplier','qty','promised','eta','delay_days','status'], await J('/api/shipments'));
  rows('sup', ['name','country','lead_time_days','on_time_pct','avg_delay_days','defect_ppm','risk_score','risk_level'], await J('/api/suppliers'));
}
async function act(u){ await J(u, {method:'POST'}); load(); }
async function disrupt(){
  await J('/api/disruption', {method:'POST', headers:{'Content-Type':'application/json'},
                              body: JSON.stringify({supplier_id:3, delay_days:10})});
  load();
}
load();
</script>
"""


@app.get("/")
def home():
    return render_template_string(DASHBOARD)


@app.get("/api/forecast/<model>")
def forecast(model):
    if model not in scm.model_fc:
        return jsonify(error="unknown model"), 404
    return jsonify(scm.forecast(model, request.args.get("days", 14, type=int)))


@app.get("/api/mrp")
def mrp():
    return jsonify(scm.mrp())


@app.post("/api/orders/auto")
def auto_order():
    return jsonify(orders=scm.auto_order())


@app.get("/api/shipments")
def shipments():
    return jsonify(scm.shipment_list())


@app.post("/api/shipments/<int:sid>/receive")
def receive(sid):
    s = scm.receive_shipment(sid)
    return (jsonify(s), 200) if s else (jsonify(error="not found or already received"), 404)


@app.get("/api/suppliers")
def suppliers():
    return jsonify(scm.supplier_scores())


@app.get("/api/production-impact")
def production_impact():
    return jsonify(scm.production_impact())


@app.get("/api/alerts")
def alerts():
    return jsonify(scm.alerts())


@app.post("/api/disruption")
def disruption():
    body = request.get_json(force=True)
    sid = int(body["supplier_id"])
    if sid not in scm.suppliers.index:
        return jsonify(error="unknown supplier"), 404
    n = scm.disrupt_supplier(sid, int(body.get("delay_days", 7)))
    return jsonify(shipments_delayed=n)


if __name__ == "__main__":
    app.run(debug=True, port=5002)
