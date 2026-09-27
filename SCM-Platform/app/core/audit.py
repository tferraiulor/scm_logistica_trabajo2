from __future__ import annotations

"""Trazabilidad y auditoría de decisiones de IA (explicabilidad).

Cada recomendación autónoma queda registrada con un desglose transparente de los
factores que la motivaron (SHAP-like), la verificación de datos empleada, y la
confianza del modelo.
"""

from typing import Any, Optional

from .. import database as db


def log_decision(
    module: str,
    action: str,
    description: str,
    factors: dict[str, Any],
    confidence: float,
    impact_eur: float,
    requires_approval: bool,
    status: str = "pending",
) -> int:
    return db.execute(
        """INSERT INTO recommendation_log
           (module, action, description, factors, confidence,
            estimated_impact_eur, requires_human_approval, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            module,
            action,
            description,
            __import__("json").dumps(factors, default=str),
            float(confidence),
            float(impact_eur),
            1 if requires_approval else 0,
            status,
            db.now_iso(),
        ),
    )
