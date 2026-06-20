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
import tarfile
import httpx
import re
import webbrowser
import threading
import time
import psutil
import urllib.request
from datetime import datetime, date, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

# --- CRITICAL PYINSTALLER PATH RESOLUTION ---
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
    IS_COMPILED = True
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
    IS_COMPILED = False

SERVERS_ROOT = os.path.join(EXE_DIR, "servers")
BACKUPS_ROOT = os.path.join(EXE_DIR, "backups")
DATA_ROOT = os.path.join(EXE_DIR, "data")
PLUGINS_ROOT = os.path.join(EXE_DIR, "plugins")
DEV_PLUGINS_ROOT = os.path.join(BASE_DIR, "dev_plugins") if not IS_COMPILED else os.path.join(EXE_DIR, "dev_plugins")

ACTIVE_PORT = 8000
START_TIME = datetime.now()

# --- DAU-SCHUTZ (RECHTE-PRÜFUNG) ---
def check_write_permissions():
    try:
        test_file = os.path.join(EXE_DIR, ".write_test")
        with open(test_file, "w") as f: f.write("test")
        os.remove(test_file)
    except PermissionError:
        print("\n" + "!"*65)
        print(" [SCHWERER FEHLER] FEHLENDE SCHREIBRECHTE!")
        print("!"*65)
        print(" EmberCore darf in diesem Ordner keine Dateien speichern.")
        print(f" Aktueller Pfad: {EXE_DIR}")
        print("\n LOESUNG:")
        print(" Verschiebe den EmberCore-Ordner aus 'Programme' / 'Program Files'")
        print(" heraus an einen freigegebenen Ort, z.B. nach:")
        print(" -> C:\\EmberCore\\  oder  D:\\Games\\EmberCore\\")
        print("\n (Bitte starte das Tool aus Sicherheitsgruenden NICHT als Admin!)")
        print("!"*65 + "\n")
        if platform.system() == "Windows": os.system("pause")
        sys.exit(1)

check_write_permissions()

def get_launch_command(mode="normal"):
    cmd = [sys.executable] if IS_COMPILED else [sys.executable, os.path.abspath(sys.argv[0])]
    if mode == "watchdog": cmd.append("--watchdog")
    elif mode == "service" or "--service" in sys.argv:
        if "--service" not in cmd: cmd.append("--service")
    return cmd

# --- WATCHDOG INTERCEPT ---
if "--watchdog" in sys.argv:
    try:
        port = int(sys.argv[sys.argv.index("--watchdog") + 1])
        parent_pid = int(sys.argv[sys.argv.index("--watchdog") + 2])
    except: sys.exit(1)

    print(f"[Watchdog] 🛡️ Gestartet. Überwache PID {parent_pid} auf Port {port}...")
    time.sleep(15)
    fails = 0

    while True:
        if not psutil.pid_exists(parent_pid):
            print("[Watchdog] ⚠️ Hauptprozess beendet. Warte 30s Grace Period...")
            time.sleep(30)
            if not psutil.pid_exists(parent_pid):
                print("[Watchdog] Starte Hauptprozess neu...")
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                subprocess.Popen(get_launch_command(), cwd=EXE_DIR, creationflags=flags)
            sys.exit(0)

        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/system/health", timeout=5).read()
            fails = 0
        except Exception:
            fails += 1
            print(f"[Watchdog] ⏳ Keine Antwort vom Hauptprozess ({fails}/4)")
            if fails >= 4:
                print("[Watchdog] 🚨 Hauptprozess HÄNGT! Führe Kill & Restart durch...")
                try: psutil.Process(parent_pid).kill()
                except: pass
                time.sleep(2)
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                subprocess.Popen(get_launch_command(), cwd=EXE_DIR, creationflags=flags)
                sys.exit(0)
        time.sleep(15)

from core.server_manager import ServerManager
from core.steamcmd_manager import SteamCMDManager
from core.backup_manager import BackupManager
from core.config_manager import ConfigManager
from core.scheduler import BackupScheduler

def get_current_system_version():
    v_path = os.path.join(BASE_DIR, "version.json") if IS_COMPILED else os.path.join(EXE_DIR, "version.json")
    if os.path.exists(v_path):
        try:
            with open(v_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    latest = data[0].copy()
                    latest["history"] = data
                    return latest
                elif isinstance(data, dict):
                    data["history"] = [data]
                    return data
        except Exception as e:
            print(f"[-] version.json Parser-Fehler: {e}")
    return {"version": "dev-build", "build_date": "unknown", "changelog": ["Lokale Entwicklungsversion."], "history": []}

system_info = get_current_system_version()
manager = ServerManager()
steam_manager = SteamCMDManager(base_dir=SERVERS_ROOT)
backup_manager = BackupManager(base_dir=EXE_DIR)
config_manager = ConfigManager()

def parse_live_config_file(file_path: str) -> dict:
    values = {}
    if not os.path.exists(file_path): return values
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                match = re.match(r'^\s*([^=;#]+)\s*=\s*(.*)$', line)
                if match:
                    key = match.group(1).strip()
                    val = match.group(2).strip()
                    if val.startswith('"') and val.endswith('"'): val = val[1:-1]
                    if val.startswith("'") and val.endswith("'"): val = val[1:-1]
                    values[key] = val
    except: pass
    return values

def guess_type_and_normalize(val_str: str):
    val_clean = str(val_str).strip()
    if val_clean.lower() in ["true", "false"]: return "boolean", val_clean.lower() == "true"
    try:
        if "." in val_clean: return "number", float(val_clean)
        return "number", int(val_clean)
    except ValueError: return "text", val_str

def apply_desired_config_to_live(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest: return
    meta = manifest.get("config_meta")
    if not meta: return
    desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
    if not os.path.exists(desired_path): return

    with open(desired_path, "r", encoding="utf-8") as f: desired_values = json.load(f)
    live_path = os.path.join(SERVERS_ROOT, plugin_id, meta.get("file_path"))

    if not os.path.exists(live_path):
        os.makedirs(os.path.dirname(live_path), exist_ok=True)
        lines = []
    else:
        with open(live_path, "r", encoding="utf-8", errors="ignore") as f: lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        match = re.match(r'^\s*([^=;#]+)\s*=\s*(.*)$', line)
        if match:
            key = match.group(1).strip()
            if key in desired_values:
                val = desired_values[key]
                if isinstance(val, bool): val = "True" if val else "False"
                new_lines.append(f"{key}={val}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, val in desired_values.items():
        if key not in updated_keys:
            if isinstance(val, bool): val = "True" if val else "False"
            new_lines.append(f"{key}={val}\n")

    with open(live_path, "w", encoding="utf-8") as f: f.writelines(new_lines)

class CompiledSafeScheduler(BackupScheduler):
    async def _check_and_run_backups(self):
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
                manifest = load_manifest(plugin_id)
                if manifest:
                    backup_config = manifest.get("backup")
                    if backup_config:
                        self.backup_manager.create_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), backup_config.get("source_path"), retention)
            if schedules_updated:
                os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
                with open(schedule_file, "w", encoding="utf-8") as f: json.dump(config, f, indent=2)

scheduler = CompiledSafeScheduler(base_dir=EXE_DIR, backup_manager=backup_manager)
game_update_cache = {}

async def fetch_game_update_status(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest or manifest.get("engine") != "steamcmd": return None
    app_id = manifest.get("steam_app_id")
    if not app_id: return None

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
                        status = {"available": str(local_id) != str(remote_id), "local": str(local_id), "remote": str(remote_id)}
                        game_update_cache[plugin_id] = status
                        return status
        except: pass
    return None

async def game_update_checker_loop():
    await asyncio.sleep(10)
    while True:
        try:
            installed = get_installed_plugins()
            for plugin in installed: await fetch_game_update_status(plugin["id"])
        except: pass
        await asyncio.sleep(3600)

async def prepare_steamcmd():
    steam_dir = os.path.join(SERVERS_ROOT, "steamcmd")
    os.makedirs(steam_dir, exist_ok=True)
    is_windows = platform.system() == "Windows"
    exe_path = os.path.join(steam_dir, "steamcmd.exe" if is_windows else "steamcmd.sh")
    if not os.path.exists(exe_path):
        url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip" if is_windows else "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, follow_redirects=True, timeout=60.0)
                if res.status_code == 200:
                    if is_windows:
                        with zipfile.ZipFile(io.BytesIO(res.content)) as z: z.extractall(steam_dir)
                    else:
                        with tarfile.open(fileobj=io.BytesIO(res.content), mode="r:gz") as tar: tar.extractall(steam_dir)
        except: pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    await prepare_steamcmd()
    asyncio.create_task(scheduler.start_loop())
    asyncio.create_task(game_update_checker_loop())

    def watchdog_spawner():
        wd_running = any("--watchdog" in p.info.get('cmdline', []) for p in psutil.process_iter(['cmdline']) if p.info.get('cmdline'))
        if not wd_running:
            cmd = get_launch_command(mode="watchdog")
            cmd.extend([str(ACTIVE_PORT), str(os.getpid())])
            flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            subprocess.Popen(cmd, cwd=EXE_DIR, creationflags=flags)

    watchdog_spawner()

    def open_browser():
        flag_path = os.path.join(EXE_DIR, ".update_reboot")
        if os.path.exists(flag_path):
            try: os.remove(flag_path)
            except: pass
        elif "--service" not in sys.argv:
            webbrowser.open(f"http://127.0.0.1:{ACTIVE_PORT}")

    threading.Timer(1.5, open_browser).start()
    yield

app = FastAPI(title="EmberCore", version=system_info["version"], lifespan=lifespan)

class InstallRequest(BaseModel): install_dir_name: Optional[str] = None
disk_cache = {}

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

    total_disk, used_disk, free_disk = shutil.disk_usage(EXE_DIR)
    result = {"server_mb": get_dir_size_mb(server_dir), "backup_mb": get_dir_size_mb(backup_dir), "total_plugin_mb": total_mb, "trend_mb_per_day": trend_mb_per_day, "host_free_gb": round(free_disk / (1024**3), 2)}
    disk_cache[plugin_id] = (result, now)
    return result

def get_plugin_paths(plugin_id: str):
    dev_path = os.path.join(DEV_PLUGINS_ROOT, plugin_id, "manifest.yaml")
    live_path = os.path.join(PLUGINS_ROOT, plugin_id, "manifest.yaml")
    if os.path.exists(dev_path): return dev_path, os.path.join(DEV_PLUGINS_ROOT, plugin_id), True
    return live_path, os.path.join(PLUGINS_ROOT, plugin_id), False

def load_manifest(plugin_id: str):
    manifest_path, _, _ = get_plugin_paths(plugin_id)
    if not os.path.exists(manifest_path): return None
    with open(manifest_path, "r", encoding="utf-8") as f: return yaml.safe_load(f)


# --- OS SERVICE & SYSTEM ROUTEN (REPARIERT: PowerShell statt cmd.exe) ---

@app.get("/api/system/health")
def system_health():
    return {"status": "ok"}

@app.get("/api/system/service/status")
def system_service_status():
    is_linux = platform.system() == "Linux"
    installed = False
    running = False

    if is_linux:
        installed = os.path.exists("/etc/systemd/system/embercore.service")
        if installed:
            try:
                res = subprocess.run(["systemctl", "is-active", "embercore"], capture_output=True, text=True)
                running = "active" in res.stdout
            except: pass
    else:
        try:
            out = subprocess.check_output(["powershell", "-Command", "(Get-ScheduledTask -TaskName 'EmberCoreDaemon' -ErrorAction SilentlyContinue) -ne $null"], text=True, stderr=subprocess.DEVNULL)
            installed = "True" in out
            if installed:
                running = any("--service" in p.info.get('cmdline', []) for p in psutil.process_iter(['cmdline']) if p.info.get('cmdline'))
        except: pass

    wd_active = any("--watchdog" in p.info.get('cmdline', []) for p in psutil.process_iter(['cmdline']) if p.info.get('cmdline'))
    proc = psutil.Process(os.getpid())

    return {
        "os": platform.system(),
        "is_installed": installed,
        "is_running": running,
        "main_pid": os.getpid(),
        "watchdog_active": wd_active,
        "uptime_seconds": (datetime.now() - START_TIME).total_seconds(),
        "ram_mb": round(proc.memory_info().rss / (1024*1024), 2),
        "cpu_percent": psutil.cpu_percent()
    }

@app.post("/api/system/service/install")
def install_system_service():
    is_linux = platform.system() == "Linux"
    exe_path = os.path.abspath(sys.executable if IS_COMPILED else sys.argv[0])

    try:
        if is_linux:
            import pwd
            current_user = pwd.getpwuid(os.getuid()).pw_name
            cmd_args = f"{exe_path} --service" if IS_COMPILED else f"{sys.executable} {exe_path} --service"
            service_content = f"""[Unit]\nDescription=EmberCore Game Server Panel\nAfter=network.target\n\n[Service]\nType=simple\nUser={current_user}\nWorkingDirectory={EXE_DIR}\nExecStart={cmd_args}\nRestart=always\nRestartSec=15\n\n[Install]\nWantedBy=multi-user.target\n"""

            if os.geteuid() != 0:
                script_path = os.path.join(EXE_DIR, "install_service.sh")
                with open(script_path, "w") as f:
                    f.write("#!/bin/bash\n")
                    f.write("cat << 'EOF' > /etc/systemd/system/embercore.service\n")
                    f.write(service_content)
                    f.write("EOF\n")
                    f.write("systemctl daemon-reload\n")
                    f.write("systemctl enable embercore.service\n")
                    f.write("systemctl start embercore.service\n")
                    f.write("echo 'EmberCore Service erfolgreich installiert und gestartet!'\n")
                os.chmod(script_path, 0o755)
                return {"status": "info", "message": "Fehlende Root-Rechte! Es wurde eine Datei 'install_service.sh' im Ordner erstellt. Bitte beende EmberCore und führe 'sudo bash ./install_service.sh' aus."}

            with open("/etc/systemd/system/embercore.service", "w") as f: f.write(service_content)
            subprocess.run(["systemctl", "daemon-reload"])
            subprocess.run(["systemctl", "enable", "embercore.service"])
            return {"status": "success", "message": "EmberCore wurde als systemd-Service installiert!"}
        else:
            import ctypes
            ps_script = os.path.join(EXE_DIR, "install_service.ps1")
            executable = exe_path if IS_COMPILED else sys.executable
            arguments = "--service" if IS_COMPILED else f"'{exe_path}' --service"

            with open(ps_script, "w", encoding="utf-8") as f:
                f.write(f"$action = New-ScheduledTaskAction -Execute '{executable}' -Argument \"{arguments}\"\n")
                f.write("$trigger = New-ScheduledTaskTrigger -AtStartup\n")
                f.write("$principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\\SYSTEM' -LogonType ServiceAccount -RunLevel Highest\n")
                f.write("Register-ScheduledTask -TaskName 'EmberCoreDaemon' -Action $action -Trigger $trigger -Principal $principal -Force\n")
                f.write("Start-ScheduledTask -TaskName 'EmberCoreDaemon'\n")

            if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
                subprocess.run(["powershell", "-Command", ps_cmd])
                return {"status": "info", "message": "Bitte bestätige jetzt das kleine Windows Administrator-Schild in der Taskleiste.\nEmberCore installiert sich dann selbst als Dienst und startet sofort!"}
            else:
                subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script], check=True, stdout=subprocess.DEVNULL)
                return {"status": "success", "message": "EmberCore wurde erfolgreich als Windows Service installiert!"}
    except Exception as e:
        return {"status": "error", "message": f"Konnte Service nicht erstellen: {e}"}

@app.post("/api/system/service/uninstall")
def uninstall_system_service():
    if platform.system() == "Linux":
        if os.geteuid() != 0:
            script_path = os.path.join(EXE_DIR, "uninstall_service.sh")
            with open(script_path, "w") as f:
                f.write("#!/bin/bash\nsystemctl stop embercore.service\nsystemctl disable embercore.service\nrm -f /etc/systemd/system/embercore.service\nsystemctl daemon-reload\necho 'Service erfolgreich entfernt!'\n")
            os.chmod(script_path, 0o755)
            return {"status": "info", "message": "Fehlende Root-Rechte! Es wurde eine Datei 'uninstall_service.sh' erstellt. Bitte mit 'sudo bash ./uninstall_service.sh' ausführen."}
        try:
            subprocess.run(["systemctl", "stop", "embercore.service"])
            subprocess.run(["systemctl", "disable", "embercore.service"])
            if os.path.exists("/etc/systemd/system/embercore.service"): os.remove("/etc/systemd/system/embercore.service")
            subprocess.run(["systemctl", "daemon-reload"])
            return {"status": "success", "message": "Service erfolgreich entfernt."}
        except Exception as e: return {"status": "error", "message": str(e)}
    else:
        import ctypes
        ps_script = os.path.join(EXE_DIR, "uninstall_service.ps1")
        with open(ps_script, "w", encoding="utf-8") as f:
            f.write("Stop-ScheduledTask -TaskName 'EmberCoreDaemon' -ErrorAction SilentlyContinue\n")
            f.write("Unregister-ScheduledTask -TaskName 'EmberCoreDaemon' -Confirm:$false -ErrorAction SilentlyContinue\n")
            f.write(f"Get-WmiObject Win32_Process | Where-Object {{ $_.CommandLine -match '--service' -and $_.Name -eq '{os.path.basename(sys.executable)}' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\n")

        if ctypes.windll.shell32.IsUserAnAdmin() == 0:
            ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
            subprocess.run(["powershell", "-Command", ps_cmd])
            return {"status": "info", "message": "Bitte bestätige jetzt die Administrator-Freigabe, um den Service restlos vom PC zu entfernen und zu stoppen."}
        else:
            try:
                subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script], check=True, stdout=subprocess.DEVNULL)
                return {"status": "success", "message": "Windows Service erfolgreich entfernt."}
            except Exception as e: return {"status": "error", "message": "Konnte Dienst nicht löschen."}

@app.post("/api/system/service/start")
def start_system_service():
    try:
        if platform.system() == "Linux":
            if os.geteuid() != 0:
                return {"status": "info", "message": "Bitte nutze 'sudo systemctl start embercore.service' in der Konsole, um den Dienst zu starten."}
            subprocess.run(["systemctl", "start", "embercore.service"])
        else:
            import ctypes
            ps_script = os.path.join(EXE_DIR, "start_service.ps1")
            with open(ps_script, "w", encoding="utf-8") as f:
                f.write("Start-ScheduledTask -TaskName 'EmberCoreDaemon'\n")

            if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
                subprocess.run(["powershell", "-Command", ps_cmd])
            else:
                subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script])
        return {"status": "success", "message": "Service-Start wurde im Hintergrund angefordert."}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.post("/api/system/service/stop")
def stop_system_service():
    try:
        if platform.system() == "Linux":
            if os.geteuid() != 0:
                return {"status": "info", "message": "Bitte nutze 'sudo systemctl stop embercore.service' in der Konsole, um den Dienst zu stoppen."}
            subprocess.run(["systemctl", "stop", "embercore.service"])
        else:
            import ctypes
            ps_script = os.path.join(EXE_DIR, "stop_service.ps1")
            with open(ps_script, "w", encoding="utf-8") as f:
                f.write("Stop-ScheduledTask -TaskName 'EmberCoreDaemon' -ErrorAction SilentlyContinue\n")
                f.write(f"Get-WmiObject Win32_Process | Where-Object {{ $_.CommandLine -match '--service' -and $_.Name -eq '{os.path.basename(sys.executable)}' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\n")

            if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
                subprocess.run(["powershell", "-Command", ps_cmd])
            else:
                subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script])
        return {"status": "success", "message": "Service-Stopp wurde angefordert."}
    except Exception as e: return {"status": "error", "message": str(e)}


@app.get("/api/system/version")
def get_system_version():
    return get_current_system_version()

@app.get("/api/system/check-update")
async def check_system_update():
    if not IS_COMPILED:
        try:
            subprocess.run(["git", "fetch"], cwd=EXE_DIR, check=True)
            status = subprocess.run(["git", "status", "-uno"], cwd=EXE_DIR, capture_output=True, text=True)
            return {"update_available": "Your branch is behind" in status.stdout}
        except: return {"update_available": False}
    else:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get("https://raw.githubusercontent.com/MasterBurns/EmberCore/main/version.json", timeout=5.0)
                if res.status_code == 200:
                    remote_data = res.json()
                    remote_version = remote_data[0].get("version", "") if isinstance(remote_data, list) else remote_data.get("version", "")
                    local_version = get_current_system_version()["version"]
                    return {"update_available": remote_version != local_version}
        except: pass
        return {"update_available": False}

@app.post("/api/system/update")
async def update_embercore():
    flag_path = os.path.join(EXE_DIR, ".update_reboot")
    if not IS_COMPILED:
        try:
            subprocess.run(["git", "fetch"], cwd=EXE_DIR, check=True)
            pull_result = subprocess.run(["git", "pull"], cwd=EXE_DIR, capture_output=True, text=True)
            if "Already up to date." in pull_result.stdout: return {"status": "info", "message": "Bereits aktuell."}
            with open(flag_path, "w") as f: f.write("1")
            async def restart():
                await asyncio.sleep(1.0)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            asyncio.create_task(restart())
            return {"status": "success", "message": "Neustart läuft..."}
        except Exception as e: return {"status": "error", "message": str(e)}
    else:
        is_linux = platform.system() == "Linux"
        ext = "tar.gz" if is_linux else "zip"
        os_prefix = "EmberCore_Linux" if is_linux else "EmberCore_Windows"
        exe_url = None

        try:
            async with httpx.AsyncClient() as client:
                api_res = await client.get("https://api.github.com/repos/MasterBurns/EmberCore/releases/latest", timeout=10.0)
                if api_res.status_code == 200:
                    for asset in api_res.json().get("assets", []):
                        name = asset.get("name", "")
                        if name.startswith(os_prefix) and name.endswith(ext) and "Setup" not in name:
                            exe_url = asset.get("browser_download_url")
                            break
        except Exception as e:
            return {"status": "error", "message": f"Fehler bei GitHub API Abfrage: {str(e)}"}

        if not exe_url:
            return {"status": "error", "message": f"Kein passendes Update-Paket ({os_prefix}...{ext}) im neuesten Release gefunden!"}

        archive_path = os.path.join(EXE_DIR, f"EmberCore_update.{ext}")
        current_exe_path = sys.executable

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(exe_url, timeout=60.0, follow_redirects=True)
                if response.status_code == 200:
                    with open(archive_path, "wb") as f: f.write(response.content)
                else:
                    return {"status": "error", "message": f"Download gescheitert (HTTP {response.status_code})!\nURL: {exe_url}"}

            with open(flag_path, "w") as f: f.write("1")

            if is_linux:
                script_path = os.path.join(EXE_DIR, "update_worker.sh")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write("#!/bin/bash\n")
                    f.write("sleep 2\n")
                    f.write(f"tar -xzf '{archive_path}' -C '{EXE_DIR}'\n")
                    f.write(f"rm -f '{archive_path}'\n")
                    if "--service" in sys.argv:
                        f.write("systemctl restart embercore.service\n")
                    else:
                        f.write(f"nohup '{current_exe_path}' {' '.join(sys.argv[1:])} > /dev/null 2>&1 &\n")
                    f.write(f"rm -f '{script_path}'\n")
                os.chmod(script_path, 0o755)
                subprocess.Popen(["bash", script_path], cwd=EXE_DIR, start_new_session=True)
            else:
                batch_path = os.path.join(EXE_DIR, "update_worker.bat")
                with open(batch_path, "w", encoding="ascii") as f:
                    f.write("@echo off\n")
                    f.write("timeout /t 2 /nobreak > nul\n")
                    f.write(f"taskkill /F /IM \"{os.path.basename(current_exe_path)}\" /T > nul 2>&1\n")
                    f.write("timeout /t 2 /nobreak > nul\n")
                    f.write(f"powershell -command \"Expand-Archive -Force '{archive_path}' '{EXE_DIR}'\"\n")
                    f.write(f"del /f /q \"{archive_path}\"\n")
                    if "--service" in sys.argv:
                        f.write("schtasks /Run /TN \"EmberCoreDaemon\"\n")
                    else:
                        f.write(f"start \"\" \"{current_exe_path}\" {' '.join(sys.argv[1:])}\n")
                    f.write("del \"%~f0\"\n")
                subprocess.Popen([batch_path], cwd=EXE_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0)

            async def kill_switch():
                await asyncio.sleep(1.0)
                os._exit(0)
            asyncio.create_task(kill_switch())
            return {"status": "success", "message": "Update erfolgreich heruntergeladen. Führe Neustart aus..."}
        except Exception as e:
            return {"status": "error", "message": f"Update Prozess gecrasht: {str(e)}"}

@app.get("/api/plugins/installed")
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
                    with open(manifest_path, "r", encoding="utf-8") as f: data = yaml.safe_load(f)
                    game_name = data.get("name", plugin_id)
                    server_name = plugin_id
                    meta = data.get("config_meta")
                    if meta:
                        desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
                        live_values = {}
                        if os.path.exists(desired_path):
                            with open(desired_path, "r", encoding="utf-8") as df: live_values = json.load(df)
                        else:
                            file_path = os.path.join(SERVERS_ROOT, plugin_id, meta.get("file_path"))
                            live_values = parse_live_config_file(file_path)

                        fields = meta.get("fields", [])
                        hostname_key = next((f["key"] for f in fields if "hostname" in f["key"].lower() or "name" in f["key"].lower()), None)
                        if hostname_key and live_values.get(hostname_key):
                            server_name = live_values.get(hostname_key)
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
    if os.path.exists(os.path.join(PLUGINS_ROOT, instance_id)): return {"status": "error", "message": "Server-ID existiert bereits!"}
    instance_dir = os.path.join(PLUGINS_ROOT, instance_id)
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
                    desired_dir = os.path.join(DATA_ROOT, instance_id)
                    os.makedirs(desired_dir, exist_ok=True)
                    with open(os.path.join(desired_dir, "desired_config.json"), "w", encoding="utf-8") as df:
                        json.dump({hostname_key: server_name}, df, indent=2)
        return {"status": "success", "message": f"Server '{server_name}' erstellt.", "instance_id": instance_id}
    except Exception as e:
        if os.path.exists(instance_dir): shutil.rmtree(instance_dir)
        return {"status": "error", "message": str(e)}

@app.post("/api/server/install/{plugin_id}")
def install_server(plugin_id: str, req: InstallRequest = None):
    manifest = load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest nicht gefunden")
    res = steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
    if plugin_id in game_update_cache:
        game_update_cache[plugin_id]["available"] = False
        game_update_cache[plugin_id]["local"] = game_update_cache[plugin_id].get("remote", "0")
    return res

@app.post("/api/server/check-updates/{plugin_id}")
async def force_check_game_updates(plugin_id: str):
    status = await fetch_game_update_status(plugin_id)
    if status:
        if status["available"]: return {"status": "success", "message": f"Steam Update verfügbar! ({status['local']} -> {status['remote']})"}
        else: return {"status": "info", "message": f"Bereits aktuell. (Build: {status['local']})"}
    return {"status": "error", "message": "Konnte Daten nicht prüfen. Ist der Server bereits installiert?"}

@app.post("/api/server/start/{plugin_id}")
def start(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest nicht gefunden")

    meta = manifest.get("config_meta")
    auto_update = False
    desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
    if os.path.exists(desired_path):
        with open(desired_path, "r", encoding="utf-8") as df:
            d_vals = json.load(df)
            auto_update = d_vals.get("AutoUpdateOnStart")

    if auto_update is True or str(auto_update).lower() == "true" or auto_update == 1:
        steam_manager.install_or_update_app(manifest.get("steam_app_id"), plugin_id, force_windows=platform.system() == "Linux" and "executable_windows" in manifest)
        if plugin_id in game_update_cache: game_update_cache[plugin_id]["available"] = False

    apply_desired_config_to_live(plugin_id)

    executable_path = os.path.join(SERVERS_ROOT, plugin_id, manifest.get("executable_windows"))
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

@app.get("/api/server/mods/{plugin_id}")
def get_server_mods(plugin_id: str):
    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
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
    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
    os.makedirs(os.path.dirname(mods_file), exist_ok=True)
    current_mods = []
    if os.path.exists(mods_file):
        with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
    if any(m["id"] == mod_id for m in current_mods): return {"status": "error", "message": "Mod existiert bereits!"}
    current_mods.append({"id": mod_id, "name": mod_name, "version": mod_version})
    with open(mods_file, "w", encoding="utf-8") as f: json.dump(current_mods, f, indent=2)
    meta = manifest["mods_meta"]
    real_modlist_path = os.path.join(SERVERS_ROOT, plugin_id, meta["file_path"])
    os.makedirs(os.path.dirname(real_modlist_path), exist_ok=True)
    mod_line = f"*{SERVERS_ROOT}/{plugin_id}/steamapps/workshop/content/{meta['steam_workshop_appid']}/{mod_id}/{mod_id}.pak\n"
    with open(real_modlist_path, "a", encoding="utf-8") as f: f.write(mod_line)
    return {"status": "success", "message": f"Mod '{mod_name}' hinzugefügt."}

@app.delete("/api/server/mods/delete/{plugin_id}/{mod_id}")
def delete_server_mod(plugin_id: str, mod_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest or "mods_meta" not in manifest: return {"status": "error", "message": "Manifest fehlt oder kein Modding unterstützt"}
    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
    if not os.path.exists(mods_file): return {"status": "success"}
    with open(mods_file, "r", encoding="utf-8") as f: current_mods = json.load(f)
    current_mods = [m for m in current_mods if m["id"] != mod_id]
    with open(mods_file, "w", encoding="utf-8") as f: json.dump(current_mods, f, indent=2)
    meta = manifest["mods_meta"]
    real_modlist_path = os.path.join(SERVERS_ROOT, plugin_id, meta["file_path"])
    if os.path.exists(real_modlist_path):
        with open(real_modlist_path, "r", encoding="utf-8") as f: lines = f.readlines()
        lines = [line for line in lines if f"/{mod_id}/" not in line]
        with open(real_modlist_path, "w", encoding="utf-8") as f: f.writelines(lines)
    return {"status": "success", "message": "Mod entfernt."}

@app.delete("/api/server/delete/{plugin_id}")
def delete_server_files(plugin_id: str):
    if manager.is_running(plugin_id): raise HTTPException(status_code=400, detail="Server läuft!")
    if os.path.exists(os.path.join(SERVERS_ROOT, plugin_id)): shutil.rmtree(os.path.join(SERVERS_ROOT, plugin_id))
    if os.path.exists(os.path.join(BACKUPS_ROOT, plugin_id)): shutil.rmtree(os.path.join(BACKUPS_ROOT, plugin_id))
    if os.path.exists(os.path.join(DATA_ROOT, plugin_id)): shutil.rmtree(os.path.join(DATA_ROOT, plugin_id))
    _, plugin_dir, is_dev = get_plugin_paths(plugin_id)
    if os.path.exists(plugin_dir) and not is_dev: shutil.rmtree(plugin_dir)
    return {"status": "success", "message": "Dateien entfernt."}

@app.post("/api/server/open-folder/{plugin_id}")
def open_server_folder(plugin_id: str):
    server_dir = os.path.abspath(os.path.join(SERVERS_ROOT, plugin_id))
    os.makedirs(server_dir, exist_ok=True)
    if platform.system() == "Windows": os.startfile(server_dir)
    elif platform.system() == "Linux": subprocess.Popen(["xdg-open", server_dir])
    return {"status": "success"}

@app.get("/api/server/config/{plugin_id}")
def get_server_config(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest: return {"enabled": False}
    meta = manifest.get("config_meta")
    if not meta: return {"enabled": False}

    fields = meta.get("fields", [])
    known_keys = {f["key"] for f in fields}

    merged_values = {f["key"]: f.get("default") for f in fields}

    live_path = os.path.join(SERVERS_ROOT, plugin_id, meta.get("file_path"))
    live_values = parse_live_config_file(live_path)

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
    all_raw_unknowns = {}
    for k, v in live_values.items():
        if k not in known_keys: all_raw_unknowns[k] = v
    for k, v in desired_values.items():
        if k not in known_keys: all_raw_unknowns[k] = v

    for k, v in all_raw_unknowns.items():
        guessed_type, normalized_val = guess_type_and_normalize(v)
        unknown_fields.append({
            "key": k,
            "label": f"⚙️ {k} (Dynamisch erkannt)",
            "type": guessed_type,
            "is_unknown": True
        })
        merged_values[k] = normalized_val

    return {"enabled": True, "fields": fields, "unknown_fields": unknown_fields, "values": merged_values}

@app.post("/api/server/config/{plugin_id}")
def save_server_config(plugin_id: str, data: dict = Body(...)):
    manifest = load_manifest(plugin_id)
    if not manifest: raise HTTPException(status_code=404, detail="Manifest fehlt")
    meta = manifest.get("config_meta")
    if not meta: raise HTTPException(status_code=400, detail="Keine Meta-Config.")

    fields = meta.get("fields", [])
    for field in fields:
        key = field["key"]
        if field.get("type") == "boolean" and key in data:
            if field.get("boolean_mode") == "numeric":
                data[key] = 1 if data[key] is True or data[key] == 1 else 0
            else:
                data[key] = "True" if data[key] is True or str(data[key]).lower() == "true" else "False"

    desired_dir = os.path.join(DATA_ROOT, plugin_id)
    os.makedirs(desired_dir, exist_ok=True)
    desired_path = os.path.join(desired_dir, "desired_config.json")

    current_desired = {}
    if os.path.exists(desired_path):
        try:
            with open(desired_path, "r", encoding="utf-8") as f: current_desired = json.load(f)
        except: pass

    current_desired.update(data)

    with open(desired_path, "w", encoding="utf-8") as f:
        json.dump(current_desired, f, indent=2)

    live_path = os.path.join(SERVERS_ROOT, plugin_id, meta.get("file_path"))
    if os.path.exists(live_path): apply_desired_config_to_live(plugin_id)
    return {"status": "success", "message": "Soll-Konfiguration gespeichert."}

@app.get("/api/server/lists/{plugin_id}")
def get_server_lists(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest or "lists_meta" not in manifest: return {"enabled": False, "lists": []}
    result = []
    for lst in manifest["lists_meta"]:
        file_path = os.path.join(SERVERS_ROOT, plugin_id, lst["file_path"])
        content = ""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f: content = f.read()
        result.append({"id": lst["id"], "name": lst["name"], "content": content})
    return {"enabled": True, "lists": result}

@app.post("/api/server/lists/{plugin_id}")
def save_server_lists(plugin_id: str, payload: dict = Body(...)):
    manifest = load_manifest(plugin_id)
    if not manifest or "lists_meta" not in manifest: return {"status": "error"}
    for lst in manifest["lists_meta"]:
        list_id = lst["id"]
        if list_id in payload:
            file_path = os.path.join(SERVERS_ROOT, plugin_id, lst["file_path"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f: f.write(payload[list_id])
    return {"status": "success", "message": "Listen gespeichert."}

@app.get("/api/server/network/{plugin_id}")
def get_network(plugin_id: str):
    manifest = load_manifest(plugin_id)
    if not manifest or "network_meta" not in manifest: return {"enabled": False, "ports": []}
    return {"enabled": True, "ports": manifest["network_meta"].get("ports", [])}

@app.post("/api/server/network/setup/{plugin_id}")
def setup_network(plugin_id: str):
    if platform.system() != "Windows":
        return {"status": "error", "message": "Netzwerk-Automatisierung wird nur unter Windows unterstützt."}

    manifest = load_manifest(plugin_id)
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

    # Firewall eintragen
    for p in ports:
        rule_name = f"EmberCore_{plugin_id}_{p['port']}_{p['protocol'].upper()}"
        ps_commands.append(f"netsh advfirewall firewall delete rule name='{rule_name}' 2> $null")
        ps_commands.append(f"netsh advfirewall firewall add rule name='{rule_name}' dir=in action=allow protocol={p['protocol']} localport={p['port']} 2> $null")

    # UPnP Router Freigabe per Windows COM Objekt
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

@app.get("/api/server/backup/schedule/{plugin_id}")
def get_backup_schedule(plugin_id: str):
    schedule_file = os.path.join(DATA_ROOT, plugin_id, "backup_schedule.json")
    if os.path.exists(schedule_file):
        with open(schedule_file, "r", encoding="utf-8") as f: return json.load(f)
    return {"schedules": [], "retention": {"keep_latest": 5, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}}

@app.post("/api/server/backup/schedule/{plugin_id}")
def save_backup_schedule(plugin_id: str, req: dict = Body(...)):
    schedule_file = os.path.join(DATA_ROOT, plugin_id, "backup_schedule.json")
    os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
    with open(schedule_file, "w", encoding="utf-8") as f: json.dump(req, f, indent=2)
    return {"status": "success"}

@app.get("/api/server/backup/list/{plugin_id}")
def list_backups(plugin_id: str): return backup_manager.list_backups(plugin_id)

@app.post("/api/server/backup/create/{plugin_id}")
def create_backup(plugin_id: str):
    backup_manager.create_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), load_manifest(plugin_id).get("backup").get("source_path"), {})
    return {"status": "success"}

@app.post("/api/server/backup/restore/{plugin_id}/{filename}")
def restore_backup(plugin_id: str, filename: str):
    backup_manager.restore_backup(plugin_id, os.path.join(SERVERS_ROOT, plugin_id), load_manifest(plugin_id).get("backup").get("source_path"), filename)
    return {"status": "success"}

@app.delete("/api/server/backup/delete/{plugin_id}/{filename}")
def delete_backup(plugin_id: str, filename: str):
    backup_manager.delete_backup(plugin_id, filename)
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
    global ACTIVE_PORT
    port = 8000
    while socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(('127.0.0.1', port)) == 0: port += 10
    ACTIVE_PORT = port
    print(f"[*] EmberCore initialisiert auf Port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__": main()
