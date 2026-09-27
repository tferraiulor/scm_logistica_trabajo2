# SCM-Platform

Plataforma de gestión de la cadena de suministro con IA y gobierno humano
(human-in-the-loop). Funciona **100% offline** y se autosirve: arranca como
servidor local (puerto 8100 o el primero libre) con una SPA en un solo
fichero.

## Módulos

| # | Módulo | Qué hace |
|---|--------|----------|
| M1 | Previsión Touchless | Lee el histórico de ventas, genera previsiones por producto/región, corrige picos anómalos (MAPE) y alerta de críticos. |
| M2 | Enrutamiento Agéntico | Mapa con red de carreteras y camiones situados por su % de avance (etiqueta por envío). Retraso/rupturas activan re-licitación con alternativos (capacidad, coste, ETA, fiabilidad). |
| M3 | Almacén Dinámico | Slotting de alta rotación, mantenimiento predictivo por sensores IoT (>3σ genera orden de trabajo) y preventivo de flota por kilometraje. |
| M4 | Riesgo de Proveedores | Puntuación 0–100 por fiabilidad/calidad/antigüedad; alerta <60 con motivo y alternativas. |
| M5 | Gobernanza HITL | Toda decisión de IA requiere aprobación humana salvo excepción (bajo impacto, alta confianza). Evidencia, impacto € y riesgo en cada pendiente. |

Un **agente en background** monitoriza la telemetría de los envíos en vivo:
incidencias la mayoría recuperables, escalada a parada con re-licitación y
avance muy lento del progreso. KPIs refrescados cada 20 s; mapa cada 8 s;
trabajos cada 15 s.

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