import os, yaml, json, re, httpx
from core.env import DEV_PLUGINS_ROOT, PLUGINS_ROOT, SERVERS_ROOT, DATA_ROOT, BASE_DIR, logger

class ConfigManager:
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
    def apply_desired_config(plugin_id: str):
        manifest = ConfigManager.load_manifest(plugin_id)
        if not manifest or not manifest.get("config_meta"): return
        desired_path = os.path.join(DATA_ROOT, plugin_id, "desired_config.json")
        if not os.path.exists(desired_path): return

        with open(desired_path, "r", encoding="utf-8") as f: desired_values = json.load(f)
        live_path = os.path.join(SERVERS_ROOT, plugin_id, manifest["config_meta"].get("file_path"))

        lines = []
        if os.path.exists(live_path):
            with open(live_path, "r", encoding="utf-8", errors="ignore") as f: lines = f.readlines()
        else: os.makedirs(os.path.dirname(live_path), exist_ok=True)

        updated_keys = set()
        new_lines = []
        fmt = manifest["config_meta"].get("format", "ini")
        
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
            for k, v in desired_values.items():
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
            for line in lines:
                match = re.match(r'^\s*([^=;#]+)\s*=\s*(.*)$', line)
                if match:
                    key = match.group(1).strip()
                    if key in desired_values:
                        val = desired_values[key]
                        val_str = "True" if val is True else ("False" if val is False else str(val))
                        new_lines.append(f"{key}={val_str}\n")
                        updated_keys.add(key)
                        continue
                new_lines.append(line)
                
            for k, v in desired_values.items():
                if k not in updated_keys:
                    val_str = "True" if v is True else ("False" if v is False else str(v))
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
