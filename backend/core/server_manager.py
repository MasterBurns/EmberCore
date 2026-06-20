import psutil
import subprocess
import os
import platform
import threading
from collections import deque

class ServerManager:
    def __init__(self):
        self.processes = {}
        # NEU: Speichert die letzten 200 Zeilen der Konsolenausgabe pro Server
        self.logs = {}

    def start_server(self, plugin_id: str, executable_path: str, args: list):
        if self.is_running(plugin_id):
            return {"status": "error", "message": "Dieser Server läuft bereits!"}

        if not os.path.exists(executable_path):
            return {"status": "error", "message": f"Datei nicht gefunden: {executable_path}"}

        working_directory = os.path.dirname(executable_path)
        current_os = platform.system()
        command = []

        if current_os == "Linux" and executable_path.lower().endswith(".exe"):
            print(f"[*] Linux erkannt. Starte Windows-Binary via Wine in: {working_directory}")
            command = ["wine", executable_path] + args
        else:
            print(f"[*] Starte nativen Server in: {working_directory}")
            command = [executable_path] + args

        # Log-Puffer (Deque behält automatisch nur die neuesten 200 Einträge)
        self.logs[plugin_id] = deque(maxlen=200)

        try:
            # WICHTIG: stdout=subprocess.PIPE fängt die Ausgaben ab anstatt sie zu ignorieren
            proc = subprocess.Popen(
                command,
                cwd=working_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.processes[plugin_id] = psutil.Process(proc.pid)

            # Hintergrund-Thread, der die Ausgaben live in den Puffer schreibt
            def read_output(p, p_id):
                for line in iter(p.stdout.readline, ''):
                    if p_id in self.logs:
                        self.logs[p_id].append(line.rstrip('\n'))
                p.stdout.close()

            t = threading.Thread(target=read_output, args=(proc, plugin_id), daemon=True)
            t.start()

            return {"status": "success", "message": "Server erfolgreich gestartet", "pid": proc.pid}
        except Exception as e:
            return {"status": "error", "message": f"Startfehler: {str(e)}"}

    def stop_server(self, plugin_id: str):
        if not self.is_running(plugin_id):
            return {"status": "error", "message": "Der Server läuft aktuell nicht."}

        proc = self.processes[plugin_id]
        try:
            proc.terminate()
            proc.wait(timeout=5)
            del self.processes[plugin_id]
            return {"status": "success", "message": "Server sauber beendet."}
        except psutil.TimeoutExpired:
            proc.kill()
            del self.processes[plugin_id]
            return {"status": "warning", "message": "Server hat nicht reagiert und wurde hart beendet."}
        except Exception as e:
            return {"status": "error", "message": f"Fehler beim Beenden: {str(e)}"}

    def is_running(self, plugin_id: str) -> bool:
        proc = self.processes.get(plugin_id)
        if proc is None:
            return False
        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
            return True
        else:
            del self.processes[plugin_id]
            return False

    def get_stats(self, plugin_id: str):
        if not self.is_running(plugin_id):
            return {"status": "offline", "cpu_percent": 0, "ram_mb": 0}

        proc = self.processes[plugin_id]
        try:
            return {
                "status": "online",
                "pid": proc.pid,
                "cpu_percent": proc.cpu_percent(interval=None),
                "ram_mb": round(proc.memory_info().rss / (1024 * 1024), 2)
            }
        except psutil.NoSuchProcess:
            del self.processes[plugin_id]
            return {"status": "offline", "cpu_percent": 0, "ram_mb": 0}
