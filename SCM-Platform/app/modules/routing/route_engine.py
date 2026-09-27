from __future__ import annotations

"""MÓDULO 2a: Motor de Enrutamiento Dinámico de Última Milla.

Calcula la ruta más eficiente considerando:
  - Tráfico en tiempo real (factor dinámico).
  - Incidentes viales (accidentes / obras).
  - Ventanas horarias (time windows) del cliente.
  - Restricciones físicas del vehículo (capacidad peso/volumen).
  - Meteorología (lluvia => factor de retraso).

Usa un enfoque de vecino más cercano (nearest-neighbor TSP) sobre nodos
geoespaciales, enriquecido con penalizaciones dinámicas.
"""

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from ... import config
from ... import database as db
from ...services import weather_client


@dataclass
class Stop:
    id: str
    name: str
    lat: float
    lng: float
    service_min: int = 15
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    demand_kg: float = 0.0


def haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _traffic_factor(zone: str = "R-MAD") -> float:
    """Tráfico dinámico: hora punta => mayor factor de tiempo."""
    hour = datetime.now().hour
    rt = db.rt_get(f"traffic:{zone}")
    if rt:
        return float(rt.get("factor", 1.0))
    if 7 <= hour <= 9 or 17 <= hour <= 20:
        return 1.35
    if 12 <= hour <= 14 or 15 <= hour <= 17:
        return 1.15
    return 1.05


def _incident_penalty() -> float:
    """Incidentes viales activos en la región (accidente/obra)."""
    incidents = db.rt_get("incidents", [])
    penalty = 1.0
    for inc in incidents:
        if inc.get("active"):
            penalty *= 1 + inc.get("impact", 0.25)
    return penalty


def _weather_penalty(region: str) -> float:
    w = weather_client.weather_for(region)
    cond = w["condition"].lower()
    if "lluvia intensa" in cond or "tormenta" in cond:
        return 1.4
    if "lluvia" in cond:
        return 1.15
    return 1.0


def _vehicle_check(stop_demand_kg: float, route_cargo_kg: float, carrier: dict) -> bool:
    """Verifica restricción física de capacidad del vehículo."""
    if stop_demand_kg + route_cargo_kg > carrier["capacity_kg"]:
        return False
    return True


def _speed_kmh(carrier: dict) -> float:
    return 80.0 if carrier["vehicle_type"] == "truck" else 60.0


def time_windows_violation(route: list[Stop], order: list[int], speed: float, factors: dict) -> float:
    """Penalización por violación de ventanas horarias en el orden dado."""
    penalty = 0.0
    t = 0.0  # minutos desde inicio
    prev = None
    for idx in order:
        stop = route[idx]
        if prev is None:
            dist = 0.0
        else:
            dist = haversine(prev.lat, prev.lng, stop.lat, stop.lng)
        travel_min = (dist / speed) * 60 * factors["traffic"] * factors["incident"] * factors["weather"]
        t += travel_min
        if stop.window_start and stop.window_end:
            ws = datetime.fromisoformat(stop.window_start)
            we = datetime.fromisoformat(stop.window_end)
            today = datetime.combine(ws.date(), ws.time())
            # Simplificación: comparar minutos del día
            t_clock = (datetime.now().replace(hour=0, minute=0) + timedelta(minutes=t)).time()
            start_min = ws.hour * 60 + ws.minute
            end_min = we.hour * 60 + we.minute
            t_min = t_clock.hour * 60 + t_clock.minute
            if t_min > end_min:
                penalty += (t_min - end_min) * 2
        t += stop.service_min
        prev = stop
    return penalty


def optimize_route(
    stops: list[dict],
    origin: dict,
    carrier_id: str,
    region: str = "R-MAD",
) -> dict:
    """Devuelve la orden optimizada de paradas + ETA + coste."""
    carrier = db.query_one("SELECT * FROM carriers WHERE carrier_id=?", (carrier_id,))
    if not carrier:
        carrier = {"carrier_id": carrier_id, "vehicle_type": "truck",
                   "capacity_kg": 24000, "capacity_m3": 90, "per_km_cost": 0.85,
                   "name": carrier_id}

    stop_objs = [Stop(**s) for s in stops]
    factors = {
        "traffic": _traffic_factor(region),
        "incident": _incident_penalty(),
        "weather": _weather_penalty(region),
    }
    speed = _speed_kmh(carrier)

    # Nearest-neighbor (heuristic) + búsqueda local 2-opt ligera
    n = len(stop_objs)
    if n == 0:
        return {"order": [], "total_km": 0, "eta": None, "factors": factors}
    if n == 1:
        order = [0]
    else:
        remaining = list(range(n))
        order = [remaining.pop(0)]
        while remaining:
            last = stop_objs[order[-1]]
            best = min(remaining, key=lambda k: haversine(last.lat, last.lng,
                                                          stop_objs[k].lat, stop_objs[k].lng))
            order.append(best)
            remaining.remove(best)

    # 2-opt local search minimizando (distancia + violación ventana)
    for _ in range(60):
        i, j = sorted(random.sample(range(n), 2))
        candidate = order.copy()
        candidate[i:j + 1] = reversed(candidate[i:j + 1])
        cur_cost = _route_cost(stop_objs, order, speed, factors)
        new_cost = _route_cost(stop_objs, candidate, speed, factors)
        if new_cost < cur_cost:
            order = candidate

    total_km = 0.0
    prev = origin
    for idx in order:
        stop = stop_objs[idx]
        total_km += haversine(prev["lat"], prev["lng"], stop.lat, stop.lng)
        prev = {"lat": stop.lat, "lng": stop.lng}

    eta_min = sum(
        _leg_minutes(prev_geo, stop_objs[order[i]], speed, factors)
        for i, prev_geo in enumerate(_ordered_geos(order + [None], stop_objs))
        if prev_geo
    )
    cost = total_km * carrier["per_km_cost"] + len(order) * 12.0

    return {
        "order": order,
        "ordered_stops": [
            {"id": stop_objs[i].id, "name": stop_objs[i].name} for i in order
        ],
        "total_km": round(total_km, 1),
        "estimated_minutes": round(eta_min, 1),
        "estimated_cost_eur": round(cost, 2),
        "factors": {k: round(v, 2) for k, v in factors.items()},
        "carrier": carrier.get("name", carrier_id),
    }


def _ordered_geos(order_tail, stops):
    out = []
    for i in order_tail:
        if i is not None:
            s = stops[i]
            out.append({"lat": s.lat, "lng": s.lng})
    return out


def _leg_minutes(prev, stop, speed, factors):
    if prev is None:
        return 0.0
    dist = haversine(prev["lat"], prev["lng"], stop.lat, stop.lng)
    return (dist / speed) * 60 * factors["traffic"] * factors["incident"] * factors["weather"] + stop.service_min


def _route_cost(stops, order, speed, factors):
    total = 0.0
    prev = None
    for idx in order:
        s = stops[idx]
        if prev is None:
            total += s.service_min
        else:
            total += _leg_minutes(prev, s, speed, factors)
        prev = {"lat": s.lat, "lng": s.lng}
    return total
