import json
import socket
import os
import uvicorn
import yaml
import platform
import shutil
import subprocess
import asyncio
from datetime import datetime, date
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from core.server_manager import ServerManager
from core.steamcmd_manager import SteamCMDManager
from core.backup_manager import BackupManager
from core.config_manager import ConfigManager
from core.scheduler import BackupScheduler

app = FastAPI(title="EmberCore", version="0.1.0")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

manager = ServerManager()
steam_manager = SteamCMDManager(base_dir=os.path.join(BASE_DIR, "servers"))
backup_manager = BackupManager(base_dir=BASE_DIR)
config_manager = ConfigManager()
scheduler = BackupScheduler(base_dir=BASE_DIR, backup_manager=backup_manager)

# Pydantic Modelle
class InstallRequest(BaseModel): install_dir_name: Optional[str] = None
class ScheduleItem(BaseModel): type: str; value: str; last_run: Optional[str] = ""; last_run_date: Optional[str] = ""
class RetentionConfig(BaseModel): keep_latest: int = 5; keep_daily: int = 7; keep_weekly: int = 4; keep_monthly: int = 3
class BackupScheduleRequest(BaseModel): schedules: List[ScheduleItem]; retention: RetentionConfig

# --- CACHE FÜR FESTPLATTEN STATS ---
# os.walk kann auf 50GB Ordnern langsam sein. Wir berechnen das nur alle 60 Sekunden neu.
disk_cache = {}

def get_dir_size_mb(path):
    total = 0
    if os.path.exists(path):
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
    return round(total / (1024 * 1024), 2)

def calculate_disk_trend(plugin_id: str):
    now = datetime.now()

    # Cache Check (Nur alle 60 Sek. scannen)
    if plugin_id in disk_cache:
        cached_data, last_check = disk_cache[plugin_id]
        if (now - last_check).total_seconds() < 60:
            return cached_data

    server_dir = os.path.join(BASE_DIR, "servers", plugin_id)
    backup_dir = os.path.join(BASE_DIR, "backups", plugin_id)

    server_mb = get_dir_size_mb(server_dir)
    backup_mb = get_dir_size_mb(backup_dir)
    total_mb = server_mb + backup_mb

    # Trend berechnen
    trend_file = os.path.join(BASE_DIR, "plugins", plugin_id, "storage_trend.json")
    trend_data = {}
    if os.path.exists(trend_file):
        with open(trend_file, "r") as f:
            trend_data = json.load(f)

    today_str = str(date.today())
    trend_data[today_str] = total_mb

    # Historie auf 7 Tage begrenzen
    sorted_dates = sorted(trend_data.keys())
    if len(sorted_dates) > 7:
        del trend_data[sorted_dates[0]]

    with open(trend_file, "w") as f:
        json.dump(trend_data, f)

    # Durchschnittliches tägliches Wachstum berechnen
    trend_mb_per_day = 0
    if len(sorted_dates) > 1:
        oldest_mb = trend_data[sorted_dates[0]]
        newest_mb = trend_data[sorted_dates[-1]]
        days_diff = (datetime.strptime(sorted_dates[-1], "%Y-%m-%d") - datetime.strptime(sorted_dates[0], "%Y-%m-%d")).days
        if days_diff > 0:
            trend_mb_per_day = round((newest_mb - oldest_mb) / days_diff, 2)

    total_disk, used_disk, free_disk = shutil.disk_usage(BASE_DIR)

    result = {
        "server_mb": server_mb,
        "backup_mb": backup_mb,
        "total_plugin_mb": total_mb,
        "trend_mb_per_day": trend_mb_per_day,
        "host_free_gb": round(free_disk / (1024**3), 2)
    }

    disk_cache[plugin_id] = (result, now)
    return result

def load_manifest(plugin_id: str):
    manifest_path = os.path.join(BASE_DIR, "plugins", plugin_id, "manifest.yaml")
    if not os.path.exists(manifest_path): raise HTTPException(status_code=404, detail="Plugin nicht gefunden.")
    with open(manifest_path, "r", encoding="utf-8") as f: return yaml.safe_load(f)


@app.get("/api/plugins/installed")
def get_installed_plugins():
    plugins_dir = os.path.join(BASE_DIR, "plugins")
    installed = []
    if os.path.exists(plugins_dir):
        for plugin_id in os.listdir(plugins_dir):
            manifest_path = os.path.join(plugins_dir, plugin_id, "manifest.yaml")
            if os.path.exists(manifest_path):
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

                # NEU: Wir prüfen live, ob dieser Server läuft!
                status = "online" if manager.is_running(plugin_id) else "offline"

                installed.append({
                    "id": plugin_id,
                    "game_name": game_name,
                    "server_name": server_name,
                    "status": status
                })
    return installed

@app.post("/api/server/install/{plugin_id}")
def install_server(plugin_id: str, req: InstallRequest = None):
    manifest = load_manifest(plugin_id)
    return steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)

@app.post("/api/server/start/{plugin_id}")
def start(plugin_id: str):
    manifest = load_manifest(plugin_id)
    exe_suffix = manifest.get("executable_windows")
    executable_path = os.path.join(BASE_DIR, "servers", plugin_id, exe_suffix)
    return manager.start_server(plugin_id, executable_path, manifest.get("default_args", []))

@app.post("/api/server/stop/{plugin_id}")
def stop(plugin_id: str):
    return manager.stop_server(plugin_id)

@app.get("/api/server/stats/{plugin_id}")
def stats(plugin_id: str):
    data = manager.get_stats(plugin_id)
    data["disk"] = calculate_disk_trend(plugin_id)
    return data

@app.delete("/api/server/delete/{plugin_id}")
def delete_server_files(plugin_id: str):
    if manager.is_running(plugin_id): raise HTTPException(status_code=400, detail="Der Server läuft aktuell und kann nicht gelöscht werden!")
    server_dir = os.path.join(BASE_DIR, "servers", plugin_id)
    if os.path.exists(server_dir): shutil.rmtree(server_dir)
    return {"status": "success", "message": "Dateien erfolgreich gelöscht."}

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
def save_server_config(plugin_id: str, data: dict):
    meta = load_manifest(plugin_id).get("config_meta")
    file_path = os.path.join(BASE_DIR, "servers", plugin_id, meta.get("file_path"))
    return config_manager.write_key_value_config(file_path, data)

@app.post("/api/server/backup/create/{plugin_id}")
def create_backup(plugin_id: str):
    manifest = load_manifest(plugin_id)
    schedule_file = os.path.join(BASE_DIR, "plugins", plugin_id, "backup_schedule.json")
    retention = json.load(open(schedule_file, "r")).get("retention") if os.path.exists(schedule_file) else None
    return backup_manager.create_backup(plugin_id, os.path.join(BASE_DIR, "servers", plugin_id), manifest.get("backup").get("source_path"), retention)

@app.get("/api/server/backup/list/{plugin_id}")
def list_backups(plugin_id: str): return backup_manager.list_backups(plugin_id)

@app.post("/api/server/backup/restore/{plugin_id}/{filename}")
def restore_backup(plugin_id: str, filename: str):
    if manager.is_running(plugin_id): return {"status": "error", "message": "Der Server muss gestoppt werden!"}
    manifest = load_manifest(plugin_id)
    return backup_manager.restore_backup(plugin_id, os.path.join(BASE_DIR, "servers", plugin_id), manifest.get("backup").get("source_path"), filename)

@app.delete("/api/server/backup/delete/{plugin_id}/{filename}")
def delete_backup(plugin_id: str, filename: str): return backup_manager.delete_backup(plugin_id, filename)

@app.get("/api/server/backup/schedule/{plugin_id}")
def get_backup_schedule(plugin_id: str):
    schedule_file = os.path.join(BASE_DIR, "plugins", plugin_id, "backup_schedule.json")
    if os.path.exists(schedule_file): return json.load(open(schedule_file, "r", encoding="utf-8"))
    return {"schedules": [], "retention": {"keep_latest": 5, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}}

@app.post("/api/server/backup/schedule/{plugin_id}")
def save_backup_schedule(plugin_id: str, req: BackupScheduleRequest):
    with open(os.path.join(BASE_DIR, "plugins", plugin_id, "backup_schedule.json"), "w", encoding="utf-8") as f:
        json.dump(jsonable_encoder(req), f, indent=2)
    return {"status": "success"}

@app.get("/api/plugins/available")
async def get_available_plugins():
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://raw.githubusercontent.com/MasterBurns/EmberCore/main/plugins_directory.json", timeout=5.0)
            return res.json() if res.status_code == 200 else []
    except: return []

@app.get("/api/server/logs/{plugin_id}")
def get_server_logs(plugin_id: str):
    if plugin_id in manager.logs:
        return {"logs": list(manager.logs[plugin_id])}
    return {"logs": []}

app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")

def main():
    port = 8000
    while socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(('127.0.0.1', port)) == 0: port += 10
    print(f"[+] Web-Interface: http://127.0.0.1:{port}")
    @app.on_event("startup")
    async def startup_event(): asyncio.create_task(scheduler.start_loop())
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__": main()
