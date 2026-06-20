import json
import socket
import os
import sys
import uvicorn
import yaml
import platform
import shutil
import subprocess
import asyncio
import io
import zipfile
import httpx
import re
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
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

manager = ServerManager()
steam_manager = SteamCMDManager(base_dir=os.path.join(BASE_DIR, "servers"))
backup_manager = BackupManager(base_dir=BASE_DIR)
config_manager = ConfigManager()
scheduler = BackupScheduler(base_dir=BASE_DIR, backup_manager=backup_manager)

# --- NEU: STEAMCMD UPDATE-CHECKER LOGIK ---
game_update_cache = {}

async def fetch_game_update_status(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest or manifest.get("engine") != "steamcmd": return None

    app_id = manifest.get("steam_app_id")
    if not app_id: return None

    local_id = "0"
    acf_path = os.path.join(BASE_DIR, "servers", plugin_id, "steamapps", f"appmanifest_{app_id}.acf")
    if os.path.exists(acf_path):
        with open(acf_path, "r", encoding="utf-8") as f:
            match = re.search(r'"buildid"\s+"(\d+)"', f.read(), re.IGNORECASE)
            if match: local_id = match.group(1)

    if local_id != "0":
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"https://api.steamcmd.net/v1/info/{app_id}", timeout=10.0)
                if res.status_code == 200:
                    data = res.json()
                    remote_id = data.get("data", {}).get(str(app_id), {}).get("depots", {}).get("branches", {}).get("public", {}).get("buildid")
                    if remote_id:
                        status = {
                            "available": str(local_id) != str(remote_id),
                            "local": str(local_id),
                            "remote": str(remote_id)
                        }
                        game_update_cache[plugin_id] = status
                        return status
        except Exception as e:
            pass
    return None

async def game_update_checker_loop():
    await asyncio.sleep(10)
    print("[*] SteamCMD Update-Radar gestartet (Prüfung stündlich).")
    while True:
        try:
            installed = get_installed_plugins()
            for plugin in installed:
                await fetch_game_update_status(plugin["id"])
        except Exception as e:
            pass
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(scheduler.start_loop())
    asyncio.create_task(game_update_checker_loop())
    yield

app = FastAPI(title="EmberCore", version="0.2.0", lifespan=lifespan)

class InstallRequest(BaseModel):
    install_dir_name: Optional[str] = None

disk_cache = {}

def get_plugin_paths(plugin_id: str):
    dev_path = os.path.join(BASE_DIR, "dev_plugins", plugin_id, "manifest.yaml")
    live_path = os.path.join(BASE_DIR, "plugins", plugin_id, "manifest.yaml")
    if os.path.exists(dev_path): return dev_path, os.path.join(BASE_DIR, "dev_plugins", plugin_id), True
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
    return {
        "server_mb": server_mb, "backup_mb": backup_mb, "total_plugin_mb": total_mb,
        "trend_mb_per_day": trend_mb_per_day, "host_free_gb": round(free_disk / (1024**3), 2)
    }

@app.get("/api/system/version")
def get_system_version():
    version_file = os.path.join(ROOT_DIR, "version.json")
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="utf-8") as f: return json.load(f)
    return {"version": "v0.1.0", "build_date": "Unknown", "changelog": ["Keine Version-Datei gefunden."]}

@app.get("/api/system/check-update")
def check_system_update():
    try:
        subprocess.run(["git", "fetch"], cwd=ROOT_DIR, check=True)
        status = subprocess.run(["git", "status", "-uno"], cwd=ROOT_DIR, capture_output=True, text=True)
        is_behind = "Your branch is behind" in status.stdout
        return {"update_available": is_behind}
    except Exception as e:
        return {"update_available": False, "error": str(e)}

@app.post("/api/system/update")
async def update_embercore():
    try:
        subprocess.run(["git", "fetch"], cwd=ROOT_DIR, check=True)
        pull_result = subprocess.run(["git", "pull"], cwd=ROOT_DIR, capture_output=True, text=True)

        if "Already up to date." in pull_result.stdout:
            return {"status": "info", "message": "EmberCore ist bereits auf dem neuesten Stand!"}

        async def restart_server():
            await asyncio.sleep(1.5)
            print("[*] EmberCore führt Auto-Update Neustart durch...")
            os.execv(sys.executable, [sys.executable] + sys.argv)

        asyncio.create_task(restart_server())
        return {"status": "success", "message": "Update erfolgreich heruntergeladen. EmberCore startet neu..."}
    except Exception as e:
        return {"status": "error", "message": f"Git Update fehlgeschlagen: {e}"}

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
                    with open(manifest_path, "r", encoding="utf-8") as f: data = yaml.safe_load(f)
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
                    installed.append({"id": plugin_id, "game_name": game_name, "server_name": display_name, "status": status})
                    seen_ids.add(plugin_id)
                except: pass
    return installed

@app.post("/api/plugins/subscribe/{plugin_id}")
async def subscribe_plugin(plugin_id: str, url: str, server_name: str = "My Server"):
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', server_name).strip('_').lower()
    if not safe_name: safe_name = "server"
    instance_id = f"{plugin_id}_{safe_name}"
    plugins_dir = os.path.join(BASE_DIR, "plugins")
    if os.path.exists(os.path.join(plugins_dir, instance_id)): return {"status": "error", "message": "Server-ID existiert bereits!"}
    instance_dir = os.path.join(plugins_dir, instance_id)
    os.makedirs(instance_dir, exist_ok=True)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=15.0)
            if response.status_code != 200: return {"status": "error", "message": "Download fehlgeschlagen."}
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref: zip_ref.extractall(instance_dir)
        manifest_path = os.path.join(instance_dir, "manifest.yaml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f: manifest = yaml.safe_load(f)
            manifest["id"] = instance_id
            with open(manifest_path, "w", encoding="utf-8") as f: yaml.dump(manifest, f, allow_unicode=True)
            meta = manifest.get("config_meta")
            if meta:
                fields = meta.get("fields", [])
                hostname_key = next((f["key"] for f in fields if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)
                if hostname_key:
                    config_file_path = os.path.join(BASE_DIR, "servers", instance_id, meta.get("file_path"))
                    os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
                    current_values = config_manager.read_key_value_config(config_file_path, fields)
                    current_values[hostname_key] = server_name
                    config_manager.write_key_value_config(config_file_path, current_values)
        return {"status": "success", "message": f"Server '{server_name}' erstellt.", "instance_id": instance_id}
    except Exception as e:
        if os.path.exists(instance_dir): shutil.rmtree(instance_dir)
        return {"status": "error", "message": str(e)}

@app.post("/api/server/install/{plugin_id}")
def install_server(plugin_id: str, req: InstallRequest = None):
    manifest = load_manifest(plugin_id)
    res = steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
    if plugin_id in game_update_cache:
        game_update_cache[plugin_id]["available"] = False
        game_update_cache[plugin_id]["local"] = game_update_cache[plugin_id].get("remote", "0")
    return res

@app.post("/api/server/check-updates/{plugin_id}")
async def force_check_game_updates(plugin_id: str):
    status = await fetch_game_update_status(plugin_id)
    if status:
        if status["available"]:
            return {"status": "success", "message": f"Steam Update verfügbar! (Lokal: {status['local']} -> Remote: {status['remote']})"}
        else:
            return {"status": "info", "message": f"Der Server ist bereits auf dem neuesten Stand. (Build: {status['local']})"}
    return {"status": "error", "message": "Konnte Versionsdaten nicht prüfen. Server evtl. noch nicht installiert?"}

@app.post("/api/server/start/{plugin_id}")
def start(plugin_id: str):
    manifest = load_manifest(plugin_id)
    meta = manifest.get("config_meta")

    if meta:
        file_path = os.path.join(BASE_DIR, "servers", plugin_id, meta.get("file_path"))
        values = config_manager.read_key_value_config(file_path, meta.get("fields", []))
        auto_update = values.get("AutoUpdateOnStart")
        if auto_update is True or str(auto_update).lower() == "true" or auto_update == 1:
            print(f"[*] Auto-Update aktiv! Prüfe SteamCMD für {plugin_id}...")
            steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
            if plugin_id in game_update_cache: game_update_cache[plugin_id]["available"] = False

    exe_suffix = manifest.get("executable_windows")
    executable_path = os.path.join(BASE_DIR, "servers", plugin_id, exe_suffix)
    return manager.start_server(plugin_id, executable_path, manifest.get("default_args", []))

@app.post("/api/server/stop/{plugin_id}")
def stop(plugin_id: str): return manager.stop_server(plugin_id)

@app.get("/api/server/stats/{plugin_id}")
def stats(plugin_id: str):
    data = manager.get_stats(plugin_id)
    data["disk"] = calculate_disk_trend(plugin_id)
    data["update_info"] = game_update_cache.get(plugin_id, {"available": False})
    return data

@app.get("/api/server/logs/{plugin_id}")
def get_server_logs(plugin_id: str):
    if plugin_id in manager.logs: return {"logs": list(manager.logs[plugin_id])}
    return {"logs": []}

@app.get("/api/server/diagnostics/{plugin_id}")
def get_diagnostics(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest or "diagnostics" not in manifest: return []
    server_logs = list(manager.logs.get(plugin_id, []))
    active_diagnostics = []
    for rule in manifest["diagnostics"]:
        for line in server_logs:
            if re.search(rule["pattern"], line, re.IGNORECASE):
                active_diagnostics.append(rule)
                break
    return active_diagnostics

@app.post("/api/server/diagnostics/fix/{plugin_id}/{fix_type}")
def apply_fix(plugin_id: str, fix_type: str):
    if manager.is_running(plugin_id): manager.stop_server(plugin_id)
    manifest = load_manifest(plugin_id)
    if fix_type == "update_server":
        steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
        return {"status": "success", "message": "Server repariert."}
    elif fix_type == "restore_backup":
        backups = backup_manager.list_backups(plugin_id)
        if not backups: return {"status": "error", "message": "Kein Backup gefunden!"}
        backup_manager.restore_backup(plugin_id, os.path.join(BASE_DIR, "servers", plugin_id), manifest.get("backup").get("source_path"), backups[0]["filename"])
        return {"status": "success", "message": "Rollback durchgeführt."}
    return {"status": "info", "message": "Manuelle Aktion nötig."}

@app.get("/api/server/mods/{plugin_id}")
def get_server_mods(plugin_id: str):
    mods_file = os.path.join(BASE_DIR, "data", plugin_id, "mods_db.json")
    if os.path.exists(mods_file):
        with open(mods_file, "r", encoding="utf-8") as f: return json.load(f)
    return []

@app.post("/api/server/mods/add/{plugin_id}/{mod_id}")
async def add_server_mod(plugin_id: str, mod_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest or "mods_meta" not in manifest: raise HTTPException(status_code=400, detail="Kein Modding unterstützt.")
    steam_url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    payload = {"itemcount": 1, "publishedfileids[0]": mod_id}
    mod_name, mod_version = f"Workshop Mod ({mod_id})", "unbekannt"
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(steam_url, data=payload, timeout=10.0)
            if res.status_code == 200:
                details = res.json().get("response", {}).get("publishedfiledetails", [{}])[0]
                if "title" in details:
                    mod_name = details["title"]
                    updated_ts = details.get("time_updated", 0)
                    mod_version = datetime.fromtimestamp(updated_ts).strftime("%d.%m.%Y") if updated_ts else "1.0.0"
    except: pass
    mods_file = os.path.join(BASE_DIR, "data", plugin_id, "mods_db.json")
    os.makedirs(os.path.dirname(mods_file), exist_ok=True)
    current_mods = []
    if os.path.exists(mods_file):
        with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
    if any(m["id"] == mod_id for m in current_mods): return {"status": "error", "message": "Mod existiert bereits!"}
    current_mods.append({"id": mod_id, "name": mod_name, "version": mod_version})
    with open(mods_file, "w", encoding="utf-8") as f: json.dump(current_mods, f, indent=2)
    meta = manifest["mods_meta"]
    real_modlist_path = os.path.join(BASE_DIR, "servers", plugin_id, meta["file_path"])
    os.makedirs(os.path.dirname(real_modlist_path), exist_ok=True)
    mod_line = f"*{BASE_DIR}/servers/{plugin_id}/steamapps/workshop/content/{meta['steam_workshop_appid']}/{mod_id}/{mod_id}.pak\n"
    with open(real_modlist_path, "a", encoding="utf-8") as f: f.write(mod_line)
    return {"status": "success", "message": f"Mod '{mod_name}' hinzugefügt."}

@app.delete("/api/server/mods/delete/{plugin_id}/{mod_id}")
def delete_server_mod(plugin_id: str, mod_id: str):
    manifest = load_manifest(plugin_id)
    mods_file = os.path.join(BASE_DIR, "data", plugin_id, "mods_db.json")
    if not os.path.exists(mods_file): return {"status": "success"}
    with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
    current_mods = [m for m in current_mods if m["id"] != mod_id]
    with open(mods_file, "w", encoding="utf-8") as f: json.dump(current_mods, f, indent=2)
    meta = manifest["mods_meta"]
    real_modlist_path = os.path.join(BASE_DIR, "servers", plugin_id, meta["file_path"])
    if os.path.exists(real_modlist_path):
        with open(real_modlist_path, "r", encoding="utf-8") as f: lines = f.readlines()
        lines = [line for line in lines if f"/{mod_id}/" not in line]
        with open(real_modlist_path, "w", encoding="utf-8") as f: f.writelines(lines)
    return {"status": "success", "message": "Mod entfernt."}

@app.delete("/api/server/delete/{plugin_id}")
def delete_server_files(plugin_id: str):
    if manager.is_running(plugin_id): raise HTTPException(status_code=400, detail="Server läuft!")
    if os.path.exists(os.path.join(BASE_DIR, "servers", plugin_id)): shutil.rmtree(os.path.join(BASE_DIR, "servers", plugin_id))
    if os.path.exists(os.path.join(BASE_DIR, "backups", plugin_id)): shutil.rmtree(os.path.join(BASE_DIR, "backups", plugin_id))
    if os.path.exists(os.path.join(BASE_DIR, "data", plugin_id)): shutil.rmtree(os.path.join(BASE_DIR, "data", plugin_id))
    _, plugin_dir, is_dev = get_plugin_paths(plugin_id)
    if os.path.exists(plugin_dir) and not is_dev: shutil.rmtree(plugin_dir)
    return {"status": "success", "message": "Dateien entfernt."}

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
    manifest = load_manifest(plugin_id)
    fields = manifest.get("config_meta", {}).get("fields", [])
    for field in fields:
        key = field["key"]
        if field.get("type") == "boolean" and key in data:
            if field.get("boolean_mode") == "numeric":
                data[key] = 1 if data[key] is True or data[key] == 1 else 0
            else:
                data[key] = "True" if data[key] is True or str(data[key]).lower() == "true" else "False"
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

@app.get("/api/plugins/available")
async def get_available_plugins():
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
