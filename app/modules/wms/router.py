from __future__ import annotations

"""Routers del Módulo 3 (WMS + Mantenimiento Predictivo)."""

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response

from ... import database as db
from . import predictive_maintenance as pm
from . import slotting
from . import stock_manager

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


@router.post("/work-orders/{order_id}/complete")
def complete_work_order(order_id: int):
    try:
        return pm.complete_work_order(order_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/zones")
def zones():
    rows = db.query("SELECT * FROM warehouse_zones ORDER BY dock_distance_m")
    for r in rows:
        r["current_skus"] = db.jloads(r.get("current_skus"), [])
    return rows


@router.post("/stock/update")
def update_stock(payload: dict):
    sku = payload.get("sku")
    region_id = payload.get("region_id")
    quantity = payload.get("quantity")
    if not sku or not region_id or quantity is None:
        raise HTTPException(400, "sku, region_id y quantity son requeridos")
    try:
        return stock_manager.update_stock(
            sku=sku,
            region_id=region_id,
            quantity=int(quantity),
            warehouse_zone=payload.get("warehouse_zone"),
            mode=payload.get("mode", "add"),
            reorder_point=payload.get("reorder_point"),
            notes=payload.get("notes"),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.post("/stock/import-csv")
async def import_stock_csv(request: Request, file: UploadFile = File(None)):
    """Acepta subida de archivo multipart o payload JSON con raw_csv."""
    default_mode = request.query_params.get("mode", "add")
    if file:
        content = await file.read()
        content_str = content.decode("utf-8-sig", errors="replace")
    else:
        try:
            body = await request.json()
            content_str = body.get("csv_text", "")
            default_mode = body.get("mode", default_mode)
        except Exception:
            raw = await request.body()
            content_str = raw.decode("utf-8-sig", errors="replace")

    if not content_str.strip():
        raise HTTPException(400, "El contenido CSV está vacío")

    return stock_manager.import_stock_csv(content_str, default_mode=default_mode)



@router.post("/stock/import-excel")
async def import_stock_excel(request: Request, file: UploadFile = File(None)):
    """Acepta subida de archivo Excel (.xlsx / .xls)."""
    default_mode = "add"
    if not file:
        raise HTTPException(400, "Debes subir un archivo Excel (.xlsx o .xls)")

    # Obtener el modo si viene como parámetro de consulta
    mode = request.query_params.get("mode", default_mode)
    content = await file.read()
    if not content:
        raise HTTPException(400, "El archivo Excel está vacío")

    try:
        return stock_manager.import_stock_excel(content, default_mode=mode)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/stock/summary")
def stock_summary():
    return stock_manager.get_stock_summary()


@router.get("/stock/template")
def stock_template():
    return PlainTextResponse(
        stock_manager.get_csv_template(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantilla_stock.csv"},
    )


@router.get("/stock/template-excel")
def stock_template_excel():
    excel_bytes = stock_manager.get_excel_template()
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=plantilla_stock.xlsx"},
    )

