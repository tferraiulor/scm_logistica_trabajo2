from __future__ import annotations

"""MÓDULO 3a: Distribución Dinámica de Inventario (Slotting).

Analiza la rotación diaria de productos y reconfigura el mapa del almacén,
sugiriendo colocar los SKUs de alta prioridad o demanda inmediata cerca de los
muelles de salida (dock-distance mínima). Produce una propuesta de re-slotting
que puede ejecutarse manual (HITL) o auto-aplicarse si el impacto es bajo.
"""

import json
from datetime import datetime, timedelta

from ... import database as db
from ...core import security
from ...core.security import ApprovalLevel


def _turnover(sku: str, region_id: str, days: int = 30) -> float:
    since = (datetime.now() - timedelta(days=days)).date().isoformat()
    rows = db.query(
        """SELECT SUM(units) AS s FROM sales_history
           WHERE sku=? AND region_id=? AND date>=?""",
        (sku, region_id, since),
    )
    return float(rows[0]["s"] or 0)


def _zonification_priority(zone_id: str) -> int:
    """Cuanto menor la distancia al muelle, mayor prioridad (0 = más cerca)."""
    zone = db.query_one("SELECT dock_distance_m FROM warehouse_zones WHERE zone_id=?", (zone_id,))
    return int(zone["dock_distance_m"]) if zone else 99


def compute_slotting(region_id: str = "R-MAD") -> dict:
    """Reordena el inventario según rotación para acercar lo caliente al muelle."""
    stock = db.query(
        """SELECT s.sku, s.on_hand, s.warehouse_zone, p.name
           FROM stock s JOIN products p ON p.sku=s.sku
           WHERE s.region_id=?""",
        (region_id,),
    )
    scored = []
    for row in stock:
        turnover = _turnover(row["sku"], region_id)
        priority = _zonification_priority(row["warehouse_zone"])
        demand_score = turnover / max(row["on_hand"], 1)
        scored.append({
            "sku": row["sku"],
            "name": row["name"],
            "on_hand": row["on_hand"],
            "current_zone": row["warehouse_zone"],
            "current_priority": priority,
            "turnover_30d": round(turnover, 1),
            "demand_score": round(demand_score, 3),
        })

    # Ordenar por demanda_score descendente (lo más demandado primero)
    scored.sort(key=lambda x: x["demand_score"], reverse=True)

    # Mapa de zonas ordenadas por cercanía al muelle
    zones_sorted = sorted(
        db.query("SELECT * FROM warehouse_zones"), key=lambda z: z["dock_distance_m"]
    )

    # Asignar slots de alta rotación a zonas cercanas al muelle
    suggestions = []
    high_turnover = scored[: max(1, len(scored) // 3)]
    for item in high_turnover:
        near = min(zones_sorted[:3], key=lambda z: z["dock_distance_m"])
        if near["zone_id"] != item["current_zone"]:
            suggestions.append({
                "sku": item["sku"],
                "name": item["name"],
                "from_zone": item["current_zone"],
                "to_zone": near["zone_id"],
                "reason": "alta rotación",
                "demand_score": item["demand_score"],
            })

    # Propuesta con gobernanza: mover un SKU es bajo impacto => auto-ejecutable
    rec_id = None
    level = None
    if suggestions:
        estimated_impact_eur = len(suggestions) * 4.0  # coste de mano de obra
        factors = {
            "n_slots_moved": len(suggestions),
            "method": "turnover_ranked",
            "data_verified": True,
            "zone_distances": {z["zone_id"]: z["dock_distance_m"] for z in zones_sorted},
        }
        level, rec_id = security.classify_action(
            module="wms",
            action="reslot_inventory",
            description=f"Re-slotting de {len(suggestions)} SKU de alta rotación hacia el muelle",
            estimated_impact_eur=estimated_impact_eur,
            factors=factors,
            confidence=0.9,
        ) if suggestions else (None, None)

    return {
        "region_id": region_id,
        "scored_inventory": scored,
        "suggested_moves": suggestions,
        "requires_approval": level == ApprovalLevel.REQUIRES_APPROVAL if level else False,
        "rec_id": rec_id,
    }


def apply_slotting(payload: dict) -> dict:
    """Aplica los movimientos sugeridos (manual desde UI o ejecutado por agente)."""
    moves = payload.get("moves", [])
    moved = 0
    for mv in moves:
        stock = db.query_one(
            "SELECT warehouse_zone FROM stock WHERE sku=? AND region_id=?",
            (mv["sku"], payload.get("region_id", "R-MAD")),
        )
        if stock:
            db.execute(
                "UPDATE stock SET warehouse_zone=? WHERE sku=? AND region_id=?",
                (mv["to_zone"], mv["sku"], payload.get("region_id", "R-MAD")),
            )
            moved += 1
    return {"moves_applied": moved, "region_id": payload.get("region_id", "R-MAD")}
