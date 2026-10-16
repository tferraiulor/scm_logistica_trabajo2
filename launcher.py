from __future__ import annotations

"""Punto de entrada para el ejecutable autónomo (PyInstaller).

- Coloca la base de datos al lado del .exe (carpeta «data»), escribible.
- Sirve la SPA embebida en 0.0.0.0 (accesible por IP/LAN), puerto 8100 o el
  primero libre.
- Si algo falla, muestra una ventana con el error y lo guarda en scm.log.
"""

import logging
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

if getattr(sys, "frozen", False):
    EXE_DIR = Path(sys.executable).resolve().parent
else:
    EXE_DIR = Path(__file__).resolve().parent

LOG_FILE = EXE_DIR / "scm.log"


def _log(msg: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    except Exception:
        pass


def _alert(msg: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "SCM-Platform", 0x10)
    except Exception:
        pass


def _find_port(start: int = 8100, tries: int = 16) -> int | None:
    for port in range(start, start + tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
    return None


def _bootstrap() -> None:
    import app.config as config

    data_dir = EXE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    config.SQLITE_PATH = data_dir / "scm.db"
    config.DATABASE_URL = f"sqlite+aiosqlite:///{data_dir / 'scm.db'}"


def _open_browser(port: int) -> None:
    time.sleep(3)
    try:
        webbrowser.open(f"http://127.0.0.1:{port}")
    except Exception as exc:  # noqa: BLE001
        _log(f"No se pudo abrir el navegador: {exc}")


def main() -> None:
    _log("Solicitud de arranque recibida")
    try:
        _bootstrap()
        if sys.stdout is None or sys.stderr is None:
            import io

            _log("Modo ventana: sin consola, se usan streams internos")
            if sys.stdout is None:
                sys.stdout = io.StringIO()
            if sys.stderr is None:
                sys.stderr = io.StringIO()
        port = _find_port()
        if not port:
            msg = (
                "No hay puerto libre en el rango 8100-8115.\n"
                "Cierra otras aplicaciones y vuelve a intentarlo."
            )
            _log(msg)
            _alert(msg)
            return

        import uvicorn  # noqa: PLC0415

        from app.main import app  # noqa: PLC0415

        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
        _log(f"Servidor en http://0.0.0.0:{port} (accesible por IP/LAN)")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        _log("ERROR DE ARRANQUE:\n" + tb)
        detail = tb.splitlines()[-1] if tb.splitlines() else "Error desconocido"
        _alert(f"No se pudo iniciar la aplicacion.\n\nDetalle:\n{detail}\n\n"
               f"Revisa el archivo scm.log (junto a SCM-Platform.exe).")
        raise


if __name__ == "__main__":
    main()