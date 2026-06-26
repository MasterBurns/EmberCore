from core.env import SERVERS_ROOT, EXE_DIR
from core.steamcmd_manager import SteamCMDManager
from core.backup_manager import BackupManager

# Hier werden die Manager global und zentral initialisiert
steam_manager = SteamCMDManager(base_dir=SERVERS_ROOT)
backup_manager = BackupManager(base_dir=EXE_DIR)
