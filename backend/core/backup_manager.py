import os
import shutil
from datetime import datetime
import zipfile
import threading

class BackupManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.backups_root = os.path.join(self.base_dir, "backups")
        self.data_root = os.path.join(self.base_dir, "data") # NEU: Hier liegen die EmberCore Configs
        
        # Speichert den Live-Status pro Plugin. Format: {"active": True, "percent": 45}
        self.active_backups = {}

    def get_progress(self, plugin_id: str):
        """Gibt den aktuellen Status an die API (Frontend) zurück."""
        return self.active_backups.get(plugin_id, {"active": False, "percent": 0})

    def create_backup(self, plugin_id: str, server_dir: str, source_rel_path: str, retention_config: dict = None):
        # Verhindern, dass jemand 5x auf den Button klickt und den Server lahmlegt
        if self.get_progress(plugin_id).get("active"):
            return {"status": "error", "message": "Ein Backup für diesen Server läuft bereits!"}

        source_full_path = os.path.normpath(os.path.join(server_dir, source_rel_path))
        if not os.path.exists(source_full_path):
            return {"status": "error", "message": f"Save-Pfad existiert nicht: {source_full_path}"}

        plugin_backup_dir = os.path.join(self.backups_root, plugin_id)
        os.makedirs(plugin_backup_dir, exist_ok=True)

        plugin_data_dir = os.path.join(self.data_root, plugin_id)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.zip"
        backup_full_path = os.path.join(plugin_backup_dir, backup_filename)

        # Status auf "Aktiv" setzen (0%)
        self.active_backups[plugin_id] = {"active": True, "percent": 0}

        # Den rechenintensiven Zip-Vorgang in einen Hintergrund-Thread auslagern!
        threading.Thread(
            target=self._zip_worker,
            args=(plugin_id, source_full_path, plugin_data_dir, backup_full_path, plugin_backup_dir, retention_config),
            daemon=True
        ).start()

        return {"status": "success", "message": "Das Full-Backup wurde im Hintergrund gestartet!"}

    def _zip_worker(self, plugin_id, game_dir, data_dir, target_zip, backup_dir, retention_config):
        """Der Hintergrund-Arbeiter, der Savegames UND Configs packt."""
        try:
            total_bytes = 0
            files_to_zip = []

            # 1. Game Saves sammeln
            for root, _, files in os.walk(game_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        try:
                            size = os.path.getsize(fp)
                            total_bytes += size
                            arcname = os.path.join("game_save", os.path.relpath(fp, game_dir))
                            files_to_zip.append((fp, arcname, size))
                        except (PermissionError, OSError): pass

            # 2. EmberCore Data (Configs, Mods, Startup) sammeln
            if os.path.exists(data_dir):
                for root, _, files in os.walk(data_dir):
                    for f in files:
                        fp = os.path.join(root, f)
                        if not os.path.islink(fp):
                            try:
                                size = os.path.getsize(fp)
                                total_bytes += size
                                arcname = os.path.join("embercore_data", os.path.relpath(fp, data_dir))
                                files_to_zip.append((fp, arcname, size))
                            except (PermissionError, OSError): pass

            # 3. ZIP Datei erstellen und Fortschritt hochzählen
            processed_bytes = 0
            with zipfile.ZipFile(target_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fp, arcname, size in files_to_zip:
                    try:
                        zf.write(fp, arcname)
                        processed_bytes += size
                        if total_bytes > 0:
                            percent = int((processed_bytes / total_bytes) * 100)
                            self.active_backups[plugin_id]["percent"] = min(percent, 99) 
                    except (PermissionError, OSError) as e:
                        from core.env import logger
                        logger.warning(f"[Backup] Überspringe gesperrte Datei: {fp} ({e})")

            # 4. Alte Backups aufräumen
            self._enforce_retention(backup_dir, retention_config)
            
        except Exception as e:
            from core.env import logger
            logger.error(f"[-] Fehler beim Backup für {plugin_id}: {e}")
            if os.path.exists(target_zip):
                os.remove(target_zip) 
        finally:
            self.active_backups[plugin_id] = {"active": False, "percent": 0}

    def restore_backup(self, plugin_id: str, server_dir: str, source_rel_path: str, filename: str):
        backup_file_path = os.path.join(self.backups_root, plugin_id, filename)
        target_game_dir = os.path.normpath(os.path.join(server_dir, source_rel_path))
        target_data_dir = os.path.join(self.data_root, plugin_id)

        if not os.path.exists(backup_file_path):
            return {"status": "error", "message": "Backup-Datei nicht gefunden."}

        try:
            is_new_format = False
            with zipfile.ZipFile(backup_file_path, 'r') as zip_ref:
                # Prüfen, ob es ein neues Full-Backup (mit Ordnern) ist
                for name in zip_ref.namelist():
                    if name.startswith("game_save/") or name.startswith("game_save\\"):
                        is_new_format = True
                        break

                if is_new_format:
                    # Altes Spiel und Configs löschen, damit es 1:1 identisch wird
                    if os.path.exists(target_game_dir): shutil.rmtree(target_game_dir)
                    if os.path.exists(target_data_dir): shutil.rmtree(target_data_dir)
                    os.makedirs(target_game_dir, exist_ok=True)
                    os.makedirs(target_data_dir, exist_ok=True)

                    for member in zip_ref.infolist():
                        # Spiel-Savegames wiederherstellen
                        if member.filename.startswith("game_save/") or member.filename.startswith("game_save\\"):
                            relative_path = member.filename.split("/", 1)[-1]
                            if not relative_path: continue
                            target_path = os.path.join(target_game_dir, relative_path)
                            if member.is_dir(): os.makedirs(target_path, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                with zip_ref.open(member) as source, open(target_path, "wb") as target:
                                    shutil.copyfileobj(source, target)
                        
                        # EmberCore Configs wiederherstellen
                        elif member.filename.startswith("embercore_data/") or member.filename.startswith("embercore_data\\"):
                            relative_path = member.filename.split("/", 1)[-1]
                            if not relative_path: continue
                            target_path = os.path.join(target_data_dir, relative_path)
                            if member.is_dir(): os.makedirs(target_path, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                with zip_ref.open(member) as source, open(target_path, "wb") as target:
                                    shutil.copyfileobj(source, target)
                else:
                    # Abwärtskompatibilität für Backups aus v0.1.7.x
                    if os.path.exists(target_game_dir): shutil.rmtree(target_game_dir)
                    os.makedirs(target_game_dir, exist_ok=True)
                    zip_ref.extractall(target_game_dir)

            return {"status": "success", "message": f"Full-Backup '{filename}' erfolgreich eingespielt!"}
        except Exception as e:
            return {"status": "error", "message": f"Wiederherstellungs-Fehler: {str(e)}"}

    def delete_backup(self, plugin_id: str, filename: str):
        file_path = os.path.join(self.backups_root, plugin_id, filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return {"status": "success", "message": f"Backup {filename} dauerhaft gelöscht."}
            return {"status": "error", "message": "Backup-Datei existiert nicht."}
        except Exception as e:
            return {"status": "error", "message": f"Lösch-Fehler: {str(e)}"}

    def list_backups(self, plugin_id: str):
        plugin_backup_dir = os.path.join(self.backups_root, plugin_id)
        if not os.path.exists(plugin_backup_dir): return []

        backups = []
        for file in os.listdir(plugin_backup_dir):
            if file.endswith(".zip"):
                file_path = os.path.join(plugin_backup_dir, file)
                stats = os.stat(file_path)
                backups.append({
                    "filename": file,
                    "date": datetime.fromtimestamp(stats.st_mtime).strftime("%d.%m.%Y %H:%M:%S"),
                    "size_mb": round(stats.st_size / (1024 * 1024), 2)
                })
        return sorted(backups, key=lambda x: x['filename'], reverse=True)

    def _enforce_retention(self, backup_dir: str, config: dict):
        """Professioneller IT-Backup Algorithmus (Grandfather-Father-Son)"""
        if not config:
            config = {"keep_latest": 5, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}

        keep_latest = int(config.get("keep_latest", 5))
        keep_daily = int(config.get("keep_daily", 7))
        keep_weekly = int(config.get("keep_weekly", 4))
        keep_monthly = int(config.get("keep_monthly", 3))

        files = [f for f in os.listdir(backup_dir) if f.endswith(".zip")]
        if not files: return

        backups = []
        for f in files:
            try:
                dt_str = f.replace("backup_", "").replace(".zip", "")
                dt = datetime.strptime(dt_str, "%Y%m%d_%H%M%S")
                backups.append({"file": f, "dt": dt, "path": os.path.join(backup_dir, f)})
            except: pass

        backups.sort(key=lambda x: x["dt"], reverse=True)
        to_keep = set()

        for i in range(min(keep_latest, len(backups))): to_keep.add(backups[i]["file"])

        daily_buckets = {}
        for b in backups:
            day_str = b["dt"].strftime("%Y-%m-%d")
            if day_str not in daily_buckets: daily_buckets[day_str] = b
        for day in sorted(daily_buckets.keys(), reverse=True)[:keep_daily]: to_keep.add(daily_buckets[day]["file"])

        weekly_buckets = {}
        for b in backups:
            yr, wk, _ = b["dt"].isocalendar()
            wk_str = f"{yr}-W{wk}"
            if wk_str not in weekly_buckets: weekly_buckets[wk_str] = b
        for wk in sorted(weekly_buckets.keys(), reverse=True)[:keep_weekly]: to_keep.add(weekly_buckets[wk]["file"])

        monthly_buckets = {}
        for b in backups:
            mo_str = b["dt"].strftime("%Y-%m")
            if mo_str not in monthly_buckets: monthly_buckets[mo_str] = b
        for mo in sorted(monthly_buckets.keys(), reverse=True)[:keep_monthly]: to_keep.add(monthly_buckets[mo]["file"])

        for b in backups:
            if b["file"] not in to_keep:
                try: os.remove(b["path"])
                except: pass

    def import_savegame(self, plugin_id: str, server_dir: str, source_rel_path: str, zip_path: str):
        import tempfile
        
        target_game_dir = os.path.normpath(os.path.join(server_dir, source_rel_path))
        target_basename = os.path.basename(source_rel_path.rstrip("/\\"))
        
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                    
                # "Kugelsichere" Suche: Suchen nach dem Ordnernamen (z.B. "SaveGames")
                found_path = None
                for root, dirs, files in os.walk(tmp_dir):
                    if target_basename.lower() in [d.lower() for d in dirs]:
                        # Finde den original case
                        for d in dirs:
                            if d.lower() == target_basename.lower():
                                found_path = os.path.join(root, d)
                                break
                        break
                
                # Wenn nicht gefunden, prüfen ob typische Savegame-Dateien vorhanden sind
                if not found_path:
                    for root, dirs, files in os.walk(tmp_dir):
                        if any(f.endswith('.sav') or f.endswith('.ark') or f.endswith('.db') for f in files):
                            found_path = tmp_dir
                            break
                            
                if not found_path:
                    return {"status": "error", "message": f"Konnte keinen '{target_basename}' Ordner oder typische Save-Dateien (.sav, .ark) in der Zip finden!"}
                
                # Falls Ziel schon existiert, komplett leeren
                if os.path.exists(target_game_dir):
                    shutil.rmtree(target_game_dir)
                
                # Gefundenen Ordner ans Ziel kopieren
                shutil.copytree(found_path, target_game_dir)
                
            return {"status": "success", "message": "Savegame wurde erfolgreich importiert und die Ordnerstruktur korrigiert!"}
        except zipfile.BadZipFile:
            return {"status": "error", "message": "Die hochgeladene Datei ist keine gültige ZIP-Datei."}
        except Exception as e:
            from core.env import logger
            logger.error(f"Import Fehler: {str(e)}")
            return {"status": "error", "message": f"Import fehlgeschlagen: {str(e)}"}
