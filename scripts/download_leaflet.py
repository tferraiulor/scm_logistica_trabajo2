import urllib.request
from pathlib import Path

def download_leaflet():
    lib_dir = Path(__file__).resolve().parent.parent / "static" / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    
    js_url = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    css_url = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    
    js_dest = lib_dir / "leaflet.js"
    css_dest = lib_dir / "leaflet.css"
    
    print("Descargando leaflet.js...")
    urllib.request.urlretrieve(js_url, js_dest)
    print("Descargando leaflet.css...")
    urllib.request.urlretrieve(css_url, css_dest)
    
    print(f"Descargado con exito: leaflet.js ({js_dest.stat().st_size} bytes), leaflet.css ({css_dest.stat().st_size} bytes)")

if __name__ == "__main__":
    download_leaflet()
