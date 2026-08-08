import os, sys, platform, subprocess, psutil, time, json, shutil, re, socket, httpx, zipfile, io, yaml
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel
import urllib.request
import logging

from core.env import (
    EXE_DIR, BASE_DIR, SERVERS_ROOT, DATA_ROOT, PLUGINS_ROOT, DEV_PLUGINS_ROOT,
    BACKUPS_ROOT, START_TIME, sys_config, logger, game_update_cache, disk_cache,
    get_current_system_version
)
from core.server_manager import server_manager
from core.config_manager import ConfigManager
from core.steamcmd_manager import SteamCMDManager
from core.backup_manager import BackupManager
from core.discord_manager import discord_manager
from core.cluster_manager import cluster_manager  # NEU IMPORTIERT

steam_manager = SteamCMDManager(base_dir=SERVERS_ROOT)
backup_manager = BackupManager(base_dir=EXE_DIR)

router = APIRouter(prefix="/api")

class InstallRequest(BaseModel): install_dir_name: str = None

class DiscordSetupPayload(BaseModel):
    app_id: str
    token: str
    pairing_key: str


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
    mods_dir = os.path.dirname(real_modlist_path)
    os.makedirs(mods_dir, exist_ok=True)

    try:
        for f in os.listdir(mods_dir):
            if f.lower().endswith(".pak"):
                os.remove(os.path.join(mods_dir, f))
    except: pass

    workshop_dir = os.path.abspath(os.path.join(SERVERS_ROOT, plugin_id, "steamapps", "workshop", "content", str(mods_meta["steam_workshop_appid"])))
    valid_mod_lines = []

    for mod in current_mods:
        mod_id = mod["id"]
        mod_folder = os.path.join(workshop_dir, str(mod_id))
        pak_path = None
        pak_filename = None

        if os.path.exists(mod_folder):
            for root, _, files in os.walk(mod_folder):
                for file in files:
                    if file.lower().endswith(".pak"):
                        pak_path = os.path.abspath(os.path.join(root, file))
                        pak_filename = file
                        break
                if pak_path: break

        if pak_path and pak_filename:
            target_pak = os.path.join(mods_dir, pak_filename)
            try: os.link(pak_path, target_pak)
            except OSError: shutil.copy2(pak_path, target_pak)
            valid_mod_lines.append(f"*{pak_filename}\n")

    with open(real_modlist_path, "w", encoding="utf-8") as f:
        f.writelines(valid_mod_lines)


# ==========================================
# DISCORD INTEGRATION
# ==========================================
@router.get("/system/discord")
async def get_discord_settings():
    """Gibt dem Frontend beim Start den aktuellen Status des Bots."""
    config = discord_manager.load_config()
    is_linked = config.get("linked", False)
    
    return {
        "discord_linked": is_linked,
        "discord_guild_name": config.get("guild_name", "Ausstehend (Warte auf /link)"),
        "discord_channel_name": config.get("channel_name", "ausstehend")
    }

@router.post("/system/discord/setup")
async def setup_discord_bot(payload: DiscordSetupPayload):
    """Speichert das Token und startet den Bot im Hintergrund-Task."""
    try:
        config = discord_manager.load_config()
        config["app_id"] = payload.app_id
        config["token"] = payload.token
        config["linked"] = False
        discord_manager.save_config(config)
        
        await discord_manager.start_bot(payload.token, payload.pairing_key)
        return {"status": "success", "message": "Bot-Prozess gestartet."}
    except Exception as e:
        logger.error(f"Fehler beim Discord Setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/system/discord/unlink")
async def unlink_discord_bot():
    """Stoppt den Bot und löscht die Config."""
    try:
        await discord_manager.stop_bot()
        if os.path.exists(discord_manager.config_path):
            os.remove(discord_manager.config_path)
        return {"status": "success", "message": "Verbindung getrennt und Bot beendet."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# CLUSTER MANAGEMENT (ARK, etc.)
# ==========================================
@router.get("/clusters")
def get_clusters():
    return cluster_manager.get_all()

@router.post("/clusters/create")
def create_cluster(payload: dict = Body(...)):
    return cluster_manager.create(
        payload.get("cluster_id"),
        payload.get("name", "Neuer Cluster"),
        payload.get("game_name", "ARK: Survival Ascended"),
        payload.get("custom_path", "").strip()
    )

@router.post("/clusters/open-folder/{cluster_id}")
def open_cluster_folder(cluster_id: str):
    return cluster_manager.open_folder(cluster_id)

@router.delete("/clusters/delete/{cluster_id}")
def delete_cluster(cluster_id: str):
    return cluster_manager.delete(cluster_id)

@router.post("/clusters/assign/{cluster_id}/{plugin_id}")
def assign_to_cluster(cluster_id: str, plugin_id: str):
    return cluster_manager.assign_server(cluster_id, plugin_id)

@router.post("/clusters/remove/{plugin_id}")
def remove_from_cluster(plugin_id: str):
    return cluster_manager.remove_server(plugin_id)

@router.get("/clusters/mods/{cluster_id}")
def get_cluster_mods(cluster_id: str):
    return cluster_manager.get_mods(cluster_id)

@router.post("/clusters/mods/sync/{cluster_id}")
def sync_cluster_mods(cluster_id: str, payload: dict = Body(...)):
    res = cluster_manager.sync_mods(cluster_id, payload.get("mod_ids", []))
    if res.get("status") == "success":
        for plugin_id in res.get("updated_members", []):
            manifest = ConfigManager.load_manifest(plugin_id)
            if manifest: rebuild_modlist(plugin_id, manifest)
    return res

@router.get("/clusters/config/sections/{cluster_id}/{plugin_id}")
def get_cluster_config_sections(cluster_id: str, plugin_id: str):
    return cluster_manager.get_config_sections(plugin_id)

@router.post("/clusters/config/sync/{cluster_id}")
def sync_cluster_config(cluster_id: str, payload: dict = Body(...)):
    return cluster_manager.sync_config(
        cluster_id,
        payload.get("master_plugin_id"),
        payload.get("selected_sections", [])
    )


# ==========================================
# SYSTEM & SERVICE ROUTEN
# ==========================================
@router.get("/system/health")
def system_health(): return {"status": "ok"}

@router.post("/system/shutdown")
def shutdown_embercore():
    logger.info("[-] Manueller Shutdown angefordert. Beende Watchdogs...")
    import psutil
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = p.info.get('cmdline') or []
            if "--watchdog" in cmdline: p.kill()
        except: pass

    def seppuku():
        import time
        time.sleep(1.5)
        os._exit(0)
    import threading
    threading.Thread(target=seppuku, daemon=True).start()
    return {"status": "success", "message": "EmberCore fährt herunter."}

@router.get("/system/settings")
def get_settings():
    return sys_config

@router.get("/system/debug")
def get_debug_info():
    from core.env import BASE_DIR
    static_dir = os.path.join(BASE_DIR, "static")
    try:
        base_files = os.listdir(BASE_DIR)
    except Exception as e:
        base_files = str(e)
    try:
        static_files = os.listdir(static_dir)
    except Exception as e:
        static_files = str(e)
    
    return {
        "BASE_DIR": BASE_DIR,
        "static_dir": static_dir,
        "base_exists": os.path.exists(BASE_DIR),
        "static_exists": os.path.exists(static_dir),
        "base_files": base_files,
        "static_files": static_files
    }

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
    except Exception as e: return {"logs": f"Lese-Fehler: {e}"}
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
                            live_values = ConfigManager.parse_live_config(os.path.join(SERVERS_ROOT, plugin_id, meta.get("file_path")), meta.get("format", "ini"))

                        hostname_key = next((f["key"] for f in meta.get("fields", []) if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)
                        if hostname_key and live_values.get(hostname_key):
                            server_name = live_values.get(hostname_key)

                    status = "online" if server_manager.is_server_online(plugin_id) else "offline"
                    display_name = f"{server_name} [DEV]" if is_dev else server_name
                    installed.append({"id": plugin_id, "game_name": game_name, "server_name": display_name, "status": status, "is_dev": is_dev})
                    seen_ids.add(plugin_id)
                except: pass
    return installed

@router.get("/server/manifest/{plugin_id}")
def get_server_manifest(plugin_id: str):
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest nicht gefunden")
    return manifest


IMPORT_TASKS = {}

def _run_amp_import(task_id: str, amp_path: str, mode: str, plugin_id: str, src_dir: str, server_dir: str):
    import shutil
    import os
    import re
    import json
    from core.env import logger, DATA_ROOT
    
    try:
        IMPORT_TASKS[task_id]["message"] = "Berechne Ordnergröße..."
        
        # Berechne Gesamtgröße
        total_size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(src_dir) for f in fn)
        copied_size = 0
        
        def copy_with_progress(src, dst):
            nonlocal copied_size
            shutil.copy2(src, dst)
            copied_size += os.path.getsize(src)
            if total_size > 0:
                progress = int((copied_size / total_size) * 100)
                IMPORT_TASKS[task_id]["progress"] = min(99, progress)
                IMPORT_TASKS[task_id]["message"] = f"{'Verschiebe' if mode == 'move' else 'Kopiere'} Dateien... ({min(99, progress)}%)"

        os.makedirs(os.path.dirname(server_dir), exist_ok=True)
        shutil.copytree(src_dir, server_dir, copy_function=copy_with_progress)
        
        # Try to extract mods from AMP config or GameUserSettings.ini
        mod_ids = set()
        
        amp_config_path = os.path.join(amp_path, "AMPConfig.conf")
        if os.path.exists(amp_config_path):
            try:
                with open(amp_config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "mod" in line.lower() and "=" in line:
                            val = line.split("=", 1)[1].strip()
                            if re.match(r'^[\d,]+$', val):
                                for m_id in val.split(','):
                                    if m_id.strip():
                                        mod_ids.add(m_id.strip())
            except Exception as e:
                logger.error(f"[!] Fehler beim Lesen der AMPConfig.conf: {e}")
                
        gus_path = os.path.join(server_dir, "ShooterGame", "Saved", "Config", "WindowsServer", "GameUserSettings.ini")
        if os.path.exists(gus_path):
            try:
                with open(gus_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("ActiveMods="):
                            val = line.split("=", 1)[1].strip()
                            for m_id in val.split(','):
                                if m_id.strip() and m_id.strip().isdigit():
                                    mod_ids.add(m_id.strip())
            except Exception as e:
                logger.error(f"[!] Fehler beim Lesen von GameUserSettings.ini (Mods): {e}")
                
        if mod_ids:
            mods_db = []
            for mid in mod_ids:
                mods_db.append({
                    "id": mid,
                    "name": f"Imported Mod ({mid})",
                    "version": "Auto-Update durch Server"
                })
            mods_dir = os.path.join(DATA_ROOT, plugin_id)
            os.makedirs(mods_dir, exist_ok=True)
            with open(os.path.join(mods_dir, "mods_db.json"), "w", encoding="utf-8") as f:
                json.dump(mods_db, f, indent=2)
            logger.info(f"[*] {len(mods_db)} Mods aus AMP Konfiguration importiert.")
            
        if mode == "move":
            IMPORT_TASKS[task_id]["message"] = "Räume alten Ordner auf..."
            shutil.rmtree(src_dir, ignore_errors=True)

        IMPORT_TASKS[task_id]["progress"] = 100
        IMPORT_TASKS[task_id]["status"] = "completed"
        IMPORT_TASKS[task_id]["message"] = f"Server erfolgreich als '{plugin_id}' importiert!"
        
    except Exception as e:
        logger.error(f"[!] Fehler beim AMP-Import-Task {task_id}: {e}")
        IMPORT_TASKS[task_id]["status"] = "error"
        IMPORT_TASKS[task_id]["message"] = f"Fehler: {str(e)}"

@router.get("/system/importer/status/{task_id}")
async def get_amp_import_status(task_id: str):
    if task_id not in IMPORT_TASKS:
        return {"status": "error", "message": "Task nicht gefunden."}
    return IMPORT_TASKS[task_id]

@router.post("/system/importer/amp")
async def import_amp_server(background_tasks: BackgroundTasks, data: dict = Body(...)):
    import shutil
    import time
    
    amp_path = data.get("path", "").strip()
    mode = data.get("mode", "move")  # 'move' or 'copy'
    
    if not amp_path or not os.path.exists(amp_path):
        return {"status": "error", "message": "Der angegebene Pfad existiert nicht."}
        
    # Auto-detect game type
    is_asa = False
    src_dir = None
    
    if os.path.exists(os.path.join(amp_path, "ARK Survival Ascended", "ShooterGame")):
        is_asa = True
        src_dir = os.path.join(amp_path, "ARK Survival Ascended")
    elif os.path.exists(os.path.join(amp_path, "ShooterGame")):
        is_asa = True
        src_dir = amp_path
        
    if not is_asa or not src_dir:
        return {"status": "error", "message": "Derzeit werden nur ASA-Server vom Importer unterstützt. Konnte 'ShooterGame' nicht finden."}
        
    # Generate unique plugin ID
    safe_name = os.path.basename(os.path.normpath(amp_path))
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', safe_name).strip('_').lower()
    if not safe_name: safe_name = "server"
    plugin_id = f"asa_{safe_name}_{int(time.time())}"
    
    instance_dir = os.path.join(PLUGINS_ROOT, plugin_id)
    server_dir = os.path.join(SERVERS_ROOT, plugin_id)
    
    if os.path.exists(instance_dir) or os.path.exists(server_dir):
        return {"status": "error", "message": "Ein Server mit diesem Namen existiert bereits."}
        
    os.makedirs(instance_dir, exist_ok=True)
    
    try:
        # Download ASA manifest
        manifest_url = "https://raw.githubusercontent.com/MasterBurns/EmberCore/main/plugins/ASA/manifest.yaml"
        async with httpx.AsyncClient() as client:
            res = await client.get(manifest_url, timeout=10.0)
            if res.status_code == 200:
                manifest_path = os.path.join(instance_dir, "manifest.yaml")
                with open(manifest_path, "wb") as f:
                    f.write(res.content)
                    
                # Fix up the manifest exactly like subscribe_plugin does
                with open(manifest_path, "r", encoding="utf-8") as f: 
                    manifest_data = yaml.safe_load(f)
                manifest_data["id"] = plugin_id
                manifest_data["source_url"] = manifest_url

                # Parse AMPConfig.conf if it exists
                amp_config_path = os.path.join(amp_path, "AMPConfig.conf")
                ext_conf = {}
                if os.path.exists(amp_config_path):
                    try:
                        with open(amp_config_path, "r", encoding="utf-8") as f:
                            for line in f:
                                if '=' not in line: continue
                                key, val = line.split('=', 1)
                                key, val = key.strip(), val.strip()
                                k_lower = key.lower()
                                if "sessionname" in k_lower or "servername" in k_lower: ext_conf["SessionName"] = val
                                elif "maxplayers" in k_lower: ext_conf["MaxPlayers"] = int(val) if val.isdigit() else 20
                                elif "map" in k_lower and "url" not in k_lower: ext_conf["Map"] = val
                                elif "serverpassword" in k_lower: ext_conf["ServerPassword"] = val
                                elif "adminpassword" in k_lower: ext_conf["ServerAdminPassword"] = val
                                elif "queryport" in k_lower: ext_conf["QueryPort"] = val
                                elif "rconport" in k_lower: ext_conf["RCONPort"] = val
                                elif "portnumber" in k_lower or "gameport" in k_lower: ext_conf["Port"] = val
                    except Exception as e:
                        logger.error(f"[!] Fehler beim Parsen von AMPConfig.conf: {e}")

                # Update Manifest default_args and network_meta with extracted ports
                if "Port" in ext_conf or "QueryPort" in ext_conf or "RCONPort" in ext_conf:
                    new_args = []
                    for arg in manifest_data.get("default_args", []):
                        if "?" in arg:
                            parts = arg.split("?")
                            new_parts = []
                            for p in parts:
                                if p.lower().startswith("port=") and "Port" in ext_conf: new_parts.append(f"Port={ext_conf['Port']}")
                                elif p.lower().startswith("queryport=") and "QueryPort" in ext_conf: new_parts.append(f"QueryPort={ext_conf['QueryPort']}")
                                elif p.lower().startswith("rconport=") and "RCONPort" in ext_conf: new_parts.append(f"RCONPort={ext_conf['RCONPort']}")
                                else: new_parts.append(p)
                            new_args.append("?".join(new_parts))
                        else: new_args.append(arg)
                    manifest_data["default_args"] = new_args
                    
                    if "network_meta" in manifest_data and "ports" in manifest_data["network_meta"]:
                        for port_obj in manifest_data["network_meta"]["ports"]:
                            desc = port_obj.get("desc", "").lower()
                            if "game" in desc and "Port" in ext_conf: port_obj["port"] = int(ext_conf["Port"])
                            elif "query" in desc and "QueryPort" in ext_conf: port_obj["port"] = int(ext_conf["QueryPort"])
                            elif "rcon" in desc and "RCONPort" in ext_conf: port_obj["port"] = int(ext_conf["RCONPort"])
                            
                    if "shutdown" in manifest_data and "rcon" in manifest_data["shutdown"]:
                        if "RCONPort" in ext_conf: manifest_data["shutdown"]["rcon"]["port"] = int(ext_conf["RCONPort"])
                        if "ServerAdminPassword" in ext_conf: manifest_data["shutdown"]["rcon"]["default_password"] = ext_conf["ServerAdminPassword"]
                
                with open(manifest_path, "w", encoding="utf-8") as f: 
                    yaml.dump(manifest_data, f, allow_unicode=True, sort_keys=False)
                    
                # Save Map to startup.json
                if "Map" in ext_conf:
                    data_dir = os.path.join(DATA_ROOT, plugin_id)
                    os.makedirs(data_dir, exist_ok=True)
                    with open(os.path.join(data_dir, "startup.json"), "w", encoding="utf-8") as f:
                        json.dump({"map": ext_conf["Map"]}, f)
                        
                # Save settings to desired_config.json
                desired = {}
                for k in ["SessionName", "MaxPlayers", "ServerPassword", "ServerAdminPassword"]:
                    if k in ext_conf: desired[k] = ext_conf[k]
                if desired:
                    data_dir = os.path.join(DATA_ROOT, plugin_id)
                    os.makedirs(data_dir, exist_ok=True)
                    with open(os.path.join(data_dir, "desired_config.json"), "w", encoding="utf-8") as f:
                        json.dump(desired, f, indent=2)
                        
            else:
                return {"status": "error", "message": "Konnte ASA Manifest nicht herunterladen."}
                
        # --- Start Background Task ---
        task_id = f"import_{plugin_id}"
        IMPORT_TASKS[task_id] = {
            "status": "running",
            "progress": 0,
            "message": "Start vorbereiten..."
        }
        
        background_tasks.add_task(_run_amp_import, task_id, amp_path, mode, plugin_id, src_dir, server_dir)
        
        return {"status": "success", "task_id": task_id, "message": "Import läuft im Hintergrund..."}
        
    except Exception as e:
        logger.error(f"[!] Fehler beim AMP-Import-Setup: {e}")
        return {"status": "error", "message": f"Setup fehlgeschlagen: {e}"}

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
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=15.0)
            if response.status_code != 200:
                return {"status": "error", "message": "Download fehlgeschlagen."}

            if url.lower().endswith(".zip") or "zip" in response.headers.get("Content-Disposition", "") or response.content[:4] == b"PK\x03\x04":
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                    zip_ref.extractall(instance_dir)
            else:
                manifest_path = os.path.join(instance_dir, "manifest.yaml")
                with open(manifest_path, "wb") as f:
                    f.write(response.content)

        manifest_path = os.path.join(instance_dir, "manifest.yaml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f: manifest = yaml.safe_load(f)
            manifest["id"] = instance_id
            manifest["source_url"] = url if not url.endswith(".zip") else ""

            # === PORT AUTO-INCREMENT LOGIC ===
            network_meta = manifest.get("network_meta")
            if network_meta and "ports" in network_meta:
                used_ports = set()
                dirs_to_scan = [(DEV_PLUGINS_ROOT, True), (PLUGINS_ROOT, False)]
                for target_dir, _ in dirs_to_scan:
                    if not os.path.exists(target_dir): continue
                    for pid in os.listdir(target_dir):
                        if pid == instance_id: continue
                        m_path = os.path.join(target_dir, pid, "manifest.yaml")
                        if os.path.exists(m_path):
                            try:
                                with open(m_path, "r", encoding="utf-8") as mf:
                                    m_data = yaml.safe_load(mf)
                                    if m_data and "network_meta" in m_data and "ports" in m_data["network_meta"]:
                                        for p in m_data["network_meta"]["ports"]:
                                            used_ports.add(int(p["port"]))
                            except: pass

                original_ports = [int(p["port"]) for p in network_meta["ports"]]
                offset = 0
                while True:
                    proposed_ports = [p + offset for p in original_ports]
                    if any(p in used_ports for p in proposed_ports):
                        offset += 10
                    else:
                        break
                
                if offset > 0:
                    logger.info(f"[*] Port-Konflikt erkannt! Iteriere Ports um +{offset} für '{instance_id}'")
                    # Update network_meta
                    for idx, p_info in enumerate(network_meta["ports"]):
                        old_port = p_info["port"]
                        new_port = old_port + offset
                        p_info["port"] = new_port
                    
                    # Update shutdown rcon port
                    if "shutdown" in manifest and "rcon" in manifest["shutdown"] and "port" in manifest["shutdown"]["rcon"]:
                        manifest["shutdown"]["rcon"]["port"] += offset
                    
                    # Update default_args
                    if "default_args" in manifest:
                        new_args = []
                        for arg in manifest["default_args"]:
                            arg_str = str(arg)
                            for orig_p in original_ports:
                                arg_str = re.sub(rf'\b{orig_p}\b', str(orig_p + offset), arg_str)
                            new_args.append(arg_str)
                        manifest["default_args"] = new_args
                        
                    # Also update config_meta default if it matches a port (rare, but good to have)
                    if "config_meta" in manifest and "fields" in manifest["config_meta"]:
                        for field in manifest["config_meta"]["fields"]:
                            if field.get("type") == "number" and field.get("default") in original_ports:
                                field["default"] += offset

            with open(manifest_path, "w", encoding="utf-8") as f: yaml.dump(manifest, f, allow_unicode=True, sort_keys=False)
            meta = manifest.get("config_meta")
            if meta:
                hostname_key = next((f["key"] for f in meta.get("fields", []) if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)
                desired_dir = os.path.join(DATA_ROOT, instance_id)
                os.makedirs(desired_dir, exist_ok=True)
                
                initial_desired = {}
                for field in meta.get("fields", []):
                    if "default" in field:
                        initial_desired[field["key"]] = field["default"]
                
                if hostname_key:
                    initial_desired[hostname_key] = server_name
                    
                with open(os.path.join(desired_dir, "desired_config.json"), "w", encoding="utf-8") as df:
                    json.dump(initial_desired, df, indent=2)

        return {"status": "success", "message": f"Server '{server_name}' erstellt.", "instance_id": instance_id}
    except Exception as e:
        if os.path.exists(instance_dir): shutil.rmtree(instance_dir)
        return {"status": "error", "message": str(e)}


# ==========================================
# SERVER VERWALTUNG ROUTEN
# ==========================================
@router.post("/server/install/{plugin_id}")
def install_server(plugin_id: str, req: InstallRequest = None):
    ConfigManager.sync_manifest_from_cloud(plugin_id)
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest nicht gefunden")

    logger.info(f"[*] Update-Prozess für '{plugin_id}' gestartet...")
    res = steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)

    mods_meta = manifest.get("mods_meta", {})
    if mods_meta and "steam_workshop_appid" in mods_meta:
        mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
        if os.path.exists(mods_file):
            with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
            if current_mods:
                steam_manager.update_workshop_mods(plugin_id, mods_meta.get("steam_workshop_appid"), current_mods)

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
        logger.info("[*] Auto-Update ist an! Synchronisiere Daten vor dem Start...")
        steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)

        mods_meta = manifest.get("mods_meta", {})
        if mods_meta and "steam_workshop_appid" in mods_meta:
            mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
            if os.path.exists(mods_file):
                with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
                if current_mods:
                    steam_manager.update_workshop_mods(plugin_id, mods_meta.get("steam_workshop_appid"), current_mods)

        if plugin_id in game_update_cache: game_update_cache[plugin_id]["available"] = False

    rebuild_modlist(plugin_id, manifest)
    ConfigManager.apply_desired_config(plugin_id)

    if platform.system() == "Linux" and "executable_linux" in manifest:
        executable_path = os.path.join(SERVERS_ROOT, plugin_id, manifest.get("executable_linux"))
    else:
        executable_path = os.path.join(SERVERS_ROOT, plugin_id, manifest.get("executable_windows"))

    args = manifest.get("default_args", []).copy()

    # === DYNAMIC ARGUMENT INJECTION (arg_mapping) ===
    # Erlaubt das direkte Einspritzen von Werten wie ServerName in die Kommandozeile
    # um z.B. Probleme mit fehlerhaften INI-Zuordnungen der Spiele zu umgehen.
    desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
    if os.path.exists(desired_path):
        try:
            with open(desired_path, "r", encoding="utf-8") as f:
                desired_data = json.load(f)
                
            arg_mapping = manifest.get("config_meta", {}).get("arg_mapping", {})
            for key, template in arg_mapping.items():
                if key in desired_data:
                    val = str(desired_data[key])
                    # Für ASA: Argumente, die mit ? anfangen, an den Map-String anhängen
                    if template.startswith("?"):
                        if args and ("?" in args[0] or args[0].endswith("_WP") or args[0].lower() in ["theisland", "scorchedearth", "aberration"]):
                            import re
                            param_name = template.split("=")[0].strip("?")  # z.B. SessionName
                            new_param = template.replace("{value}", val).strip("?")
                            
                            if f"?{param_name}=" in args[0]:
                                # Ersetze den alten Wert
                                args[0] = re.sub(rf"\?{param_name}=[^?]*", f"?{new_param}", args[0])
                            else:
                                # Hänge ihn neu an
                                args[0] += f"?{new_param}"
                    else:
                        # Für normale Argumente (wie -ServerName=... für Conan)
                        import re
                        if "=" in template:
                            param_name = template.split("=")[0] # z.B. -ServerName
                            new_param = template.replace("{value}", val)
                            
                            # Check if parameter already exists in args
                            replaced = False
                            for i in range(len(args)):
                                if args[i].startswith(f"{param_name}="):
                                    args[i] = new_param
                                    replaced = True
                                    break
                            
                            if not replaced:
                                args.append(new_param)
                        else:
                            args.append(template.replace("{value}", val))
                        
            logger.info(f"[*] Arg Mapping: {len(arg_mapping)} Parameter in Kommandozeile injiziert.")
        except Exception as e:
            logger.error(f"[!] Fehler beim Arg Mapping: {e}")

    # === CUSTOM START PARAMETERS & KARTEN-INJECTOR ===
    startup_file = os.path.join(DATA_ROOT, plugin_id, "startup.json")
    if os.path.exists(startup_file):
        try:
            with open(startup_file, "r") as f:
                startup_data = json.load(f)
                
                # Custom Start Parameters
                custom_params = startup_data.get("custom_start_parameters", "").strip()
                if custom_params:
                    import shlex
                    args.extend(shlex.split(custom_params))
                    logger.info(f"[*] Custom Parameters Injector: Hänge '{custom_params}' an.")
                
                # Karten-Injector
                saved_map = startup_data.get("map")
                if saved_map and args and "?" in args[0]:
                    parts = args[0].split("?", 1)
                    args[0] = f"{saved_map}?{parts[1]}"
                    logger.info(f"[*] Map Override: Starte Server mit Karte '{saved_map}'")
        except: pass

    # === MODS-INJECTOR (CurseForge / ASA) ===
    mods_meta = manifest.get("mods_meta", {})
    if mods_meta.get("provider") == "curseforge":
        mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
        if os.path.exists(mods_file):
            try:
                with open(mods_file, "r", encoding="utf-8") as f:
                    current_mods = json.load(f)
                    if current_mods:
                        mod_ids = [m["id"] for m in current_mods]
                        mod_string = ",".join(mod_ids)
                        args.append(f"-mods={mod_string}")
                        logger.info(f"[*] Mod Injector: {len(mod_ids)} Mods via -mods Argument angehängt.")
            except Exception as e:
                logger.error(f"[!] Fehler beim Laden der Mods für Injector: {e}")

    # === DYNAMISCHE CLUSTER INJECTION & SICHERHEIT ===
    cluster_info = cluster_manager.get_injection_args(plugin_id)
    if cluster_info:
        logger.info(f"[*] Server ist Teil von Cluster '{cluster_info['cluster_id']}'. Führe Pre-Flight Check aus...")
        ConfigManager.enforce_cluster_rules(plugin_id, manifest)
        args.extend(cluster_info["args"])

    return server_manager.start_server(plugin_id, executable_path, args)

@router.post("/server/stop/{plugin_id}")
def stop(plugin_id: str):
    return server_manager.stop_server(plugin_id)

@router.get("/server/stats/{plugin_id}")
def stats(plugin_id: str, skip_disk: bool = False):
    data = server_manager.get_stats(plugin_id)
    data["disk"] = calculate_disk_trend(plugin_id) if not skip_disk else {}
    data["update_info"] = game_update_cache.get(plugin_id, {"available": False})
    
    # NEU: Dem Frontend den Backup-Status mitteilen
    data["backup_progress"] = backup_manager.get_progress(plugin_id) 
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
    
    mods_meta = manifest.get("mods_meta", {})
    provider = mods_meta.get("provider", "steam")
    
    mod_name, mod_version = f"Mod ({mod_id})", "unbekannt"
    
    if provider == "steam":
        steam_url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
        payload = {"itemcount": 1, "publishedfileids[0]": mod_id}
        mod_name = f"Workshop Mod ({mod_id})"
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
    elif provider == "curseforge":
        mod_name = f"CurseForge Mod ({mod_id})"
        mod_version = "Auto-Update durch Server"
        
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
    return _do_delete_mod(plugin_id, mod_id)

@router.post("/server/mods/delete_bulk/{plugin_id}")
def delete_server_mod_bulk(plugin_id: str, data: dict = Body(...)):
    return _do_delete_mod(plugin_id, data.get("mod_id", ""))

def _do_delete_mod(plugin_id: str, mod_id: str):
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
    if not manifest: return {"enabled": False}
    meta = manifest.get("config_meta")
    if not meta: return {"enabled": False}

    fields = meta.get("fields", [])
    config_file_path = meta.get("file_path", "Unbekannt")
    
    # Add file path to defined fields
    for f in fields:
        f["file"] = f.get("file_path", config_file_path)
        
    known_keys = {f["key"] for f in fields}
    merged_values = {f["key"]: f.get("default") for f in fields}

    live_values = ConfigManager.get_full_live_config(plugin_id)

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
            unknown_fields.append({"key": k, "label": f"⚙️ {k} (Dynamisch erkannt)", "type": guessed_type, "is_unknown": True, "file": config_file_path})
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

@router.post("/server/network/{plugin_id}")
def save_network(plugin_id: str, data: dict = Body(...)):
    manifest_path = os.path.join(PLUGINS_ROOT, plugin_id, "manifest.yaml")
    if not os.path.exists(manifest_path):
        return {"status": "error", "message": "Server-Manifest nicht gefunden."}
        
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
            
        new_ports = data.get("ports", [])
        if "network_meta" not in manifest:
            manifest["network_meta"] = {"ports": []}
            
        manifest["network_meta"]["ports"] = new_ports
        
        # Update default_args to match new ports
        if "default_args" in manifest:
            new_args = []
            for arg in manifest["default_args"]:
                if "?" in arg:
                    parts = arg.split("?")
                    new_parts = []
                    for p in parts:
                        updated = False
                        for p_obj in new_ports:
                            desc = p_obj.get("desc", "").lower()
                            if "game" in desc and p.lower().startswith("port="):
                                new_parts.append(f"Port={p_obj['port']}")
                                updated = True
                                break
                            elif "query" in desc and p.lower().startswith("queryport="):
                                new_parts.append(f"QueryPort={p_obj['port']}")
                                updated = True
                                break
                            elif "rcon" in desc and p.lower().startswith("rconport="):
                                new_parts.append(f"RCONPort={p_obj['port']}")
                                updated = True
                                break
                        if not updated:
                            new_parts.append(p)
                    new_args.append("?".join(new_parts))
                else:
                    updated_standalone = False
                    for p_obj in new_ports:
                        desc = p_obj.get("desc", "").lower()
                        if "game" in desc and (arg.lower().startswith("-port=") or arg.lower().startswith("port=")):
                            prefix = "-Port=" if arg.startswith("-") else "Port="
                            new_args.append(f"{prefix}{p_obj['port']}")
                            updated_standalone = True
                            break
                        elif "query" in desc and (arg.lower().startswith("-queryport=") or arg.lower().startswith("queryport=")):
                            prefix = "-QueryPort=" if arg.startswith("-") else "QueryPort="
                            new_args.append(f"{prefix}{p_obj['port']}")
                            updated_standalone = True
                            break
                        elif "rcon" in desc and (arg.lower().startswith("-rconport=") or arg.lower().startswith("rconport=")):
                            prefix = "-RCONPort=" if arg.startswith("-") else "RCONPort="
                            new_args.append(f"{prefix}{p_obj['port']}")
                            updated_standalone = True
                            break
                    if not updated_standalone:
                        new_args.append(arg)
            manifest["default_args"] = new_args
            
        # Determine shutdown rcon port
        shutdown_rcon_port = None
        if "shutdown" in manifest and "rcon" in manifest["shutdown"]:
            for p_obj in new_ports:
                if "rcon" in p_obj.get("desc", "").lower():
                    shutdown_rcon_port = p_obj["port"]
                    break

        override_data = {
            "ports": new_ports,
            "default_args": manifest.get("default_args", []),
            "shutdown_rcon_port": shutdown_rcon_port
        }
        
        override_dir = os.path.join(DATA_ROOT, plugin_id)
        os.makedirs(override_dir, exist_ok=True)
        with open(os.path.join(override_dir, "network_override.json"), "w", encoding="utf-8") as f:
            json.dump(override_data, f, indent=4)
            
        return {"status": "success", "message": "Netzwerk-Ports erfolgreich aktualisiert."}
    except Exception as e:
        logger.error(f"[!] Fehler beim Speichern der Netzwerk-Ports: {e}")
        return {"status": "error", "message": str(e)}

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
    return backup_manager.create_backup(
        plugin_id,
        os.path.join(SERVERS_ROOT, plugin_id),
        ConfigManager.load_manifest(plugin_id).get("backup").get("source_path"),
        {}
    )

@router.post("/server/backup/restore/{plugin_id}/{filename}")
def restore_backup(plugin_id: str, filename: str):
    backup_manager.restore_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), ConfigManager.load_manifest(plugin_id).get("backup").get("source_path"), filename)
    return {"status": "success"}

@router.delete("/server/backup/delete/{plugin_id}/{filename}")
def delete_backup(plugin_id: str, filename: str):
    backup_manager.delete_backup(plugin_id, filename)
    return {"status": "success"}

from fastapi import UploadFile, File
import tempfile
import shutil

@router.post("/server/backup/import/{plugin_id}")
async def import_backup(plugin_id: str, file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        return {"status": "error", "message": "Bitte lade nur .zip Dateien hoch!"}
        
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
            
        manifest = ConfigManager.load_manifest(plugin_id)
        if not manifest or "backup" not in manifest or "source_path" not in manifest["backup"]:
            os.remove(tmp_path)
            return {"status": "error", "message": "Plugin hat keinen definierten Save-Pfad im Manifest."}
            
        source_rel_path = manifest["backup"]["source_path"]
        server_dir = os.path.join(SERVERS_ROOT, plugin_id)
        
        # Achtung: Wir führen hier KEIN automatisches Backup mehr durch,
        # da create_backup asynchron läuft und es sonst knallt, wenn wir direkt danach löschen.
        
        res = backup_manager.import_savegame(plugin_id, server_dir, source_rel_path, tmp_path)
        os.remove(tmp_path)
        return res
        
    except Exception as e:
        return {"status": "error", "message": f"Upload Fehler: {str(e)}"}

@router.get("/server/startup/{plugin_id}")
def get_server_startup(plugin_id: str):
    """Liest aus dem Manifest, ob Karten wählbar sind, und lädt die aktuelle Auswahl."""
    manifest = ConfigManager.load_manifest(plugin_id)
    if not manifest: return {"enabled": False}
    
    maps = manifest.get("maps", [])
    has_maps = len(maps) > 0
    selected_map = maps[0] if has_maps else ""
    
    show_external_console = False
    show_in_discord = True
    startup_file = os.path.join(DATA_ROOT, plugin_id, "startup.json")
    if os.path.exists(startup_file):
        try:
            with open(startup_file, "r") as f:
                data = json.load(f)
                selected_map = data.get("map", selected_map)
                show_external_console = data.get("show_external_console", False)
                show_in_discord = data.get("show_in_discord", True)
        except: pass
        
    return {"enabled": True, "has_maps": has_maps, "available_maps": maps, "selected_map": selected_map, "show_external_console": show_external_console, "show_in_discord": show_in_discord}

@router.post("/server/startup/{plugin_id}")
def save_server_startup(plugin_id: str, payload: dict = Body(...)):
    """Speichert die gewünschte Karte und Konsoleneinstellung für den nächsten Start ab."""
    startup_file = os.path.join(DATA_ROOT, plugin_id, "startup.json")
    data = {}
    if os.path.exists(startup_file):
        try:
            with open(startup_file, "r") as f:
                data = json.load(f)
        except: pass
        
    if "selected_map" in payload:
        data["map"] = payload.get("selected_map")
    if "show_external_console" in payload:
        data["show_external_console"] = payload.get("show_external_console")
    if "show_in_discord" in payload:
        data["show_in_discord"] = payload.get("show_in_discord")
    if "custom_start_parameters" in payload:
        data["custom_start_parameters"] = payload.get("custom_start_parameters")
        
    with open(startup_file, "w") as f:
        json.dump(data, f)
    return {"status": "success"}