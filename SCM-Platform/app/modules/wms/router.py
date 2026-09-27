from __future__ import annotations

"""Routers del Módulo 3 (WMS + Mantenimiento Predictivo)."""

from fastapi import APIRouter

from ... import database as db
from . import predictive_maintenance as pm
from . import slotting

router = APIRouter(prefix="/api/wms", tags=["wms"])


@router.get("/slotting")
def slotting_proposal(region_id: str = "R-MAD"):
    return slotting.compute_slotting(region_id)


@router.post("/slotting/apply")
def apply_slotting(payload: dict):
    return slotting.apply_slotting(payload)


@router.post("/telemetry/simulate")
def simulate_telemetry(payload: dict = None):
    return pm.simulate_telemetry(payload)


@router.post("/telemetry/ingest")
def ingest_telemetry(payload: dict):
    records = payload.get("records", [])
    return pm.ingest_telemetry(records)


@router.get("/telemetry")
def telemetry(machine_id: str = None):
    return pm.machine_telemetry(machine_id)


@router.get("/machines")
def machines():
    return db.query("SELECT * FROM machines ORDER BY machine_id")


@router.get("/work-orders")
def work_orders(status: str = None):
    return pm.work_orders(status)


@router.get("/zones")
def zones():
    rows = db.query("SELECT * FROM warehouse_zones ORDER BY dock_distance_m")
    for r in rows:
        r["current_skus"] = db.jloads(r.get("current_skus"), [])
    return rows
