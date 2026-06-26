import os, sys, platform, subprocess, psutil, time, json, shutil, re, socket, httpx, zipfile, io, yaml
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
import urllib.request
import logging

from core.env import (
    EXE_DIR, BASE_DIR, SERVERS_ROOT, DATA_ROOT, PLUGINS_ROOT, DEV_PLUGINS_ROOT,
    BACKUPS_ROOT, START_TIME, sys_config, logger, game_update_cache, disk_cache,
    get_current_system_version, steam_manager, backup_manager
)
from core.server_manager import server_manager
from core.config_manager import ConfigManager

router = APIRouter(prefix="/api")

class InstallRequest(BaseModel): install_dir_name: str = None

# ==========================================
# HILFSFUNKTIONEN (Helper)
# ==========================================
def calculate_disk_trend(plugin_id: str):
    now = datetime.now()
    if plugin_id in disk_cache:
        cached_data, last_check = disk_cache[plugin_id]
        if (now - last_check).total_seconds() < 60: return cached_data

    def get_dir_size_mb(path):
        total = 0
        if os.path.exists(path):
            for dirpath, _, fnames in os.walk(path):
                for f in fnames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp): total += os.path.getsize(fp)
        return round(total / (1024 * 1024), 2)

    server_dir = os.path.join(SERVERS_ROOT, plugin_id)
    backup_dir = os.path.join(BACKUPS_ROOT, plugin_id)
    total_mb = get_dir_size_mb(server_dir) + get_dir_size_mb(backup_dir)

    trend_file = os.path.join(DATA_ROOT, plugin_id, "storage_trend.json")
    os.makedirs(os.path.dirname(trend_file), exist_ok=True)
    trend_data = {}
    if os.path.exists(trend_file):
        try:
            with open(trend_file, "r") as f: trend_data = json.load(f)
        except: pass

    trend_data[str(date.today())] = total_mb
    sorted_dates = sorted(trend_data.keys())
    if len(sorted_dates) > 7: del trend_data[sorted_dates[0]]
    with open(trend_file, "w") as f: json.dump(trend_data, f)

    trend_mb_per_day = 0
    if len(sorted_dates) > 1:
        old, new = trend_data[sorted_dates[0]], trend_data[sorted_dates[-1]]
        days = (datetime.strptime(sorted_dates[-1], "%Y-%m-%d") - datetime.strptime(sorted_dates[0], "%Y-%m-%d")).days
        if days > 0: trend_mb_per_day = round((new - old) / days, 2)

    _, _, free_disk = shutil.disk_usage(EXE_DIR)
    res = {"server_mb": get_dir_size_mb(server_dir), "backup_mb": get_dir_size_mb(backup_dir), "total_plugin_mb": total_mb, "trend_mb_per_day": trend_mb_per_day, "host_free_gb": round(free_disk / (1024**3), 2)}
    disk_cache[plugin_id] = (res, now)
    return res

def rebuild_modlist(plugin_id: str, manifest: dict):
    mods_meta = manifest.get("mods_meta", {})
    if not mods_meta or "steam_workshop_appid" not in mods_meta: return

    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
    if not os.path.exists(mods_file): return

    with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)

    real_modlist_path = os.path.join(SERVERS_ROOT, plugin_id, mods_meta["file_path"])
    os.makedirs(os.path.dirname(real_modlist_path), exist_ok=True)
    workshop_dir = os.path.abspath(os.path.join(SERVERS_ROOT, plugin_id, "steamapps", "workshop", "content", str(mods_meta["steam_workshop_appid"])))

    valid_mod_lines = []

    for mod in current_mods:
        mod_id = mod["id"]
        mod_folder = os.path.join(workshop_dir, str(mod_id))
        pak_path = None
        
        # Durchsuche den Ordner nach der echten .pak Datei (Ignoriere den Dateinamen)
        if os.path.exists(mod_folder):
            for root, _, files in os.walk(mod_folder):
                for file in files:
                    if file.lower().endswith(".pak"):
                        pak_path = os.path.abspath(os.path.join(root, file)).replace("\\", "/")
                        break
                if pak_path: break
                
        if pak_path:
            valid_mod_lines.append(f"*{pak_path}\n")
        else:
            fallback_path = f"{SERVERS_ROOT}/{plugin_id}/steamapps/workshop/content/{mods_meta['steam_workshop_appid']}/{mod_id}/{mod_id}.pak".replace("\\", "/")
            valid_mod_lines.append(f"*{fallback_path}\n")

    with open(real_modlist_path, "w", encoding="utf-8") as f:
        f.writelines(valid_mod_lines)


# ==========================================
# SYSTEM & SERVICE ROUTEN
# ==========================================
@router.get("/system/health")
def system_health():
    return {"status": "ok"}

@router.get("/system/settings")
def get_sys_settings():
    return sys_config

@router.post("/system/settings")
def save_sys_settings_api(data: dict = Body(...)):
    sys_config.update(data)
    SYS_CONFIG_PATH = os.path.join(DATA_ROOT, "system_config.json")
    with open(SYS_CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(sys_config, f, indent=2)
    is_verbose = sys_config.get("verbose_logging")
    logger.setLevel(logging.DEBUG if is_verbose else logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO if is_verbose else logging.WARNING)
    return {"status": "success"}

@router.get("/system/logs")
def get_sys_logs():
    log_file = os.path.join(EXE_DIR, "logs", "embercore.log")
    try:
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                return {"logs": "".join(f.readlines()[-1000:])}
    except Exception as e:
        return {"logs": f"Lese-Fehler: {e}"}
    return {"logs": "Bisher keine Logs vorhanden."}

@router.post("/system/logs/clear")
def clear_sys_logs():
    log_file = os.path.join(EXE_DIR, "logs", "embercore.log")
    try:
        with open(log_file, "w", encoding="utf-8") as f: f.write("")
        return {"status": "success"}
    except Exception: return {"status": "error"}

@router.get("/system/service/status")
def system_service_status_api():
    is_linux = platform.system() == "Linux"
    installed, running = False, False

    if is_linux:
        installed = os.path.exists("/etc/systemd/system/embercore.service")
        if installed:
            try:
                res = subprocess.run(["systemctl", "is-active", "embercore"], capture_output=True, text=True)
                running = "active" in res.stdout
            except: pass
    else:
        try:
            flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            res = subprocess.run(["sc", "query", "EmberCore"], capture_output=True, text=True, creationflags=flags)
            if res.returncode == 0:
                installed = True
                running = "RUNNING" in res.stdout
        except: pass

    wd_active = False
    try: wd_active = any("--watchdog" in p.info.get('cmdline', []) for p in psutil.process_iter(['cmdline']) if p.info.get('cmdline'))
    except: pass
    
    try:
        proc = psutil.Process(os.getpid())
        ember_ram = round(proc.memory_info().rss / (1024*1024), 2)
        proc.cpu_percent(interval=None); time.sleep(0.05)
        ember_cpu = round(proc.cpu_percent(interval=None) / psutil.cpu_count(), 1)
    except: ember_ram, ember_cpu = 0.0, 0.0

    return { "os": platform.system(), "is_installed": installed, "is_running": running, "main_pid": os.getpid(), "watchdog_active": wd_active, "uptime_seconds": (datetime.now() - START_TIME).total_seconds(), "ram_mb": ember_ram, "cpu_percent": ember_cpu }

@router.post("/system/service/install")
def install_system_service_api():
    from core.update_manager import update_manager
    return update_manager.install_system_service()

@router.post("/system/service/uninstall")
def uninstall_system_service_api():
    from core.update_manager import update_manager
    return update_manager.uninstall_system_service()

@router.post("/system/service/start")
def start_system_service_api():
    from core.update_manager import update_manager
    return update_manager.start_system_service()

@router.post("/system/service/stop")
def stop_system_service_api():
    from core.update_manager import update_manager
    return update_manager.stop_system_service()

@router.get("/system/version")
def get_system_version_api(): return get_current_system_version()

@router.get("/system/check-update")
async def check_system_update_api():
    from core.update_manager import update_manager
    if hasattr(update_manager, 'check_system_update'):
        return await update_manager.check_system_update(get_current_system_version()["version"])
    else: return {"update_available": False}

@router.post("/system/update")
async def update_embercore_api():
    from core.update_manager import update_manager
    if hasattr(update_manager, 'process_update'):
        return await update_manager.process_update()
    else: return {"status": "error", "message": "Update Manager nicht vollständig."}


# ==========================================
# PLUGINS & MARKETPLACE ROUTEN
# ==========================================
@router.get("/plugins/installed")
def get_installed_plugins():
    dirs_to_scan = [(DEV_PLUGINS_ROOT, True), (PLUGINS_ROOT, False)]
    installed = []
    seen_ids = set()
    for target_dir, is_dev in dirs_to_scan:
        if not os.path.exists(target_dir): continue
        for plugin_id in os.listdir(target_dir):
            if plugin_id in seen_ids: continue
            manifest_path = os.path.join(target_dir, plugin_id, "manifest.yaml")
            if os.path.exists(manifest_path):
                try:
                    data = ConfigManager.load_manifest(plugin_id)
                    if not data: continue
                    game_name = data.get("name", plugin_id)
                    server_name = plugin_id
                    meta = data.get("config_meta")
                    if meta:
                        desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
                        live_values = {}
                        if os.path.exists(desired_path):
                            with open(desired_path, "r", encoding="utf-8") as df: live_values = json.load(df)
                        else:
                            live_values = ConfigManager.parse_live_config(os.path.join(SERVERS_ROOT, plugin_id, meta.get("file_path")))

                        hostname_key = next((f["key"] for f in meta.get("fields", []) if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)
                        if hostname_key and live_values.get(hostname_key):
                            server_name = live_values.get(hostname_key)
                    
                    status = "online" if server_manager.is_server_online(plugin_id) else "offline"
                    display_name = f"{server_name} [DEV]" if is_dev else server_name
                    installed.append({"id": plugin_id, "game_name": game_name, "server_name": display_name, "status": status})
                    seen_ids.add(plugin_id)
                except: pass
    return installed

@router.get("/plugins/available")
async def get_available_plugins():
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://raw.githubusercontent.com/MasterBurns/EmberCore/main/plugins_directory.json", timeout=5.0)
            return res.json() if res.status_code == 200 else []
    except: return []

@router.post("/plugins/subscribe/{plugin_id}")
async def subscribe_plugin(plugin_id: str, url: str, server_name: str = "My Server"):
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', server_name).strip('_').lower()
    if not safe_name: safe_name = "server"
    instance_id = f"{plugin_id}_{safe_name}"
    
    if os.path.exists(os.path.join(PLUGINS_ROOT, instance_id)): 
        return {"status": "error", "message": "Server-ID existiert bereits!"}
        
    instance_dir = os.path.join(PLUGINS_ROOT, instance_id)
    os.makedirs(instance_dir, exist_ok=True)
    
    try:
        # Erkennt automatisch, ob ZIP oder rohe YAML heruntergeladen wird!
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=15.0)
            if response.status_code != 200: 
                return {"status": "error", "message": "Download fehlgeschlagen."}
            
            if url.lower().endswith(".zip") or "zip" in response.headers.get("Content-Disposition", "") or response.content[:4] == b"PK\x03\x04":
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref: 
                    zip_ref.extractall(instance_dir)
            else:
                # Es ist eine direkte YAML-Datei
                manifest_path = os.path.join(instance_dir, "manifest.yaml")
                with open(manifest_path, "wb") as f:
                    f.write(response.content)

        manifest_path = os.path.join(instance_dir, "manifest.yaml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f: manifest = yaml.safe_load(f)
            manifest["id"] = instance_id
            with open(manifest_path, "w", encoding="utf-8") as f: yaml.dump(manifest, f, allow_unicode=True, sort_keys=False)
            meta = manifest.get("config_meta")
            if meta:
                hostname_key = next((f["key"] for f in meta.get("fields", []) if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)
                if hostname_key:
                    desired_dir = os.path.join(DATA_ROOT, instance_id)
                    os.makedirs(desired_dir, exist_ok=True)
                    with open(os.path.join(desired_dir, "desired_config.json"), "w", encoding="utf-8") as df:
                        json.dump({hostname_key: server_name}, df, indent=2)
                        
        return {"status": "success", "message": f"Server '{server_name}' erstellt.", "instance_id": instance_id}
    except Exception as e:
        if os.path.exists(instance_dir): shutil.rmtree(instance_dir)
        return {"status": "error", "message": str(e)}


# ==========================================
# SERVER VERWALTUNG ROUTEN
# ==========================================
@router.post("/server/install/{plugin_id}")
def install_server(plugin_id: str, req: InstallRequest = None):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest nicht gefunden")
    
    res = steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
    
    mods_meta = manifest.get("mods_meta", {})
    if mods_meta and "steam_workshop_appid" in mods_meta:
        mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
        if os.path.exists(mods_file):
            with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
            mod_ids = [m["id"] for m in current_mods]
            if mod_ids:
                steam_manager.update_workshop_mods(plugin_id, mods_meta.get("steam_workshop_appid"), mod_ids)
                
    rebuild_modlist(plugin_id, manifest)

    if plugin_id in game_update_cache: game_update_cache[plugin_id]["available"] = False
    return res

@router.post("/server/check-updates/{plugin_id}")
async def force_check_game_updates(plugin_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest or manifest.get("engine") != "steamcmd": return {"status": "error", "message": "Ist der Server bereits installiert?"}
    app_id = manifest.get("steam_app_id")
    local_id = "0"
    acf_path = os.path.join(SERVERS_ROOT, plugin_id, "steamapps", f"appmanifest_{app_id}.acf")
    if os.path.exists(acf_path):
        with open(acf_path, "r", encoding="utf-8") as f:
            match = re.search(r'"buildid"\s+"(\d+)"', f.read(), re.IGNORECASE)
            if match: local_id = match.group(1)

    if local_id != "0":
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"https://api.steamcmd.net/v1/info/{app_id}", timeout=10.0)
                if res.status_code == 200:
                    remote_id = res.json().get("data", {}).get(str(app_id), {}).get("depots", {}).get("branches", {}).get("public", {}).get("buildid")
                    if remote_id:
                        game_update_cache[plugin_id] = {"available": str(local_id) != str(remote_id), "local": str(local_id), "remote": str(remote_id)}
                        if str(local_id) != str(remote_id): return {"status": "success", "message": f"Update verfügbar! ({local_id} -> {remote_id})"}
                        else: return {"status": "info", "message": f"Bereits aktuell. (Build: {local_id})"}
        except: pass
    return {"status": "error", "message": "Konnte Daten nicht prüfen."}

@router.post("/server/start/{plugin_id}")
def start(plugin_id: str):
    if server_manager.is_server_online(plugin_id):
        return {"status": "error", "message": "Der Server läuft bereits im Hintergrund!"}

    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest nicht gefunden")

    auto_update = False
    desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
    if os.path.exists(desired_path):
        with open(desired_path, "r", encoding="utf-8") as df:
            auto_update = json.load(df).get("AutoUpdateOnStart")

    if auto_update in [True, "True", "true", 1]:
        steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
        
        mods_meta = manifest.get("mods_meta", {})
        if mods_meta and "steam_workshop_appid" in mods_meta:
            mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
            if os.path.exists(mods_file):
                with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
                mod_ids = [m["id"] for m in current_mods]
                if mod_ids:
                    steam_manager.update_workshop_mods(plugin_id, mods_meta.get("steam_workshop_appid"), mod_ids)

        if plugin_id in game_update_cache: game_update_cache[plugin_id]["available"] = False
        
    rebuild_modlist(plugin_id, manifest)
    ConfigManager.apply_desired_config(plugin_id)
    
    executable_path = os.path.join(SERVERS_ROOT, plugin_id, manifest.get("executable_windows"))
    return server_manager.start_server(plugin_id, executable_path, manifest.get("default_args", []))

@router.post("/server/stop/{plugin_id}")
def stop(plugin_id: str): 
    return server_manager.stop_server(plugin_id)

@router.get("/server/stats/{plugin_id}")
def stats(plugin_id: str):
    data = server_manager.get_stats(plugin_id)
    data["disk"] = calculate_disk_trend(plugin_id)
    data["update_info"] = game_update_cache.get(plugin_id, {"available": False})
    return data

@router.get("/server/logs/{plugin_id}")
def get_server_logs(plugin_id: str):
    return {"logs": list(server_manager.logs.get(plugin_id, []))}

@router.get("/server/diagnostics/{plugin_id}")
def get_diagnostics(plugin_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest or "diagnostics" not in manifest: return []
    server_logs = list(server_manager.logs.get(plugin_id, []))
    active_diagnostics = []
    for rule in manifest["diagnostics"]:
        for line in server_logs:
            if re.search(rule["pattern"], line, re.IGNORECASE):
                active_diagnostics.append(rule)
                break
    return active_diagnostics

@router.post("/server/diagnostics/fix/{plugin_id}/{fix_type}")
def apply_fix(plugin_id: str, fix_type: str):
    if server_manager.is_server_online(plugin_id): server_manager.stop_server(plugin_id)

    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: return {"status": "error", "message": "Manifest nicht gefunden"}

    if fix_type == "update_server":
        steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
        return {"status": "success", "message": "Server repariert."}
    elif fix_type == "restore_backup":
        backups = backup_manager.list_backups(plugin_id)
        if not backups: return {"status": "error", "message": "Kein Backup gefunden!"}
        backup_manager.restore_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), manifest.get("backup").get("source_path"), backups[0]["filename"])
        return {"status": "success", "message": "Rollback durchgeführt."}
    return {"status": "info", "message": "Manuelle Aktion nötig."}

@router.get("/server/mods/{plugin_id}")
def get_server_mods(plugin_id: str):
    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
    if os.path.exists(mods_file):
        with open(mods_file, "r", encoding="utf-8") as f: return json.load(f)
    return []

@router.post("/server/mods/add/{plugin_id}/{mod_id}")
async def add_server_mod(plugin_id: str, mod_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
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
    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
    os.makedirs(os.path.dirname(mods_file), exist_ok=True)
    current_mods = []
    if os.path.exists(mods_file):
        with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
    if any(m["id"] == mod_id for m in current_mods): return {"status": "error", "message": "Mod existiert bereits!"}
    
    current_mods.append({"id": mod_id, "name": mod_name, "version": mod_version})
    with open(mods_file, "w", encoding="utf-8") as f: json.dump(current_mods, f, indent=2)
    
    rebuild_modlist(plugin_id, manifest)
    
    return {"status": "success", "message": f"Mod '{mod_name}' zur Liste hinzugefügt. Bitte klicke nun auf 'Install / Update', um sie herunterzuladen!"}

@router.delete("/server/mods/delete/{plugin_id}/{mod_id}")
def delete_server_mod(plugin_id: str, mod_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest or "mods_meta" not in manifest: return {"status": "error", "message": "Manifest fehlt oder kein Modding unterstützt"}
    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
    if not os.path.exists(mods_file): return {"status": "success"}
    
    with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
    current_mods = [m for m in current_mods if m["id"] != mod_id]
    with open(mods_file, "w", encoding="utf-8") as f: json.dump(current_mods, f, indent=2)
    
    rebuild_modlist(plugin_id, manifest)
    
    return {"status": "success", "message": "Mod entfernt."}

@router.delete("/server/delete/{plugin_id}")
def delete_server_files(plugin_id: str):
    if server_manager.is_server_online(plugin_id): raise HTTPException(status_code=400, detail="Server läuft noch!")
    if os.path.exists(os.path.join(SERVERS_ROOT, plugin_id)): shutil.rmtree(os.path.join(SERVERS_ROOT, plugin_id))
    if os.path.exists(os.path.join(BACKUPS_ROOT, plugin_id)): shutil.rmtree(os.path.join(BACKUPS_ROOT, plugin_id))
    if os.path.exists(os.path.join(DATA_ROOT, plugin_id)): shutil.rmtree(os.path.join(DATA_ROOT, plugin_id))
    _, plugin_dir, is_dev = ConfigManager.get_plugin_paths(plugin_id)
    if os.path.exists(plugin_dir) and not is_dev: shutil.rmtree(plugin_dir)
    return {"status": "success", "message": "Dateien entfernt."}

@router.post("/server/open-folder/{plugin_id}")
def open_server_folder(plugin_id: str):
    server_dir = os.path.abspath(os.path.join(SERVERS_ROOT, plugin_id))
    os.makedirs(server_dir, exist_ok=True)
    if platform.system() == "Windows": os.startfile(server_dir)
    elif platform.system() == "Linux": subprocess.Popen(["xdg-open", server_dir])
    return {"status": "success"}

@router.get("/server/config/{plugin_id}")
def get_server_config(plugin_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: return {"enabled": False}
    meta = manifest.get("config_meta")
    if not meta: return {"enabled": False}

    fields = meta.get("fields", [])
    known_keys = {f["key"] for f in fields}
    merged_values = {f["key"]: f.get("default") for f in fields}

    live_path = os.path.join(SERVERS_ROOT, plugin_id, meta.get("file_path"))
    live_values = ConfigManager.parse_live_config(live_path)

    for k, v in live_values.items():
        if k in known_keys: merged_values[k] = v

    desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
    desired_values = {}
    if os.path.exists(desired_path):
        try:
            with open(desired_path, "r", encoding="utf-8") as f:
                desired_values = json.load(f)
                for k, v in desired_values.items():
                    if k in known_keys: merged_values[k] = v
        except: pass

    unknown_fields = []
    all_raw_unknowns = {**live_values, **desired_values}

    for k, v in all_raw_unknowns.items():
        if k not in known_keys:
            val_clean = str(v).strip()
            if val_clean.lower() in ["true", "false"]: guessed_type, normalized_val = "boolean", val_clean.lower() == "true"
            else:
                try: guessed_type, normalized_val = ("number", float(val_clean)) if "." in val_clean else ("number", int(val_clean))
                except ValueError: guessed_type, normalized_val = "text", v
            unknown_fields.append({"key": k, "label": f"⚙️ {k} (Dynamisch erkannt)", "type": guessed_type, "is_unknown": True})
            merged_values[k] = normalized_val

    return {"enabled": True, "fields": fields, "unknown_fields": unknown_fields, "values": merged_values}

@router.post("/server/config/{plugin_id}")
def save_server_config(plugin_id: str, data: dict = Body(...)):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest fehlt")
    meta = manifest.get("config_meta")
    if not meta: raise HTTPException(status_code=400, detail="Keine Meta-Config.")

    fields = meta.get("fields", [])
    for field in fields:
        key = field["key"]
        if field.get("type") == "boolean" and key in data:
            if field.get("boolean_mode") == "numeric": data[key] = 1 if data[key] in [True, 1, "1", "true", "True"] else 0
            else: data[key] = "True" if data[key] in [True, 1, "1", "true", "True"] else "False"

    desired_dir = os.path.join(DATA_ROOT, plugin_id)
    os.makedirs(desired_dir, exist_ok=True)
    desired_path = os.path.join(desired_dir, "desired_config.json")

    current_desired = {}
    if os.path.exists(desired_path):
        try:
            with open(desired_path, "r", encoding="utf-8") as f: current_desired = json.load(f)
        except: pass

    current_desired.update(data)
    with open(desired_path, "w", encoding="utf-8") as f: json.dump(current_desired, f, indent=2)
    ConfigManager.apply_desired_config(plugin_id)
    return {"status": "success", "message": "Soll-Konfiguration gespeichert."}

@router.get("/server/lists/{plugin_id}")
def get_server_lists(plugin_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest or "lists_meta" not in manifest: return {"enabled": False, "lists": []}
    result = []
    for lst in manifest["lists_meta"]:
        file_path = os.path.join(SERVERS_ROOT, plugin_id, lst["file_path"])
        content = open(file_path, "r", encoding="utf-8", errors="ignore").read() if os.path.exists(file_path) else ""
        result.append({"id": lst["id"], "name": lst["name"], "content": content})
    return {"enabled": True, "lists": result}

@router.post("/server/lists/{plugin_id}")
def save_server_lists(plugin_id: str, payload: dict = Body(...)):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest or "lists_meta" not in manifest: return {"status": "error"}
    for lst in manifest["lists_meta"]:
        list_id = lst["id"]
        if list_id in payload:
            file_path = os.path.join(SERVERS_ROOT, plugin_id, lst["file_path"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f: f.write(payload[list_id])
    return {"status": "success", "message": "Listen gespeichert."}

@router.get("/server/network/{plugin_id}")
def get_network(plugin_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest or "network_meta" not in manifest: return {"enabled": False, "ports": []}
    return {"enabled": True, "ports": manifest["network_meta"].get("ports", [])}

@router.post("/server/network/setup/{plugin_id}")
def setup_network(plugin_id: str):
    if platform.system() != "Windows":
        return {"status": "error", "message": "Netzwerk-Automatisierung wird nur unter Windows unterstützt."}

    manifest = ConfigManager.load_manifest(plugin_id)
    ports = manifest.get("network_meta", {}).get("ports", [])
    if not ports: return {"status": "error", "message": "Keine Ports definiert."}

    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except: pass

    ps_commands = ["Write-Host 'EmberCore konfiguriert Firewall & Router...'"]
    for p in ports:
        rule_name = f"EmberCore_{plugin_id}_{p['port']}_{p['protocol'].upper()}"
        ps_commands.append(f"netsh advfirewall firewall delete rule name='{rule_name}' 2> $null")
        ps_commands.append(f"netsh advfirewall firewall add rule name='{rule_name}' dir=in action=allow protocol={p['protocol']} localport={p['port']} 2> $null")

    ps_commands.append("$upnp = New-Object -ComObject HNetCfg.NATUPnP")
    ps_commands.append("if ($upnp) { $map = $upnp.StaticPortMappingCollection; if ($map) {")
    for p in ports:
        rule_name = f"EmberCore_{plugin_id}_{p['port']}_{p['protocol'].upper()}"
        ps_commands.append(f"  try {{ $map.Remove({p['port']}, '{p['protocol'].upper()}') }} catch {{}}")
        ps_commands.append(f"  try {{ $map.Add({p['port']}, '{p['protocol'].upper()}', {p['port']}, '{local_ip}', $true, '{rule_name}') }} catch {{}}")
    ps_commands.append("} }")
    ps_commands.append("Write-Host 'Erfolgreich hinzugefuegt! Fenster schliesst sich in 3 Sekunden.'")
    ps_commands.append("Start-Sleep -Seconds 3")

    ps_script = os.path.join(EXE_DIR, "network_setup.ps1")
    with open(ps_script, "w", encoding="utf-8") as f: f.write("\n".join(ps_commands))

    subprocess.Popen(["powershell", "-Command", f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"])
    return {"status": "success", "message": "Bitte bestätige gleich die Windows-Sicherheitsabfrage (Schild-Symbol), um die Freigabe abzuschließen!"}

@router.get("/server/backup/schedule/{plugin_id}")
def get_backup_schedule(plugin_id: str):
    schedule_file = os.path.join(DATA_ROOT, plugin_id, "backup_schedule.json")
    if os.path.exists(schedule_file):
        with open(schedule_file, "r", encoding="utf-8") as f: return json.load(f)
    return {"schedules": [], "retention": {"keep_latest": 5, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}}

@router.post("/server/backup/schedule/{plugin_id}")
def save_backup_schedule(plugin_id: str, req: dict = Body(...)):
    schedule_file = os.path.join(DATA_ROOT, plugin_id, "backup_schedule.json")
    os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
    with open(schedule_file, "w", encoding="utf-8") as f: json.dump(req, f, indent=2)
    return {"status": "success"}

@router.get("/server/backup/list/{plugin_id}")
def list_backups(plugin_id: str): return backup_manager.list_backups(plugin_id)

@router.post("/server/backup/create/{plugin_id}")
def create_backup(plugin_id: str):
    backup_manager.create_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), ConfigManager.load_manifest(plugin_id).get("backup").get("source_path"), {})
    return {"status": "success"}

@router.post("/server/backup/restore/{plugin_id}/{filename}")
def restore_backup(plugin_id: str, filename: str):
    backup_manager.restore_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), ConfigManager.load_manifest(plugin_id).get("backup").get("source_path"), filename)
    return {"status": "success"}

@router.delete("/server/backup/delete/{plugin_id}/{filename}")
def delete_backup(plugin_id: str, filename: str):
    backup_manager.delete_backup(plugin_id, filename)
    return {"status": "success"}
