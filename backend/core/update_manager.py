import os, sys, platform, subprocess, asyncio, urllib.request, zipfile, tarfile, io, httpx, shutil
from core.env import EXE_DIR, SERVERS_ROOT, IS_COMPILED, logger

class UpdateManager:
    async def prepare_steamcmd(self):
        steam_dir = os.path.join(SERVERS_ROOT, "steamcmd")
        os.makedirs(steam_dir, exist_ok=True)
        is_windows = platform.system() == "Windows"
        exe_path = os.path.join(steam_dir, "steamcmd.exe" if is_windows else "steamcmd.sh")
        if not os.path.exists(exe_path):
            url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip" if is_windows else "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
            try:
                logger.info("Lade SteamCMD herunter...")
                async with httpx.AsyncClient() as client:
                    res = await client.get(url, follow_redirects=True, timeout=60.0)
                    if res.status_code == 200:
                        if is_windows:
                            with zipfile.ZipFile(io.BytesIO(res.content)) as z: z.extractall(steam_dir)
                        else:
                            with tarfile.open(fileobj=io.BytesIO(res.content), mode="r:gz") as tar: tar.extractall(steam_dir)
            except Exception as e:
                logger.error(f"Fehler beim Download von SteamCMD: {e}")

    async def check_system_update(self, current_version):
        if not IS_COMPILED:
            try:
                subprocess.run(["git", "fetch"], cwd=EXE_DIR, check=True)
                status = subprocess.run(["git", "status", "-uno"], cwd=EXE_DIR, capture_output=True, text=True)
                return {"update_available": "Your branch is behind" in status.stdout}
            except: return {"update_available": False}
        else:
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get("https://raw.githubusercontent.com/MasterBurns/EmberCore/main/version.json", timeout=5.0)
                    if res.status_code == 200:
                        remote_data = res.json()
                        remote_version = remote_data[0].get("version", "") if isinstance(remote_data, list) else remote_data.get("version", "")
                        return {"update_available": remote_version != current_version}
            except: pass
            return {"update_available": False}

    async def process_update(self):
        flag_path = os.path.join(EXE_DIR, ".update_reboot")
        if not IS_COMPILED:
            try:
                subprocess.run(["git", "fetch"], cwd=EXE_DIR, check=True)
                pull_result = subprocess.run(["git", "pull"], cwd=EXE_DIR, capture_output=True, text=True)
                if "Already up to date." in pull_result.stdout: return {"status": "info", "message": "Bereits aktuell."}
                with open(flag_path, "w") as f: f.write("1")
                async def restart():
                    await asyncio.sleep(1.0)
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                asyncio.create_task(restart())
                return {"status": "success", "message": "Neustart läuft..."}
            except Exception as e: return {"status": "error", "message": str(e)}
        else:
            is_linux = platform.system() == "Linux"
            ext = "tar.gz" if is_linux else "zip"
            os_prefix = "EmberCore_Linux" if is_linux else "EmberCore_Windows"
            exe_url = None

            try:
                async with httpx.AsyncClient() as client:
                    api_res = await client.get("https://api.github.com/repos/MasterBurns/EmberCore/releases/latest", timeout=10.0)
                    if api_res.status_code == 200:
                        for asset in api_res.json().get("assets", []):
                            name = asset.get("name", "")
                            if name.startswith(os_prefix) and name.endswith(ext) and "Setup" not in name:
                                exe_url = asset.get("browser_download_url")
                                break
            except Exception as e:
                return {"status": "error", "message": f"Fehler bei GitHub API Abfrage: {str(e)}"}

            if not exe_url:
                return {"status": "error", "message": f"Kein passendes Update-Paket ({os_prefix}...{ext}) im neuesten Release gefunden!"}

            archive_path = os.path.join(EXE_DIR, f"EmberCore_update.{ext}")
            current_exe_path = sys.executable

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(exe_url, timeout=60.0, follow_redirects=True)
                    if response.status_code == 200:
                        with open(archive_path, "wb") as f: f.write(response.content)
                    else:
                        return {"status": "error", "message": f"Download gescheitert (HTTP {response.status_code})!\nURL: {exe_url}"}

                with open(flag_path, "w") as f: f.write("1")

                if is_linux:
                    script_path = os.path.join(EXE_DIR, "update_worker.sh")
                    with open(script_path, "w", encoding="utf-8") as f:
                        f.write("#!/bin/bash\n")
                        f.write("sleep 2\n")
                        if "--service" in sys.argv:
                            f.write("systemctl stop embercore.service\n")
                        f.write(f"tar -xzf '{archive_path}' -C '{EXE_DIR}'\n")
                        f.write(f"rm -f '{archive_path}'\n")
                        if "--service" in sys.argv:
                            f.write("systemctl start embercore.service\n")
                        else:
                            f.write(f"nohup '{current_exe_path}' {' '.join(sys.argv[1:])} > /dev/null 2>&1 &\n")
                        f.write(f"rm -f '{script_path}'\n")
                    os.chmod(script_path, 0o755)
                    subprocess.Popen(["bash", script_path], cwd=EXE_DIR, start_new_session=True)
                else:
                    batch_path = os.path.join(EXE_DIR, "update_worker.bat")
                    with open(batch_path, "w", encoding="ascii") as f:
                        f.write("@echo off\n")
                        f.write("echo [EmberCore Updater] Warte auf Beendigung des Hauptprozesses...\n")
                        f.write("timeout /t 2 /nobreak > nul\n")
                        
                        f.write("echo [EmberCore Updater] Beende Dienste und blockierende Prozesse...\n")
                        f.write("net stop EmberCore > nul 2>&1\n")
                        f.write("sc stop EmberCore > nul 2>&1\n")
                        f.write("timeout /t 2 /nobreak > nul\n")
                        
                        # FIX: Aggressiver Tree-Kill für ALLE EmberCore Prozesse (Zombies!)
                        f.write("echo [EmberCore Updater] Raeume Zombie-Prozesse ab...\n")
                        f.write("taskkill /F /T /IM EmberCore.exe > nul 2>&1\n")
                        f.write("taskkill /F /T /IM EmberCoreService.exe > nul 2>&1\n")
                        f.write(f"taskkill /F /T /IM \"{os.path.basename(current_exe_path)}\" > nul 2>&1\n")
                        f.write("timeout /t 3 /nobreak > nul\n")
                        
                        f.write("echo [EmberCore Updater] Entpacke neues Update...\n")
                        f.write(f"powershell -command \"Expand-Archive -Force '{archive_path}' '{EXE_DIR}'\" > nul 2>&1\n")
                        f.write(f"del /f /q \"{archive_path}\"\n")
                        
                        f.write("echo [EmberCore Updater] Starte System neu...\n")
                        if "--service" in sys.argv:
                            f.write(f"sc start EmberCore > nul 2>&1\n")
                        else:
                            f.write(f"start \"\" \"{current_exe_path}\" {' '.join(sys.argv[1:])}\n")
                        f.write("del \"%~f0\"\n")
                    
                    # Batch-Datei komplett losgelöst vom Hauptprozess starten
                    subprocess.Popen([batch_path], cwd=EXE_DIR, creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)

                async def kill_switch():
                    await asyncio.sleep(1.0)
                    os._exit(0)
                asyncio.create_task(kill_switch())
                return {"status": "success", "message": "Update erfolgreich heruntergeladen. Führe Neustart aus..."}
            except Exception as e:
                return {"status": "error", "message": str(e)}

    def install_system_service(self):
        is_linux = platform.system() == "Linux"
        exe_path = os.path.abspath(sys.executable if IS_COMPILED else sys.argv[0])

        try:
            if is_linux:
                import pwd
                current_user = pwd.getpwuid(os.getuid()).pw_name
                cmd_args = f"{exe_path} --service" if IS_COMPILED else f"{sys.executable} {exe_path} --service"
                service_content = f"[Unit]\nDescription=EmberCore Game Server Panel\nAfter=network.target\n\n[Service]\nType=simple\nUser={current_user}\nWorkingDirectory={EXE_DIR}\nExecStart={cmd_args}\nRestart=always\nRestartSec=15\n\n[Install]\nWantedBy=multi-user.target\n"

                if os.geteuid() != 0:
                    script_path = os.path.join(EXE_DIR, "install_service.sh")
                    with open(script_path, "w") as f:
                        f.write("#!/bin/bash\n")
                        f.write("cat << 'EOF' > /etc/systemd/system/embercore.service\n")
                        f.write(service_content)
                        f.write("EOF\n")
                        f.write("systemctl daemon-reload\n")
                        f.write("systemctl enable embercore.service\n")
                        f.write("systemctl start embercore.service\n")
                        f.write("echo 'EmberCore Service erfolgreich installiert und gestartet!'\n")
                    os.chmod(script_path, 0o755)
                    return {"status": "info", "message": "Fehlende Root-Rechte! Es wurde eine Datei 'install_service.sh' im Ordner erstellt. Bitte beende EmberCore und führe 'sudo bash ./install_service.sh' aus."}

                with open("/etc/systemd/system/embercore.service", "w") as f: f.write(service_content)
                subprocess.run(["systemctl", "daemon-reload"])
                subprocess.run(["systemctl", "enable", "embercore.service"])
                return {"status": "success", "message": "EmberCore wurde als systemd-Service installiert!"}
            else:
                winsw_url = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
                svc_exe = os.path.join(EXE_DIR, "EmberCoreService.exe")
                svc_xml = os.path.join(EXE_DIR, "EmberCoreService.xml")

                if not os.path.exists(svc_exe):
                    try:
                        req = urllib.request.Request(winsw_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=30) as response, open(svc_exe, 'wb') as out_file:
                            shutil.copyfileobj(response, out_file)
                    except Exception as e:
                        return {"status": "error", "message": f"Konnte WinSW Service-Wrapper nicht herunterladen: {e}"}

                def escape_xml(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                executable_path = escape_xml(os.path.abspath(sys.executable))
                working_dir = escape_xml(EXE_DIR)

                if IS_COMPILED:
                    arguments = "--service"
                else:
                    script_path = escape_xml(os.path.abspath(sys.argv[0]))
                    arguments = f'"{script_path}" --service'

                xml_content = f"<service>\n  <id>EmberCore</id>\n  <name>EmberCore</name>\n  <description>EmberCore Game Server Panel Background Service</description>\n  <executable>{executable_path}</executable>\n  <arguments>{arguments}</arguments>\n  <log mode=\"roll\"></log>\n  <workingdirectory>{working_dir}</workingdirectory>\n  <onfailure action=\"restart\" delay=\"10 sec\"/>\n  <startmode>DelayedAuto</startmode>\n</service>"

                with open(svc_xml, "w", encoding="utf-8") as f: f.write(xml_content)

                ps_script = os.path.join(EXE_DIR, "install_service.ps1")
                with open(ps_script, "w", encoding="utf-8") as f:
                    f.write("Unregister-ScheduledTask -TaskName 'EmberCoreDaemon' -Confirm:$false -ErrorAction SilentlyContinue\n")
                    f.write(f"& '{svc_exe}' install\n")
                    f.write(f"& '{svc_exe}' start\n")

                import ctypes
                if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                    ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
                    subprocess.run(["powershell", "-Command", ps_cmd])
                    return {"status": "info", "message": "Bitte das Windows Admin-Schild bestätigen. EmberCore lädt den Wrapper und registriert sich als ECHTER Windows Dienst!"}
                else:
                    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script], check=True, stdout=subprocess.DEVNULL)
                    return {"status": "success", "message": "Echter Windows-Dienst erfolgreich installiert!"}
        except Exception as e:
            return {"status": "error", "message": f"Konnte Service nicht erstellen: {e}"}

    def uninstall_system_service(self):
        if platform.system() == "Linux":
            if os.geteuid() != 0:
                script_path = os.path.join(EXE_DIR, "uninstall_service.sh")
                with open(script_path, "w") as f:
                    f.write("#!/bin/bash\nsystemctl stop embercore.service\nsystemctl disable embercore.service\nrm -f /etc/systemd/system/embercore.service\nsystemctl daemon-reload\necho 'Service erfolgreich entfernt!'\n")
                os.chmod(script_path, 0o755)
                return {"status": "info", "message": "Fehlende Root-Rechte! Es wurde eine Datei 'uninstall_service.sh' erstellt. Bitte mit 'sudo bash ./uninstall_service.sh' ausführen."}
            try:
                subprocess.run(["systemctl", "stop", "embercore.service"])
                subprocess.run(["systemctl", "disable", "embercore.service"])
                if os.path.exists("/etc/systemd/system/embercore.service"): os.remove("/etc/systemd/system/embercore.service")
                subprocess.run(["systemctl", "daemon-reload"])
                return {"status": "success", "message": "Service erfolgreich entfernt."}
            except Exception as e: return {"status": "error", "message": str(e)}
        else:
            import ctypes
            svc_exe = os.path.join(EXE_DIR, "EmberCoreService.exe")
            ps_script = os.path.join(EXE_DIR, "uninstall_service.ps1")
            with open(ps_script, "w", encoding="utf-8") as f:
                f.write("Unregister-ScheduledTask -TaskName 'EmberCoreDaemon' -Confirm:$false -ErrorAction SilentlyContinue\n")
                f.write(f"if (Test-Path '{svc_exe}') {{ & '{svc_exe}' stop; & '{svc_exe}' uninstall }}\n")
                f.write(f"Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -match '--service' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\n")

            if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
                subprocess.run(["powershell", "-Command", ps_cmd])
                return {"status": "info", "message": "Windows UAC-Fenster geöffnet. Bitte bestätigen, um den Service restlos zu entfernen!"}
            else:
                try:
                    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script], check=True)
                    return {"status": "success", "message": "Windows Service erfolgreich entfernt."}
                except Exception as e: return {"status": "error", "message": "Konnte Dienst nicht löschen."}

    def start_system_service(self):
        try:
            if platform.system() == "Linux":
                if os.geteuid() != 0:
                    return {"status": "info", "message": "Bitte nutze 'sudo systemctl start embercore.service' in der Konsole, um den Dienst zu starten."}
                subprocess.run(["systemctl", "start", "embercore.service"])
            else:
                import ctypes
                svc_exe = os.path.join(EXE_DIR, "EmberCoreService.exe")
                ps_script = os.path.join(EXE_DIR, "start_service.ps1")
                with open(ps_script, "w", encoding="utf-8") as f:
                    f.write(f"if (Test-Path '{svc_exe}') {{ & '{svc_exe}' start }}\n")

                if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                    ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
                    subprocess.run(["powershell", "-Command", ps_cmd])
                else:
                    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script])
            return {"status": "success", "message": "Service-Start wurde im Hintergrund angefordert."}
        except Exception as e: return {"status": "error", "message": str(e)}

    def stop_system_service(self):
        try:
            if platform.system() == "Linux":
                if os.geteuid() != 0:
                    return {"status": "info", "message": "Bitte nutze 'sudo systemctl stop embercore.service' in der Konsole, um den Dienst zu stoppen."}
                subprocess.run(["systemctl", "stop", "embercore.service"])
            else:
                import ctypes
                svc_exe = os.path.join(EXE_DIR, "EmberCoreService.exe")
                ps_script = os.path.join(EXE_DIR, "stop_service.ps1")
                with open(ps_script, "w", encoding="utf-8") as f:
                    f.write(f"if (Test-Path '{svc_exe}') {{ & '{svc_exe}' stop }}\n")
                    f.write(f"Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -match '--service' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\n")

                if ctypes.windll.shell32.IsUserAnAdmin() == 0:
                    ps_cmd = f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -WindowStyle Hidden -File \"{ps_script}\"' -Verb RunAs"
                    subprocess.run(["powershell", "-Command", ps_cmd])
                else:
                    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script])
            return {"status": "success", "message": "Service-Stopp wurde angefordert."}
        except Exception as e: return {"status": "error", "message": str(e)}

update_manager = UpdateManager()
