import os
import platform
from core.env import logger

def find_shootergame_root(base_path: str, max_depth: int = 5) -> str:
    """
    Sucht rekursiv nach dem Ordner 'ShooterGame' und gibt dessen Elternordner (Server Root) zurück.
    Pruned bestimmte Verzeichnisse aus, um die Suche schnell zu halten.
    """
    if not os.path.exists(base_path): return None

    prune_list = ["steamapps", "workshop", "content", ".git", "backups", "updater_backup", "logs", "mods"]
    queue = [(base_path, 0)]
    
    matches = []
    min_depth_found = -1

    while queue:
        current_path, current_depth = queue.pop(0)
        
        if current_depth > max_depth: continue
        if min_depth_found != -1 and current_depth > min_depth_found: continue

        try:
            with os.scandir(current_path) as it:
                for entry in it:
                    if entry.is_dir():
                        name_lower = entry.name.lower()
                        if name_lower == "shootergame":
                            matches.append(current_path)
                            min_depth_found = current_depth
                        elif name_lower not in prune_list and not entry.name.startswith("."):
                            queue.append((entry.path, current_depth + 1))
        except PermissionError: pass

    if not matches: return None

    # Falls mehrere Treffer auf gleicher Ebene, priorisiere typische AMP/ARK Namen
    preferred = ["ark survival ascended", "ark-sa", "asa", "2430930"]
    for match in matches:
        match_name = os.path.basename(match).lower()
        if match_name in preferred:
            return match

    return matches[0]

def parse_amp_config(config_dir: str) -> dict:
    """
    Sucht die AMPConfig.conf im Ordner oder bis zu 2 Ebenen darüber und parst die Werte.
    """
    ext_conf = {}
    amp_config_path = None
    
    current_dir = config_dir
    for _ in range(3):
        p = os.path.join(current_dir, "AMPConfig.conf")
        if os.path.exists(p):
            amp_config_path = p
            break
        parent = os.path.dirname(current_dir)
        if parent == current_dir: break
        current_dir = parent

    if not amp_config_path: return ext_conf

    try:
        with open(amp_config_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        import json, re
        # Versuche JSON parsing (Tolerant für trailing commas)
        try:
            clean_content = re.sub(r',\s*}', '}', content)
            json_data = json.loads(clean_content)
            for key, val in json_data.items():
                k_lower = key.lower()
                v_str = str(val).strip()
                if "instance" in k_lower or "friendly" in k_lower: ext_conf["InstanceName"] = v_str
                elif "sessionname" in k_lower or "servername" in k_lower: ext_conf["SessionName"] = v_str
                elif "maxplayers" in k_lower or "maxusers" in k_lower: ext_conf["MaxPlayers"] = int(v_str) if v_str.isdigit() else 20
                elif "map" in k_lower and "url" not in k_lower: ext_conf["Map"] = v_str
                elif "serverpassword" in k_lower: ext_conf["ServerPassword"] = v_str
                elif "adminpassword" in k_lower: ext_conf["ServerAdminPassword"] = v_str
                elif "queryport" in k_lower: ext_conf["QueryPort"] = v_str
                elif "rconport" in k_lower: ext_conf["RCONPort"] = v_str
                elif "portnumber" in k_lower or "gameport" in k_lower or k_lower == "port": ext_conf["Port"] = v_str
        except Exception:
            # Fallback zeilenbasiert
            for line in content.splitlines():
                if ':' in line or '=' in line:
                    sep = '=' if '=' in line else ':'
                    key, val = line.split(sep, 1)
                    key = key.replace('"', '').strip()
                    val = val.replace('"', '').strip().strip(',')
                    k_lower = key.lower()
                    if "instance" in k_lower or "friendly" in k_lower: ext_conf["InstanceName"] = val
                    elif "sessionname" in k_lower or "servername" in k_lower: ext_conf["SessionName"] = val
                    elif "maxplayers" in k_lower or "maxusers" in k_lower: ext_conf["MaxPlayers"] = int(val) if val.isdigit() else 20
                    elif "map" in k_lower and "url" not in k_lower: ext_conf["Map"] = val
                    elif "serverpassword" in k_lower: ext_conf["ServerPassword"] = val
                    elif "adminpassword" in k_lower: ext_conf["ServerAdminPassword"] = val
                    elif "queryport" in k_lower: ext_conf["QueryPort"] = val
                    elif "rconport" in k_lower: ext_conf["RCONPort"] = val
                    elif "portnumber" in k_lower or "gameport" in k_lower or k_lower == "port": ext_conf["Port"] = val
                    
    except Exception as e:
        logger.error(f"[!] Fehler beim Parsen von AMPConfig.conf in {amp_config_path}: {e}")
        
    # Fallback auf GameUserSettings.ini, falls AMPConfig.conf nicht genug liefert
    try:
        sg_root = find_shootergame_root(config_dir)
        if sg_root:
            from core.config_manager import ConfigManager
            live_data = ConfigManager.parse_live_config(os.path.dirname(sg_root), "GameUserSettings.ini")
            if live_data:
                server_settings = live_data.get("ServerSettings", {})
                if "SessionName" not in ext_conf and "SessionName" in server_settings: ext_conf["SessionName"] = server_settings["SessionName"]
                if "RCONPort" not in ext_conf and "RCONPort" in server_settings: ext_conf["RCONPort"] = server_settings["RCONPort"]
                if "QueryPort" not in ext_conf and "QueryPort" in server_settings: ext_conf["QueryPort"] = server_settings["QueryPort"]
                if "Port" not in ext_conf and "Port" in server_settings: ext_conf["Port"] = server_settings["Port"]
                if "MaxPlayers" not in ext_conf and "MaxPlayers" in server_settings: ext_conf["MaxPlayers"] = server_settings["MaxPlayers"]
    except Exception as e:
        logger.warning(f"Fallback GameUserSettings.ini schlug fehl: {e}")

    # Sanitisierung: Keine leeren Strings, None oder False
    for k in list(ext_conf.keys()):
        if ext_conf[k] in [None, False, "", "False", "None"]:
            del ext_conf[k]
            
    if "InstanceName" not in ext_conf: ext_conf["InstanceName"] = os.path.basename(config_dir)
    if "Map" not in ext_conf: ext_conf["Map"] = "Unbekannt"
    if "Port" not in ext_conf: ext_conf["Port"] = 7777

    return ext_conf

def discover_amp_instances(custom_paths: list = None) -> list:
    """
    Scant Standard- und benutzerdefinierte Pfade nach AMP Instanzen, die ShooterGame enthalten.
    """
    scan_roots = []
    
    if platform.system() == "Windows":
        scan_roots.append("C:\\AMP\\Instances")
    else:
        scan_roots.extend(["/home/amp/.ampdata/instances", "/opt/amp/instances"])

    if custom_paths:
        for p in custom_paths:
            if p.strip() and p.strip() not in scan_roots:
                scan_roots.append(p.strip())

    instances = []
    
    for root in scan_roots:
        if not os.path.exists(root): continue
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if entry.is_dir():
                        server_root = find_shootergame_root(entry.path)
                        if server_root:
                            amp_config = parse_amp_config(entry.path)
                            instances.append({
                                "instance_name": entry.name,
                                "instance_path": entry.path,
                                "server_root": server_root,
                                "session_name": amp_config.get("SessionName", "Unbekannt"),
                                "map": amp_config.get("Map", "TheIsland_WP"),
                                "port": amp_config.get("Port", 7777),
                                "query_port": amp_config.get("QueryPort", 27015),
                                "rcon_port": amp_config.get("RCONPort", 27020)
                            })
        except Exception as e:
            logger.error(f"[!] Fehler beim Scannen von {root}: {e}")

    return instances
