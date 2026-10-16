from __future__ import annotations

"""Datos semilla realistas para demostrar la plataforma end-to-end."""

import json
import math
import random
from datetime import datetime, timedelta

import numpy as np

from . import database as db

PRODUCTS = [
    ("SKU-PLS-001", "Pulidora Industrial X200", "herramienta", '{"l":0.4,"w":0.3,"h":0.25}', 6.2, 1),
    ("SKU-PLS-002", "Atornillador SinCable PRO", "herramienta", '{"l":0.3,"w":0.2,"h":0.12}', 1.8, 0),
    ("SKU-CON-001", "Conector Eléctrico 16A", "electrico", '{"l":0.1,"w":0.1,"h":0.08}', 0.35, 0),
    ("SKU-BAT-001", "Batería Li-Ion 20V", "electrico", '{"l":0.18,"w":0.1,"h":0.22}', 0.9, 1),
    ("SKU-TAL-001", "Taladro Percutor 800W", "herramienta", '{"l":0.42,"w":0.3,"h":0.28}', 2.6, 0),
    ("SKU-ACE-001", "Aceite Industrial 5L", "consumible", '{"l":0.2,"w":0.2,"h":0.3}', 4.1, 1),
    ("SKU-GUA-001", "Guantes Nitrilo Caja", "consumible", '{"l":0.3,"w":0.2,"h":0.15}', 0.6, 0),
    ("SKU-SEN-001", "Sensor Temperatura IoT", "electrico", '{"l":0.08,"w":0.06,"h":0.05}', 0.12, 1),
]

REGIONS = [
    ("R-MAD", "Madrid", "WH-MAD"),
    ("R-BCN", "Barcelona", "WH-BCN"),
    ("R-VLC", "Valencia", "WH-VLC"),
    ("R-SEV", "Sevilla", "WH-SEV"),
    ("R-BIL", "Bilbao", "WH-BIL"),
    ("R-FRA", "Frankfurt", "WH-FRA"),
    ("R-LIS", "Lisboa", "WH-LIS"),
    ("R-MIL", "Milán", "WH-MIL"),
]

CARRIERS = [
    ("C-1", "Transrapid Express", "truck", 24000, 90, 1, '["R-MAD","R-BCN","R-VLC","R-BIL"]', 0.85, 4.9),
    ("C-2", "Carga del Norte", "truck", 22000, 80, 1, '["R-BIL","R-MAD"]', 0.90, 4.7),
    ("C-3", "EuroRush Logistics", "truck", 26000, 95, 1, '["R-FRA","R-MIL"]', 1.05, 4.6),
    ("C-4", "Iberia Cargo Line", "truck", 20000, 70, 1, '["R-SEV","R-LIS"]', 0.95, 4.8),
    ("C-5", "Mediterranea Freight", "truck", 24000, 88, 1, '["R-VLC","R-BCN"]', 0.80, 4.5),
    ("C-6", "Alpine Haulage", "van", 8000, 30, 1, '["R-MIL","R-FRA"]', 0.70, 4.4),
]

SUPPLIERS = [
    ("SP-MOT-01", "Motores del Sur S.A.", "España", "Sevilla", "Motores eléctricos", 0.87, 72, 22, 145.0, "active"),
    ("SP-MOT-02", "Precision Electric GmbH", "Alemania", "Múnich", "Motores eléctricos", 0.94, 88, 12, 168.0, "active"),
    ("SP-MOT-03", "Andina Motorworks", "Portugal", "Oporto", "Motores eléctricos", 0.78, 55, 40, 132.0, "active"),
    ("SP-TAL-01", "FerroRotor Trading", "España", "Bilbao", "Acero aleado", 0.82, 64, 30, 89.0, "active"),
    ("SP-TAL-02", "Arcelor Minería MX", "México", "Monterrey", "Acero aleado", 0.71, 48, 68, 76.0, "active"),
    ("SP-TAL-03", "Nordic Steel AB", "Suecia", "Gotemburgo", "Acero aleado", 0.92, 90, 8, 118.0, "active"),
    ("SP-ELC-01", "Circuitos Iberia", "España", "Zaragoza", "Componente electrónico", 0.85, 70, 25, 4.20, "active"),
    ("SP-ELC-02", "Wei Electronics Ltd.", "China", "Shenzhen", "Componente electrónico", 0.38, 18, 80, 3.10, "active"),
    ("SP-ELC-03", "Texas Components", "EE.UU.", "Austin", "Componente electrónico", 0.90, 85, 15, 5.60, "active"),
    ("SP-ELC-04", "CoreComp Manila", "Filipinas", "Manila", "Componente electrónico", 0.83, 68, 45, 4.40, "active"),
]

ZONES = [
    ("Z-REC", "Recepción", 5, 40, "[]"),
    ("Z-STO-A", "Almacenaje A (alta rotación)", 8, 200, "[]"),
    ("Z-STO-B", "Almacenaje B (media rotación)", 20, 300, "[]"),
    ("Z-PICK", "Zona de Picking", 3, 80, "[]"),
    ("Z-DOCK", "Muelle de salida", 1, 40, "[]"),
]

MACHINES = [
    ("MAC-CINT-01", "Cinta Transportadora Principal", "conveyor", 0.9, 80.0, 0),
    ("MAC-CINT-02", "Cinta Transportadora Empaque", "conveyor", 1.0, 75.0, 0),
    ("MAC-ROB-01", "Brazo Robótico Picking", "robot", 0.7, 70.0, 0),
    ("MAC-ROB-02", "Brazo Robótico Paletizado", "robot", 0.8, 65.0, 0),
    ("MAC-CINT-03", "Cinta Elevadora", "conveyor", 1.1, 60.0, 0),
]


def _seasonal_annual(date: datetime, sku: str) -> float:
    """Estacionalidad anual suave (picos estacionales reales)."""
    seed = hash(sku) % 1000
    yearly = 1 + 0.30 * math.sin(2 * math.pi * date.timetuple().tm_yday / 365 + seed % 6)
    return yearly


def _seasonal(date: datetime, sku: str) -> float:
    seed = hash(sku) % 1000
    yearly = 1 + 0.35 * math.sin(2 * math.pi * date.timetuple().tm_yday / 365 + seed % 6)
    weekly = 1 + 0.15 * math.sin(2 * math.pi * date.weekday() / 7 + seed % 4)
    rng = random.Random(seed + date.toordinal())
    noise = rng.uniform(0.75, 1.25)
    return yearly * weekly * noise


def seed(force: bool = False) -> None:
    db.init_db()
    # Mantenciones de flota siempre presentes (aunque la BD ya esté poblada)
    from .modules.wms import predictive_maintenance as pm

    pm.ensure_fleet_orders()
    if force:
        for tbl in ("recommendation_log", "alerts", "deliveries", "supplier_score_history",
                    "maintenance_telemetry", "work_orders", "sales_history",
                    "promotions", "stock", "machines", "warehouse_zones",
                    "suppliers", "carriers", "regions", "products", "logistic_orders"):
            db.execute(f"DELETE FROM {tbl}")
    _seed_logistic_orders()
    products = db.query_one("SELECT COUNT(*) AS c FROM products")
    if products and products["c"] > 0 and not force:
        return


    db.executemany("INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?)", PRODUCTS)
    db.executemany("INSERT OR REPLACE INTO regions VALUES (?,?,?)", REGIONS)
    db.executemany("INSERT OR REPLACE INTO carriers VALUES (?,?,?,?,?,?,?,?,?)", CARRIERS)
    db.executemany("INSERT OR REPLACE INTO suppliers VALUES (?,?,?,?,?,?,?,?,?,?)", SUPPLIERS)
    db.executemany("INSERT OR REPLACE INTO warehouse_zones VALUES (?,?,?,?,?)", ZONES)
    db.executemany("INSERT OR REPLACE INTO machines VALUES (?,?,?,?,?,?)", MACHINES)

    today = datetime.now()
    DOW = [0.68, 1.18, 1.28, 1.22, 1.15, 0.88, 0.70]
    ND = 180
    dates = [(today - timedelta(days=ND - 1 - i)).date() for i in range(ND)]
    dow_arr = np.array([DOW[d.weekday()] for d in dates])
    rows = []
    for sku, *_ in PRODUCTS:
        base = 1000 - hash(sku) % 800
        yearly = np.array(
            [_seasonal_annual(datetime.combine(d, datetime.min.time()), sku) for d in dates]
        )
        for region_id, *_ in REGIONS:
            rng = random.Random(hash((sku, region_id)) % 10**6)
            noise_arr = np.empty(ND)
            n = 1.0
            for i in range(ND):
                n = 0.45 * n + 0.55 * rng.uniform(0.82, 1.18)
                noise_arr[i] = n
            units_arr = np.maximum(0, (base * yearly * dow_arr * noise_arr).astype(int)).tolist()
            channel = "distribuidor" if region_id in {"R-FRA", "R-LIS", "R-MIL"} else "retail"
            rows.extend(
                (d.isoformat(), sku, region_id, int(u), round(u * random.uniform(4, 40), 2), channel)
                for d, u in zip(dates, units_arr)
            )
    db.executemany(
        "INSERT INTO sales_history (date, sku, region_id, units, price_eur, channel) VALUES (?,?,?,?,?,?)",
        rows,
    )

    promos = [
        ("SKU-PLS-001", "R-MAD", "discount", (today - timedelta(days=5)).date().isoformat(),
         (today + timedelta(days=6)).date().isoformat(), 1.35),
        ("SKU-BAT-001", "R-BCN", "bundle", (today - timedelta(days=1)).date().isoformat(),
         (today + timedelta(days=9)).date().isoformat(), 1.5),
        ("SKU-TAL-001", "R-VLC", "holiday", (today - timedelta(days=2)).date().isoformat(),
         (today + timedelta(days=7)).date().isoformat(), 1.4),
        ("SKU-ACE-001", "R-SEV", "discount", today.date().isoformat(),
         (today + timedelta(days=14)).date().isoformat(), 1.25),
    ]
    db.executemany(
        "INSERT INTO promotions (sku, region_id, promo_type, start_date, end_date, impact_factor) VALUES (?,?,?,?,?,?)",
        promos,
    )

    stock = []
    zones_cold = ["Z-STO-B", "Z-PICK", "Z-STO-B"]  # algunos lejos del muelle para que el slotting sugiera movimientos
    for sku, *_ in PRODUCTS:
        for region_id, *_ in REGIONS:
            zone = zones_cold[hash(sku) % len(zones_cold)]
            stock.append((sku, region_id, zone, random.randint(30, 400), 60))
    db.executemany("INSERT OR REPLACE INTO stock VALUES (?,?,?,?,?)", stock)

    # Telemetría histórica normal
    mt_rows = []
    for mid, *_ in MACHINES:
        for i in range(30):
            ts = datetime.now() - timedelta(hours=i)
            mt_rows.append((mid, ts.isoformat(),
                            round(random.gauss(0.4, 0.08), 3),
                            round(random.gauss(55, 4), 1), 0))
    db.executemany(
        "INSERT INTO maintenance_telemetry (machine_id, ts, vibration, temperature, anomaly) VALUES (?,?,?,?,?)",
        mt_rows,
    )

    _seed_deliveries()
    _seed_score_history()
    _seed_recommendations()


CITY_COORDS = {
    # Sudamérica (Brasil - Conexión directa con BD_Logistica e Ifood)
    "WH-BH": (-19.9167, -43.9345), "Belo Horizonte": (-19.9167, -43.9345),
    "WH-SP": (-23.5505, -46.6333), "São Paulo": (-23.5505, -46.6333),
    "WH-RJ": (-22.9068, -43.1729), "Rio de Janeiro": (-22.9068, -43.1729),
    "Curitiba": (-25.4284, -49.2733), "Porto Alegre": (-30.0346, -51.2177),
    "Brasília": (-15.7975, -47.8919), "Campinas": (-22.9099, -47.0626),
    "Santos": (-23.9618, -46.3322),
    # Sudamérica (Cono Sur & Andina)
    "WH-BUE": (-34.6037, -58.3816), "Buenos Aires": (-34.6037, -58.3816),
    "WH-SCL": (-33.4489, -70.6693), "Santiago": (-33.4489, -70.6693),
    "WH-LIM": (-12.0464, -77.0428), "Lima": (-12.0464, -77.0428),
    "WH-BOG": (4.7110, -74.0721), "Bogotá": (4.7110, -74.0721),
    "Mendoza": (-32.8895, -68.8458), "Rosario": (-32.9468, -60.6393),
    "Montevideo": (-34.9011, -56.1645), "Córdoba AR": (-31.4201, -64.1888),
    "Valparaíso": (-33.0472, -71.6127), "Medellín": (6.2442, -75.5812),
    # Conexiones Internacionales / Globales
    "WH-MEX": (19.4326, -99.1332), "Ciudad de México": (19.4326, -99.1332),
    "WH-MIA": (25.7617, -80.1918), "Miami": (25.7617, -80.1918),
    "WH-MAD": (40.4168, -3.7038), "Madrid": (40.4168, -3.7038),
    "WH-BCN": (41.3874, 2.1686), "Barcelona": (41.3874, 2.1686),
    "WH-VLC": (39.4699, -0.3763), "Valencia": (39.4699, -0.3763),
    "WH-SEV": (37.3891, -5.9845), "Sevilla": (37.3891, -5.9845),
    "WH-BIL": (43.263, -2.935), "Bilbao": (43.263, -2.935),
    "WH-FRA": (50.1109, 8.6821), "Frankfurt": (50.1109, 8.6821),
    "WH-LIS": (38.7223, -9.1393), "Lisboa": (38.7223, -9.1393),
    "WH-MIL": (45.4642, 9.19), "Milán": (45.4642, 9.19),
}


def _seed_deliveries():
    today = datetime.now()
    # Envíos estratégicos: Sudamérica protagonista + rutas globales transcontinentales
    trips = [
        # Corredores principales Brasil (Dataset Ifood & BD Logistica)
        ("WH-SP", "Rio de Janeiro", "in_transit", "", 0.42, 78, 0),
        ("WH-BH", "São Paulo", "in_transit", "tráfego pesado Rodovia Fernão Dias", 0.65, 62, 28),
        ("WH-RJ", "Belo Horizonte", "in_transit", "", 0.28, 75, 0),
        ("WH-SP", "Campinas", "in_transit", "", 0.85, 84, 0),
        ("WH-SP", "Santos", "in_transit", "obras na serra", 0.70, 48, 15),
        ("WH-SP", "Curitiba", "in_transit", "", 0.35, 80, 0),
        ("WH-BH", "Brasília", "planned", "", 0.0, 0, 0),
        # Corredores Cono Sur (Argentina & Chile)
        ("WH-BUE", "Rosario", "in_transit", "", 0.52, 88, 0),
        ("WH-BUE", "Mendoza", "in_transit", "viento zonda en cordillera", 0.38, 70, 35),
        ("WH-SCL", "Valparaíso", "in_transit", "", 0.78, 82, 0),
        ("WH-SCL", "Mendoza", "disrupted", "cierre preventivo Paso Los Libertadores", 0.46, 0, 90),
        ("WH-BUE", "Montevideo", "in_transit", "", 0.60, 65, 0),
        # Corredor Andino (Colombia & Perú)
        ("WH-BOG", "Medellín", "in_transit", "derrumbe en autopista", 0.50, 45, 45),
        ("WH-LIM", "Santiago", "in_transit", "", 0.25, 82, 0),
        # Enlaces marítimos/aéreos Globales (Sudamérica ➔ Norteamérica / Europa)
        ("WH-SP", "Miami", "in_transit", "", 0.58, 850, 0),
        ("WH-BUE", "Madrid", "in_transit", "", 0.64, 870, 0),
        ("WH-RJ", "Lisboa", "in_transit", "", 0.48, 860, 0),
        ("WH-MEX", "Bogotá", "in_transit", "", 0.35, 780, 0),
        # Europa (continuidad de hubs)
        ("WH-MAD", "Barcelona", "in_transit", "", 0.45, 85, 0),
        ("WH-FRA", "Madrid", "planned", "", 0.0, 0, 0),
    ]
    for i, (origin, destination, status, reason, progress, speed, delay) in enumerate(trips):
        carrier = CARRIERS[i % len(CARRIERS)]
        region = REGIONS[i % len(REGIONS)]
        window_start = today.replace(hour=(8 + (i % 12)), minute=0).isoformat()
        a = CITY_COORDS.get(origin)
        b = CITY_COORDS.get(destination)
        lat = lng = 0.0
        if a and b:
            lat = a[0] + (b[0] - a[0]) * progress
            lng = a[1] + (b[1] - a[1]) * progress
        telemetry = json.dumps({
            "status": status,
            "lat": round(lat, 4), "lng": round(lng, 4),
            "speed_kmh": speed,
            "progress_pct": round(progress * 100, 1),
            "delay_min": delay, "reason": reason,
        })
        db.execute(
            """INSERT INTO deliveries
               (shipment_id, carrier_id, origin, destination, customer_id,
                vehicle_telemetry, route_plan, planned_eta, current_eta,
                required_window_start, required_window_end, cost_eur, status, incident_log)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"SHIP-{1000+i}", carrier[0],
                origin, destination, f"CUST-{i}",
                telemetry,
                '[]', today.isoformat(), today.isoformat(),
                window_start, today.replace(hour=(11 + (i % 12)), minute=0).isoformat(),
                carrier[5] * 300, status, '[]',
            ),
        )


def _seed_recommendations():
    """Sugerencias de IA pre-generadas para que Gobernanza muestre feed desde el inicio."""
    now = db.now_iso()
    rows = [
        ("routing", "reroute_delivery",
         "Re-rutar SHIP-1002 vía Bilbao: retención aduanera detectada en Irún, el desvío ahorra 95 min en el ETA del cliente.",
         {"delay_min": 95, "candidates": 3, "eta_saved_h": 1.58, "data_verified": True},
         0.91, 1240.0, 1, "requires_approval"),
        ("suppliers", "switch_supplier",
         "Sustituir compra de motores eléctricos: Precision Electric GmbH (score 88) frente a Motores del Sur S.A. (score 62) para recuperar OTIF.",
         {"score_new": 88, "score_current": 62, "cost_delta_pct": 15.9, "otif_gain": 0.07},
         0.87, 3400.0, 1, "requires_approval"),
        ("wms", "slotting_rebalance",
         "Reubicar SKU-BAT-001 de Z-STO-B a Z-DOCK: alta rotación detectada, reduce el tiempo de picking un 23%.",
         {"turnover_rank": 1, "distance_saved_m": 12, "dock_distance_new": 1},
         0.94, 560.0, 0, "approved"),
    ]
    for module, action, description, factors, confidence, impact, req, status in rows:
        db.execute(
            """INSERT INTO recommendation_log
               (module, action, description, factors, confidence,
                estimated_impact_eur, requires_human_approval, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (module, action, description, json.dumps(factors),
             confidence, impact, req, status, now),
        )


def _seed_score_history():
    for s in SUPPLIERS:
        breakdown = {"otif": s[5], "financial": s[6] / 100, "geo_risk": s[7] / 100}
        score = round(100 - (100 * ((1 - s[5]) * 0.5 + (100 - s[6]) / 100 * 0.3 + s[7] / 100 * 0.2)), 1)
        db.execute(
            "INSERT INTO supplier_score_history (supplier_id, score, breakdown, evaluated_at) VALUES (?,?,?,?)",
            (s[0], score, json.dumps(breakdown), db.now_iso()),
        )


def _seed_logistic_orders() -> None:
    """Asegura que los 4.282 registros de BD_Logistica estén cargados en SQLite."""
    existing = db.query_one("SELECT COUNT(*) AS c FROM logistic_orders")
    if existing and existing["c"] > 0:
        return

    # Intentar desde Excel si existe
    try:
        from pathlib import Path
        excel_path = Path(db._db_path()).parent / "BD_Logistica.xlsx"
        if excel_path.exists():
            from scripts.ingest_logistic_db import ingest_logistic_dataset
            ingest_logistic_dataset(excel_file=excel_path, db_file=db._db_path())
            return
    except Exception:
        pass

    # Generación determinista fiel al dataset BD_Logistica (4.282 pedidos: BH 1494, SP 1413, RJ 1375; 3.135 Atrasados)
    rng = random.Random(4282)
    destinations = (["BH"] * 1494) + (["SP"] * 1413) + (["RJ"] * 1375)
    rng.shuffle(destinations)

    statuses = (["Atrasado"] * 3135) + (["No Prazo"] * 1147)
    rng.shuffle(statuses)

    return_reasons = (
        (["Produto Errado"] * 1562)
        + (["Danificado"] * 1339)
        + (["Arrependimento"] * 285)
        + (["S/ Devolu."] * 1096)
    )
    rng.shuffle(return_reasons)

    clients = [
        "Supermercado Central", "Rede Brasil Sul", "Atacadão Minas",
        "Distribuidora Paulista", "Comercial Carioca", "Empório Sudeste",
        "Logística Express BR", "Grupo Varejo Nacional",
    ]
    drivers = [
        "Carlos Mendes", "João Silva", "Marcos Oliveira", "Rafael Costa",
        "Pedro Santos", "Lucas Ferreira", "André Souza", "Felipe Almeida",
        "Bruno Lima", "Gustavo Pereira",
    ]

    base_date = datetime.now().date() - timedelta(days=120)
    rows = []
    for idx in range(4282):
        order_id = f"PED-{20250001 + idx}"
        client = clients[idx % len(clients)]
        driver = drivers[(idx * 3 + rng.randint(0, 2)) % len(drivers)]
        dest = destinations[idx]
        status = statuses[idx]
        ret_reason = return_reasons[idx]
        ret_qty = 0 if ret_reason == "S/ Devolu." else rng.randint(1, 8)
        items = rng.randint(5, 85)
        billed = round(items * rng.uniform(28.5, 115.0), 2)

        issue_d = base_date + timedelta(days=rng.randint(0, 100))
        planned_d = issue_d + timedelta(days=10)
        disp_d = issue_d + timedelta(days=rng.randint(1, 3))
        if status == "Atrasado":
            deliv_days = rng.randint(11, 17)
        else:
            deliv_days = rng.randint(6, 10)
        actual_d = issue_d + timedelta(days=deliv_days)

        rows.append((
            order_id, client, driver,
            issue_d.isoformat(), planned_d.isoformat(), dest,
            items, billed, disp_d.isoformat(), actual_d.isoformat(),
            ret_qty, ret_reason, deliv_days, status,
        ))

    db.executemany(
        """INSERT OR IGNORE INTO logistic_orders (
            order_id, client, driver, issue_date, planned_delivery_date,
            destination, items_count, billed_brl, dispatched_date,
            actual_delivery_date, return_quantity, return_reason,
            delivery_days, delay_status
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )

