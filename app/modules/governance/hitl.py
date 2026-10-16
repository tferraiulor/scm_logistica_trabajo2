from __future__ import annotations

"""MÓDULO 5: Panel de Gobernanza Humana y Control de Alucinaciones (HITL).

Garantiza que la IA no tome decisiones que destruyan valor financiero o violen
normativas. Define una Matriz de Criterio Humano: el sistema puede sugerir u
optimizar de forma autónoma, pero las decisiones de alto coste / legales /
estratégicas requieren aprobación obligatoria del Logistics Manager.

Cada recomendación expone trazabilidad y explicabilidad (qué factores pesaron
+ verificación de datos) para control de alucinaciones.
"""

from typing import Optional

from ... import database as db
from ...core import security
from ... import config


def decision_matrix() -> list[dict]:
    """Matriz de criterio humano (reglas de gobernanza configurables)."""
    return [
        {
            "rule_id": "HITL-01",
            "decision": "Re-licitación (re-tender) de carga a transportista alternativo",
            "auto_threshold": "Retraso < 60 min sin violar ventana contractual",
            "requires_approval_when": "Impacto financiero >= {:.0f}€ o violación de ventana clave".format(
                config.HITL_FINANCIAL_THRESHOLD_EUR
            ),
            "owner": "Logistics Manager",
        },
        {
            "rule_id": "HITL-02",
            "decision": "Cancelación o reemplazo de un proveedor principal",
            "auto_threshold": "Nunca (siempre requiere aprobación)",
            "requires_approval_when": "Siempre: decisión contractual estratégica",
            "owner": "Logistics Manager / Procurement Director",
        },
        {
            "rule_id": "HITL-03",
            "decision": "Contratación de flete aéreo de emergencia",
            "auto_threshold": "Nunca (siempre requiere aprobación)",
            "requires_approval_when": "Siempre: alto coste extraordinario",
            "owner": "Logistics Manager",
        },
        {
            "rule_id": "HITL-04",
            "decision": "Re-slotting de inventario hacia muelle (WMS)",
            "auto_threshold": "Movimiento interno de baja complejidad",
            "requires_approval_when": "Impacto financiero >= {:.0f}€".format(
                config.HITL_FINANCIAL_THRESHOLD_EUR
            ),
            "owner": "Ops Agent (auto) / Logistics Manager (umbral)",
        },
        {
            "rule_id": "HITL-05",
            "decision": "Orden de trabajo de mantenimiento predictivo preventivo",
            "auto_threshold": "Coste < {:.0f}€, sin parada crítica".format(
                config.HITL_FINANCIAL_THRESHOLD_EUR
            ),
            "requires_approval_when": "Parada de maquinaria crítica de alta producción",
            "owner": "Ops Agent (auto) / Facility Manager (umbral)",
        },
        {
            "rule_id": "HITL-06",
            "decision": "Sugerencia de proveedores alternativos por score crítico",
            "auto_threshold": "Solo sugerencia (no ejecuta contratos)",
            "requires_approval_when": "Cambio de proveedor con impacto contractual",
            "owner": "Procurement (aprueba el cambio)",
        },
    ]


def pending() -> list[dict]:
    rows = security.pending_approvals()
    for r in rows:
        r["factors"] = db.jloads(r.get("factors"), {})
    return rows


def decision_trace(module: Optional[str] = None) -> list[dict]:
    return security.trace(module)


def approve(rec_id: int, actor: Optional[str] = None) -> dict:
    try:
        return security.approve(rec_id, actor)
    except PermissionError as exc:
        raise PermissionError(str(exc)) from exc


def reject(rec_id: int, actor: Optional[str] = None, note: str = "") -> dict:
    return security.reject(rec_id, actor, note)


def can_authorize() -> bool:
    return security.can_authorize()
