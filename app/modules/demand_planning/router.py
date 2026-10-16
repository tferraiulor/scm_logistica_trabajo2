from __future__ import annotations

"""Routers del Módulo 1 (Demand Planning)."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from ... import database as db
from . import forecast_engine
from . import sales_engine

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
    sql = """SELECT s.sku, 
                    COALESCE(p.name, s.sku) AS name, 
                    s.region_id, 
                    s.on_hand, 
                    s.reorder_point, 
                    s.warehouse_zone,
                    COALESCE(p.category, 'general') AS category,
                    ROUND(100.0 * s.on_hand / MAX(s.reorder_point * 3, 1)) AS fill_pct
             FROM stock s 
             LEFT JOIN products p ON p.sku = s.sku"""
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


@router.post("/sales/record")
def record_sale(payload: dict):
    sku = payload.get("sku")
    region_id = payload.get("region_id")
    units = payload.get("units")
    if not sku or not region_id or not units:
        raise HTTPException(400, "sku, region_id y units son requeridos")
    try:
        return sales_engine.record_sale(
            sku=sku,
            region_id=region_id,
            units=int(units),
            price_eur=payload.get("price_eur"),
            channel=payload.get("channel", "retail"),
            date_str=payload.get("date"),
            customer_notes=payload.get("notes"),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.post("/sales/batch-generate")
def batch_generate_sales(payload: dict = None):
    count = int(payload.get("count", 10)) if payload else 10
    intensity = payload.get("intensity") if payload else None
    return sales_engine.batch_generate_sales(count=count, intensity=intensity)


@router.post("/sales/auto-config")
def set_auto_sales_config(payload: dict):
    return sales_engine.set_auto_config(
        enabled=payload.get("enabled"),
        interval_sec=payload.get("interval_sec"),
        intensity=payload.get("intensity"),
        channels=payload.get("channels"),
        regions=payload.get("regions"),
    )


@router.get("/sales/auto-status")
def get_auto_sales_status():
    return sales_engine.get_auto_status()


@router.get("/sales/feed")
def sales_feed(limit: int = 30):
    return sales_engine.get_recent_sales(limit=limit)


@router.get("/sales/kpis")
def sales_kpis():
    return sales_engine.get_sales_kpis()

