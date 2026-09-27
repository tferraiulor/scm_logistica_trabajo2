from __future__ import annotations

"""Aplicación principal: API REST + Dashboard SPA.

Orquesta los 5 módulos y lanza un agente en background (Módulo 2) que monitoriza
la telemetría de transportistas para detectar retrasos y disparar el bucle
agéntico de forma autónoma.
"""

import asyncio
import json
import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import database as db
from . import seed
from .modules.demand_planning.router import router as demand_router
from .modules.routing.router import router as routing_router
from .modules.wms.router import router as wms_router
from .modules.suppliers.router import router as suppliers_router
from .modules.governance.router import router as governance_router
from .modules import demand_planning, governance, routing, suppliers, wms

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("scm")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


async def _autonomous_agent_loop():
    """Agente en background: monitoriza telemetría y dispara el bucle agéntico."""
    from .modules.routing import agentic_loop

    logger.info("Agentic loop iniciado: monitorizando telemetría de transportistas...")
    tick = 0
    while True:
        await asyncio.sleep(5)
        tick += 1
        try:
            deliveries = db.query(
                "SELECT * FROM deliveries WHERE status IN ('in_transit','planned')"
            )
            for d in deliveries:
                telemetry = db.jloads(d.get("vehicle_telemetry"), {})
                # Avance muy lento del progreso para los camiones en ruta
                if d["status"] == "in_transit":
                    pr = float(telemetry.get("progress_pct", 0) or 0)
                    if pr < 99.0:
                        pr = min(99.0, pr + 0.03)
                        telemetry["progress_pct"] = round(pr, 2)
                        db.execute(
                            "UPDATE deliveries SET vehicle_telemetry=? WHERE id=?",
                            (json.dumps(telemetry), d["id"]),
                        )
                delay = telemetry.get("delay_min", 0) or 0
                # Estado 1: en ruta sin incidencias (mayoría) -> a veces incidente menor (ámbar)
                if d["status"] == "in_transit" and delay == 0 and random.random() < 0.007:
                    incident = random.choice(
                        ["tráfico denso", "tormenta en ruta", "obras en autovía",
                         "accidente vial", "huelga en puerto"]
                    )
                    new_delay = random.randint(15, 45)
                    telemetry["delay_min"] = new_delay
                    telemetry["reason"] = incident
                    db.execute(
                        "UPDATE deliveries SET vehicle_telemetry=? WHERE id=?",
                        (json.dumps(telemetry), d["id"]),
                    )
                    logger.info("Retraso espontáneo: %s +%dmin (%s)", d["shipment_id"], new_delay, incident)
                # Estado 2: retrasado (ámbar) -> la mayoría se recupera; pocas veces escala a DETENIDO
                elif d["status"] == "in_transit" and delay > 0:
                    r = random.random()
                    if r < 0.006:
                        telemetry["delay_min"] = 0
                        telemetry["reason"] = ""
                        db.execute(
                            "UPDATE deliveries SET vehicle_telemetry=?, current_eta=planned_eta WHERE id=?",
                            (json.dumps(telemetry), d["id"]),
                        )
                        logger.info("Recuperación: %s vuelve a estar dentro de lo programado", d["shipment_id"])
                    elif r < 0.01:
                        location = telemetry.get("lat", 40.4), telemetry.get("lng", -3.7)
                        origin_zone = d["destination"][:5] or "R-MAD"
                        try:
                            result = agentic_loop.handle_disruption(
                                shipment_id=d["shipment_id"],
                                delay_min=float(delay),
                                reason=telemetry.get("reason", "incidente") or "incidente",
                                re_tender=True,
                                origin_zone=f"R-{origin_zone[-2:]}" if len(origin_zone) >= 2 else "R-MAD",
                            )
                            logger.info(
                                "Escalada a DETENIDO: %s -> %s (aprobación requerida=%s)",
                                d["shipment_id"], telemetry.get("reason"),
                                result.get("requires_approval"),
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("Fallo en bucle agéntico para %s: %s", d["shipment_id"], exc)
        except Exception:  # noqa: BLE001
            logger.exception("Error en loop agéntico")


DB_READY = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _bootstrap():
        await asyncio.to_thread(seed.seed)
        db.rt_set("current_user", {"name": "Logistics Manager", "role": "logistics_manager"})
        await asyncio.to_thread(demand_planning.forecast_engine.evaluate_forecast_improvement)
        DB_READY.set()

    await _bootstrap()
    agent_task = asyncio.create_task(_autonomous_agent_loop())
    yield
    agent_task.cancel()


app = FastAPI(
    title="Supply Chain Management Platform · Predictive & Agentic",
    description=(
        "Plataforma predictiva y autónoma de gestión de cadena de suministro con "
        "5 módulos: Previsión Touchless, Enrutamiento Agéntico, WMS Dinámico, "
        "Riesgo de Proveedores y Gobernanza HITL."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(demand_router)
app.include_router(routing_router)
app.include_router(wms_router)
app.include_router(suppliers_router)
app.include_router(governance_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "db_ready": DB_READY.is_set(), "modules": 5, "agents": ["agentic_loop"]}


@app.get("/api/dashboard")
def dashboard():
    """Resumen agregado para el panel de control."""
    return {
        "forecast_improvement": demand_planning.forecast_engine.evaluate_forecast_improvement(),
        "supplier_risk": [
            s for s in suppliers.risk_scoring.evaluate_all() if s["score"] < 60
        ],
        "pending_approvals": len(governance.hitl.pending()),
        "open_work_orders": len(db.query("SELECT * FROM work_orders WHERE status='open'")),
        "active_deliveries": len(db.query(
            "SELECT * FROM deliveries WHERE status IN ('in_transit','planned')"
        )),
        "alerts_open": len(db.query("SELECT * FROM alerts WHERE status='open'")),
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/downloads/{filename}")
def download(filename: str):
    """Descarga de la copia portable (exe + LEEME) para compartir con externos."""
    from pathlib import Path as _Path

    safe = _Path(filename).name
    target = BASE_DIR / "downloads" / safe
    if target.is_file():
        return FileResponse(str(target), filename=safe, media_type="application/zip")
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Archivo no encontrado")


@app.get("/")
def index(request: Request):
    return FileResponse(str(STATIC_DIR / "index.html"))
