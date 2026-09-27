from __future__ import annotations

"""Cliente de variables meteorológicas dinámicas.

- Modo real: consulta OpenWeatherMap (5-day / 3h) usando OPENWEATHER_API_KEY.
- Modo simulado: si no hay API key o falla la red, genera datos estocásticos
  realistas (temperatura, precipitación, viento, estado) con caché en memoria.

Se usa para enriquecer la previsión de demanda (Módulo 1) y el motor de rutas
(Módulo 2, por ejemplo lluvia => factor de retraso).
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from .. import config
from .. import database as db

_CACHE: dict[str, dict] = {}
_CACHE_TIME: dict[str, datetime] = {}


def _coord_for_region(region_id: str) -> tuple[float, float]:
    """Coordenadas simuladas por región (mercantilmente plausibles)."""
    coords = {
        "R-MAD": (40.4168, -3.7038),
        "R-BCN": (41.3874, 2.1686),
        "R-VLC": (39.4699, -0.3763),
        "R-SEV": (37.3891, -5.9845),
        "R-BIL": (43.2630, -2.9350),
        "R-FRA": (50.1109, 8.6821),
        "R-LIS": (38.7223, -9.1393),
        "R-MIL": (45.4642, 9.1900),
    }
    return coords.get(region_id, (40.4168, -3.7038))


def weather_for(region_id: str, force_refresh: bool = False) -> dict:
    """Devuelve el estado meteorológico actual de la región con caché."""
    now = datetime.now(timezone.utc)
    cached_at = _CACHE_TIME.get(region_id)
    if not force_refresh and cached_at:
        if (now - cached_at).total_seconds() < config.WEATHER_CACHE_TTL_SECONDS:
            return _CACHE[region_id]

    data = _fetch_openweather(region_id) or _mock_weather(region_id)
    _CACHE[region_id] = data
    _CACHE_TIME[region_id] = now
    return data


def _fetch_openweather(region_id: str) -> Optional[dict]:
    if not config.OPENWEATHER_API_KEY:
        return None
    lat, lon = _coord_for_region(region_id)
    try:
        r = httpx.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "lat": lat,
                "lon": lon,
                "appid": config.OPENWEATHER_API_KEY,
                "units": "metric",
            },
            timeout=5,
        )
        r.raise_for_status()
        j = r.json()
        return {
            "temp_c": j["main"]["temp"],
            "rain_mm_h": j.get("rain", {}).get("1h", 0.0),
            "snow_mm_h": j.get("snow", {}).get("1h", 0.0),
            "wind_kmh": j["wind"]["speed"] * 3.6,
            "condition": j["weather"][0]["description"],
            "source": "openweather",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:  # noqa: BLE001
        return None


def _mock_weather(region_id: str) -> dict:
    """Generador determinista-segmentado por región para reproducibilidad."""
    rng = random.Random(hash(region_id) % 100000 + int(datetime.now().hour))
    is_rainy = rng.random() < 0.35
    condition = (
        rng.choice(["lluvia moderada", "lluvia intensa", "chubascos", "tormenta"])
        if is_rainy
        else rng.choice(["despejado", "nubes dispersas", "nublado"])
    )
    base = {"R-MAD": 16, "R-BCN": 17, "R-VLC": 20, "R-SEV": 22,
            "R-BIL": 14, "R-FRA": 12, "R-LIS": 19, "R-MIL": 18}
    temp = base.get(region_id, 16) + rng.uniform(-3, 3)
    return {
        "temp_c": round(temp, 1),
        "rain_mm_h": round(rng.uniform(2, 40), 1) if is_rainy else 0.0,
        "snow_mm_h": 0.0,
        "wind_kmh": round(rng.uniform(5, 60), 1),
        "condition": condition,
        "source": "simulated",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
