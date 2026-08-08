import os, threading, re, time
import psutil
from core.env import logger
from core.config_manager import ConfigManager
from core.steamcmd_manager import SteamCMDManager
from core.env import SERVERS_ROOT

INSTALL_TASKS = {}
steamcmd_lock = threading.Lock()
steam_manager = SteamCMDManager(base_dir=SERVERS_ROOT)

def _process_queue():
    while True:
        # Find next queued task
        next_task_id = None
        for t_id, task in INSTALL_TASKS.items():
            if task["status"] == "queued":
                next_task_id = t_id
                break
        
        if not next_task_id:
            break # Queue empty
            
        task = INSTALL_TASKS[next_task_id]
        if task["status"] == "cancelled":
            continue
            
        task["status"] = "running"
        task["message"] = "Starte Installation..."
        
        # We process this task while holding the lock implicitly by not moving to the next one
        try:
            _run_install(next_task_id, task["manifest"])
        except Exception as e:
            logger.exception(f"Install error for {next_task_id}: {e}")
            if task["status"] != "cancelled":
                task["status"] = "error"
                task["message"] = f"Unerwarteter Fehler: {e}"

def _run_install(plugin_id: str, manifest: dict):
    task = INSTALL_TASKS[plugin_id]
    try:
        app_id = manifest.get("steam_app_id")
        if not app_id:
            task["status"] = "error"
            task["message"] = "Kein steam_app_id im Manifest gefunden."
            return

        # 1. App Update (0-85%)
        task["phase"] = f"Lade App {app_id}..."
        process = steam_manager.stream_app_update(app_id, plugin_id, force_windows=(os.name != "nt" and "executable_windows" in manifest))
        if not process:
            task["status"] = "error"
            task["message"] = "Konnte SteamCMD nicht starten."
            return

        task["pid"] = process.pid
        for line in process.stdout:
            if task["status"] == "cancelled":
                process.kill()
                return
            
            line_clean = line.strip()
            # Parse progress: Update state (0x61) downloading, progress: 43.20 (4475471413 / 10359850616)
            m = re.search(r'progress:\s*([\d.]+)', line_clean, re.IGNORECASE)
            if m:
                percent = float(m.group(1))
                # Map 0-100 to 0-85
                task["progress"] = min(85.0, percent * 0.85)
                task["message"] = f"App-Update: {percent:.1f}%"
            elif "Success! App" in line_clean or "fully installed" in line_clean or "already up to date" in line_clean:
                task["progress"] = 85.0
                task["message"] = "App-Update abgeschlossen."
            elif "Error!" in line_clean or "ERROR" in line_clean:
                task["message"] = line_clean
        
        process.wait()
        if process.returncode not in [0, 7]:
            if task["status"] == "cancelled": return
            task["status"] = "error"
            task["message"] = f"SteamCMD Fehler (Code {process.returncode}): {task['message']}"
            return

        if task["status"] == "cancelled": return

        # 2. Workshop Mods (85-99%)
        mods_meta = manifest.get("mods_meta", {})
        if mods_meta and "steam_workshop_appid" in mods_meta:
            from core.env import DATA_ROOT
            import json
            mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
            if os.path.exists(mods_file):
                with open(mods_file, "r", encoding="utf-8") as f:
                    current_mods = json.load(f)
                if current_mods:
                    task["phase"] = f"Lade {len(current_mods)} Mods..."
                    task["message"] = "Prüfe Workshop Mods..."
                    process = steam_manager.stream_workshop_mods(plugin_id, mods_meta.get("steam_workshop_appid"), current_mods)
                    if process:
                        task["pid"] = process.pid
                        mod_count = len(current_mods)
                        mods_processed = 0
                        for line in process.stdout:
                            if task["status"] == "cancelled":
                                process.kill()
                                return
                            line_clean = line.strip()
                            if "Downloading item" in line_clean:
                                mods_processed += 1
                                current_p = min(mod_count, mods_processed)
                                task["progress"] = 85.0 + (14.0 * (current_p / mod_count))
                                task["message"] = f"Mod {current_p}/{mod_count} wird heruntergeladen..."
                            elif "Success" in line_clean:
                                pass
                            elif "ERROR" in line_clean:
                                task["message"] = line_clean
                                
                        process.wait()

        if task["status"] == "cancelled": return

        # 3. Finalize
        task["phase"] = "Abschluss..."
        task["message"] = "Modliste wird generiert..."
        from api.router import rebuild_modlist, game_update_cache
        rebuild_modlist(plugin_id, manifest)
        if plugin_id in game_update_cache: 
            game_update_cache[plugin_id]["available"] = False
            
        task["progress"] = 100
        task["status"] = "completed"
        task["message"] = "Installation/Update erfolgreich abgeschlossen!"

    except Exception as e:
        logger.exception(f"Install error for {plugin_id}: {e}")
        if task["status"] != "cancelled":
            task["status"] = "error"
            task["message"] = f"Unerwarteter Fehler: {e}"

def _start_queue_if_needed():
    # Prüfe ob bereits ein Thread läuft
    is_running = any(t["status"] == "running" for t in INSTALL_TASKS.values())
    if not is_running:
        t = threading.Thread(target=_process_queue)
        t.daemon = True
        t.start()

def start_update(plugin_id: str, manifest: dict, auto_start: bool = False) -> dict:
    task_id = plugin_id
    if task_id in INSTALL_TASKS and INSTALL_TASKS[task_id]["status"] in ["running", "queued"]:
        return {"status": "error", "message": "Installation/Update läuft oder wartet bereits."}

    # Finde heraus ob gerade schon jemand updatet
    is_running = any(t["status"] == "running" for t in INSTALL_TASKS.values())
    running_id = next((t_id for t_id, t in INSTALL_TASKS.items() if t["status"] == "running"), None)

    if is_running:
        initial_status = "queued"
        initial_msg = f"Warte auf laufendes Update von '{running_id}'..."
    else:
        initial_status = "queued" # Wird sofort vom Queue-Worker umgeschaltet
        initial_msg = "Wird in Kürze gestartet..."

    INSTALL_TASKS[task_id] = {
        "status": initial_status,
        "progress": 0,
        "message": initial_msg,
        "phase": "Warteschlange",
        "pid": None,
        "auto_start": auto_start,
        "manifest": manifest
    }

    _start_queue_if_needed()

    return {"status": "success", "message": "Installation zur Warteschlange hinzugefügt."}

def get_status(plugin_id: str) -> dict:
    if plugin_id not in INSTALL_TASKS:
        return {"status": "not_found", "message": "Keine aktive Installation."}
    return INSTALL_TASKS[plugin_id]

def cancel(plugin_id: str) -> dict:
    if plugin_id not in INSTALL_TASKS:
        return {"status": "error", "message": "Kein aktiver Task zum Abbrechen gefunden."}
    
    task = INSTALL_TASKS[plugin_id]
    if task["status"] not in ["running", "queued"]:
        return {"status": "error", "message": f"Task ist nicht aktiv (aktuell: {task['status']})."}

    was_running = task["status"] == "running"
    task["status"] = "cancelled"
    task["message"] = "Abgebrochen – nächster Install setzt fort/validiert neu."
    
    pid = task.get("pid")
    if pid and was_running:
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try: child.kill()
                except psutil.NoSuchProcess: pass
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            logger.warning(f"Fehler beim Killen des SteamCMD-Prozesses {pid}: {e}")
            
    if not was_running:
        _start_queue_if_needed() # Just in case it was the only one
            
    return {"status": "success", "message": "Installation abgebrochen."}
