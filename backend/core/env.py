import os, sys, logging, json
from datetime import datetime
from logging.handlers import RotatingFileHandler

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
    IS_COMPILED = True
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    EXE_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
    IS_COMPILED = False

SERVERS_ROOT = os.path.join(EXE_DIR, "servers")
BACKUPS_ROOT = os.path.join(EXE_DIR, "backups")
DATA_ROOT = os.path.join(EXE_DIR, "data")
PLUGINS_ROOT = os.path.join(EXE_DIR, "plugins")
DEV_PLUGINS_ROOT = os.path.join(BASE_DIR, "dev_plugins") if not IS_COMPILED else os.path.join(EXE_DIR, "dev_plugins")
SYS_CONFIG_PATH = os.path.join(DATA_ROOT, "system_config.json")

os.makedirs(DATA_ROOT, exist_ok=True)
os.makedirs(os.path.join(EXE_DIR, "logs"), exist_ok=True)

# Globale States
ACTIVE_PORT = 8000
START_TIME = datetime.now()
game_update_cache = {}
disk_cache = {}

def load_sys_config():
    if os.path.exists(SYS_CONFIG_PATH):
        try:
            with open(SYS_CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"verbose_logging": False}

sys_config = load_sys_config()
logger = logging.getLogger("EmberCore")
logger.setLevel(logging.DEBUG if sys_config.get("verbose_logging") else logging.INFO)

if not logger.handlers:
    fh = RotatingFileHandler(os.path.join(EXE_DIR, "logs", "embercore.log"), maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(ch)

def check_write_permissions():
    try:
        test_file = os.path.join(EXE_DIR, ".write_test")
        with open(test_file, "w") as f: f.write("test")
        os.remove(test_file)
    except PermissionError:
        logger.error("[SCHWERER FEHLER] FEHLENDE SCHREIBRECHTE im Verzeichnis!")
        sys.exit(1)

check_write_permissions()

def get_current_system_version():
    v_path = os.path.join(BASE_DIR, "version.json") if IS_COMPILED else os.path.join(EXE_DIR, "version.json")
    if os.path.exists(v_path):
        try:
            with open(v_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    latest = data[0].copy(); latest["history"] = data; return latest
                elif isinstance(data, dict):
                    data["history"] = [data]; return data
        except: pass
    return {"version": "dev-build", "build_date": "unknown", "changelog": ["Lokale Entwicklungsversion."], "history": []}
