import json
import socket
import os
import uvicorn
import yaml
import platform
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from core.update_manager import UpdateManager
from core.server_manager import ServerManager
from core.steamcmd_manager import SteamCMDManager

app = FastAPI(title="EmberCore", version="0.1.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

manager = ServerManager()
steam_manager = SteamCMDManager(base_dir=os.path.join(BASE_DIR, "servers"))
update_manager = UpdateManager(base_dir=BASE_DIR)

class InstallRequest(BaseModel):
    install_dir_name: str = None

def load_manifest(plugin_id: str):
    manifest_path = os.path.join(BASE_DIR, "plugins", plugin_id, "manifest.yaml")
    if not os.path.exists(manifest_path):
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} nicht gefunden.")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# --- API ROUTEN ---
@app.get("/api/status")
def get_status():
    return {"status": "online", "message": "EmberCore läuft einwandfrei!"}

@app.post("/api/server/install/{plugin_id}")
def install_server(plugin_id: str, req: InstallRequest = None):
    manifest = load_manifest(plugin_id)
    if manifest.get("engine") != "steamcmd":
        return {"status": "error", "message": "Dieses Plugin nutzt kein SteamCMD."}

    app_id = manifest.get("steam_app_id")
    if not req or not req.install_dir_name or req.install_dir_name == "string":
        target_dir = plugin_id
    else:
        target_dir = req.install_dir_name

    force_windows = False
    if platform.system() == "Linux" and "executable_windows" in manifest:
        force_windows = True

    return steam_manager.install_or_update_app(app_id, target_dir, force_windows=force_windows)

@app.post("/api/server/start/{plugin_id}")
def start(plugin_id: str):
    manifest = load_manifest(plugin_id)
    server_dir = os.path.join(BASE_DIR, "servers", plugin_id)
    exe_suffix = manifest.get("executable_windows")
    executable_path = os.path.join(server_dir, exe_suffix)
    args = manifest.get("default_args", [])

    return manager.start_server(executable_path, args)

@app.post("/api/server/stop")
def stop():
    return manager.stop_server()

@app.get("/api/server/stats")
def stats():
    return manager.get_stats()

@app.post("/api/plugins/subscribe/{plugin_id}")
async def subscribe_plugin(plugin_id: str, url: str):
    # Beispiel-URL zum Testen könnte ein ZIP auf deinem GitHub-Repo sein
    return await update_manager.install_or_update_plugin_from_zip(plugin_id, url)

@app.get("/api/plugins/available")
async def get_available_plugins():
    """
    Fragt das zentrale Plugin-Verzeichnis LIVE von MasterBurns' GitHub ab.
    """
    # Die offizielle "Raw"-URL deiner Datei auf GitHub
    github_url = "https://raw.githubusercontent.com/MasterBurns/EmberCore/main/plugins_directory.json"

    try:
        async with httpx.AsyncClient() as client:
            # Wir holen uns die JSON-Datei direkt von GitHub
            response = await client.get(github_url, follow_redirects=True, timeout=5.0)

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"GitHub gab einen Fehlercode zurück: {response.status_code}"
                )
    except httpx.RequestError as e:
        # Falls das System offline ist oder GitHub streikt, fangen wir das sauber ab
        raise HTTPException(
            status_code=503,
            detail=f"Plugin-Verzeichnis konnte nicht geladen werden: {str(e)}"
        )

# --- NEU: Statischen Ordner als Weboberfläche bereitstellen ---
# WICHTIG: Das MUSS ganz unten nach den API-Routen stehen, damit /api/Routen Vorrang haben!
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def load_config():
    config_path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(config_path):
        return {"host": "0.0.0.0", "start_port": 8000}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    config = load_config()
    host = config.get("host", "0.0.0.0")
    port = config.get("start_port", 8000)

    max_attempts = 10
    attempts = 0

    print(f"[*] Starte EmberCore Boot-Sequenz...")
    while is_port_in_use(port) and attempts < max_attempts:
        port += 10
        attempts += 1

    if is_port_in_use(port):
        print("[-] Kritischer Fehler: Keine freien Ports gefunden.")
        return

    print(f"[+] Web-Interface wird gestartet auf: http://127.0.0.1:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
