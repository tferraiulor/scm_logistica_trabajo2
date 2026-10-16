"""Módulo de Inteligencia Logística y Análisis de Datos Reales (Ifood / BD_Logistica).

Conecta la plataforma SCM con los 4.282 registros reales de pedidos, motoristas,
destinos (BH, SP, RJ), volumen de ítems, valor facturado y análisis de retrasos.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from ... import database as db

router = APIRouter(prefix="/api/logistics", tags=["logistics_real_data"])


@router.get("/metrics")
def get_global_metrics() -> Dict[str, Any]:
    """Retorna métricas consolidadas sobre el dataset logístico real."""
    total_row = db.query_one("""
        SELECT 
            COUNT(*) AS total_orders,
            COALESCE(SUM(items_count), 0) AS total_items,
            COALESCE(SUM(billed_brl), 0.0) AS total_revenue_brl,
            COALESCE(AVG(billed_brl), 0.0) AS avg_ticket_brl,
            COALESCE(AVG(delivery_days), 0.0) AS avg_delivery_days,
            COALESCE(SUM(CASE WHEN delay_status = 'Atrasado' THEN 1 ELSE 0 END), 0) AS delayed_orders,
            COALESCE(SUM(CASE WHEN delay_status = 'No Prazo' THEN 1 ELSE 0 END), 0) AS on_time_orders,
            COALESCE(SUM(return_quantity), 0) AS total_returns
        FROM logistic_orders
    """)

    total_orders = total_row["total_orders"] if total_row else 0
    delayed = total_row["delayed_orders"] if total_row else 0
    delay_rate = round((delayed / total_orders * 100.0), 2) if total_orders > 0 else 0.0

    # Desglose regional (BH, SP, RJ)
    regions_breakdown = db.query("""
        SELECT 
            destination AS region,
            COUNT(*) AS orders_count,
            SUM(items_count) AS items_sum,
            ROUND(SUM(billed_brl), 2) AS revenue_brl,
            SUM(CASE WHEN delay_status = 'Atrasado' THEN 1 ELSE 0 END) AS delayed_count,
            SUM(CASE WHEN delay_status = 'No Prazo' THEN 1 ELSE 0 END) AS on_time_count,
            ROUND(100.0 * SUM(CASE WHEN delay_status = 'Atrasado' THEN 1 ELSE 0 END) / COUNT(*), 2) AS delay_percentage,
            ROUND(AVG(delivery_days), 1) AS avg_days,
            SUM(return_quantity) AS returns_count
        FROM logistic_orders
        GROUP BY destination
        ORDER BY orders_count DESC
    """)

    # Desglose por motivo de devolución
    returns_breakdown = db.query("""
        SELECT 
            return_reason,
            COUNT(*) AS occurrences,
            SUM(return_quantity) AS units_returned
        FROM logistic_orders
        WHERE return_reason IS NOT NULL AND return_reason != ''
        GROUP BY return_reason
        ORDER BY occurrences DESC
    """)

    # Top motoristas con mayor tasa de retraso y volumen
    drivers_summary = db.query("""
        SELECT 
            driver,
            COUNT(*) AS total_trips,
            SUM(items_count) AS items_delivered,
            ROUND(SUM(billed_brl), 2) AS total_billed_brl,
            SUM(CASE WHEN delay_status = 'Atrasado' THEN 1 ELSE 0 END) AS delayed_trips,
            ROUND(100.0 * SUM(CASE WHEN delay_status = 'Atrasado' THEN 1 ELSE 0 END) / COUNT(*), 2) AS delay_rate,
            ROUND(AVG(delivery_days), 1) AS avg_delivery_days
        FROM logistic_orders
        GROUP BY driver
        ORDER BY total_trips DESC
    """)

    # Top clientes
    clients_summary = db.query("""
        SELECT 
            client,
            COUNT(*) AS total_orders,
            SUM(items_count) AS items_count,
            ROUND(SUM(billed_brl), 2) AS total_billed_brl,
            SUM(CASE WHEN delay_status = 'Atrasado' THEN 1 ELSE 0 END) AS delayed_orders,
            ROUND(100.0 * SUM(CASE WHEN delay_status = 'Atrasado' THEN 1 ELSE 0 END) / COUNT(*), 2) AS delay_rate
        FROM logistic_orders
        GROUP BY client
        ORDER BY total_orders DESC
    """)

    return {
        "dataset_name": "BD_Logistica (IfoodCase)",
        "total_orders": total_orders,
        "total_items": total_row["total_items"] if total_row else 0,
        "total_revenue_brl": round(total_row["total_revenue_brl"], 2) if total_row else 0.0,
        "avg_ticket_brl": round(total_row["avg_ticket_brl"], 2) if total_row else 0.0,
        "avg_delivery_days": round(total_row["avg_delivery_days"], 1) if total_row else 0.0,
        "delayed_orders": delayed,
        "on_time_orders": total_row["on_time_orders"] if total_row else 0,
        "delay_rate_pct": delay_rate,
        "total_returns": total_row["total_returns"] if total_row else 0,
        "regions": regions_breakdown,
        "returns": returns_breakdown,
        "drivers": drivers_summary,
        "clients": clients_summary,
        "ifood_benchmark": {
            "total_orders": 153604,
            "overall_delay_pct": 9.95,
            "driver_delay_pct": 9.97,
            "restaurant_delay_pct": 38.82,
            "avg_distance_km": 4.51,
            "avg_delivery_time_min": 27.12,
            "top_modal": "MOTORCYCLE (92.4%)",
            "top_model": "OWN_DELIVERY (91.4%)",
        },
    }


@router.get("/orders")
def get_orders(
    region: Optional[str] = None,
    status: Optional[str] = None,
    driver: Optional[str] = None,
    client: Optional[str] = None,
    return_reason: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Consulta paginada y filtrable de los pedidos reales."""
    where_clauses = []
    params = []

    if region:
        where_clauses.append("destination = ?")
        params.append(region.strip().upper())
    if status:
        where_clauses.append("delay_status = ?")
        params.append(status.strip())
    if driver:
        where_clauses.append("driver = ?")
        params.append(driver.strip())
    if client:
        where_clauses.append("client = ?")
        params.append(client.strip())
    if return_reason:
        where_clauses.append("return_reason = ?")
        params.append(return_reason.strip())
    if q and q.strip():
        term = f"%{q.strip()}%"
        where_clauses.append("(order_id LIKE ? OR client LIKE ? OR driver LIKE ? OR return_reason LIKE ?)")
        params.extend([term, term, term, term])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_row = db.query_one(f"SELECT COUNT(*) AS total FROM logistic_orders {where_sql}", tuple(params))
    total_matching = count_row["total"] if count_row else 0

    query_sql = f"""
        SELECT 
            order_id, client, driver, issue_date, planned_delivery_date,
            destination, items_count, billed_brl, dispatched_date,
            actual_delivery_date, return_quantity, return_reason,
            delivery_days, delay_status
        FROM logistic_orders
        {where_sql}
        ORDER BY id ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    orders = db.query(query_sql, tuple(params))

    return {
        "total": total_matching,
        "limit": limit,
        "offset": offset,
        "orders": orders,
    }

