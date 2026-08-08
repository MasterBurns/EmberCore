import os, yaml, json, re, httpx
from core.env import DEV_PLUGINS_ROOT, PLUGINS_ROOT, SERVERS_ROOT, DATA_ROOT, BASE_DIR, BACKUPS_ROOT, logger

class ConfigManager:
    @staticmethod
    def rename_plugin(old_id: str, new_id: str) -> dict:
        import shutil
        warnings = []
        
        try:
            old_server = os.path.join(SERVERS_ROOT, old_id)
            new_server = os.path.join(SERVERS_ROOT, new_id)
            if os.path.exists(old_server):
                if os.path.exists(new_server):
                    return {"status": "error", "message": f"Zielverzeichnis '{new_id}' existiert bereits unter servers/."}
                try: shutil.move(old_server, new_server)
                except Exception as e: return {"status": "error", "message": f"Konnte Server-Verzeichnis nicht verschieben: {e}"}
                
            old_data = os.path.join(DATA_ROOT, old_id)
            new_data = os.path.join(DATA_ROOT, new_id)
            if os.path.exists(old_data):
                if not os.path.exists(new_data):
                    try: shutil.move(old_data, new_data)
                    except Exception as e: warnings.append(f"Konnte Data-Verzeichnis nicht verschieben: {e}")
                
            old_backup = os.path.join(BACKUPS_ROOT, old_id)
            new_backup = os.path.join(BACKUPS_ROOT, new_id)
            if os.path.exists(old_backup):
                if not os.path.exists(new_backup):
                    try: shutil.move(old_backup, new_backup)
                    except Exception as e: warnings.append(f"Konnte Backup-Verzeichnis nicht verschieben: {e}")
                
            old_plugin = os.path.join(PLUGINS_ROOT, old_id)
            new_plugin = os.path.join(PLUGINS_ROOT, new_id)
            if os.path.exists(old_plugin):
                if not os.path.exists(new_plugin):
                    try: shutil.move(old_plugin, new_plugin)
                    except Exception as e: return {"status": "error", "message": f"Konnte Plugin-Verzeichnis nicht verschieben: {e}"}
                
                # Manifest ID patchen
                manifest_path = os.path.join(new_plugin, "manifest.yaml")
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f: manifest_data = yaml.safe_load(f)
                        manifest_data["id"] = new_id
                        with open(manifest_path, "w", encoding="utf-8") as f: yaml.dump(manifest_data, f, allow_unicode=True, sort_keys=False)
                    except Exception as e: warnings.append(f"Konnte manifest.yaml ID nicht aktualisieren: {e}")
                    
            # Cluster DB patchen
            cluster_db_path = os.path.join(DATA_ROOT, "clusters_db.json")
            if os.path.exists(cluster_db_path):
                try:
                    with open(cluster_db_path, "r", encoding="utf-8") as f: cluster_db = json.load(f)
                    changed = False
                    for c_id, c_data in cluster_db.items():
                        if "members" in c_data:
                            new_members = []
                            for m in c_data["members"]:
                                if m == old_id:
                                    new_members.append(new_id)
                                    changed = True
                                else:
                                    new_members.append(m)
                            c_data["members"] = new_members
                    if changed:
                        with open(cluster_db_path, "w", encoding="utf-8") as f: json.dump(cluster_db, f, indent=2)
                except Exception as e:
                    warnings.append(f"Konnte clusters_db.json nicht patchen: {e}")
                    
            # Firewall patchen
            from core.firewall_manager import firewall_manager
            try:
                firewall_manager.remove_rules_for_plugin(old_id)
                from core.config_manager import ConfigManager
                new_manifest = ConfigManager.load_manifest(new_id)
                if new_manifest:
                    firewall_manager.apply_rules_for_plugin(new_id, new_manifest)
            except Exception as e:
                warnings.append(f"Fehler bei der Firewall-Aktualisierung: {e}")
                
            return {"status": "success", "message": "Server erfolgreich umbenannt.", "warnings": warnings}
        except Exception as e:
            logger.exception(f"[!] Kritischer Fehler bei Rename {old_id} -> {new_id}: {e}")
            return {"status": "error", "message": f"Kritischer Systemfehler beim Umbenennen: {str(e)}"}
    @staticmethod
    def get_plugin_paths(plugin_id: str):
        dev_path = os.path.join(DEV_PLUGINS_ROOT, plugin_id, "manifest.yaml")
        live_path = os.path.join(PLUGINS_ROOT, plugin_id, "manifest.yaml")
        if os.path.exists(dev_path): return dev_path, os.path.join(DEV_PLUGINS_ROOT, plugin_id), True
        return live_path, os.path.join(PLUGINS_ROOT, plugin_id), False

    @staticmethod
    def sync_manifest_from_cloud(plugin_id: str):
        dev_path, live_dir, is_dev = ConfigManager.get_plugin_paths(plugin_id)
        if is_dev: return  # Lokale Entwickler-Plugins niemals überschreiben!

        live_path = os.path.join(live_dir, "manifest.yaml")
        if not os.path.exists(live_path): return

        try:
            with open(live_path, "r", encoding="utf-8") as f: local_manifest = yaml.safe_load(f)
            source_url = local_manifest.get("source_url")

            # Fallback für Server, die VOR diesem Feature installiert wurden
            if not source_url:
                try:
                    res_dir = httpx.get("https://raw.githubusercontent.com/MasterBurns/EmberCore/main/plugins_directory.json", timeout=5.0)
                    if res_dir.status_code == 200:
                        for p in res_dir.json():
                            # Finde Server via Steam-ID oder Name
                            if str(p.get("steam_app_id", "")) == str(local_manifest.get("steam_app_id", "")) or p.get("name") == local_manifest.get("name"):
                                source_url = p.get("yaml_url")
                                break
                except: pass

            # Nur reine YAML-URLs synchronisieren (Keine ZIPs)
            if not source_url or source_url.endswith(".zip"): return

            # Manifest herunterladen
            res = httpx.get(source_url, follow_redirects=True, timeout=5.0)
            if res.status_code == 200 and b"PK\x03\x04" not in res.content[:4]:
                new_manifest = yaml.safe_load(res.content)

                # Nur nicht-lokale Sections überschreiben
                preserved_sections = ["config_meta", "default_args", "shutdown"]
                for section in preserved_sections:
                    if section in local_manifest:
                        new_manifest[section] = local_manifest[section]

                # Wichtig: Die lokale ID und die Quell-URL in das frische Manifest übernehmen!
                new_manifest["id"] = local_manifest.get("id", plugin_id)
                new_manifest["source_url"] = source_url

                with open(live_path, "w", encoding="utf-8") as f:
                    yaml.dump(new_manifest, f, allow_unicode=True, sort_keys=False)

                logger.info(f"[Cloud Sync] Manifest für '{plugin_id}' erfolgreich aus GitHub aktualisiert!")
        except Exception as e:
            logger.warning(f"[Cloud Sync] Konnte Manifest nicht synchronisieren: {e}")

    @staticmethod
    def load_manifest(plugin_id: str):
        dev_path, _, is_dev = ConfigManager.get_plugin_paths(plugin_id)
        if is_dev:
            with open(dev_path, "r", encoding="utf-8") as f: return yaml.safe_load(f)

        live_path = os.path.join(PLUGINS_ROOT, plugin_id, "manifest.yaml")
        if not os.path.exists(live_path): return None

        with open(live_path, "r", encoding="utf-8") as f: local_manifest = yaml.safe_load(f)

        # Lokaler Schema Sync (Für abwärtskompatible Templates)
        template_name = plugin_id.split('_')[0]
        global_template_path = os.path.join(BASE_DIR, "static", "templates", f"{template_name}.yaml")
        if not os.path.exists(global_template_path):
            global_template_path = os.path.join(DEV_PLUGINS_ROOT, template_name, "manifest.yaml")

        if os.path.exists(global_template_path):
            try:
                with open(global_template_path, "r", encoding="utf-8") as f: global_manifest = yaml.safe_load(f)
                migrated = False
                for key in ["shutdown", "diagnostics", "lists_meta", "mods_meta", "network_meta"]:
                    if key in global_manifest and key not in local_manifest:
                        local_manifest[key] = global_manifest[key]
                        migrated = True

                if "config_meta" in global_manifest and "fields" in global_manifest["config_meta"]:
                    if "config_meta" not in local_manifest:
                        local_manifest["config_meta"] = {"fields": [], "file_path": global_manifest["config_meta"].get("file_path", "")}
                        migrated = True
                    elif "file_path" not in local_manifest["config_meta"] and "file_path" in global_manifest["config_meta"]:
                        local_manifest["config_meta"]["file_path"] = global_manifest["config_meta"]["file_path"]
                        migrated = True
                        
                    local_keys = {f["key"] for f in local_manifest["config_meta"].get("fields", [])}
                    for field in global_manifest["config_meta"]["fields"]:
                        if field["key"] not in local_keys:
                            local_manifest["config_meta"]["fields"].append(field)
                            migrated = True

                if migrated:
                    with open(live_path, "w", encoding="utf-8") as f: yaml.dump(local_manifest, f, allow_unicode=True, default_flow_style=False)
            except Exception as e: logger.error(f"[Schema Sync] Fehler: {e}")

        # Dynamically merge network_override.json
        import json
        override_file = os.path.join(DATA_ROOT, plugin_id, "network_override.json")
        if os.path.exists(override_file):
            try:
                with open(override_file, "r", encoding="utf-8") as f:
                    override_data = json.load(f)
                    if "ports" in override_data and "network_meta" in local_manifest:
                        local_manifest["network_meta"]["ports"] = override_data["ports"]
                    if "default_args" in override_data:
                        local_manifest["default_args"] = override_data["default_args"]
                    if "shutdown_rcon_port" in override_data and override_data["shutdown_rcon_port"] and "shutdown" in local_manifest and "rcon" in local_manifest["shutdown"]:
                        local_manifest["shutdown"]["rcon"]["port"] = override_data["shutdown_rcon_port"]
            except Exception as e:
                logger.error(f"[ConfigManager] Fehler beim Laden von network_override.json: {e}")

        return local_manifest

    @staticmethod
    def parse_live_config(file_path: str, format: str = "ini") -> dict:
        values = {}
        if not os.path.exists(file_path): return values
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    match = re.match(r'^\s*([^=;#]+)\s*=\s*(.*)$', line)
                    if match:
                        k, v = match.group(1).strip(), match.group(2).strip()
                        if v.startswith('"') and v.endswith('"'): v = v[1:-1]
                        if v.startswith("'") and v.endswith("'"): v = v[1:-1]
                        values[k] = v
                        
            if format == "palworld_ini" and "OptionSettings" in values:
                # OptionSettings=(ServerName="Default Palworld Server",ServerDescription="",...)
                # We extract the content inside the parentheses
                opt_str = values["OptionSettings"]
                if opt_str.startswith("(") and opt_str.endswith(")"):
                    opt_str = opt_str[1:-1]
                    
                # Split by comma, but be careful of commas inside quotes.
                # A simple regex for key=value where value might be quoted or not:
                parts = re.findall(r'([^,]+)="([^"]*)"|([^,]+)=([^,]*)', opt_str)
                for p in parts:
                    if p[0]: # quoted value
                        values[p[0].strip()] = p[1]
                    elif p[2]: # unquoted value
                        values[p[2].strip()] = p[3]
                        
        except: pass
        return values

    @staticmethod
    def get_full_live_config(plugin_id: str) -> dict:
        manifest = ConfigManager.load_manifest(plugin_id)
        if not manifest or not manifest.get("config_meta"): return {}
        
        default_file = manifest["config_meta"].get("file_path")
        fmt = manifest["config_meta"].get("format", "ini")
        
        files_to_read = {default_file} if default_file else set()
        for field in manifest["config_meta"].get("fields", []):
            if "file_path" in field:
                files_to_read.add(field["file_path"])
                
        all_values = {}
        for fpath in files_to_read:
            live_path = os.path.join(SERVERS_ROOT, plugin_id, fpath)
            all_values.update(ConfigManager.parse_live_config(live_path, fmt))
            
        return all_values

    @staticmethod
    def apply_desired_config(plugin_id: str):
        manifest = ConfigManager.load_manifest(plugin_id)
        if not manifest or not manifest.get("config_meta"): return
        desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
        if not os.path.exists(desired_path): return

        with open(desired_path, "r", encoding="utf-8") as f: desired_values = json.load(f)
        
        default_file = manifest["config_meta"].get("file_path")
        fmt = manifest["config_meta"].get("format", "ini")
        
        # Group keys by target file
        file_groups = {}
        key_sections = {}
        for field in manifest["config_meta"].get("fields", []):
            k = field["key"]
            fpath = field.get("file_path", default_file)
            section = field.get("section", "ServerSettings")
            key_sections[k] = section
            
            if fpath not in file_groups: file_groups[fpath] = []
            file_groups[fpath].append(k)

        # Handle keys that are in desired_values but not in fields (fallback to default file)
        for k in desired_values:
            if k not in key_sections:
                if default_file not in file_groups: file_groups[default_file] = []
                if k not in file_groups[default_file]:
                    file_groups[default_file].append(k)
                    key_sections[k] = "ServerSettings" # Default section
        
        # Process each file group
        for fpath, keys_for_file in file_groups.items():
            if not fpath: continue
            
            live_path = os.path.join(SERVERS_ROOT, plugin_id, fpath)
            lines = []
            if os.path.exists(live_path):
                with open(live_path, "r", encoding="utf-8", errors="ignore") as f: lines = f.readlines()
            else: 
                os.makedirs(os.path.dirname(live_path), exist_ok=True)
                
            desired_values_for_file = {k: desired_values[k] for k in keys_for_file if k in desired_values}
            if not desired_values_for_file: continue
            
            updated_keys = set()
            new_lines = []
            
            if fmt == "palworld_ini":
                # For Palworld, we completely rewrite OptionSettings
                # Find the [Script/Pal.PalGameWorldSettings] header
                has_header = False
                for line in lines:
                    if "[/Script/Pal.PalGameWorldSettings]" in line:
                        has_header = True
                        break
                        
                new_lines = []
                if not has_header:
                    new_lines.append("[/Script/Pal.PalGameWorldSettings]\n")
                else:
                    for line in lines:
                        if not line.strip().startswith("OptionSettings="):
                            new_lines.append(line)
                            
                # Build the OptionSettings string
                opt_parts = []
                for k, v in desired_values_for_file.items():
                    if isinstance(v, bool):
                        val_str = "True" if v else "False"
                    elif isinstance(v, (int, float)):
                        if isinstance(v, float):
                            val_str = f"{v:.6f}"
                        else:
                            val_str = str(v)
                    else:
                        # Escape quotes in strings
                        safe_v = str(v).replace('"', '\\"')
                        val_str = f'"{safe_v}"'
                    opt_parts.append(f"{k}={val_str}")
                    
                new_lines.append(f"OptionSettings=({','.join(opt_parts)})\n")
                
            else:
                current_section = None
                
                for line in lines:
                    sec_match = re.match(r'^\s*\[(.*?)\]\s*$', line)
                    if sec_match:
                        current_section = sec_match.group(1).strip()
                        new_lines.append(line)
                        continue

                    match = re.match(r'^\s*([^=;#]+)\s*=\s*(.*)$', line)
                    if match:
                        key = match.group(1).strip()
                        if key in desired_values_for_file:
                            expected_section = key_sections.get(key, "ServerSettings")
                            
                            # Reparatur-Logik: Falls der Key in der falschen oder in gar keiner Section steht,
                            # wird er hier verworfen. Der Append-Block am Ende fügt ihn dann korrekt in die
                            # richtige Section ein.
                            if current_section != expected_section:
                                continue

                            val = desired_values_for_file[key]
                            val_str = "True" if val is True else ("False" if val is False else str(val))
                            new_lines.append(f"{key}={val_str}\n")
                            updated_keys.add(key)
                            continue
                    new_lines.append(line)
                    
                for k, v in desired_values_for_file.items():
                    if k not in updated_keys:
                        val_str = "True" if v is True else ("False" if v is False else str(v))
                        section = key_sections.get(k, "ServerSettings")
                        section_header = f"[{section}]"
                        
                        # Suche die Section im File
                        section_idx = -1
                        for i, line in enumerate(new_lines):
                            if line.strip() == section_header:
                                section_idx = i
                                break
                                
                        if section_idx != -1:
                            # Füge direkt unter dem gefundenen Section-Header ein
                            new_lines.insert(section_idx + 1, f"{k}={val_str}\n")
                        else:
                            # Section existiert noch nicht, hänge sie ans Ende an
                            if new_lines and not new_lines[-1].endswith('\n'):
                                new_lines[-1] += '\n'
                            new_lines.append(f"\n{section_header}\n")
                            new_lines.append(f"{k}={val_str}\n")

            with open(live_path, "w", encoding="utf-8") as f: f.writelines(new_lines)


    @staticmethod
    def enforce_cluster_rules(plugin_id: str, manifest: dict):
        """
        Zwingt dem Server vor dem Start die kritischen Cluster-Settings auf.
        Verhindert Charakterverlust durch Fehlkonfiguration.
        """
        if "cluster_meta" not in manifest: return

        server_dir = ConfigManager.get_server_dir(plugin_id)

        for rule in manifest["cluster_meta"].get("enforce_files", []):
            file_path = os.path.abspath(os.path.join(server_dir, rule["file_path"]))

            # Falls die Config noch nicht existiert (First Boot), Ordner erstellen
            if not os.path.exists(file_path):
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                open(file_path, 'a').close()

            if rule.get("format") == "ini":
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for section, kv_pairs in rule.get("values", {}).items():
                    section_header = f"[{section}]"
                    section_found = any(line.strip() == section_header for line in lines)

                    if not section_found:
                        lines.append(f"\n{section_header}\n")

                    for k, v in kv_pairs.items():
                        in_section = False
                        key_found = False

                        for i, line in enumerate(lines):
                            stripped = line.strip()
                            if stripped.startswith("[") and stripped != section_header:
                                in_section = False
                            if stripped == section_header:
                                in_section = True

                            # Wenn wir in der richtigen Sektion sind und den Key finden -> Überschreiben
                            if in_section and stripped.lower().startswith(f"{k.lower()}="):
                                lines[i] = f"{k}={v}\n"
                                key_found = True
                                break

                        # Wenn der Key fehlt, direkt unter die Sektionsüberschrift einfügen
                        if not key_found:
                            for i, line in enumerate(lines):
                                if line.strip() == section_header:
                                    lines.insert(i + 1, f"{k}={v}\n")
                                    break

                # Datei sauber zurückschreiben
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

                from core.env import logger
                logger.info(f"[*] Cluster-Sicherheitsprotokoll: {os.path.basename(file_path)} für '{plugin_id}' synchronisiert.")
