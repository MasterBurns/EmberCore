import os, threading, re, time
import psutil
from core.env import logger, sys_config, SERVERS_ROOT
from core.config_manager import ConfigManager
from core.steamcmd_manager import SteamCMDManager

INSTALL_TASKS = {}
steamcmd_lock = threading.Lock()
steam_manager = SteamCMDManager(base_dir=SERVERS_ROOT)

def _cleanup_orphans():
    try:
        # Check if any task is running
        if any(t.get("status") == "running" for t in INSTALL_TASKS.values()):
            return
            
        now = time.time()
        for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                name = p.info['name'].lower()
                if "steamcmd" in name:
                    # check if older than 10 mins
                    if now - p.info['create_time'] > 600:
                        cmdline = p.info.get('cmdline', [])
                        if cmdline and any(SERVERS_ROOT in arg for arg in cmdline):
                            logger.warning(f"[SteamCMD] Killing orphaned process {p.info['pid']}")
                            p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        logger.error(f"Error during orphan cleanup: {e}")

def _kill_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try: child.kill()
            except psutil.NoSuchProcess: pass
        parent.kill()
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.warning(f"Error killing process tree {pid}: {e}")

def _process_queue():
    while True:
        next_task_id = None
        for t_id, task in INSTALL_TASKS.items():
            if task["status"] == "queued":
                next_task_id = t_id
                break
        
        if not next_task_id:
            break
            
        task = INSTALL_TASKS[next_task_id]
        if task.get("status") == "cancelled":
            continue
            
        running_id = next((t_id for t_id, t in INSTALL_TASKS.items() if t["status"] == "running"), None)
        if running_id:
            task["waiting_for"] = running_id

        _cleanup_orphans()
        
        steamcmd_lock.acquire()
        watchdog_timer = None
        
        try:
            if task["status"] == "cancelled":
                continue
                
            task["status"] = "running"
            task["waiting_for"] = None
            task["message"] = "Starte Installation..."
            task["last_output_at"] = time.time()
            task["last_line"] = ""
            
            inactivity_timeout = int(sys_config.get("mod_inactivity_timeout_s", 300))
            absolute_timeout = int(sys_config.get("mod_absolute_timeout_s", 3600))
            
            def watchdog_check():
                nonlocal watchdog_timer
                if task["status"] != "running":
                    return
                now = time.time()
                inactive = now - task.get("last_output_at", now)
                
                if inactive > inactivity_timeout or (now - task.get("start_time", now)) > absolute_timeout:
                    pid = task.get("pid")
                    if pid:
                        _kill_process_tree(pid)
                    task["status"] = "error"
                    task["message"] = "hängte bei Mod Download / Update (Timeout)"
                else:
                    watchdog_timer = threading.Timer(10, watchdog_check)
                    watchdog_timer.daemon = True
                    watchdog_timer.start()

            task["start_time"] = time.time()
            watchdog_timer = threading.Timer(10, watchdog_check)
            watchdog_timer.daemon = True
            watchdog_timer.start()
            
            _run_install(next_task_id, task["manifest"])
            
        except Exception as e:
            logger.exception(f"Install error for {next_task_id}: {e}")
            if task["status"] != "cancelled":
                task["message"] = f"Unerwarteter Fehler: {e}"
        finally:
            if watchdog_timer:
                watchdog_timer.cancel()
            steamcmd_lock.release()
            if task["status"] not in ["completed", "error", "cancelled"]:
                task["status"] = "error"
                if not task.get("message") or task["message"] == "Starte Installation...":
                    task["message"] = "Task wurde unerwartet beendet."
                    
def _run_install(plugin_id: str, manifest: dict):
    task = INSTALL_TASKS[plugin_id]
    app_id = manifest.get("steam_app_id")
    if not app_id:
        task["status"] = "error"
        task["message"] = "Kein steam_app_id im Manifest gefunden."
        return

    # 1. App Update
    task["phase"] = f"Lade App {app_id}..."
    process = steam_manager.stream_app_update(app_id, plugin_id, force_windows=(os.name != "nt" and "executable_windows" in manifest))
    if not process:
        task["status"] = "error"
        task["message"] = "Konnte SteamCMD nicht starten."
        return

    task["pid"] = process.pid
    for line in process.stdout:
        if task["status"] in ["cancelled", "error"]:
            process.kill()
            return
        
        task["last_output_at"] = time.time()
        line_clean = line.strip()
        task["last_line"] = line_clean
        
        m = re.search(r'progress:\s*([\d.]+)', line_clean, re.IGNORECASE)
        if m:
            percent = float(m.group(1))
            task["progress"] = min(85.0, percent * 0.85)
            task["message"] = f"App-Update: {percent:.1f}%"
        elif "Update state" in line_clean:
            if "validating" in line_clean.lower(): task["phase"] = "Validating..."
            elif "reconfiguring" in line_clean.lower(): task["phase"] = "Reconfiguring..."
            elif "stopping" in line_clean.lower(): task["phase"] = "Stopping..."
            elif "downloading" in line_clean.lower(): task["phase"] = "Downloading..."
            
        elif "Success! App" in line_clean or "fully installed" in line_clean or "already up to date" in line_clean:
            task["progress"] = 85.0
            task["message"] = "App-Update abgeschlossen."
        elif "Error!" in line_clean or "ERROR" in line_clean or "FAILURE" in line_clean:
            task["message"] = line_clean
    
    process.wait()
    if process.returncode not in [0, 7]:
        if task["status"] in ["cancelled", "error"]: return
        task["status"] = "error"
        task["message"] = f"SteamCMD Fehler (Code {process.returncode}): {task['message']}"
        return

    if task["status"] in ["cancelled", "error"]: return

    # 2. Workshop Mods
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
                        if task["status"] in ["cancelled", "error"]:
                            process.kill()
                            return
                            
                        task["last_output_at"] = time.time()
                        line_clean = line.strip()
                        task["last_line"] = line_clean
                        
                        if "Downloading item" in line_clean:
                            task["phase"] = "Mod-Download..."
                            mods_processed += 1
                            current_p = min(mod_count, mods_processed)
                            task["progress"] = 85.0 + (14.0 * (current_p / mod_count))
                            task["message"] = f"Mod {current_p}/{mod_count} wird heruntergeladen..."
                        elif "Success" in line_clean:
                            pass
                        elif "ERROR" in line_clean or "Error!" in line_clean or "FAILURE" in line_clean:
                            task["message"] = line_clean
                            
                    process.wait()

    if task["status"] in ["cancelled", "error"]: return

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

def _start_queue_if_needed():
    is_running = any(t["status"] == "running" for t in INSTALL_TASKS.values())
    if not is_running:
        t = threading.Thread(target=_process_queue)
        t.daemon = True
        t.start()

def start_update(plugin_id: str, manifest: dict, auto_start: bool = False) -> dict:
    task_id = plugin_id
    if task_id in INSTALL_TASKS and INSTALL_TASKS[task_id]["status"] in ["running", "queued"]:
        return {"status": "error", "message": "Installation/Update läuft oder wartet bereits."}

    is_running = any(t["status"] == "running" for t in INSTALL_TASKS.values())
    running_id = next((t_id for t_id, t in INSTALL_TASKS.items() if t["status"] == "running"), None)

    if is_running:
        initial_status = "queued"
        initial_msg = f"Warte auf laufendes Update von '{running_id}'..."
    else:
        initial_status = "queued"
        initial_msg = "Wird in Kürze gestartet..."

    INSTALL_TASKS[task_id] = {
        "status": initial_status,
        "progress": 0,
        "message": initial_msg,
        "phase": "Warteschlange",
        "pid": None,
        "auto_start": auto_start,
        "manifest": manifest,
        "last_output_at": time.time(),
        "last_line": "",
        "waiting_for": running_id
    }

    _start_queue_if_needed()
    return {"status": "success", "message": "Installation zur Warteschlange hinzugefügt."}

def get_status(plugin_id: str) -> dict:
    if plugin_id not in INSTALL_TASKS:
        return {"status": "not_found", "message": "Keine aktive Installation."}
        
    task = INSTALL_TASKS[plugin_id]
    if task["status"] == "running":
        inactive_time = time.time() - task.get("last_output_at", time.time())
        if inactive_time > 120:
            task["stalled"] = True
            if task.get("message", "") != "hängte bei Mod Download / Update (Timeout)":
                task["message"] = "SteamCMD hängt evtl. an einem Lock – Cancel möglich."
        else:
            task["stalled"] = False
            
    return task

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
        _kill_process_tree(pid)
            
    if not was_running:
        _start_queue_if_needed()
            
    return {"status": "success", "message": "Installation abgebrochen."}
