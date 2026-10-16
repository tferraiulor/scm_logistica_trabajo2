from __future__ import annotations

"""Genera un CSV de ventas de ejemplo (formato ERP) para el Módulo 1."""

import csv
import os
import random
from datetime import datetime, timedelta

from app.seed import _seasonal_annual

SKUS = [
    ("SKU-PLS-001", "Pulidora Industrial X200"),
    ("SKU-PLS-002", "Atornillador SinCable PRO"),
    ("SKU-CON-001", "Conector Eléctrico 16A"),
    ("SKU-BAT-001", "Batería Li-Ion 20V"),
    ("SKU-TAL-001", "Taladro Percutor 800W"),
    ("SKU-ACE-001", "Aceite Industrial 5L"),
    ("SKU-GUA-001", "Guantes Nitrilo Caja"),
    ("SKU-SEN-001", "Sensor Temperatura IoT"),
]
REGIONS = ["R-MAD", "R-BCN", "R-VLC", "R-SEV", "R-BIL", "R-FRA", "R-LIS", "R-MIL"]

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "sample_sales.csv")
OUT = os.path.normpath(OUT)

DOW = [0.68, 1.18, 1.28, 1.22, 1.15, 0.88, 0.70]
today = datetime.now()
rows = []
for sku, _ in SKUS:
    base = 1000 - hash(sku) % 800
    for region in REGIONS:
        rng = random.Random(hash((sku, region)) % 10**6)
        noise = 1.0
        for i in range(180):
            day = today - timedelta(days=179 - i)
            dow = DOW[day.weekday()]
            noise = 0.45 * noise + 0.55 * rng.uniform(0.82, 1.18)
            units = max(0, int(base * _seasonal_annual(day, sku) * dow * noise))
            rows.append((day.date().isoformat(), sku, region, units,
                         round(units * random.uniform(4, 40), 2), "erp"))

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "sku", "region_id", "units", "price_eur", "channel"])
    w.writerows(rows)

print(f"CSV generado: {OUT} con {len(rows)} registros")
