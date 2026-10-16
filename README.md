# SCM-Platform

Plataforma de gestión de la cadena de suministro con IA y gobierno humano
(human-in-the-loop). Funciona **100% offline** y se autosirve: arranca como
servidor local (puerto 8100 o el primero libre) con una SPA en un solo
fichero.

## Módulos y Pestañas de la Plataforma

| # | Módulo / Pestaña | Qué hace |
|---|------------------|----------|
| M1 | 1 · Previsión Touchless | Previsiones de demanda por producto/región, corrección de anomalías (MAPE) y alertas de rotura de stock. |
| M2 | 2 · Rutas & Agente | Mapa Satelital HD centrado en Sudamérica (SP, BH, RJ) y rutas globales. Monitorización en vivo con bucle agéntico de auto-relicitación. |
| M3 | 3 · Almacén Dinámico | Slotting predictivo de alta rotación y mantenimiento preventivo IoT de maquinaria. |
| M4 | 4 · Proveedores | Puntuación de riesgo 0–100 (OTIF, estabilidad y riesgo geopolítico). |
| M5 | 5 · Gobernanza HITL | Auditoría de decisiones de IA y control humano para acciones de alto impacto. |
| P6 | 6 · Cargar Stock | Importador intuitivo Drag & Drop para Excel `.xlsx` / `.xls` y CSV, con descarga de plantilla oficial y contador en vivo. |
| P7 | 7 · Registro de Ventas | Transmisión de ventas en tiempo real con simulación reactiva, alertas de reposición y desglose de canales. |
| P8 | 8 · Dataset Real (Ifood 4.282) | Ingesta y análisis de 4.282 despachos reales de `BD_Logistica.xlsx` en SQLite local: BH, SP, RJ, motoristas y causas de devolución. |
| P9 | 9 · Hallazgos EDA Ifood (153.604) | Diagnóstico analítico de causa raíz: retraso en cocina (38,82%) vs repartidor (9,97%), motos vs bicicletas y rutas multi-drop. |
| P10 | 10 · Protocolo & Testeo C2 | Protocolo estricto y registro formal cuali-cuantitativo del primer testeo con usuarios reales, métricas SUS y análisis DEO. |

Un **agente en background** monitoriza la telemetría de los envíos en vivo:
incidencias recuperables, escalada a parada con re-licitación y
avance continuo. KPIs refrescados cada 20 s; mapa cada 8 s;
ventas y stock en vivo cada 3–4 s.

## Inicio rápido

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python run.py                  # http://127.0.0.1:8100
```

La base de datos y los datos de demostración se generan automáticamente en
`data/` al primer arranque. No hace falta instalar nada más.

## Ejecutable portable (Windows)

Se puede compilar a un único `.exe` sin consola con PyInstaller:

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --noconsole --name SCM-Platform \
  --add-data "static;static" \
  --hidden-import "uvicorn.logging" \
  --hidden-import "uvicorn.loops.auto" \
  --hidden-import "uvicorn.loops.asyncio" \
  --hidden-import "uvicorn.protocols.http.auto" \
  --hidden-import "uvicorn.protocols.http.h11_impl" \
  --hidden-import "uvicorn.protocols.websockets.auto" \
  --hidden-import "uvicorn.protocols.websockets.wsproto_impl" \
  --hidden-import "uvicorn.lifespan.on" \
  --hidden-import "anyio" \
  launcher.py
```

El `launcher.py` busca el primer puerto libre 8100-8115, crea `data/` junto al
`.exe`, guarda `scm.log` y muestra una ventana de error si algo falla. Hay un
workflow de GitHub Actions (`.github/workflows/build.yml`) que compila el `.exe`
en un tag `v*`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests -q
```

## Configuración (variables de entorno)

| Variable | Default | Efecto |
|----------|---------|--------|
| `DATABASE_URL` | `data/scm.db` | Ruta SQLite |
| `FORECAST_HORIZON` | `30` | Días de previsión |
| `HITL_COST_THRESHOLD` | `5000` | € desde el que pasa por HITL |
| `HITL_AUTO_ACTIONS` | `reslot_inventory` | Acciones auto-ejecutables |
| `HITL_AUTO_MAX_IMPACT` | `500` | Impacto € máx. para autonomía |
| `HITL_AUTO_MIN_CONF` | `0.9` | Confianza mínima para autonomía |
| `AGENT_POLL_SEC` | `15` | Cadencia del agente (s) |
| `RISK_CRITICAL` / `RISK_WARNING` | `30` / `60` | Umbrales de proveedores |

## Estructura

```
SCM-Platform/
├── app/                  # FastAPI: config, main (agente+API), módulos
│   ├── modules/
│   │   ├── demand_planning/      # M1
│   │   ├── routing/              # M2 (agente + re-licitación)
│   │   ├── wms/                  # M3 (slotting + mantenimiento)
│   │   ├── suppliers/            # M4
│   │   └── governance/           # M5 (HITL)
│   └── services/                 # Clientes externos (meteo, etc.)
├── static/               # SPA monofichero + libs (sin CDN)
├── scripts/              # Utilidades (generador CSV demo, reset, sync)
├── tests/                # Pruebas de humo (20)
├── run.py                # Punto de entrada servidor
└── launcher.py           # Punto de entrada ejecutable portable
```

## Licencia

MIT. Ver `LICENSE`.