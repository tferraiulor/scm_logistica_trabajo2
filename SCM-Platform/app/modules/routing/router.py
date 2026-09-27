from __future__ import annotations

"""Routers del Módulo 2 (Routing + Agentic Loop)."""

from fastapi import APIRouter, HTTPException

from ... import database as db
from . import agentic_loop, route_engine

router = APIRouter(prefix="/api/routing", tags=["routing"])


@router.get("/carriers")
def carriers():
    rows = db.query("SELECT * FROM carriers ORDER BY rating DESC")
    for r in rows:
        r["zones"] = db.jloads(r.get("zones"), [])
    return rows


@router.post("/register-carrier")
def register_carrier(payload: dict):
    return agentic_loop.register(payload)


@router.post("/optimize")
def optimize(payload: dict):
    stops = payload.get("stops", [])
    origin = payload.get("origin", {"lat": 40.4168, "lng": -3.7038})
    carrier = payload.get("carrier_id", "C-1")
    region = payload.get("region", "R-MAD")
    try:
        return route_engine.optimize_route(stops, origin, carrier, region)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.post("/simulate-disruption")
def simulate_disruption(payload: dict):
    try:
        return agentic_loop.simulate_disruption(payload)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/deliveries")
def deliveries():
    rows = db.query(
        """SELECT d.id, d.shipment_id, d.carrier_id, c.name AS carrier_name,
                  d.origin, d.destination, d.customer_id, d.planned_eta, d.current_eta,
                  d.status, d.required_window_start, d.required_window_end, d.cost_eur,
                  d.vehicle_telemetry, d.incident_log
           FROM deliveries d LEFT JOIN carriers c ON c.carrier_id=d.carrier_id
           ORDER BY d.id DESC LIMIT 100"""
    )
    for r in rows:
        telemetry = db.jloads(r.get("vehicle_telemetry"), {})
        r["lat"] = telemetry.get("lat", 0)
        r["lng"] = telemetry.get("lng", 0)
        r["speed_kmh"] = telemetry.get("speed_kmh", 0)
        r["progress_pct"] = telemetry.get("progress_pct", 0)
        r["delay_min"] = telemetry.get("delay_min", 0)
        r["telemetry_status"] = telemetry.get("status", r.get("status"))
        r["telemetry_reason"] = telemetry.get("reason", "")
        r["incidents"] = db.jloads(r.get("incident_log"), [])
    return rows


@router.get("/logs")
def agent_logs():
    """Panel de logs del bucle agéntico."""
    return db.query(
        """SELECT * FROM alerts WHERE module='routing' ORDER BY id DESC LIMIT 100"""
    )
