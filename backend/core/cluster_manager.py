import os, json, platform, subprocess
from core.env import DATA_ROOT, logger
from core.config_manager import ConfigManager

class ClusterManager:
    def __init__(self):
        self.db_path = os.path.join(DATA_ROOT, "clusters_db.json")

    def _get_db(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Fehler beim Lesen der Cluster-DB: {e}")
        return {}

    def _save_db(self, data):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_all(self):
        return self._get_db()

    def create(self, cluster_id, name, game_name, custom_path):
        if not cluster_id: return {"status": "error", "message": "Keine Cluster-ID angegeben."}
        db = self._get_db()
        if cluster_id in db: return {"status": "error", "message": "Cluster-ID existiert bereits."}

        if custom_path:
            shared_dir = os.path.abspath(custom_path).replace("\\", "/")
        else:
            shared_dir = os.path.abspath(os.path.join(DATA_ROOT, "shared_clusters", cluster_id)).replace("\\", "/")

        try:
            os.makedirs(shared_dir, exist_ok=True)
        except Exception as e:
            return {"status": "error", "message": f"Konnte Ordner nicht erstellen: {e}"}

        db[cluster_id] = {
            "name": name,
            "game_name": game_name,
            "shared_dir": shared_dir,
            "members": []
        }
        self._save_db(db)
        return {"status": "success", "message": f"Cluster '{name}' für {game_name} erstellt!"}

    def open_folder(self, cluster_id):
        db = self._get_db()
        if cluster_id not in db: return {"status": "error", "message": "Cluster nicht gefunden."}

        shared_dir = db[cluster_id].get("shared_dir")
        if not shared_dir or not os.path.exists(shared_dir):
            return {"status": "error", "message": "Der Ordner wurde noch nicht vom System erstellt."}

        if platform.system() == "Windows": os.startfile(shared_dir)
        elif platform.system() == "Linux": subprocess.Popen(["xdg-open", shared_dir])
        return {"status": "success"}

    def delete(self, cluster_id):
        db = self._get_db()
        if cluster_id not in db: return {"status": "error", "message": "Cluster nicht gefunden."}
        del db[cluster_id]
        self._save_db(db)
        logger.info(f"[-] Cluster '{cluster_id}' wurde manuell aufgelöst.")
        return {"status": "success", "message": "Cluster erfolgreich aufgelöst."}

    def assign_server(self, cluster_id, plugin_id):
        db = self._get_db()
        if cluster_id not in db: return {"status": "error", "message": "Cluster nicht gefunden."}

        for cid, cdata in db.items():
            if plugin_id in cdata["members"]:
                cdata["members"].remove(plugin_id)

        manifest = ConfigManager.load_manifest(plugin_id)
        if manifest and "config_meta" in manifest:
            desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
            new_desired = {}
            if os.path.exists(desired_path):
                try:
                    with open(desired_path, "r", encoding="utf-8") as f: new_desired = json.load(f)
                except: pass

            used_ports = set()
            for member in db[cluster_id]["members"]:
                m_desired_path = os.path.join(DATA_ROOT, member, "desired_config.json")
                if os.path.exists(m_desired_path):
                    try:
                        with open(m_desired_path, "r", encoding="utf-8") as f:
                            m_data = json.load(f)
                            for k, v in m_data.items():
                                if "port" in k.lower():
                                    try: used_ports.add(int(v))
                                    except: pass
                    except: pass

            updated_ports = False
            for field in manifest["config_meta"].get("fields", []):
                key = field["key"]
                if "port" in key.lower():
                    current_port = int(new_desired.get(key, field.get("default", 0)))
                    original_port = current_port

                    while current_port in used_ports:
                        current_port += 2

                    if current_port != original_port:
                        new_desired[key] = current_port
                        used_ports.add(current_port)
                        updated_ports = True

            if updated_ports:
                logger.info(f"[*] Port-Konflikt in Cluster '{cluster_id}' gelöst! Neue Ports gespeichert.")
                os.makedirs(os.path.dirname(desired_path), exist_ok=True)
                with open(desired_path, "w", encoding="utf-8") as f: json.dump(new_desired, f, indent=2)
                ConfigManager.apply_desired_config(plugin_id)

        db[cluster_id]["members"].append(plugin_id)
        self._save_db(db)
        return {"status": "success", "message": f"Server zum Cluster hinzugefügt (Ports automatisch abgeglichen)."}

    def remove_server(self, plugin_id):
        db = self._get_db()
        for cid, cdata in db.items():
            if plugin_id in cdata["members"]:
                cdata["members"].remove(plugin_id)
        self._save_db(db)
        return {"status": "success", "message": "Server aus Cluster isoliert."}

    def get_mods(self, cluster_id):
        db = self._get_db()
        if cluster_id not in db: return {"status": "error", "message": "Cluster nicht gefunden."}

        cluster_members = db[cluster_id].get("members", [])
        if not cluster_members: return {"mods": []}

        pooled_mods = {}
        for plugin_id in cluster_members:
            mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
            if os.path.exists(mods_file):
                try:
                    with open(mods_file, "r", encoding="utf-8") as f:
                        server_mods = json.load(f)
                        for mod in server_mods:
                            if mod["id"] not in pooled_mods:
                                pooled_mods[mod["id"]] = {
                                    "id": mod["id"],
                                    "name": mod.get("name", f"Mod {mod['id']}"),
                                    "version": mod.get("version", "unbekannt"),
                                    "active_on": [plugin_id]
                                }
                            else:
                                pooled_mods[mod["id"]]["active_on"].append(plugin_id)
                except: pass
        return {"mods": list(pooled_mods.values()), "member_count": len(cluster_members)}

    def sync_mods(self, cluster_id, target_mod_ids):
        db = self._get_db()
        if cluster_id not in db: return {"status": "error", "message": "Cluster nicht gefunden."}

        cluster_members = db[cluster_id].get("members", [])
        if not cluster_members: return {"status": "error", "message": "Der Cluster ist leer."}

        pool_data = self.get_mods(cluster_id).get("mods", [])
        mod_lookup = { m["id"]: {"id": m["id"], "name": m["name"], "version": m["version"]} for m in pool_data }

        unified_mods = []
        for m_id in target_mod_ids:
            if m_id in mod_lookup: unified_mods.append(mod_lookup[m_id])
            else: unified_mods.append({"id": m_id, "name": f"Workshop Mod ({m_id})", "version": "unbekannt"})

        for plugin_id in cluster_members:
            mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
            os.makedirs(os.path.dirname(mods_file), exist_ok=True)
            with open(mods_file, "w", encoding="utf-8") as f: json.dump(unified_mods, f, indent=2)

        logger.info(f"[*] Cluster '{cluster_id}': {len(unified_mods)} Mods auf {len(cluster_members)} Server synchronisiert.")
        return {"status": "success", "message": "Mods erfolgreich auf alle Server gespiegelt!", "updated_members": cluster_members}

    def get_config_sections(self, plugin_id):
        ini_path = os.path.abspath(os.path.join(DATA_ROOT, plugin_id, "ShooterGame/Saved/Config/WindowsServer/GameUserSettings.ini"))
        if not os.path.exists(ini_path): return {"sections": []}

        sections = []
        try:
            with open(ini_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        sections.append(stripped[1:-1])
        except Exception as e: logger.error(f"Fehler beim Lesen der Sektionen: {e}")
        return {"sections": sections}

    def sync_config(self, cluster_id, master_id, selected_sections):
        db = self._get_db()
        if cluster_id not in db: return {"status": "error", "message": "Cluster nicht gefunden."}

        cluster_members = db[cluster_id].get("members", [])
        if not master_id or master_id not in cluster_members: return {"status": "error", "message": "Ungültige Master-Server-ID."}
        if len(cluster_members) < 2: return {"status": "error", "message": "Mindestens zwei Server benötigt."}

        master_ini = os.path.abspath(os.path.join(DATA_ROOT, master_id, "ShooterGame/Saved/Config/WindowsServer/GameUserSettings.ini"))
        if not os.path.exists(master_ini): return {"status": "error", "message": "Master-Konfigurationsdatei nicht gefunden."}

        KEY_BLACKLIST = {"sessionname", "port", "queryport", "rconport", "rconenabled", "serveradminpassword", "serverpassword", "spectatorpassword"}
        master_data = {}
        current_section = None

        with open(master_ini, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith(";"): continue

                if stripped.startswith("[") and stripped.endswith("]"):
                    current_section = stripped[1:-1]
                    if selected_sections and current_section not in selected_sections: current_section = None
                    if current_section and current_section not in master_data: master_data[current_section] = {}
                elif current_section and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    if k.strip().lower() not in KEY_BLACKLIST:
                        master_data[current_section][k.strip()] = v.strip()

        target_members = [m for m in cluster_members if m != master_id]
        for target_id in target_members:
            target_ini = os.path.abspath(os.path.join(DATA_ROOT, target_id, "ShooterGame/Saved/Config/WindowsServer/GameUserSettings.ini"))
            if not os.path.exists(target_ini):
                os.makedirs(os.path.dirname(target_ini), exist_ok=True)
                open(target_ini, 'a').close()

            with open(target_ini, "r", encoding="utf-8") as f: target_lines = f.readlines()

            for section, kv_pairs in master_data.items():
                section_header = f"[{section}]"
                section_found = any(line.strip() == section_header for line in target_lines)
                if not section_found: target_lines.append(f"\n{section_header}\n")

                for k, v in kv_pairs.items():
                    in_section = False
                    key_found = False
                    for i, line in enumerate(target_lines):
                        line_stripped = line.strip()
                        if line_stripped.startswith("[") and line_stripped != section_header: in_section = False
                        if line_stripped == section_header: in_section = True
                        if in_section and line_stripped.lower().startswith(f"{k.lower()}="):
                            target_lines[i] = f"{k}={v}\n"
                            key_found = True
                            break
                    if not key_found:
                        for i, line in enumerate(target_lines):
                            if line.strip() == section_header:
                                target_lines.insert(i + 1, f"{k}={v}\n")
                                break

            with open(target_ini, "w", encoding="utf-8") as f: f.writelines(target_lines)

        return {"status": "success", "message": "Synchronisierung erfolgreich abgeschlossen!"}

    def get_injection_args(self, plugin_id):
        """Gibt die Startparameter für die EXE zurück, falls der Server in einem Cluster ist."""
        db = self._get_db()
        for cluster_id, cdata in db.items():
            if plugin_id in cdata.get("members", []):
                shared_dir = cdata.get("shared_dir")
                os.makedirs(shared_dir, exist_ok=True)
                return {
                    "cluster_id": cluster_id,
                    "shared_dir": shared_dir,
                    "args": [
                        f"-clusterid={cluster_id}",
                        f"-ClusterDirOverride=\"{shared_dir}\"",
                        "-NoTransferFromFiltering"
                    ]
                }
        return None

cluster_manager = ClusterManager()