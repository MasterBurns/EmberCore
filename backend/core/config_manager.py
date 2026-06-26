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
                    if "config_meta" not in local_manifest: local_manifest["config_meta"] = {"fields": []}
                    local_keys = {f["key"] for f in local_manifest["config_meta"].get("fields", [])}
                    for field in global_manifest["config_meta"]["fields"]:
                        if field["key"] not in local_keys:
                            local_manifest["config_meta"]["fields"].append(field)
                            migrated = True

                if migrated:
                    with open(live_path, "w", encoding="utf-8") as f: yaml.dump(local_manifest, f, allow_unicode=True, default_flow_style=False)
            except Exception as e: logger.error(f"[Schema Sync] Fehler: {e}")

        return local_manifest

    @staticmethod
    def parse_live_config(file_path: str) -> dict:
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

        for key, val in desired_values.items():
            if key not in updated_keys:
                val_str = "True" if val is True else ("False" if val is False else str(val))
                new_lines.append(f"{key}={val_str}\n")

        with open(live_path, "w", encoding="utf-8") as f: f.writelines(new_lines)
