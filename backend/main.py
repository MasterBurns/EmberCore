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
import re  # NEU: Um Servernamen sicher für Ordnerpfade zu machen
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

class ScheduleItem(BaseModel):
    type: str
    value: str
    last_run: Optional[str] = ""
    last_run_date: Optional[str] = ""

class RetentionConfig(BaseModel):
    keep_latest: int = 5
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 3

class BackupScheduleRequest(BaseModel):
    schedules: List[ScheduleItem] = []
    retention: RetentionConfig = RetentionConfig()

disk_cache = {}

def get_plugin_paths(plugin_id: str):
    dev_path = os.path.join(BASE_DIR, "dev_plugins", plugin_id, "manifest.yaml")
    live_path = os.path.join(BASE_DIR, "plugins", plugin_id, "manifest.yaml")
    if os.path.exists(dev_path): return dev_path, os.path.join(BASE_DIR, "dev_plugins", plugin_id), True
    return live_path, os.path.join(BASE_DIR, "plugins", plugin_id), False

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

def load_manifest(plugin_id: str):
    manifest_path, _, _ = get_plugin_paths(plugin_id)
    if not os.path.exists(manifest_path): return None
    with open(manifest_path, "r", encoding="utf-8") as f: return yaml.safe_load(f)

@app.get("/api/plugins/installed")
def get_installed_plugins():
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


# --- NEU: MULTI-INSTANCING MIT NAMENSABFRAGE ---
@app.post("/api/plugins/subscribe/{plugin_id}")
async def subscribe_plugin(plugin_id: str, url: str, server_name: str = "My Server"):
    # Generiere eine sichere ID aus dem Wunschnamen (z.B. conan_exiles_deathworld)
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', server_name).strip('_').lower()
    if not safe_name: safe_name = "server"

    instance_id = f"{plugin_id}_{safe_name}"

    plugins_dir = os.path.join(BASE_DIR, "plugins")
    dev_plugins_dir = os.path.join(BASE_DIR, "dev_plugins")

    # Verhindert serverseitig doppelte Instanzen
    if os.path.exists(os.path.join(plugins_dir, instance_id)) or os.path.exists(os.path.join(dev_plugins_dir, instance_id)):
        return {"status": "error", "message": f"Fehler: Ein Server mit der System-ID '{instance_id}' existiert bereits!"}

    instance_dir = os.path.join(plugins_dir, instance_id)
    os.makedirs(instance_dir, exist_ok=True)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=15.0)
            if response.status_code != 200:
                return {"status": "error", "message": f"GitHub meldet Fehler {response.status_code}."}

            try:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                    zip_ref.extractall(instance_dir)
            except zipfile.BadZipFile:
                return {"status": "error", "message": "Die heruntergeladene Datei ist keine gültige ZIP."}

        # Manifest anpassen und den Config-Seed legen
        manifest_path = os.path.join(instance_dir, "manifest.yaml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)

            # Überschreibe die interne ID, damit EmberCore sie trennen kann
            manifest["id"] = instance_id

            with open(manifest_path, "w", encoding="utf-8") as f:
                yaml.dump(manifest, f, allow_unicode=True)

            # Schreibe den Servernamen direkt in die Game-Engine Konfiguration!
            meta = manifest.get("config_meta")
            if meta:
                fields = meta.get("fields", [])
                hostname_key = next((f["key"] for f in fields if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)

                if hostname_key:
                    config_file_path = os.path.join(BASE_DIR, "servers", instance_id, meta.get("file_path"))
                    # Wir erzeugen die Struktur vorab. Bei Conan generiert die Unreal-Engine
                    # die restlichen Settings dann einfach um unsere Datei herum!
                    os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
                    current_values = config_manager.read_key_value_config(config_file_path, fields)
                    current_values[hostname_key] = server_name
                    config_manager.write_key_value_config(config_file_path, current_values)

        return {"status": "success", "message": f"Server '{server_name}' erfolgreich erstellt.", "instance_id": instance_id}

    except Exception as e:
        if os.path.exists(instance_dir): shutil.rmtree(instance_dir)
        return {"status": "error", "message": f"Systemfehler beim Download: {repr(e)}"}


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
        if os.path.exists(plugin_dir) and not is_dev: shutil.rmtree(plugin_dir)

        return {"status": "success", "message": "Server-Dateien zurückgesetzt. Quellcode geschützt." if is_dev else "Server restlos gelöscht."}
    except Exception as e: return {"status": "error", "message": str(e)}

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

@app.post("/api/server/backup/create/{plugin_id}")
def create_backup(plugin_id: str):
    manifest = load_manifest(plugin_id)
    schedule_file = os.path.join(BASE_DIR, "data", plugin_id, "backup_schedule.json")
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
    schedule_file = os.path.join(BASE_DIR, "data", plugin_id, "backup_schedule.json")
    default_config = {
        "schedules": [],
        "retention": {"keep_latest": 5, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}
    }
    if os.path.exists(schedule_file):
        try:
            with open(schedule_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "time" in data and "schedules" not in data:
                if data["time"] != "disabled":
                    default_config["schedules"].append({"type": "daily", "value": str(data["time"])})
                return default_config
            if "schedules" not in data: data["schedules"] = []
            if "retention" not in data: data["retention"] = default_config["retention"]
            return data
        except:
            return default_config
    return default_config

@app.post("/api/server/backup/schedule/{plugin_id}")
def save_backup_schedule(plugin_id: str, req: dict = Body(...)):
    schedule_file = os.path.join(BASE_DIR, "data", plugin_id, "backup_schedule.json")

    schedules_raw = req.get("schedules", [])
    retention_raw = req.get("retention", {})

    valid_schedules = []
    if isinstance(schedules_raw, list):
        for s in schedules_raw:
            if isinstance(s, dict) and "type" in s and "value" in s:
                valid_schedules.append({
                    "type": str(s["type"]), "value": str(s["value"]),
                    "last_run": str(s.get("last_run", "")), "last_run_date": str(s.get("last_run_date", ""))
                })

    def safe_int(val, fallback):
        try: return int(val) if val not in ["", None] else fallback
        except: return fallback

    valid_retention = {
        "keep_latest": safe_int(retention_raw.get("keep_latest"), 5),
        "keep_daily": safe_int(retention_raw.get("keep_daily"), 7),
        "keep_weekly": safe_int(retention_raw.get("keep_weekly"), 4),
        "keep_monthly": safe_int(retention_raw.get("keep_monthly"), 3),
    }

    os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
    with open(schedule_file, "w", encoding="utf-8") as f:
        json.dump({"schedules": valid_schedules, "retention": valid_retention}, f, indent=2)

    return {"status": "success", "message": "Zeitpläne gespeichert."}

@app.get("/api/plugins/available")
async def get_available_plugins():
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://raw.githubusercontent.com/MasterBurns/EmberCore/main/plugins_directory.json", timeout=5.0)
            return res.json() if res.status_code == 200 else []
    except: return []

app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")

def main():
    port = 8000
    while socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(('127.0.0.1', port)) == 0: port += 10
    print(f"[+] Web-Interface: http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__": main()
