import os
import shutil
from datetime import datetime
import zipfile

class BackupManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.backups_root = os.path.join(self.base_dir, "backups")

    def create_backup(self, plugin_id: str, server_dir: str, source_rel_path: str, retention_config: dict = None):
        source_full_path = os.path.normpath(os.path.join(server_dir, source_rel_path))
        if not os.path.exists(source_full_path):
            return {"status": "error", "message": f"Save-Pfad existiert nicht: {source_full_path}"}

        plugin_backup_dir = os.path.join(self.backups_root, plugin_id)
        os.makedirs(plugin_backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.zip"
        backup_full_path = os.path.join(plugin_backup_dir, backup_filename)

        try:
            shutil.make_archive(base_name=backup_full_path.replace('.zip', ''), format='zip', root_dir=source_full_path)
            # Aufbewahrungsregel anwenden
            self._enforce_retention(plugin_backup_dir, retention_config)
            return {"status": "success", "message": f"Backup erfolgreich erstellt: {backup_filename}"}
        except Exception as e:
            return {"status": "error", "message": f"Backup-Fehler: {str(e)}"}

    def restore_backup(self, plugin_id: str, server_dir: str, source_rel_path: str, filename: str):
        backup_file_path = os.path.join(self.backups_root, plugin_id, filename)
        target_dir = os.path.normpath(os.path.join(server_dir, source_rel_path))
        if not os.path.exists(backup_file_path):
            return {"status": "error", "message": "Backup-Datei nicht gefunden."}
        try:
            if os.path.exists(target_dir): shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)
            with zipfile.ZipFile(backup_file_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
            return {"status": "success", "message": f"Backup '{filename}' erfolgreich eingespielt!"}
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

        # 1. Behalte absolut X Neueste
        for i in range(min(keep_latest, len(backups))):
            to_keep.add(backups[i]["file"])

        # 2. Behalte 1 pro Tag (für X Tage)
        daily_buckets = {}
        for b in backups:
            day_str = b["dt"].strftime("%Y-%m-%d")
            if day_str not in daily_buckets: daily_buckets[day_str] = b
        for day in sorted(daily_buckets.keys(), reverse=True)[:keep_daily]:
            to_keep.add(daily_buckets[day]["file"])

        # 3. Behalte 1 pro Woche (für X Wochen)
        weekly_buckets = {}
        for b in backups:
            yr, wk, _ = b["dt"].isocalendar()
            wk_str = f"{yr}-W{wk}"
            if wk_str not in weekly_buckets: weekly_buckets[wk_str] = b
        for wk in sorted(weekly_buckets.keys(), reverse=True)[:keep_weekly]:
            to_keep.add(weekly_buckets[wk]["file"])

        # 4. Behalte 1 pro Monat (für X Monate)
        monthly_buckets = {}
        for b in backups:
            mo_str = b["dt"].strftime("%Y-%m")
            if mo_str not in monthly_buckets: monthly_buckets[mo_str] = b
        for mo in sorted(monthly_buckets.keys(), reverse=True)[:keep_monthly]:
            to_keep.add(monthly_buckets[mo]["file"])

        # Lösche den verbleibenden Rest
        for b in backups:
            if b["file"] not in to_keep:
                os.remove(b["path"])
                print(f"[*] Housekeeping: Altes Backup gelöscht -> {b['file']}")
