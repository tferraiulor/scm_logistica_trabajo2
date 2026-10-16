from __future__ import annotations

"""Motor de Registro Automático y Transaccional de Ventas.

Permite:
  1. Registrar ventas manuales con descuento directo en el inventario físico.
  2. Generar ventas automáticas en segundo plano (simulador/bot de alta frecuencia).
  3. Emitir alertas automáticas de rotura si el stock cae bajo el punto de reorden.
  4. Proveer feed y métricas en tiempo real de facturación y volumen por canal y región.
"""

from collections import deque
from datetime import datetime
import logging
import random
import threading
from typing import Any, Dict, List, Optional

from ... import database as db

logger = logging.getLogger("scm.demand.sales")

_lock = threading.RLock()

# Estado del bot en segundo plano
_bot_state: Dict[str, Any] = {
    "enabled": True,  # activo por defecto para demostrar plataforma viva
    "interval_sec": 5,
    "intensity": "medium",  # "low" (1-5), "medium" (5-20), "high" (20-80)
    "channels": ["retail", "ecommerce", "distribuidor"],
    "regions": [],
    "total_auto_sales": 0,
    "last_tick": 0.0,
}

# Buffer en memoria de las ventas más recientes para respuesta ultrarrápida
_recent_sales_buffer: deque = deque(maxlen=100)

BASE_PRICES = {
    "SKU-PLS-001": 185.0,  # Pulidora Industrial X200
    "SKU-PLS-002": 95.0,   # Atornillador SinCable PRO
    "SKU-CON-001": 12.5,   # Conector Eléctrico 16A
    "SKU-BAT-001": 65.0,   # Batería Li-Ion 20V
    "SKU-TAL-001": 120.0,  # Taladro Percutor 800W
    "SKU-ACE-001": 35.0,   # Aceite Industrial 5L
    "SKU-GUA-001": 18.0,   # Guantes Nitrilo Caja
    "SKU-SEN-001": 45.0,   # Sensor Temperatura IoT
}


def record_sale(
    sku: str,
    region_id: str,
    units: int,
    price_eur: Optional[float] = None,
    channel: str = "retail",
    date_str: Optional[str] = None,
    customer_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Registra una venta, descuenta el stock y verifica alertas de rotura."""
    with _lock:
        sku = sku.strip().upper()
        region_id = region_id.strip().upper()
        units = max(1, int(units))
        channel = (channel or "retail").strip().lower()
        now = datetime.now()
        date_val = date_str or now.date().isoformat()
        time_str = now.strftime("%H:%M:%S")

        # Determinar precio unitario si no se proporciona
        base_p = BASE_PRICES.get(sku, 50.0)
        # Pequeña variación de precio según canal (+10% retail, -15% distribuidor)
        channel_mult = 1.15 if channel == "retail" else 1.05 if channel == "ecommerce" else 0.85
        unit_price = float(price_eur) if price_eur is not None and float(price_eur) > 0 else round(base_p * channel_mult, 2)
        total_eur = round(unit_price * units, 2)

        # 1. Consultar y descontar stock actual
        stock_row = db.query_one(
            "SELECT on_hand, reorder_point, warehouse_zone FROM stock WHERE sku=? AND region_id=?",
            (sku, region_id),
        )

        if stock_row:
            curr_on_hand = int(stock_row["on_hand"])
            reorder_pt = int(stock_row["reorder_point"])
            zone = stock_row["warehouse_zone"]
        else:
            curr_on_hand = 100
            reorder_pt = 30
            zone = "Z-STO-A"
            db.execute(
                "INSERT OR IGNORE INTO stock (sku, region_id, warehouse_zone, on_hand, reorder_point) VALUES (?, ?, ?, ?, ?)",
                (sku, region_id, zone, curr_on_hand, reorder_pt),
            )

        new_on_hand = max(0, curr_on_hand - units)
        db.execute(
            "UPDATE stock SET on_hand=? WHERE sku=? AND region_id=?",
            (new_on_hand, sku, region_id),
        )

        # 2. Registrar en sales_history
        db.execute(
            """INSERT INTO sales_history (date, sku, region_id, units, price_eur, channel)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (date_val, sku, region_id, units, total_eur, channel),
        )
        sale_id = db.query_one("SELECT last_insert_rowid() AS id")["id"]

        # 3. Comprobar alertas de rotura
        alert_info = None
        if new_on_hand <= reorder_pt:
            severity = "critical" if new_on_hand == 0 else "warning"
            msg = (
                f"Venta de {units}u provocó nivel {'AGOTADO' if new_on_hand == 0 else 'CRÍTICO'} "
                f"de {sku} en {region_id} (disponible: {new_on_hand}u, mín: {reorder_pt}u)"
            )
            db.execute(
                """INSERT INTO alerts (module, type, severity, message, payload, created_at, status)
                   VALUES (?, 'stockout', ?, ?, ?, ?, 'open')""",
                (
                    "demand",
                    severity,
                    msg,
                    db.jdumps({
                        "sku": sku,
                        "region_id": region_id,
                        "on_hand": new_on_hand,
                        "units_sold": units,
                        "sale_id": sale_id,
                    }),
                    db.now_iso(),
                ),
            )
            alert_info = {"severity": severity, "message": msg}

        # Obtener nombre del producto y región
        prod = db.query_one("SELECT name, category FROM products WHERE sku=?", (sku,))
        prod_name = prod["name"] if prod else sku
        reg = db.query_one("SELECT name FROM regions WHERE region_id=?", (region_id,))
        reg_name = reg["name"] if reg else region_id

        sale_record = {
            "id": sale_id,
            "timestamp": f"{date_val} {time_str}",
            "time": time_str,
            "sku": sku,
            "product_name": prod_name,
            "region_id": region_id,
            "region_name": reg_name,
            "units": units,
            "unit_price_eur": unit_price,
            "total_eur": total_eur,
            "channel": channel,
            "previous_stock": curr_on_hand,
            "current_stock": new_on_hand,
            "reorder_point": reorder_pt,
            "alert": alert_info,
            "notes": customer_notes,
        }

        _recent_sales_buffer.appendleft(sale_record)
        return sale_record


def generate_random_sale(
    intensity: Optional[str] = None,
    channels: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Genera una venta aleatoria realista con catálogo y volúmenes configurados."""
    intensity = intensity or _bot_state["intensity"]
    channels = channels or _bot_state["channels"] or ["retail", "ecommerce", "distribuidor"]
    
    # Obtener catálogo de SKUs y regiones
    skus = [row["sku"] for row in db.query("SELECT sku FROM products")]
    if not skus:
        skus = list(BASE_PRICES.keys())
    
    available_regions = regions or [row["region_id"] for row in db.query("SELECT region_id FROM regions")]
    if not available_regions:
        available_regions = ["R-MAD", "R-BCN", "R-VLC", "R-SEV", "R-BIL"]

    sku = random.choice(skus)
    region_id = random.choice(available_regions)
    channel = random.choice(channels)

    if intensity == "low":
        units = random.randint(1, 5)
    elif intensity == "high":
        units = random.randint(15, 60)
    else:  # medium
        units = random.randint(3, 18)

    rec = record_sale(sku=sku, region_id=region_id, units=units, channel=channel)
    _bot_state["total_auto_sales"] += 1
    return rec


def batch_generate_sales(count: int = 10, intensity: Optional[str] = None) -> List[Dict[str, Any]]:
    """Genera una ráfaga de N ventas de golpe."""
    results = []
    for _ in range(max(1, min(count, 50))):
        results.append(generate_random_sale(intensity=intensity))
    return results


def get_recent_sales(limit: int = 30) -> List[Dict[str, Any]]:
    """Devuelve las ventas más recientes (combinando buffer y BD)."""
    with _lock:
        if len(_recent_sales_buffer) >= limit:
            return list(_recent_sales_buffer)[:limit]
        
        # Si el buffer tiene pocas, consultar BD
        rows = db.query(
            """SELECT s.id, s.date, s.sku, p.name AS product_name, s.region_id, r.name AS region_name,
                      s.units, s.price_eur AS total_eur, s.channel,
                      st.on_hand AS current_stock, st.reorder_point
               FROM sales_history s
               LEFT JOIN products p ON p.sku = s.sku
               LEFT JOIN regions r ON r.region_id = s.region_id
               LEFT JOIN stock st ON (st.sku = s.sku AND st.region_id = s.region_id)
               ORDER BY s.id DESC LIMIT ?""",
            (limit,),
        )
        for r in rows:
            r["unit_price_eur"] = round(r["total_eur"] / max(1, r["units"]), 2)
            r["time"] = (r.get("date") or "")[-8:] if len(r.get("date") or "") > 10 else "12:00:00"
            r["timestamp"] = r.get("date")
        return rows


def get_sales_kpis() -> Dict[str, Any]:
    """Calcula las métricas de venta en tiempo real."""
    today_str = datetime.now().date().isoformat()
    
    # Totales hoy
    today_row = db.query_one(
        "SELECT COUNT(*) AS tx_count, COALESCE(SUM(units), 0) AS total_units, COALESCE(SUM(price_eur), 0) AS total_revenue FROM sales_history WHERE date >= ?",
        (today_str,),
    )
    # Totales globales (últimos 30 días)
    all_row = db.query_one(
        "SELECT COUNT(*) AS tx_count, COALESCE(SUM(units), 0) AS total_units, COALESCE(SUM(price_eur), 0) AS total_revenue FROM sales_history"
    )

    tx_today = int(today_row["tx_count"]) if today_row else 0
    units_today = int(today_row["total_units"]) if today_row else 0
    rev_today = float(today_row["total_revenue"]) if today_row else 0.0
    avg_ticket = round(rev_today / max(1, tx_today), 2) if tx_today > 0 else 0.0

    # Top producto
    top_sku_row = db.query_one(
        """SELECT s.sku, p.name, SUM(s.units) AS u, SUM(s.price_eur) AS rev
           FROM sales_history s
           LEFT JOIN products p ON p.sku = s.sku
           GROUP BY s.sku ORDER BY u DESC LIMIT 1"""
    )

    # Ventas por canal (hoy)
    by_channel = db.query(
        """SELECT channel, SUM(units) AS units, SUM(price_eur) AS revenue
           FROM sales_history
           GROUP BY channel ORDER BY revenue DESC"""
    )

    # Ventas por región
    by_region = db.query(
        """SELECT s.region_id, r.name AS region_name, SUM(s.units) AS units, SUM(s.price_eur) AS revenue
           FROM sales_history s
           LEFT JOIN regions r ON r.region_id = s.region_id
           GROUP BY s.region_id ORDER BY units DESC LIMIT 6"""
    )

    return {
        "today_transactions": tx_today,
        "today_units": units_today,
        "today_revenue_eur": round(rev_today, 2),
        "today_avg_ticket": avg_ticket,
        "total_revenue_eur": round(float(all_row["total_revenue"] or 0), 2),
        "total_units_sold": int(all_row["total_units"] or 0),
        "top_product": {
            "sku": top_sku_row["sku"] if top_sku_row else "—",
            "name": top_sku_row["name"] if top_sku_row else "—",
            "units": int(top_sku_row["u"]) if top_sku_row else 0,
            "revenue": round(float(top_sku_row["rev"] or 0), 2) if top_sku_row else 0.0,
        } if top_sku_row else None,
        "by_channel": by_channel,
        "by_region": by_region,
        "bot_status": get_auto_status(),
    }


def get_auto_status() -> Dict[str, Any]:
    with _lock:
        return dict(_bot_state)


def set_auto_config(
    enabled: Optional[bool] = None,
    interval_sec: Optional[int] = None,
    intensity: Optional[str] = None,
    channels: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    with _lock:
        if enabled is not None:
            _bot_state["enabled"] = bool(enabled)
        if interval_sec is not None:
            _bot_state["interval_sec"] = max(1, min(60, int(interval_sec)))
        if intensity is not None and intensity in ("low", "medium", "high"):
            _bot_state["intensity"] = intensity
        if channels is not None:
            _bot_state["channels"] = [c.lower() for c in channels]
        if regions is not None:
            _bot_state["regions"] = regions
        return dict(_bot_state)


def tick_auto_sales() -> Optional[Dict[str, Any]]:
    """Llamado en cada ciclo del loop background para despachar ventas periódicas si enabled."""
    import time
    with _lock:
        if not _bot_state.get("enabled", True):
            return None
        now_ts = time.time()
        interval = float(_bot_state.get("interval_sec", 5))
        last_t = float(_bot_state.get("last_tick", 0.0))
        if now_ts - last_t >= interval:
            _bot_state["last_tick"] = now_ts
            return generate_random_sale()
    return None
