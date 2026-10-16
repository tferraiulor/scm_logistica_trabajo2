"""Script de ingestión y carga del dataset logístico real (BD_Logistica.xlsx).

Limpia valores nulos, formatea fechas de emisión, entrega prevista y real,
separa cliente y motorista, y puebla la base de datos local SQLite (data/scm.db).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scm.ingest_logistic")

BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = BASE_DIR / "data" / "BD_Logistica.xlsx"
DB_PATH = BASE_DIR / "data" / "scm.db"


def ingest_logistic_dataset(excel_file: Path = EXCEL_PATH, db_file: Path = DB_PATH) -> dict:
    if not excel_file.exists():
        # Fallback a descargas si no estuviera en data/
        downloads_alt = Path.home() / "Downloads" / "BD_Logistica.xlsx"
        if downloads_alt.exists():
            excel_file = downloads_alt
        else:
            raise FileNotFoundError(f"No se encontró el archivo Excel en {excel_file} ni en {downloads_alt}")

    logger.info(f"Leyendo dataset logístico desde: {excel_file}")
    df = pd.read_excel(excel_file)
    initial_rows = len(df)
    logger.info(f"Filas leídas originalmente: {initial_rows}")

    # 1. Normalizar nombres de columnas eliminando espacios accidentales
    df.columns = [c.strip() for c in df.columns]

    # 2. Manejo y limpieza de valores nulos
    # Separar Cliente y Motorista
    driver_col = "Cliente - Motorista"
    if driver_col in df.columns:
        parts = df[driver_col].astype(str).str.split("-", n=1, expand=True)
        df["Cliente"] = parts[0].str.strip()
        df["Motorista"] = parts[1].str.strip() if parts.shape[1] > 1 else "No Asignado"
    else:
        df["Cliente"] = "General"
        df["Motorista"] = "Flota Propia"

    # 3. Formateo de fechas a ISO YYYY-MM-DD
    date_cols = ["Data Emissão Pedido", "Data Entrega Prevista", "Saída para Entrega", "Data Entrega Real"]
    for d_col in date_cols:
        if d_col in df.columns:
            df[d_col] = pd.to_datetime(df[d_col], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        else:
            df[d_col] = ""

    # 4. Formatear números y nulos
    df["Nº Pedido"] = df["Nº Pedido"].astype(str).str.strip()
    df["Destino"] = df["Destino"].astype(str).str.strip().str.upper()
    df["Itens"] = pd.to_numeric(df["Itens"], errors="coerce").fillna(1).astype(int)
    df["R$ Faturados"] = pd.to_numeric(df["R$ Faturados"], errors="coerce").fillna(0.0).round(2)
    
    qty_dev_col = "Qtd Devolução" if "Qtd Devolução" in df.columns else "Qtd Devolução"
    df["Qtd Devolução"] = pd.to_numeric(df[qty_dev_col], errors="coerce").fillna(0).astype(int)
    
    df["Mot. Devolução"] = df.get("Mot. Devolução", pd.Series(["S/ Devolu."] * len(df))).fillna("S/ Devolu.").astype(str).str.strip()
    df["Dias Para Entrega"] = pd.to_numeric(df.get("Dias Para Entrega", 0), errors="coerce").fillna(0).astype(int)
    df["Status"] = df["Status"].astype(str).str.strip()

    # 5. Insertar en SQLite
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    # Asegurar creación de la tabla
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logistic_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE NOT NULL,
        client TEXT NOT NULL,
        driver TEXT NOT NULL,
        issue_date TEXT,
        planned_delivery_date TEXT,
        destination TEXT NOT NULL,
        items_count INTEGER NOT NULL DEFAULT 0,
        billed_brl REAL NOT NULL DEFAULT 0.0,
        dispatched_date TEXT,
        actual_delivery_date TEXT,
        return_quantity INTEGER DEFAULT 0,
        return_reason TEXT,
        delivery_days INTEGER DEFAULT 0,
        delay_status TEXT NOT NULL
    );
    """)

    # Borrar tabla previa para carga fresca de datos reales
    cur.execute("DELETE FROM logistic_orders")

    records = []
    for _, row in df.iterrows():
        records.append((
            row["Nº Pedido"],
            row["Cliente"],
            row["Motorista"],
            row["Data Emissão Pedido"],
            row["Data Entrega Prevista"],
            row["Destino"],
            int(row["Itens"]),
            float(row["R$ Faturados"]),
            row["Saída para Entrega"],
            row["Data Entrega Real"],
            int(row["Qtd Devolução"]),
            row["Mot. Devolução"],
            int(row["Dias Para Entrega"]),
            row["Status"]
        ))

    cur.executemany("""
    INSERT OR REPLACE INTO logistic_orders (
        order_id, client, driver, issue_date, planned_delivery_date,
        destination, items_count, billed_brl, dispatched_date,
        actual_delivery_date, return_quantity, return_reason,
        delivery_days, delay_status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, records)

    conn.commit()
    conn.close()

    total_inserted = len(records)
    logger.info(f"Base de datos {db_file} poblada con éxito: {total_inserted} pedidos logísticos.")
    return {
        "status": "success",
        "total_records": total_inserted,
        "destinations": df["Destino"].value_counts().to_dict(),
        "delay_summary": df["Status"].value_counts().to_dict(),
    }


if __name__ == "__main__":
    res = ingest_logistic_dataset()
    print("Resultado de Ingestión:", res)
