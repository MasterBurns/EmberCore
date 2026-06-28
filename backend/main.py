import sys, os, subprocess, platform

# ==========================================
# WATCHDOG (Fängt Windows-Fenster Schließungen ab)
# Wichtig: Muss ganz oben stehen!
# ==========================================
def get_launch_command(mode="normal"):
    from core.env import IS_COMPILED
    cmd = [sys.executable] if IS_COMPILED else [sys.executable, os.path.abspath(sys.argv[0])]
    if mode == "watchdog": cmd.append("--watchdog")
    elif mode == "service" or "--service" in sys.argv:
        if "--service" not in cmd: cmd.append("--service")
    return cmd

if "--watchdog" in sys.argv:
    import time, urllib.request, psutil
    from core.env import EXE_DIR
    try:
        port = int(sys.argv[sys.argv.index("--watchdog") + 1])
        parent_pid = int(sys.argv[sys.argv.index("--watchdog") + 2])
    except: sys.exit(1)
    time.sleep(15)
    fails = 0
    while True:
        if not psutil.pid_exists(parent_pid):
            time.sleep(30)
            if not psutil.pid_exists(parent_pid):
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                subprocess.Popen(get_launch_command(), cwd=EXE_DIR, creationflags=flags)
            sys.exit(0)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/system/health", timeout=5).read()
            fails = 0
        except Exception:
            fails += 1
            if fails >= 4:
                try: psutil.Process(parent_pid).kill()
                except: pass
                time.sleep(2)
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                subprocess.Popen(get_launch_command(), cwd=EXE_DIR, creationflags=flags)
                sys.exit(0)
        time.sleep(15)


# ==========================================
# FASTAPI BOOTLOADER
# ==========================================
import socket, threading, webbrowser, asyncio, psutil
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 1. Wir importieren unsere neuen sauberen Module
import core.env as env
from core.env import ACTIVE_PORT, EXE_DIR, BASE_DIR, logger, sys_config
from core.scheduler import BackupScheduler

# 2. Wir binden die aufgeteilten API-Routen und Manager ein
from api.router import router, backup_manager

class CompiledSafeScheduler(BackupScheduler):
    async def _check_and_run_backups(self):
        from core.env import PLUGINS_ROOT, DEV_PLUGINS_ROOT, DATA_ROOT, SERVERS_ROOT
        from core.config_manager import ConfigManager
        import json
        from datetime import datetime, timedelta

        plugin_ids = set()
        for folder in [PLUGINS_ROOT, DEV_PLUGINS_ROOT]:
            if os.path.exists(folder):
                for p_id in os.listdir(folder):
                    if os.path.isdir(os.path.join(folder, p_id)): plugin_ids.add(p_id)

        for plugin_id in plugin_ids:
            schedule_file = os.path.join(DATA_ROOT, plugin_id, "backup_schedule.json")
            if not os.path.exists(schedule_file): continue
            with open(schedule_file, "r", encoding="utf-8") as f: config = json.load(f)

            schedules = config.get("schedules", [])
            retention = config.get("retention", {})
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            backup_needed = False
            schedules_updated = False

            for sched in schedules:
                stype = sched.get("type")
                val = sched.get("value")
                if stype == "interval":
                    try:
                        hours = int(val)
                        last_run_str = sched.get("last_run", "")
                        if not last_run_str:
                            backup_needed = True
                            sched["last_run"] = now.isoformat()
                            schedules_updated = True
                        else:
                            last_run = datetime.fromisoformat(last_run_str)
                            if now >= last_run + timedelta(hours=hours):
                                backup_needed = True
                                sched["last_run"] = now.isoformat()
                                schedules_updated = True
                    except: pass
                elif stype == "daily":
                    try:
                        th, tm = map(int, val.split(":"))
                        last_run_date = sched.get("last_run_date", "")
                        if last_run_date != today_str:
                            if now.hour > th or (now.hour == th and now.minute >= tm):
                                backup_needed = True
                                sched["last_run_date"] = today_str
                                schedules_updated = True
                    except: pass

            if backup_needed:
                manifest = ConfigManager.load_manifest(plugin_id)
                if manifest and manifest.get("backup"):
                    logger.info(f"Führe geplantes Backup für {plugin_id} aus...")
                    self.backup_manager.create_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), manifest.get("backup").get("source_path"), retention)

            if schedules_updated:
                os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
                with open(schedule_file, "w", encoding="utf-8") as f: json.dump(config, f, indent=2)

scheduler = CompiledSafeScheduler(base_dir=EXE_DIR, backup_manager=backup_manager)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background Tasks starten
    from core.update_manager import update_manager
    if hasattr(update_manager, 'prepare_steamcmd'):
        await update_manager.prepare_steamcmd()

    asyncio.create_task(scheduler.start_loop())

    from api.router import force_check_game_updates
    from core.config_manager import ConfigManager
    async def game_update_checker_loop():
        await asyncio.sleep(10)
        while True:
            try:
                dirs = [(env.DEV_PLUGINS_ROOT, True), (env.PLUGINS_ROOT, False)]
                seen = set()
                for t_dir, _ in dirs:
                    if not os.path.exists(t_dir): continue
                    for p_id in os.listdir(t_dir):
                        if p_id not in seen and os.path.exists(os.path.join(t_dir, p_id, "manifest.yaml")):
                            await force_check_game_updates(p_id)
                            seen.add(p_id)
            except: pass
            await asyncio.sleep(3600)

    asyncio.create_task(game_update_checker_loop())

    # Watchdog Spawner (abgekoppelt)
    def watchdog_spawner():
        if "--service" in sys.argv: return
        wd_running = any("--watchdog" in p.info.get('cmdline', []) for p in psutil.process_iter(['cmdline']) if p.info.get('cmdline'))
        if not wd_running:
            cmd = get_launch_command(mode="watchdog")
            cmd.extend([str(ACTIVE_PORT), str(os.getpid())])
            flags = 0x00000008 | 0x00000200 if platform.system() == "Windows" else 0
            subprocess.Popen(cmd, cwd=EXE_DIR, creationflags=flags, start_new_session=True if platform.system() != "Windows" else False)

    watchdog_spawner()

    # Browser öffnen
    def open_browser():
        flag_path = os.path.join(EXE_DIR, ".update_reboot")
        if os.path.exists(flag_path):
            try: os.remove(flag_path)
            except: pass
        elif "--service" not in sys.argv:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{ACTIVE_PORT}")

    threading.Timer(1.5, open_browser).start()
    yield

# 3. FastAPI initialisieren
from core.env import get_current_system_version
app = FastAPI(title="EmberCore", version=get_current_system_version()["version"], lifespan=lifespan)

# 4. API-Routen mounten
app.include_router(router)

# 5. Das modulare Vue.js Frontend bereitstellen
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")

def clean_orphaned_watchdogs():
    """Killt alle alten Watchdogs vor dem Start, um Boot-Loops zu verhindern."""
    import psutil
    current_pid = os.getpid()
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = p.info.get('cmdline') or []
            if "--watchdog" in cmdline and p.info['pid'] != current_pid:
                logger.info(f"[*] Bereinige verwaisten Geister-Watchdog (PID {p.info['pid']})...")
                p.kill()
        except: pass

def main():
    global ACTIVE_PORT

    # NEU: Erst aufräumen, dann Port binden!
    if "--watchdog" not in sys.argv and "--service" not in sys.argv:
        clean_orphaned_watchdogs()

    port = 8000
    while socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(('127.0.0.1', port)) == 0: port += 10
    ACTIVE_PORT = port
    env.ACTIVE_PORT = port

    log_config = uvicorn.config.LOGGING_CONFIG
    if not sys_config.get("verbose_logging"):
        log_config["loggers"]["uvicorn.access"]["level"] = "WARNING"

    logger.info(f"[*] EmberCore startet Webserver auf Port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=log_config)

if __name__ == "__main__": main()
