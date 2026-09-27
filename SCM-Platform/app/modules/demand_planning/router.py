from __future__ import annotations

"""Routers del Módulo 1 (Demand Planning)."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from ... import database as db
from . import forecast_engine

router = APIRouter(prefix="/api/demand", tags=["demand"])


@router.get("/skus")
def list_skus():
    return db.query("SELECT sku, name, category FROM products ORDER BY sku")


@router.get("/regions")
def list_regions():
    return db.query("SELECT region_id, name FROM regions ORDER BY region_id")


@router.post("/forecast")
def forecast(payload: dict):
    sku = payload.get("sku")
    region = payload.get("region_id")
    horizon = payload.get("horizon_days")
    if not sku or not region:
        raise HTTPException(400, "sku y region_id son obligatorios")
    result = forecast_engine.run_forecast(sku, region, horizon)
    alerts = forecast_engine.check_alerts(sku, region, result)
    return {**result, "alerts": alerts}


@router.get("/improvement")
def improvement():
    return forecast_engine.evaluate_forecast_improvement()


@router.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    content = await file.read()
    return forecast_engine.ingest_sales_file(file.filename or "input", content)


@router.get("/stock")
def stock_all(region_id: str = None):
    """Retorna todo el inventario. Si se pasa region_id filtra por región."""
    sql = """SELECT s.sku, p.name, s.region_id, s.on_hand, s.reorder_point, s.warehouse_zone,
                    p.category,
                    ROUND(100.0 * s.on_hand / MAX(s.reorder_point * 3, 1)) AS fill_pct
             FROM stock s JOIN products p ON p.sku=s.sku"""
    params: tuple = ()
    if region_id:
        sql += " WHERE s.region_id=?"
        params = (region_id,)
    sql += " ORDER BY s.on_hand ASC"
    return db.query(sql, params)


@router.get("/stock/critical")
def stock_critical():
    return db.query(
        """SELECT s.sku, p.name, s.region_id, s.on_hand, s.reorder_point
           FROM stock s JOIN products p ON p.sku=s.sku
           WHERE s.on_hand <= s.reorder_point ORDER BY s.on_hand ASC"""
    )


@router.get("/alerts")
def alerts():
    return db.query(
        """SELECT * FROM alerts WHERE module='demand' ORDER BY id DESC LIMIT 100"""
    )
