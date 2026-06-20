import json
import socket
import os
import uvicorn
import yaml
import platform
import shutil
import subprocess
import asyncio
import io
import zipfile
import httpx
from datetime import datetime, date
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from core.server_manager import ServerManager
from core.steamcmd_manager import SteamCMDManager
from core.backup_manager import BackupManager
from core.config_manager import ConfigManager
from core.scheduler import BackupScheduler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

manager = ServerManager()
steam_manager = SteamCMDManager(base_dir=os.path.join(BASE_DIR, "servers"))
backup_manager = BackupManager(base_dir=BASE_DIR)
config_manager = ConfigManager()
scheduler = BackupScheduler(base_dir=BASE_DIR, backup_manager=backup_manager)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(scheduler.start_loop())
    yield

app = FastAPI(title="EmberCore", version="0.1.0", lifespan=lifespan)

class InstallRequest(BaseModel):
    install_dir_name: Optional[str] = None

disk_cache = {}

# --- NEU: HELFER ZUR PFAD-ERMITTLUNG (Dev vs Live) ---
def get_plugin_paths(plugin_id: str):
    dev_path = os.path.join(BASE_DIR, "dev_plugins", plugin_id, "manifest.yaml")
    live_path = os.path.join(BASE_DIR, "plugins", plugin_id, "manifest.yaml")

    if os.path.exists(dev_path):
        return dev_path, os.path.join(BASE_DIR, "dev_plugins", plugin_id), True
    return live_path, os.path.join(BASE_DIR, "plugins", plugin_id), False

def load_manifest(plugin_id: str):
    manifest_path, _, _ = get_plugin_paths(plugin_id)
    if not os.path.exists(manifest_path): return None
    with open(manifest_path, "r", encoding="utf-8") as f: return yaml.safe_load(f)

def get_dir_size_mb(path):
    total = 0
    if os.path.exists(path):
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp): total += os.path.getsize(fp)
    return round(total / (1024 * 1024), 2)

def calculate_disk_trend(plugin_id: str):
    now = datetime.now()
    if plugin_id in disk_cache:
        cached_data, last_check = disk_cache[plugin_id]
        if (now - last_check).total_seconds() < 60: return cached_data

    server_dir = os.path.join(BASE_DIR, "servers", plugin_id)
    backup_dir = os.path.join(BASE_DIR, "backups", plugin_id)

    server_mb = get_dir_size_mb(server_dir)
    backup_mb = get_dir_size_mb(backup_dir)
    total_mb = server_mb + backup_mb

    # Zustand-JSONs liegen jetzt sicher im data-Ordner
    trend_file = os.path.join(BASE_DIR, "data", plugin_id, "storage_trend.json")
    os.makedirs(os.path.dirname(trend_file), exist_ok=True)

    trend_data = {}
    if os.path.exists(trend_file):
        try:
            with open(trend_file, "r") as f: trend_data = json.load(f)
        except: pass

    today_str = str(date.today())
    trend_data[today_str] = total_mb

    sorted_dates = sorted(trend_data.keys())
    if len(sorted_dates) > 7: del trend_data[sorted_dates[0]]

    with open(trend_file, "w") as f: json.dump(trend_data, f)

    trend_mb_per_day = 0
    if len(sorted_dates) > 1:
        oldest_mb = trend_data[sorted_dates[0]]
        newest_mb = trend_data[sorted_dates[-1]]
        days_diff = (datetime.strptime(sorted_dates[-1], "%Y-%m-%d") - datetime.strptime(sorted_dates[0], "%Y-%m-%d")).days
        if days_diff > 0: trend_mb_per_day = round((newest_mb - oldest_mb) / days_diff, 2)

    total_disk, used_disk, free_disk = shutil.disk_usage(BASE_DIR)
    result = {
        "server_mb": server_mb, "backup_mb": backup_mb, "total_plugin_mb": total_mb,
        "trend_mb_per_day": trend_mb_per_day, "host_free_gb": round(free_disk / (1024**3), 2)
    }
    disk_cache[plugin_id] = (result, now)
    return result

@app.get("/api/plugins/installed")
def get_installed_plugins():
    # Scanne dev_plugins (Priorität) und danach plugins
    dirs_to_scan = [("dev_plugins", True), ("plugins", False)]
    installed = []
    seen_ids = set()

    for folder_name, is_dev in dirs_to_scan:
        target_dir = os.path.join(BASE_DIR, folder_name)
        if not os.path.exists(target_dir): continue

        for plugin_id in os.listdir(target_dir):
            if plugin_id in seen_ids: continue
            manifest_path = os.path.join(target_dir, plugin_id, "manifest.yaml")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)

                    game_name = data.get("name", plugin_id)
                    server_name = plugin_id

                    meta = data.get("config_meta")
                    if meta:
                        file_path = os.path.join(BASE_DIR, "servers", plugin_id, meta.get("file_path"))
                        fields = meta.get("fields", [])
                        hostname_key = next((f["key"] for f in fields if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)
                        if hostname_key:
                            values = config_manager.read_key_value_config(file_path, fields)
                            if values.get(hostname_key): server_name = values.get(hostname_key)

                    status = "online" if manager.is_running(plugin_id) else "offline"

                    # Markiere Entwicklungs-Plugins im UI-Payload, falls nötig
                    display_name = f"{server_name} [DEV]" if is_dev else server_name

                    installed.append({
                        "id": plugin_id,
                        "game_name": game_name,
                        "server_name": display_name,
                        "status": status
                    })
                    seen_ids.add(plugin_id)
                except: pass
    return installed

@app.get("/api/plugins/available")
async def get_available_plugins():
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://raw.githubusercontent.com/MasterBurns/EmberCore/main/plugins_directory.json", timeout=5.0)
            return res.json() if res.status_code == 200 else []
    except: return []

@app.post("/api/plugins/subscribe/{plugin_id}")
async def subscribe_plugin(plugin_id: str, url: str):
    # Live-Downloads landen immer im flüchtigen plugins/ Ordner
    plugins_dir = os.path.join(BASE_DIR, "plugins")
    os.makedirs(plugins_dir, exist_ok=True)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=15.0)
            if response.status_code != 200: return {"status": "error", "message": "Fehler beim GitHub Download."}
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                zip_ref.extractall(os.path.join(plugins_dir, plugin_id))
        return {"status": "success", "message": f"Server-Engine '{plugin_id}' hinzugefügt."}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.post("/api/server/start/{plugin_id}")
def start(plugin_id: str):
    manifest = load_manifest(plugin_id)
    executable_path = os.path.join(BASE_DIR, "servers", plugin_id, manifest.get("executable_windows"))
    return manager.start_server(plugin_id, executable_path, manifest.get("default_args", []))

@app.post("/api/server/stop/{plugin_id}")
def stop(plugin_id: str): return manager.stop_server(plugin_id)

@app.get("/api/server/stats/{plugin_id}")
def stats(plugin_id: str):
    data = manager.get_stats(plugin_id)
    data["disk"] = calculate_disk_trend(plugin_id)
    return data

@app.get("/api/server/logs/{plugin_id}")
def get_server_logs(plugin_id: str):
    if hasattr(manager, 'logs') and plugin_id in manager.logs: return {"logs": list(manager.logs[plugin_id])}
    return {"logs": []}

# --- SCHUTZ-LOGIK BEIM LÖSCHEN ---
@app.delete("/api/server/delete/{plugin_id}")
def delete_server_files(plugin_id: str):
    if manager.is_running(plugin_id): raise HTTPException(status_code=400, detail="Server läuft!")

    server_dir = os.path.join(BASE_DIR, "servers", plugin_id)
    backup_dir = os.path.join(BASE_DIR, "backups", plugin_id)
    data_dir = os.path.join(BASE_DIR, "data", plugin_id)

    _, plugin_dir, is_dev = get_plugin_paths(plugin_id)

    try:
        if os.path.exists(server_dir): shutil.rmtree(server_dir)
        if os.path.exists(backup_dir): shutil.rmtree(backup_dir)
        if os.path.exists(data_dir): shutil.rmtree(data_dir)

        # WICHTIG: Lösche den Manifest-Ordner NUR, wenn es kein Dev-Plugin ist!
        if os.path.exists(plugin_dir) and not is_dev:
            shutil.rmtree(plugin_dir)

        return {"status": "success", "message": "Server-Dateien zurückgesetzt. Quellcode im Git wurde geschützt." if is_dev else "Server restlos gelöscht."}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.post("/api/server/install/{plugin_id}")
def install_server(plugin_id: str, req: InstallRequest = None):
    manifest = load_manifest(plugin_id)
    return steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)

@app.post("/api/server/open-folder/{plugin_id}")
def open_server_folder(plugin_id: str):
    server_dir = os.path.abspath(os.path.join(BASE_DIR, "servers", plugin_id))
    os.makedirs(server_dir, exist_ok=True)
    if platform.system() == "Windows": os.startfile(server_dir)
    elif platform.system() == "Linux": subprocess.Popen(["xdg-open", server_dir])
    return {"status": "success"}

@app.get("/api/server/config/{plugin_id}")
def get_server_config(plugin_id: str):
    meta = load_manifest(plugin_id).get("config_meta")
    if not meta: return {"enabled": False}
    file_path = os.path.join(BASE_DIR, "servers", plugin_id, meta.get("file_path"))
    return {"enabled": True, "fields": meta.get("fields", []), "values": config_manager.read_key_value_config(file_path, meta.get("fields", []))}

@app.post("/api/server/config/{plugin_id}")
def save_server_config(plugin_id: str, data: dict = Body(...)):
    meta = load_manifest(plugin_id).get("config_meta")
    file_path = os.path.join(BASE_DIR, "servers", plugin_id, meta.get("file_path"))
    return config_manager.write_key_value_config(file_path, data)

@app.get("/api/server/backup/schedule/{plugin_id}")
def get_backup_schedule(plugin_id: str):
    schedule_file = os.path.join(BASE_DIR, "data", plugin_id, "backup_schedule.json")
    if os.path.exists(schedule_file):
        with open(schedule_file, "r", encoding="utf-8") as f: return json.load(f)
    return {"schedules": [], "retention": {"keep_latest": 5, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}}

@app.post("/api/server/backup/schedule/{plugin_id}")
def save_backup_schedule(plugin_id: str, req: dict = Body(...)):
    schedule_file = os.path.join(BASE_DIR, "data", plugin_id, "backup_schedule.json")
    os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
    with open(schedule_file, "w", encoding="utf-8") as f: json.dump(req, f, indent=2)
    return {"status": "success"}

app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")

def main():
    port = 8000
    while socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(('127.0.0.1', port)) == 0: port += 10
    print(f"[+] Web-Interface: http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__": main()
