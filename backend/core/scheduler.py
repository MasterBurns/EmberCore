import asyncio
import os
import json
from datetime import datetime, timedelta

class BackupScheduler:
    def __init__(self, base_dir, backup_manager):
        self.base_dir = base_dir
        self.backup_manager = backup_manager
        self.plugins_dir = os.path.join(self.base_dir, "plugins")

    async def start_loop(self):
        print("[*] EmberCore Backup-Zeitplaner (Multi-Schedule) gestartet.")
        while True:
            try:
                await self._check_and_run_backups()
            except Exception as e:
                print(f"[-] Fehler im Scheduler-Loop: {e}")
            await asyncio.sleep(60)

    async def _check_and_run_backups(self):
        if not os.path.exists(self.plugins_dir): return

        for plugin_id in os.listdir(self.plugins_dir):
            plugin_path = os.path.join(self.plugins_dir, plugin_id)
            if not os.path.isdir(plugin_path): continue

            schedule_file = os.path.join(plugin_path, "backup_schedule.json")
            if not os.path.exists(schedule_file): continue

            with open(schedule_file, "r", encoding="utf-8") as f:
                config = json.load(f)

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
                print(f"[+] Scheduler: Führe zeitgesteuertes Backup für '{plugin_id}' aus...")
                manifest_path = os.path.join(plugin_path, "manifest.yaml")
                if os.path.exists(manifest_path):
                    import yaml
                    with open(manifest_path, "r", encoding="utf-8") as mf:
                        manifest = yaml.safe_load(mf)
                    backup_config = manifest.get("backup")
                    if backup_config:
                        server_dir = os.path.join(self.base_dir, "servers", plugin_id)
                        self.backup_manager.create_backup(plugin_id, server_dir, backup_config.get("source_path"), retention)

            if schedules_updated:
                with open(schedule_file, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
