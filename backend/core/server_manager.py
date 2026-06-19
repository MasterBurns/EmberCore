import psutil
import subprocess
import os
import platform

class ServerManager:
    def __init__(self):
        self.process = None

    def start_server(self, executable_path: str, args: list):
        if self.is_running():
            return {"status": "error", "message": "Ein Server läuft bereits!"}

        if not os.path.exists(executable_path):
            return {"status": "error", "message": f"Datei nicht gefunden: {executable_path}"}

        # --- NEU: Das Arbeitsverzeichnis des Servers ermitteln ---
        working_directory = os.path.dirname(executable_path)
        # --------------------------------------------------------

        current_os = platform.system()
        command = []

        if current_os == "Linux" and executable_path.lower().endswith(".exe"):
            print(f"[*] Linux erkannt. Starte Windows-Binary via Wine im Ordner: {working_directory}")
            command = ["wine", executable_path] + args
        else:
            print(f"[*] Starte nativen Server im Ordner: {working_directory}")
            command = [executable_path] + args

        try:
            # --- NEU: cwd=working_directory zwingt den Prozess in seinen eigenen Ordner ---
            proc = subprocess.Popen(command, cwd=working_directory)
            self.process = psutil.Process(proc.pid)

            return {"status": "success", "message": "Server erfolgreich gestartet", "pid": proc.pid}
        except Exception as e:
            return {"status": "error", "message": f"Startfehler: {str(e)}"}

    def stop_server(self):
        if not self.is_running():
            return {"status": "error", "message": "Es läuft aktuell kein Server."}

        try:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
            return {"status": "success", "message": "Server sauber beendet."}
        except psutil.TimeoutExpired:
            self.process.kill()
            self.process = None
            return {"status": "warning", "message": "Server hat nicht reagiert und wurde hart beendet."}
        except Exception as e:
            return {"status": "error", "message": f"Fehler beim Beenden: {str(e)}"}

    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.is_running() and self.process.status() != psutil.STATUS_ZOMBIE

    def get_stats(self):
        if not self.is_running():
            return {"status": "offline"}

        try:
            return {
                "status": "online",
                "pid": self.process.pid,
                "cpu_percent": self.process.cpu_percent(interval=None),
                "ram_mb": round(self.process.memory_info().rss / (1024 * 1024), 2)
            }
        except psutil.NoSuchProcess:
            self.process = None
            return {"status": "offline"}
