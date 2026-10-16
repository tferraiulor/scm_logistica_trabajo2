from __future__ import annotations

"""Gestor de inventario y carga de stock (manual y masiva por CSV).

Permite el ingreso, ajuste y regularización de existencias físicas
por producto y almacén regional, así como la importación masiva por archivo CSV.
"""

import csv
import io
import logging
from typing import Any, Dict, List, Optional

from ... import database as db

logger = logging.getLogger("scm.wms.stock")


def update_stock(
    sku: str,
    region_id: str,
    quantity: int,
    warehouse_zone: Optional[str] = None,
    mode: str = "add",  # "add" | "subtract" | "set"
    reorder_point: Optional[int] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Actualiza o crea un registro de stock para un SKU y región dada.
    
    Modes:
      - 'add': suma quantity a las existencias actuales.
      - 'subtract': resta quantity de las existencias actuales (mínimo 0).
      - 'set': fija el stock directamente a quantity.
    """
    sku = sku.strip().upper()
    region_id = region_id.strip().upper()
    quantity = int(quantity)

    # Validar que el producto exista o crearlo si es nuevo
    prod = db.query_one("SELECT * FROM products WHERE sku=?", (sku,))
    if not prod:
        # Registrar producto genérico si no existe
        db.execute(
            "INSERT OR IGNORE INTO products (sku, name, category, weight_kg, fragile) VALUES (?, ?, ?, ?, ?)",
            (sku, f"Producto {sku}", "general", 1.0, 0),
        )

    # Consultar stock actual
    curr = db.query_one(
        "SELECT * FROM stock WHERE sku=? AND region_id=?", (sku, region_id)
    )

    if curr:
        curr_on_hand = int(curr["on_hand"])
        curr_rp = int(curr["reorder_point"])
        curr_zone = curr["warehouse_zone"] or "Z-STO-A"
    else:
        curr_on_hand = 0
        curr_rp = 50
        curr_zone = "Z-STO-A"

    if mode == "add":
        new_on_hand = curr_on_hand + quantity
    elif mode == "subtract":
        new_on_hand = max(0, curr_on_hand - quantity)
    elif mode == "set":
        new_on_hand = max(0, quantity)
    else:
        raise ValueError(f"Modo de actualización desconocido: {mode}")

    target_zone = warehouse_zone if warehouse_zone else curr_zone
    target_rp = int(reorder_point) if reorder_point is not None else curr_rp

    db.execute(
        """INSERT OR REPLACE INTO stock (sku, region_id, warehouse_zone, on_hand, reorder_point)
           VALUES (?, ?, ?, ?, ?)""",
        (sku, region_id, target_zone, new_on_hand, target_rp),
    )

    # Verificar si cae en nivel crítico o si se recuperó
    alert_created = False
    if new_on_hand <= target_rp:
        severity = "critical" if new_on_hand == 0 else "warning"
        msg = f"Stock bajo en {region_id}: {sku} tiene {new_on_hand} unidades (punto de reorden: {target_rp})"
        db.execute(
            """INSERT INTO alerts (module, type, severity, message, payload, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, 'open')""",
            (
                "wms",
                "stockout",
                severity,
                msg,
                db.jdumps({"sku": sku, "region_id": region_id, "on_hand": new_on_hand, "notes": notes}),
                db.now_iso(),
            ),
        )
        alert_created = True

    return {
        "sku": sku,
        "region_id": region_id,
        "previous_on_hand": curr_on_hand,
        "on_hand": new_on_hand,
        "warehouse_zone": target_zone,
        "reorder_point": target_rp,
        "mode": mode,
        "quantity_delta": quantity if mode != "set" else (new_on_hand - curr_on_hand),
        "is_critical": new_on_hand <= target_rp,
        "alert_created": alert_created,
    }


def import_stock_csv(content_str: str, default_mode: str = "add") -> Dict[str, Any]:
    """Procesa e ingesta un archivo o texto CSV con inventario.
    
    Formato esperado (con encabezados en minúsculas o mayúsculas):
    sku,region_id,warehouse_zone,quantity,reorder_point
    """
    f = io.StringIO(content_str.strip())
    # Detectar delimitador (coma o punto y coma)
    first_line = content_str.splitlines()[0] if content_str.splitlines() else ""
    delimiter = ";" if ";" in first_line and "," not in first_line else ","
    
    reader = csv.DictReader(f, delimiter=delimiter)
    
    rows_processed = 0
    rows_updated = 0
    errors: List[str] = []
    results: List[Dict[str, Any]] = []

    for idx, row in enumerate(reader, start=2):
        rows_processed += 1
        # Normalizar claves a minúsculas
        clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
        
        sku = clean_row.get("sku") or clean_row.get("producto") or clean_row.get("codigo")
        region_id = clean_row.get("region_id") or clean_row.get("region") or clean_row.get("almacen")
        qty_str = clean_row.get("quantity") or clean_row.get("cantidad") or clean_row.get("stock")
        zone = clean_row.get("warehouse_zone") or clean_row.get("zona") or "Z-STO-A"
        rp_str = clean_row.get("reorder_point") or clean_row.get("punto_reorden")

        if not sku or not region_id or not qty_str:
            errors.append(f"Fila {idx}: faltan campos obligatorios (sku, region_id o quantity)")
            continue

        try:
            qty = int(float(qty_str))
            rp = int(float(rp_str)) if rp_str else None
        except ValueError:
            errors.append(f"Fila {idx}: cantidad o punto de reorden no es numérico ({qty_str})")
            continue

        try:
            res = update_stock(
                sku=sku,
                region_id=region_id,
                quantity=qty,
                warehouse_zone=zone,
                mode=default_mode,
                reorder_point=rp,
                notes=f"Importación masiva CSV fila {idx}",
            )
            rows_updated += 1
            results.append(res)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Fila {idx} ({sku}): {exc}")

    return {
        "rows_processed": rows_processed,
        "rows_updated": rows_updated,
        "errors": errors,
        "results": results[:20],  # muestra de primeros resultados
    }


def import_stock_excel(file_bytes: bytes, default_mode: str = "add") -> Dict[str, Any]:
    """Procesa e ingesta un archivo Excel (.xlsx / .xls) con inventario.
    
    Busca columnas equivalentes a:
    sku / producto / codigo
    region_id / region / almacen
    warehouse_zone / zona
    quantity / cantidad / stock
    reorder_point / punto_reorden / minimo
    """
    import pandas as pd

    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError(f"No se pudo leer el archivo Excel: {exc}") from exc

    # Limpiar nombres de columnas
    df.columns = [str(c).strip().lower() for c in df.columns]

    rows_processed = 0
    rows_updated = 0
    errors: List[str] = []
    results: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        row_num = idx + 2
        rows_processed += 1

        sku = row.get("sku") or row.get("producto") or row.get("codigo")
        region_id = row.get("region_id") or row.get("region") or row.get("almacen")
        qty_val = row.get("quantity") if "quantity" in row else (row.get("cantidad") if "cantidad" in row else row.get("stock"))
        zone = row.get("warehouse_zone") or row.get("zona") or "Z-STO-A"
        rp_val = row.get("reorder_point") if "reorder_point" in row else (row.get("punto_reorden") if "punto_reorden" in row else row.get("minimo"))

        if pd.isna(sku) or pd.isna(region_id) or pd.isna(qty_val):
            errors.append(f"Fila {row_num}: faltan campos obligatorios (sku, region o cantidad)")
            continue

        sku_str = str(sku).strip()
        region_str = str(region_id).strip()
        zone_str = str(zone).strip() if not pd.isna(zone) else "Z-STO-A"

        try:
            qty = int(float(qty_val))
            rp = int(float(rp_val)) if not pd.isna(rp_val) and str(rp_val).strip() != "" else None
        except (ValueError, TypeError):
            errors.append(f"Fila {row_num}: cantidad o punto de reorden inválido ({qty_val})")
            continue

        try:
            res = update_stock(
                sku=sku_str,
                region_id=region_str,
                quantity=qty,
                warehouse_zone=zone_str,
                mode=default_mode,
                reorder_point=rp,
                notes=f"Importación Excel fila {row_num}",
            )
            rows_updated += 1
            results.append(res)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Fila {row_num} ({sku_str}): {exc}")

    return {
        "rows_processed": rows_processed,
        "rows_updated": rows_updated,
        "errors": errors,
        "results": results[:20],
    }


def get_excel_template() -> bytes:
    """Genera y devuelve bytes de un archivo Excel .xlsx con plantilla de stock."""
    import pandas as pd
    data = [
        {"sku": "SKU-PLS-001", "region_id": "R-MAD", "warehouse_zone": "Z-STO-A", "quantity": 150, "reorder_point": 60},
        {"sku": "SKU-PLS-002", "region_id": "R-BCN", "warehouse_zone": "Z-STO-B", "quantity": 80, "reorder_point": 50},
        {"sku": "SKU-BAT-001", "region_id": "R-VLC", "warehouse_zone": "Z-PICK", "quantity": 120, "reorder_point": 40},
        {"sku": "SKU-TAL-001", "region_id": "R-SEV", "warehouse_zone": "Z-STO-A", "quantity": 95, "reorder_point": 45},
        {"sku": "SKU-ACE-001", "region_id": "R-BIL", "warehouse_zone": "Z-STO-B", "quantity": 200, "reorder_point": 80},
    ]
    df = pd.DataFrame(data)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Stock")
    return out.getvalue()


def get_stock_summary() -> Dict[str, Any]:
    """Calcula métricas globales agregadas sobre el stock."""
    total_skus = db.query_one("SELECT COUNT(DISTINCT sku) AS c FROM products")["c"]
    total_units_row = db.query_one("SELECT COALESCE(SUM(on_hand), 0) AS total FROM stock")
    total_units = int(total_units_row["total"]) if total_units_row else 0
    
    total_records = db.query_one("SELECT COUNT(*) AS c FROM stock")["c"]
    critical_records = db.query_one("SELECT COUNT(*) AS c FROM stock WHERE on_hand <= reorder_point")["c"]
    
    regions = db.query(
        """SELECT s.region_id, r.name AS region_name, 
                  SUM(s.on_hand) AS total_units,
                  COUNT(s.sku) AS sku_count,
                  SUM(CASE WHEN s.on_hand <= s.reorder_point THEN 1 ELSE 0 END) AS critical_count
           FROM stock s
           LEFT JOIN regions r ON r.region_id = s.region_id
           GROUP BY s.region_id
           ORDER BY total_units DESC"""
    )
    
    return {
        "total_skus": total_skus,
        "total_units": total_units,
        "total_locations": total_records,
        "critical_count": critical_records,
        "regions": regions,
    }


def get_csv_template() -> str:
    """Devuelve el contenido CSV de ejemplo para descargar."""
    return (
        "sku,region_id,warehouse_zone,quantity,reorder_point\n"
        "SKU-PLS-001,R-MAD,Z-STO-A,150,60\n"
        "SKU-PLS-002,R-BCN,Z-STO-B,80,50\n"
        "SKU-BAT-001,R-VLC,Z-PICK,120,40\n"
        "SKU-TAL-001,R-SEV,Z-STO-A,95,45\n"
        "SKU-ACE-001,R-BIL,Z-STO-B,200,80\n"
    )
