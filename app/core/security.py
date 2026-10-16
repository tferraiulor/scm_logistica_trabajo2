from __future__ import annotations

"""Control de autorización humana (Human-in-the-Loop) y RBAC.

Define qué decisiones de los agentes autónomos pueden auto-ejecutarse y cuáles
requieren aprobación obligatoria de un Logistics Manager, basado en el impacto
financiero/legal/estratégico. También registra la trazabilidad de cada decisión
en la tabla recommendation_log para su auditoría.
"""

import json
from enum import Enum
from typing import Any, Optional

from .. import config
from .. import database as db


class ApprovalLevel(Enum):
    AUTO = "auto"                       # se ejecuta sin intervención
    NOTIFY = "notify"                   # se ejecuta y notifica
    REQUIRES_APPROVAL = "requires_approval"  # bloquea hasta aprobación


# Roles disponibles en la plataforma
ROLES = {
    "logistics_manager",   # puede autorizar decisiones de alto coste
    "supply_planner",      # gestor de previsiones
    "ops_agent",           # operador de almacén/rutas
    "analyst",             # solo lectura
    "auditor",             # solo lectura de gobernanza
}


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str)


def _current_user() -> dict:
    return db.rt_get("current_user", {"role": "logistics_manager", "name": "demo"})


def current_role() -> str:
    return _current_user().get("role", "logistics_manager")


def can_authorize() -> bool:
    role = current_role()
    return role in {"logistics_manager", "supply_planner"}


def classify_action(
    module: str,
    action: str,
    description: str,
    estimated_impact_eur: float,
    factors: dict[str, Any],
    confidence: float,
    is_contract_cancel: bool = False,
    is_emergency_air_freight: bool = False,
) -> tuple[ApprovalLevel, int]:
    """Devuelve (nivel de aprobación, row_id del log de recomendación)."""

    requires_approval = True  # gobernanza prudente: aprobación humana por defecto

    # Excepción: acciones de bajo impacto y reversibles en lista blanca
    # pueden auto-ejecutarse si se mantienen dentro del coste y confianza mínimos.
    if (
        action in config.HITL_AUTO_EXECUTE_ACTIONS
        and estimated_impact_eur <= config.HITL_AUTO_MAX_IMPACT_EUR
        and confidence >= config.HITL_AUTO_MIN_CONFIDENCE
    ):
        requires_approval = False

    # Límites estrictos de gobernanza: alto coste financiero o contractual
    if estimated_impact_eur >= config.HITL_FINANCIAL_THRESHOLD_EUR:
        requires_approval = True
    if config.HITL_CONTRACT_CANCEL_REQUIRES_APPROVAL and is_contract_cancel:
        requires_approval = True
    if is_emergency_air_freight:
        requires_approval = True

    if requires_approval:
        level = ApprovalLevel.REQUIRES_APPROVAL
        status = "requires_approval"
    else:
        # Autónomo: se ejecuta y se notifica en logs/trazabilidad
        level = ApprovalLevel.NOTIFY
        status = "auto_executed"

    row_id = db.execute(
        """INSERT INTO recommendation_log
           (module, action, description, factors, confidence,
            estimated_impact_eur, requires_human_approval, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            module,
            action,
            description,
            _json(factors),
            float(confidence),
            float(estimated_impact_eur),
            1 if requires_approval else 0,
            status,
            db.now_iso(),
        ),
    )
    return level, row_id


def record_decision(rec_id: int, outcome: str, actor: str, note: str = "") -> None:
    label = f"{actor}: {note}".strip(" :")
    db.execute(
        "UPDATE recommendation_log SET status=?, decision_by=?, decision_at=? WHERE id=?",
        (outcome, label, db.now_iso(), rec_id),
    )


def pending_approvals() -> list[dict]:
    return db.query(
        "SELECT * FROM recommendation_log WHERE status='requires_approval' ORDER BY id DESC"
    )


def approve(rec_id: int, actor: Optional[str] = None) -> dict:
    if not can_authorize():
        raise PermissionError(
            "Rol sin privilegios para autorizar decisiones de alto impacto."
        )
    actor = actor or _current_user().get("name", "logistics_manager")
    db.execute(
        "UPDATE recommendation_log SET status='approved', decision_by=?, decision_at=? WHERE id=?",
        (actor, db.now_iso(), rec_id),
    )
    return {"id": rec_id, "status": "approved", "decided_by": actor}


def reject(rec_id: int, actor: Optional[str] = None, note: str = "") -> dict:
    actor = actor or _current_user().get("name", "logistics_manager")
    db.execute(
        "UPDATE recommendation_log SET status='rejected', decision_by=?, decision_at=? WHERE id=?",
        (f"{actor}: {note}".strip(" :"), db.now_iso(), rec_id),
    )
    return {"id": rec_id, "status": "rejected", "decided_by": actor}


def trace(module: str | None = None) -> list[dict]:
    sql = "SELECT * FROM recommendation_log"
    params: tuple = ()
    if module:
        sql += " WHERE module=?"
        params = (module,)
    sql += " ORDER BY id DESC LIMIT 200"
    rows = db.query(sql, params)
    for r in rows:
        r["factors"] = db.jloads(r.get("factors"), {})
        r["impact_eur"] = r.pop("estimated_impact_eur", None)
    return rows
