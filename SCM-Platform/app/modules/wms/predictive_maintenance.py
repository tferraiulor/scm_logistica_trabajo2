from __future__ import annotations

"""MÓDULO 3b: Monitoreo IoT para Mantenimiento Predictivo.

Recibe telemetría simulada de sensores de maquinaria (cintas transportadoras,
brazos robóticos). Detecta anomalías mediante umbrales adaptativos (baseline
desviación estándar) ante vibraciones/saturación o sobrecalentamiento sutil, y
genera una orden de trabajo (work order) automática ANTES de la avería
estructural. Cada alerta se enruta por gobernanza para auto-ejecutar la orden.
"""

import json
import random
import threading
from datetime import datetime, timedelta

from ... import database as db
from ...core import security
from ...core.security import ApprovalLevel


def _baseline(machine_id: str) -> dict:
    """Baseline histórico del sensor (media/desv estándar) para umbral adaptativo."""
    rows = db.query(
        """SELECT vibration, temperature FROM maintenance_telemetry
           WHERE machine_id=? AND anomaly=0 ORDER BY id DESC LIMIT 200""",
        (machine_id,),
    )
    if not rows:
        m = db.query_one("SELECT * FROM machines WHERE machine_id=?", (machine_id,))
        return {
            "vib_mean": 0.4, "vib_std": 0.1,
            "temp_mean": 60.0, "temp_std": 5.0,
            "threshold_vib": m["threshold_vibration"] if m else 0.9,
            "threshold_temp": m["threshold_temp"] if m else 80.0,
        }
    vibs = [r["vibration"] for r in rows]
    temps = [r["temperature"] for r in rows]
    return {
        "vib_mean": sum(vibs) / len(vibs),
        "vib_std": _std(vibs),
        "temp_mean": sum(temps) / len(temps),
        "temp_std": _std(temps),
        "n_samples": len(rows),
    }


def _std(vals):
    m = sum(vals) / len(vals)
    return (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5


def ingest_telemetry(records: list[dict]) -> dict:
    """Ingesta lote de telemetría y ejecuta detección de anomalías."""
    created_orders = []
    rows = []
    for rec in records:
        mid = rec["machine_id"]
        vib = float(rec["vibration"])
        temp = float(rec["temperature"])
        ts = rec.get("ts", datetime.now().isoformat())
        baseline = _baseline(mid)
        machine = db.query_one(
            "SELECT threshold_vibration, threshold_temp FROM machines WHERE machine_id=?",
            (mid,),
        ) or {}

        anomaly = 0
        # Detección: desviación > 3 sigma del baseline adaptativo, o umbral rígido
        vib_anomaly = vib > baseline["vib_mean"] + 3 * baseline["vib_std"]
        temp_anomaly = temp > baseline["temp_mean"] + 3 * baseline["temp_std"]
        vib_hard = vib > (machine.get("threshold_vibration") or 0.9)
        temp_hard = temp > (machine.get("threshold_temp") or 80.0)
        if vib_anomaly or temp_anomaly or vib_hard or temp_hard:
            anomaly = 1
            wo = _create_work_order(mid, vib, temp, baseline, machine)
            if wo:
                created_orders.append(wo)

        rows.append((mid, ts, round(vib, 3), round(temp, 1), anomaly))

    db.executemany(
        "INSERT INTO maintenance_telemetry (machine_id, ts, vibration, temperature, anomaly) VALUES (?,?,?,?,?)",
        rows,
    )
    return {"records": len(rows), "anomalies_detected": len(created_orders),
            "work_orders": created_orders}


def _create_work_order(mid, vib, temp, baseline, machine) -> dict | None:
    """Genera orden de trabajo predictiva + alerta. Enrutada por gobernanza."""
    factors = {
        "machine_id": mid,
        "vibration": round(vib, 3),
        "temperature": round(temp, 1),
        "baseline_vib_mean": round(baseline["vib_mean"], 3),
        "baseline_temp_mean": round(baseline["temp_mean"], 1),
        "data_verified": True,
        "signal": "IoT sensor",
    }
    level, rec_id = security.classify_action(
        module="wms",
        action="create_predictive_work_order",
        description=f"Orden predictiva preventiva para {mid} (vib={vib} g, T={temp}°C)",
        estimated_impact_eur=350.0,   # coste de parada preventiva (bajo)
        factors=factors,
        confidence=0.88,
    )

    wid = db.execute(
        """INSERT INTO work_orders (machine_id, type, priority, description, triggered_by, status, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            mid, "predictive", "high",
            f"Vibración {vib:.2f}g y/o temperatura {temp:.1f}°C fuera de rango adaptativo",
            json.dumps(factors), "open", db.now_iso(),
        ),
    )
    db.execute(
        """INSERT INTO alerts (module, type, severity, message, payload, created_at, status)
           VALUES ('wms','maintenance','warning',?,?,?,'open')""",
        (
            f"Anomalía predictiva en {mid}: generar trabajo preventivo antes de avería",
            json.dumps(factors), db.now_iso(),
        ),
    )
    return {"work_order_id": wid, "machine_id": mid, "vibration": round(vib, 3),
            "temperature": round(temp, 1), "requires_approval": level == ApprovalLevel.REQUIRES_APPROVAL,
            "rec_id": rec_id}


def simulate_telemetry(payload: dict = None) -> dict:
    """Genera un lote de telemetría con posible anomalía arrastrando hacia la avería."""
    payload = payload or {}
    machines = db.query("SELECT machine_id FROM machines")
    batch = []
    for m in machines:
        mid = m["machine_id"]
        # Un sensor presenta degradación progresiva (simula fallo incipiente)
        degrade = _degradation_state(mid)
        vib = _gauss(0.4, 0.08) * (1 + degrade)
        temp = _gauss(55.0, 4.0) * (1 + degrade * 0.15)
        batch.append({"machine_id": mid, "vibration": round(min(vib, 3.0), 3),
                      "temperature": round(min(temp, 120.0), 1),
                      "ts": datetime.now().isoformat()})
    return ingest_telemetry(batch)


def _degradation_state(mid: str) -> float:
    """Estado de degradación persistido en RT para simular falla incipiente."""
    state = db.rt_get(f"degrade:{mid}", 0.0)
    if mid == "MAC-CINT-01":  # máquina focal de la demo se degrada con el tiempo
        state = min(2.5, state + 0.12)
        db.rt_set(f"degrade:{mid}", state)
    return state


def _gauss(mu, sigma):
    import math
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    return mu + z * sigma


def ensure_fleet_orders() -> list:
    """Asegura órdenes de manutención preventiva de camiones (flota) con su fecha programada."""
    existing = db.query(
        "SELECT COUNT(*) AS c FROM work_orders WHERE triggered_by='fleet_maintenance'"
    )
    if existing and existing[0]["c"] > 0:
        return []
    carriers = db.query("SELECT carrier_id, name, vehicle_type FROM carriers")
    today = datetime.now().date()
    created = []
    for idx, v in enumerate(carriers):
        due = datetime.combine(today + timedelta(days=1 + idx * 2), datetime.min.time())
        db.execute(
            """INSERT INTO work_orders (machine_id, type, priority, description, triggered_by, status, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                v["carrier_id"], "fleet",
                "high" if idx in (0, 1) else "medium",
                f"Mantención preventiva camión {v['carrier_id']} · {v['name']} · revisión de {40000 + idx * 20000} km",
                "fleet_maintenance", "open", due.isoformat(),
            ),
        )
        created.append(v["carrier_id"])
    return created


def work_orders(status: str = None) -> list[dict]:
    sql = "SELECT * FROM work_orders"
    params = ()
    if status:
        sql += " WHERE status=?"
        params = (status,)
    sql += " ORDER BY created_at DESC, id DESC"
    rows = db.query(sql, params)
    for r in rows:
        r["triggered_by"] = db.jloads(r.get("triggered_by"), {})
    return rows


def machine_telemetry(machine_id: str = None) -> list[dict]:
    sql = "SELECT * FROM maintenance_telemetry"
    params = ()
    if machine_id:
        sql += " WHERE machine_id=?"
        params = (machine_id,)
    sql += " ORDER BY id DESC LIMIT 100"
    return db.query(sql, params)
