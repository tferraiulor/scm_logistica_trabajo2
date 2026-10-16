from __future__ import annotations

"""Smoke tests end-to-end de los 5 módulos usando el TestClient de FastAPI."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configurar una BD temporal para los tests (debe hacerse antes de importar app)
import app.config as config

_TMP_DB = os.path.join(os.path.dirname(__file__), "test_scm.db")
config.SQLITE_PATH = os.path.normpath(_TMP_DB)
config.DATABASE_URL = f"sqlite:///{_TMP_DB}"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "forecast_improvement" in body
    assert "pending_approvals" in body


# ---- MÓDULO 1 ----
def test_demand_forecast(client):
    r = client.post("/api/demand/forecast",
                    json={"sku": "SKU-PLS-001", "region_id": "R-MAD", "horizon_days": 14})
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"]
    assert len(body["projections"]) == 14
    assert body["mape"] is not None
    assert body["mape_improvement_pct"] is not None
    assert "alerts" in body


def test_demand_improvement(client):
    r = client.get("/api/demand/improvement")
    assert r.status_code == 200
    assert r.json()["avg_model_mape"] is not None


def test_demand_stock_alerts(client):
    r = client.get("/api/demand/stock")
    assert r.status_code == 200


def test_demand_ingest_csv(client):
    csv_data = "date,sku,region_id,units,price_eur,channel\n2026-01-01,SKU-PLS-001,R-MAD,10,120,erp\n"
    r = client.post("/api/demand/ingest",
                    files={"file": ("ventas.csv", csv_data, "text/csv")})
    assert r.status_code == 200
    assert r.json()["rows_ingested"] == 1


# ---- MÓDULO 2 ----
def test_routing_carriers(client):
    r = client.get("/api/routing/carriers")
    assert r.status_code == 200
    assert len(r.json()) >= 5


def test_routing_optimize(client):
    r = client.post("/api/routing/optimize", json={
        "stops": [
            {"id": "A", "name": "Cliente A", "lat": 40.42, "lng": -3.70, "service_min": 15},
            {"id": "B", "name": "Cliente B", "lat": 40.44, "lng": -3.66, "service_min": 20},
            {"id": "C", "name": "Cliente C", "lat": 40.40, "lng": -3.72, "service_min": 10},
        ],
        "origin": {"lat": 40.41, "lng": -3.70},
        "carrier_id": "C-1", "region": "R-MAD",
    })
    assert r.status_code == 200
    body = r.json()
    assert len(body["order"]) == 3
    assert body["total_km"] > 0


def test_routing_agentic_loop(client):
    # Escenario: re-tender de bajo impacto (debe auto-ejecutarse)
    r = client.post("/api/routing/simulate-disruption", json={
        "shipment_id": "SHIP-1000", "delay_min": 25,
        "reason": "obras en autovía", "re_tender": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["impact"]["delay_min"] == 25
    assert "actions_taken" in body


def test_routing_deliveries(client):
    r = client.get("/api/routing/deliveries")
    assert r.status_code == 200


# ---- MÓDULO 3 ----
def test_wms_slotting(client):
    r = client.get("/api/wms/slotting")
    assert r.status_code == 200


def test_wms_telemetry_simulate(client):
    r = client.post("/api/wms/telemetry/simulate", json={})
    assert r.status_code == 200
    assert r.json()["records"] > 0


def test_wms_work_orders(client):
    r = client.get("/api/wms/work-orders")
    assert r.status_code == 200


def test_wms_machines(client):
    r = client.get("/api/wms/machines")
    assert r.status_code == 200
    assert len(r.json()) >= 5


# ---- MÓDULO 4 ----
def test_supplier_scores(client):
    r = client.get("/api/suppliers/scores")
    assert r.status_code == 200
    scores = r.json()
    assert len(scores) == 10
    assert all(0 <= s["score"] <= 100 for s in scores)


def test_supplier_alternatives(client):
    # Wei Electronics (SP-ELC-02) tiene score crítico => alternativas + rec_id
    r = client.get("/api/suppliers/alternatives/SP-ELC-02")
    assert r.status_code == 200
    body = r.json()
    assert body["critical"] is True
    assert len(body["alternatives"]) == 3
    assert body["rec_id"] is not None


# ---- MÓDULO 5 ----
def test_governance_matrix(client):
    r = client.get("/api/governance/matrix")
    assert r.status_code == 200
    assert len(r.json()) >= 5


def test_governance_pending_and_trace(client):
    r = client.get("/api/governance/pending")
    assert r.status_code == 200
    r2 = client.get("/api/governance/trace")
    assert r2.status_code == 200
    assert isinstance(r2.json(), list)


def test_hitl_approval_flow(client):
    # Crear una recomendación que requiere aprobación (alto impacto)
    from app.core import security
    from app.core.security import ApprovalLevel
    level, rec_id = security.classify_action(
        module="quiz", action="high_cost_test",
        description="Prueba de aprobación alto coste",
        estimated_impact_eur=20000.0,
        factors={"k": "v"},
        confidence=0.9,
        is_emergency_air_freight=True,
    )
    assert level == ApprovalLevel.REQUIRES_APPROVAL
    r = client.post(f"/api/governance/approve/{rec_id}", json={"actor": "Logistics Manager"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Supply Chain" in r.text
    assert "Cargar Stock" in r.text
    assert "Registro de Ventas" in r.text
    assert "Google Maps" in r.text


# ---- PESTAÑA CARGA DE STOCK ----
def test_wms_stock_update_manual(client):
    # Probar suma de stock
    r = client.post("/api/wms/stock/update", json={
        "sku": "SKU-PLS-001",
        "region_id": "R-MAD",
        "quantity": 50,
        "mode": "add",
        "warehouse_zone": "Z-STO-A",
        "reorder_point": 40,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["sku"] == "SKU-PLS-001"
    assert body["on_hand"] >= 50

    # Probar fijación de stock exacto
    r2 = client.post("/api/wms/stock/update", json={
        "sku": "SKU-PLS-001",
        "region_id": "R-MAD",
        "quantity": 125,
        "mode": "set",
    })
    assert r2.status_code == 200
    assert r2.json()["on_hand"] == 125


def test_wms_stock_import_csv(client):
    csv_data = (
        "sku,region_id,warehouse_zone,quantity,reorder_point\n"
        "SKU-TEST-001,R-MAD,Z-STO-A,75,30\n"
        "SKU-TEST-002,R-BCN,Z-STO-B,45,20\n"
    )
    r = client.post("/api/wms/stock/import-csv", json={
        "csv_text": csv_data,
        "mode": "set",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["rows_processed"] == 2
    assert body["rows_updated"] == 2


def test_wms_stock_summary_and_template(client):
    r = client.get("/api/wms/stock/summary")
    assert r.status_code == 200
    assert "total_units" in r.json()
    assert "total_skus" in r.json()

    r2 = client.get("/api/wms/stock/template")
    assert r2.status_code == 200
    assert "sku,region_id" in r2.text


# ---- PESTAÑA REGISTRO DE VENTAS ----
def test_sales_record_decrements_stock(client):
    # 1. Asegurar stock conocido
    client.post("/api/wms/stock/update", json={
        "sku": "SKU-BAT-001",
        "region_id": "R-MAD",
        "quantity": 80,
        "mode": "set",
        "reorder_point": 30,
    })

    # 2. Registrar venta de 20 unidades
    r = client.post("/api/demand/sales/record", json={
        "sku": "SKU-BAT-001",
        "region_id": "R-MAD",
        "units": 20,
        "price_eur": 65.0,
        "channel": "retail",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["units"] == 20
    assert body["current_stock"] == 60
    assert body["total_eur"] == 1300.0


def test_sales_batch_and_kpis(client):
    r = client.post("/api/demand/sales/batch-generate", json={"count": 5, "intensity": "low"})
    assert r.status_code == 200
    assert len(r.json()) == 5

    r_feed = client.get("/api/demand/sales/feed")
    assert r_feed.status_code == 200
    assert len(r_feed.json()) > 0

    r_kpi = client.get("/api/demand/sales/kpis")
    assert r_kpi.status_code == 200
    body = r_kpi.json()
    assert body["today_transactions"] > 0
    assert body["today_revenue_eur"] > 0


def test_sales_auto_config(client):
    r = client.post("/api/demand/sales/auto-config", json={
        "enabled": False,
        "interval_sec": 8,
        "intensity": "high",
    })
    assert r.status_code == 200
    st = r.json()
    assert st["enabled"] is False
    assert st["interval_sec"] == 8

    # Restaurar a activo
    client.post("/api/demand/sales/auto-config", json={"enabled": True, "interval_sec": 5})


def test_stockout_alert_generation(client):
    """Verifica que al caer el stock por debajo del reorder_point no falle db.jdumps y genere alerta."""
    r = client.post("/api/wms/stock/update", json={
        "sku": "SKU-CON-001",
        "region_id": "R-MAD",
        "quantity": 10,
        "mode": "set",
        "reorder_point": 50,
    })
    assert r.status_code == 200
    assert r.json()["on_hand"] == 10

    r2 = client.post("/api/demand/sales/record", json={
        "sku": "SKU-CON-001",
        "region_id": "R-MAD",
        "units": 5,
        "price_eur": 12.5,
        "channel": "retail",
    })
    assert r2.status_code == 200
    assert r2.json()["alert"] is not None
    assert r2.json()["current_stock"] == 5


def test_wms_excel_template(client):
    r = client.get("/api/wms/stock/template-excel")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers.get("content-type", "")


def test_wms_work_order_completion(client):
    # Simular telemetría y obtener órdenes
    client.post("/api/wms/telemetry/simulate", json={})
    orders = client.get("/api/wms/work-orders").json()
    if orders:
        oid = orders[0]["id"]
        r = client.post(f"/api/wms/work-orders/{oid}/complete")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"


def test_governance_role_switch_and_rbac(client):
    # Cambiar a rol analyst y verificar que no puede aprobar
    r_role = client.post("/api/governance/role", json={"role": "analyst"})
    assert r_role.status_code == 200
    assert r_role.json()["current_role"] == "analyst"
    assert r_role.json()["can_authorize"] is False

    from app.core import security
    _, rec_id = security.classify_action(
        module="routing", action="test_rbac",
        description="Prueba RBAC analyst",
        estimated_impact_eur=15000.0,
        factors={}, confidence=0.85,
    )
    r_app = client.post(f"/api/governance/approve/{rec_id}", json={})
    assert r_app.status_code == 403

    # Restaurar a logistics_manager y aprobar
    r_mgr = client.post("/api/governance/role", json={"role": "logistics_manager"})
    assert r_mgr.status_code == 200
    assert r_mgr.json()["can_authorize"] is True
    r_ok = client.post(f"/api/governance/approve/{rec_id}", json={})
    assert r_ok.status_code == 200
    assert r_ok.json()["status"] == "approved"


def test_real_logistics_dataset(client):
    r = client.get("/api/logistics/metrics")
    assert r.status_code == 200
    m = r.json()
    assert m["total_orders"] == 4282
    assert m["delayed_orders"] == 3135
    assert len(m["regions"]) == 3

    # Filtrado por búsqueda, motivo de devolución y paginación
    r_orders = client.get("/api/logistics/orders?region=SP&status=Atrasado&return_reason=Produto%20Errado&limit=10&offset=0")
    assert r_orders.status_code == 200
    body = r_orders.json()
    assert body["total"] > 0
    assert len(body["orders"]) <= 10
    assert all(o["destination"] == "SP" and o["delay_status"] == "Atrasado" for o in body["orders"])

    # Búsqueda por texto libre
    r_q = client.get("/api/logistics/orders?q=PED-&limit=5")
    assert r_q.status_code == 200
    assert r_q.json()["total"] == 4282

