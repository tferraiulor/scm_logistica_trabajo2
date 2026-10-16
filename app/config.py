from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/data/scm.db")
SQLITE_PATH = BASE_DIR / "data" / "scm.db"

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
WEATHER_CACHE_TTL_SECONDS = int(os.getenv("WEATHER_CACHE_TTL", "600"))

FORECAST_HORIZON_DAYS = int(os.getenv("FORECAST_HORIZON", "30"))
FORECAST_CONFIDENCE_THRESHOLD = float(os.getenv("FORECAST_CONFIDENCE", "0.85"))

HITL_FINANCIAL_THRESHOLD_EUR = float(os.getenv("HITL_COST_THRESHOLD", "5000"))
HITL_CONTRACT_CANCEL_REQUIRES_APPROVAL = True

# Gobernanza prudente: lo autónomo es la excepción, no la regla.
# Solo estas acciones (bajo impacto, reversibles) pueden auto-ejecutarse,
# y únicamente si no superan el coste máximo y tienen confianza suficiente.
HITL_AUTO_EXECUTE_ACTIONS = [
    a.strip() for a in os.getenv("HITL_AUTO_ACTIONS", "reslot_inventory").split(",")
]
HITL_AUTO_MAX_IMPACT_EUR = float(os.getenv("HITL_AUTO_MAX_IMPACT", "500"))
HITL_AUTO_MIN_CONFIDENCE = float(os.getenv("HITL_AUTO_MIN_CONF", "0.9"))

AGENT_LOOP_POLL_INTERVAL = int(os.getenv("AGENT_POLL_SEC", "15"))
AGENT_RE_TENDER_ATTEMPTS = int(os.getenv("AGENT_RE_TENDER_ATTEMPTS", "3"))

RISK_SCORE_CRITICAL_THRESHOLD = int(os.getenv("RISK_CRITICAL", "30"))
RISK_SCORE_WARNING_THRESHOLD = int(os.getenv("RISK_WARNING", "60"))
