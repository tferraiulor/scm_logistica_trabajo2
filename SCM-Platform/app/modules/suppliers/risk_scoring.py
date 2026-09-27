from __future__ import annotations

"""MÓDULO 4: Evaluación de Riesgo de Proveedores (Supplier Risk Scoring).

Genera un score ponderado 0-100 por proveedor evaluando:
  - Histórico de cumplimiento de entregas (OTIF).
  - Estabilidad financiera declarada.
  - Factores de riesgo geopolíticos / desastres naturales según ubicación.

Ante una caída crítica del score de un proveedor clave, sugiere automáticamente
3 proveedores alternativos de la base de datos que cubran el mismo material.
Cada "alternativa crítica" se registra con trazabilidad (Módulo 5).
"""

import json
from typing import Optional

from ... import database as db
from ...core import security
from ...core.security import ApprovalLevel

WEIGHTS = {"otif": 0.5, "financial": 0.3, "geo": 0.2}


def compute_score(supplier: dict) -> dict:
    """Score ponderado 0-100 (mayor = menor riesgo)."""
    otif = float(supplier["otif_rate"])           # 0..1
    financial = float(supplier["financial_stability"]) / 100  # 0..1
    geo = 1 - (float(supplier["geo_risk"]) / 100)             # 0..1 (invertido)
    score = (
        otif * WEIGHTS["otif"]
        + financial * WEIGHTS["financial"]
        + geo * WEIGHTS["geo"]
    ) * 100
    return {
        "score": round(score, 1),
        "breakdown": {
            "otif": round(otif, 3),
            "financial": round(financial, 3),
            "geo": round(geo, 3),
        },
        "risk_level": _risk_level(score),
    }


def _risk_level(score: float) -> str:
    if score < 30:
        return "critical"
    if score < 60:
        return "high"
    if score < 80:
        return "medium"
    return "low"


def evaluate_supplier(supplier_id: str, persist: bool = True) -> dict:
    sup = db.query_one("SELECT * FROM suppliers WHERE supplier_id=?", (supplier_id,))
    if not sup:
        raise ValueError(f"Proveedor {supplier_id} no encontrado")
    result = compute_score(sup)
    result.update({"supplier_id": supplier_id, "name": sup["name"],
                    "material": sup["material"]})
    if persist:
        db.execute(
            """INSERT INTO supplier_score_history (supplier_id, score, breakdown, evaluated_at)
               VALUES (?,?,?,?)""",
            (supplier_id, result["score"],
             json.dumps(result["breakdown"]), db.now_iso()),
        )
    return result


def evaluate_all() -> list[dict]:
    suppliers = db.query("SELECT * FROM suppliers")
    out = []
    for s in suppliers:
        out.append(evaluate_supplier(s["supplier_id"], persist=False))
    return sorted(out, key=lambda x: x["score"])


def _geo_risk_label(supplier: dict) -> str:
    g = float(supplier["geo_risk"])
    if g >= 60:
        return "Alto (desastres/geopolítica)"
    if g >= 30:
        return "Moderado"
    return "Bajo"


def suggest_alternatives(supplier_id: str, n: int = 3) -> dict:
    """Sugiere proveedores alternativos que cubran el mismo material."""
    sup = db.query_one("SELECT * FROM suppliers WHERE supplier_id=?", (supplier_id,))
    if not sup:
        raise ValueError(f"Proveedor {supplier_id} no encontrado")
    target_material = sup["material"]

    candidates = db.query(
        "SELECT * FROM suppliers WHERE material=? AND supplier_id!=? AND status='active'",
        (target_material, supplier_id),
    )
    if not candidates:
        return {"supplier_id": supplier_id, "alternatives": [],
                "critical": False, "note": "sin alternativas para el material"}

    scored = []
    for c in candidates:
        cs = compute_score(c)
        cost_diff_pct = (float(sup["unit_cost"]) - float(c["unit_cost"])) / max(
            float(sup["unit_cost"]), 0.001
        )
        scored.append({
            "supplier_id": c["supplier_id"],
            "name": c["name"],
            "country": c["country"],
            "material": c["material"],
            "score": cs["score"],
            "risk_level": cs["risk_level"],
            "unit_cost": c["unit_cost"],
            "geo_risk_label": _geo_risk_label(c),
            "cost_vs_current_pct": round(cost_diff_pct * 100, 1),
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    alternatives = scored[:n]

    # ¿Score crítico del proveedor evaluado? => registrar con trazabilidad
    my_score = compute_score(sup)["score"]
    critical = my_score < 30
    rec_id = None
    if critical and alternatives:
        factors = {
            "current_score": my_score,
            "material": target_material,
            "alternatives_proposed": [a["supplier_id"] for a in alternatives],
            "data_verified": True,
            "otif": sup["otif_rate"],
            "geo_risk": sup["geo_risk"],
        }
        level, rec_id = security.classify_action(
            module="suppliers",
            action="suggest_alternatives_critical",
            description=(
                f"Score crítico ({my_score}) de proveedor clave {sup['name']}. "
                f"{len(alternatives)} alternativas sugeridas para {target_material}."
            ),
            estimated_impact_eur=4000.0,
            factors=factors,
            confidence=0.9,
        )
        return {
            "supplier_id": supplier_id,
            "name": sup["name"],
            "current_score": my_score,
            "critical": True,
            "alternatives": alternatives,
            "requires_approval": level == ApprovalLevel.REQUIRES_APPROVAL,
            "rec_id": rec_id,
        }
    return {"supplier_id": supplier_id, "current_score": my_score,
            "critical": critical, "alternatives": alternatives}


def history(supplier_id: str) -> list[dict]:
    rows = db.query(
        """SELECT * FROM supplier_score_history WHERE supplier_id=? ORDER BY id DESC LIMIT 50""",
        (supplier_id,),
    )
    for r in rows:
        r["breakdown"] = db.jloads(r.get("breakdown"), {})
    return rows
