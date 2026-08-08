import os
import urllib.request
import zipfile
import tarfile
import subprocess
import platform

class SteamCMDManager:
    def __init__(self, base_dir="servers"):
        self.base_dir = os.path.abspath(base_dir)
        self.steamcmd_dir = os.path.join(self.base_dir, "steamcmd")

        # Erkennen, welches SteamCMD wir lokal ausführen müssen
        if platform.system() == "Windows":
            self.exe_path = os.path.join(self.steamcmd_dir, "steamcmd.exe")
        else:
            self.exe_path = os.path.join(self.steamcmd_dir, "steamcmd.sh")

    def install_steamcmd_if_missing(self):
        if os.path.exists(self.exe_path):
            return True

        print("[*] SteamCMD nicht gefunden. Lade passende Version herunter...")
        os.makedirs(self.steamcmd_dir, exist_ok=True)

        current_os = platform.system()
        try:
            if current_os == "Windows":
                zip_path = os.path.join(self.steamcmd_dir, "steamcmd.zip")
                urllib.request.urlretrieve("https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip", zip_path)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(self.steamcmd_dir)
                os.remove(zip_path)
            else:
                # Linux (CachyOS) native Tarball laden
                tar_path = os.path.join(self.steamcmd_dir, "steamcmd_linux.tar.gz")
                urllib.request.urlretrieve("https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz", tar_path)
                with tarfile.open(tar_path, "r:gz") as tar_ref:
                    tar_ref.extractall(self.steamcmd_dir)
                os.remove(tar_path)
                # Ausführungsrechte für das Shell-Skript setzen
                os.chmod(self.exe_path, 0o755)

            print("[+] SteamCMD erfolgreich installiert!")
            return True
        except Exception as e:
            print(f"[-] Fehler bei der SteamCMD-Installation: {e}")
            return False

    def install_or_update_app(self, app_id: int, install_dir_name: str, force_windows: bool = False):
        """Lädt einen Server via SteamCMD herunter oder aktualisiert ihn."""
        self.install_steamcmd_if_missing()

        install_dir_abs = os.path.join(self.base_dir, install_dir_name)
        os.makedirs(install_dir_abs, exist_ok=True)

        print(f"[*] Starte Update/Installation von Steam App {app_id} in {install_dir_abs}...")

        # Basis-Befehl zusammenstellen
        cmd = [self.exe_path]

        # Wenn wir auf Linux sind, aber explizit Windows-Dateien wollen (für Wine-Tests)
        if platform.system() != "Windows" and force_windows:
            cmd += ["+@sSteamCmdForcePlatformType", "windows"]

        cmd += [
            "+force_install_dir", install_dir_abs,
            "+login", "anonymous",
            "+app_update", str(app_id),
            "+quit"
        ]

        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        try:
            process = subprocess.run(cmd, creationflags=flags)
            # SteamCMD gibt auf Linux bei Erfolg manchmal Code 0 oder 7 zurück
            if process.returncode in [0, 7]:
                print(f"[+] App {app_id} erfolgreich heruntergeladen/aktualisiert!")
                return {"status": "success", "install_dir": install_dir_abs}
            else:
                return {"status": "error", "message": f"SteamCMD gab Fehlercode {process.returncode} zurück."}
        except Exception as e:
            return {"status": "error", "message": f"SteamCMD Fehler: {e}"}

    def update_workshop_mods(self, plugin_id: str, workshop_appid: str, mods_info: list):
        import platform, subprocess, os
        from core.env import logger
        
        if not mods_info: 
            return
            
        install_dir = os.path.abspath(os.path.join(self.base_dir, plugin_id))
        is_windows = platform.system() == "Windows"
        exe_path = os.path.join(self.base_dir, "steamcmd", "steamcmd.exe" if is_windows else "steamcmd.sh")
        
        if not os.path.exists(exe_path):
            logger.error("[SteamCMD] Fehler: SteamCMD nicht gefunden für Mod-Download!")
            return
            
        # ====== DEIN GEWÜNSCHTER INFO BLOCK ======
        print(f"\n{'#'*60}")
        print(f"### MODS für \"{plugin_id.upper()}\" ###")
        print(f"{'#'*60}")
        print(f"Steam AppID: {workshop_appid}")
        print(f"Status: Lade {len(mods_info)} Mods herunter...")
        for m in mods_info:
            print(f" - [{m.get('id', 'Unbekannt')}] {m.get('name', 'Ohne Namen')}")
        print(f"{'#'*60}\n")
        # =========================================
        
        cmd = [exe_path, "+force_install_dir", install_dir, "+login", "anonymous"]
        for m in mods_info:
            cmd.extend(["+workshop_download_item", str(workshop_appid), str(m.get('id', ''))])
            cmd.append("validate")
        cmd.append("+quit")
        
        flags = subprocess.CREATE_NO_WINDOW if is_windows else 0
        try:
            # Wir leiten die Ausgabe live in deine CMD um!
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, bufsize=1, creationflags=flags
            )
            for line in process.stdout:
                line_clean = line.strip()
                # Um Spam zu vermeiden, zeigen wir nur den Download-Status
                if "Update state" in line_clean or "Success" in line_clean or "ERROR" in line_clean or "Downloading item" in line_clean:
                    print(f"> {line_clean}")
            process.wait()
            print(f"\n[+] Alle Mods erfolgreich verarbeitet!\n{'#'*60}\n")
        except Exception as e:
            logger.error(f"[SteamCMD] Mod-Download fehlgeschlagen: {e}")

    def stream_app_update(self, app_id: int, install_dir_name: str, force_windows: bool = False):
        """Identisch zu install_or_update_app, gibt aber Popen für asynchrones Lesen zurück."""
        self.install_steamcmd_if_missing()

        install_dir_abs = os.path.join(self.base_dir, install_dir_name)
        os.makedirs(install_dir_abs, exist_ok=True)

        cmd = [self.exe_path]
        if platform.system() != "Windows" and force_windows:
            cmd += ["+@sSteamCmdForcePlatformType", "windows"]

        cmd += [
            "+force_install_dir", install_dir_abs,
            "+login", "anonymous",
            "+app_update", str(app_id),
            "+quit"
        ]

        flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, creationflags=flags
            )
            return process
        except Exception as e:
            from core.env import logger
            logger.error(f"[SteamCMD] Start fehlgeschlagen: {e}")
            return None

    def stream_workshop_mods(self, plugin_id: str, workshop_appid: str, mods_info: list):
        """Identisch zu update_workshop_mods, gibt aber Popen für asynchrones Lesen zurück."""
        if not mods_info:
            return None
            
        install_dir = os.path.abspath(os.path.join(self.base_dir, plugin_id))
        is_windows = platform.system() == "Windows"
        exe_path = os.path.join(self.base_dir, "steamcmd", "steamcmd.exe" if is_windows else "steamcmd.sh")
        
        if not os.path.exists(exe_path):
            return None
            
        cmd = [exe_path, "+force_install_dir", install_dir, "+login", "anonymous"]
        for m in mods_info:
            cmd.extend(["+workshop_download_item", str(workshop_appid), str(m.get('id', ''))])
            cmd.append("validate")
        cmd.append("+quit")
        
        flags = subprocess.CREATE_NO_WINDOW if is_windows else 0
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, bufsize=1, creationflags=flags
            )
            return process
        except Exception as e:
            from core.env import logger
            logger.error(f"[SteamCMD] Mod-Download Start fehlgeschlagen: {e}")
            return None