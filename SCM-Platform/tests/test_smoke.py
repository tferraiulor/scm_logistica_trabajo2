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
    assert body["mape_improvement_pct"] is not None and body["mape_improvement_pct"] > 0
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
