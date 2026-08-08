import os, psutil, time, platform, subprocess, socket, struct, threading, json, shutil
from collections import deque
from core.env import SERVERS_ROOT, DATA_ROOT, logger, sys_config
from core.config_manager import ConfigManager

class DummyStream:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def close(self, *args, **kwargs): pass
    def read(self, *args, **kwargs): return b""

class AdoptedProcess:
    def __init__(self, pid):
        self.pid = pid
        self.ps = psutil.Process(pid)
        self.stdin = DummyStream()
        self.stdout = DummyStream()
        self.stderr = DummyStream()
        self.returncode = None
        self.args = []
    def poll(self):
        try:
            if self.ps.is_running() and self.ps.status() not in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]: return None
            self.returncode = 0; return 0
        except psutil.NoSuchProcess:
            self.returncode = 0; return 0
    def wait(self, timeout=None):
        try: self.ps.wait(timeout)
        except: pass
    def kill(self):
        try:
            for child in self.ps.children(recursive=True):
                try: child.kill()
                except: pass
            self.ps.kill()
        except: pass
    def terminate(self): self.kill()

class ServerManager:
    def __init__(self):
        self.processes = {}
        self.logs = {}

    def _read_output(self, plugin_id, process):
        self.logs[plugin_id] = deque(maxlen=200)
        while True:
            line = process.stdout.readline()
            if not line: break
            try:
                text = line.decode('utf-8', errors='replace').strip()
                if text: self.logs[plugin_id].append(text)
            except: pass

    def get_server_processes(self, plugin_id: str):
        target_procs = {}
        verbose = sys_config.get("verbose_logging", False)
        try:
            base_path = os.path.normcase(os.path.realpath(os.path.join(SERVERS_ROOT, plugin_id)))
            server_dir_clean = base_path if base_path.endswith(os.sep) else base_path + os.sep

            manifest = ConfigManager.load_manifest(plugin_id)
            target_ports = []
            if manifest and "network_meta" in manifest and "ports" in manifest["network_meta"]:
                for p_info in manifest["network_meta"]["ports"]:
                    if "port" in p_info: target_ports.append(int(p_info["port"]))

            if target_ports:
                try:
                    for conn in psutil.net_connections(kind='all'):
                        if conn.laddr and conn.laddr.port in target_ports and conn.pid:
                            if conn.pid not in target_procs:
                                try:
                                    proc = psutil.Process(conn.pid)
                                    p_name_check = str(proc.name() or '').lower()
                                    if p_name_check not in ["steamcmd.exe", "embercore.exe", "python.exe"]:
                                        server_dir_clean = os.path.normcase(os.path.realpath(os.path.join(SERVERS_ROOT, plugin_id)))
                                        server_dir_clean = server_dir_clean if server_dir_clean.endswith(os.sep) else server_dir_clean + os.sep
                                        matched = False
                                        try:
                                            exe = proc.exe()
                                            if exe:
                                                exe_path = os.path.normcase(os.path.realpath(exe))
                                                if exe_path.startswith(server_dir_clean): matched = True
                                        except: pass
                                        if not matched:
                                            try:
                                                cwd = proc.cwd()
                                                if cwd:
                                                    cwd_path = os.path.normcase(os.path.realpath(cwd))
                                                    cwd_path = cwd_path if cwd_path.endswith(os.sep) else cwd_path + os.sep
                                                    if cwd_path.startswith(server_dir_clean): matched = True
                                            except: pass
                                        
                                        if matched:
                                            target_procs[proc.pid] = proc
                                except: pass
                except: pass

            if plugin_id in self.processes:
                try:
                    parent_proc = psutil.Process(self.processes[plugin_id].pid)
                    if parent_proc.is_running() and parent_proc.status() not in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                        target_procs[parent_proc.pid] = parent_proc
                except psutil.NoSuchProcess: del self.processes[plugin_id]

            for p in psutil.process_iter(['pid', 'exe', 'cwd', 'name', 'cmdline']):
                if p.info['pid'] in target_procs: continue
                try:
                    p_name = str(p.info.get('name') or '').lower()
                    if p_name in ["embercore.exe", "python.exe", "cmd.exe", "conhost.exe", "embercoreservice.exe", "winsw-x64.exe", "explorer.exe", "svchost.exe", "system idle process", "steamcmd.exe", "steamerrorreporter.exe", "steamerrorreporter64.exe"]:
                        continue

                    matched = False
                    exe = p.info.get('exe')
                    cwd = p.info.get('cwd')
                    cmdline = p.info.get('cmdline')

                    server_dir_clean = os.path.normcase(os.path.realpath(os.path.join(SERVERS_ROOT, plugin_id)))
                    server_dir_clean = server_dir_clean if server_dir_clean.endswith(os.sep) else server_dir_clean + os.sep

                    if exe:
                        exe_path = os.path.normcase(os.path.realpath(exe))
                        if exe_path.startswith(server_dir_clean): matched = True
                    if not matched and cwd:
                        cwd_path = os.path.normcase(os.path.realpath(cwd))
                        cwd_path = cwd_path if cwd_path.endswith(os.sep) else cwd_path + os.sep
                        if cwd_path.startswith(server_dir_clean): matched = True
                    if not matched and cmdline:
                        cmd_safe = [str(x) for x in cmdline if x is not None]
                        cmd_str = " ".join(cmd_safe).lower()
                        if f"servers/{plugin_id}/".lower() in cmd_str or f"servers\\{plugin_id}\\".lower() in cmd_str: matched = True

                    if matched: target_procs[p.info['pid']] = psutil.Process(p.info['pid'])
                except: pass

            all_procs = {}
            for pid, proc in target_procs.items():
                all_procs[pid] = proc
                try:
                    for child in proc.children(recursive=True): all_procs[child.pid] = child
                except: pass
            return all_procs
        except Exception as e: logger.error(f"[Recovery] Fehler im Haupt-Scanner: {e}")
        return target_procs

    def is_server_online(self, plugin_id: str) -> bool:
        procs = self.get_server_processes(plugin_id)
        if procs:
            if plugin_id not in self.processes:
                main_pid = min(procs.keys())
                self.processes[plugin_id] = AdoptedProcess(main_pid)
                logger.info(f"[Recovery] Server '{plugin_id}' erfolgreich im OS abgefangen! (Haupt-PID: {main_pid})")
            return True
        else:
            if plugin_id in self.processes: del self.processes[plugin_id]
            return False

    def start_server(self, plugin_id: str, executable_path: str, args: list):
        if self.is_server_online(plugin_id): return {"status": "error", "message": "Läuft bereits"}
        ConfigManager.apply_desired_config(plugin_id)
        cwd = os.path.dirname(executable_path)
        
        # SteamAPI Fix: Unreal Engine / SteamCMD Servers often need steamclient64.dll next to the executable
        # SteamCMD downloads it to the server root, but the exe is often in Binaries/Win64
        server_root = os.path.normcase(os.path.realpath(os.path.join(SERVERS_ROOT, plugin_id)))
        steamclient_src = os.path.join(server_root, "steamclient64.dll")
        steamclient_dst = os.path.join(cwd, "steamclient64.dll")
        if os.path.exists(steamclient_src) and not os.path.exists(steamclient_dst):
            try:
                shutil.copy2(steamclient_src, steamclient_dst)
                logger.info(f"[*] Kopiere steamclient64.dll nach {cwd} (Steam Browser Fix)")
            except Exception as e:
                logger.error(f"[!] Fehler beim Kopieren von steamclient64.dll: {e}")
                
        # Check if user wants an external console
        show_external_console = False
        startup_file = os.path.join(DATA_ROOT, plugin_id, "startup.json")
        if os.path.exists(startup_file):
            try:
                import json
                with open(startup_file, "r") as f:
                    show_external_console = json.load(f).get("show_external_console", False)
            except: pass

        try:
            startupinfo = None
            if platform.system() == "Windows":
                if show_external_console:
                    # CREATE_NEW_CONSOLE spawns the application in a new visible window. 
                    # Note: We can't reliably pipe stdout and stderr if it's in a new console for some UE apps,
                    # but we will try anyway. The user requested to see the external console.
                    flags = subprocess.CREATE_NEW_CONSOLE
                    p = subprocess.Popen([executable_path] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True, bufsize=1, creationflags=flags)
                else:
                    # DO NOT use CREATE_NO_WINDOW (0x08000000) for Unreal Engine servers!
                    # It breaks Steam Sockets/Networking. Use STARTUPINFO with SW_HIDE instead.
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    p = subprocess.Popen([executable_path] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True, bufsize=1, startupinfo=startupinfo)
            else:
                p = subprocess.Popen([executable_path] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True, bufsize=1)
            
            self.processes[plugin_id] = p
            self.logs[plugin_id] = deque(maxlen=200)

            def read_output(proc, pid):
                for line in iter(proc.stdout.readline, ''):
                    if line: self.logs[pid].append(line.strip())
                proc.stdout.close()

            threading.Thread(target=read_output, args=(p, plugin_id), daemon=True).start()
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Fehler beim Starten: {e}")
            return {"status": "error", "message": str(e)}

    def stop_server(self, plugin_id: str):
        logger.info(f"[-] Stoppen von Server '{plugin_id}' angefordert...")
        procs = self.get_server_processes(plugin_id)
        if not procs:
            if plugin_id in self.processes: del self.processes[plugin_id]
            return {"status": "success"}

        manifest = ConfigManager.load_manifest(plugin_id)
        graceful = False

        if manifest and "shutdown" in manifest and "rcon" in manifest["shutdown"]:
            rcon_meta = manifest["shutdown"]["rcon"]
            try:
                live_cfg = ConfigManager.parse_live_config(os.path.join(SERVERS_ROOT, plugin_id, rcon_meta.get("config_path", "")))
                port_key = rcon_meta.get("port_key", "RconPort")
                
                # Port Fallback Candidates
                port_candidates = []
                p1 = live_cfg.get(port_key)
                if p1: port_candidates.append(int(p1))
                p2 = rcon_meta.get("port")
                if p2: port_candidates.append(int(p2))
                port_candidates.extend([27020, 27015])
                
                ports_to_try = []
                for p in port_candidates:
                    if p not in ports_to_try: ports_to_try.append(p)
                
                password = rcon_meta.get("default_password", "")
                if "password_key" in rcon_meta: password = live_cfg.get(rcon_meta["password_key"], password)
                cmd = rcon_meta.get("command", "CloseServer")

                def build_rcon_packet(pkt_id, pkt_type, body):
                    payload = struct.pack('<ii', pkt_id, pkt_type) + body.encode('utf-8') + b'\x00\x00'
                    return struct.pack('<i', len(payload)) + payload

                for port in ports_to_try:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
                            # Sende Auth
                            s.sendall(build_rcon_packet(1, 3, password))
                            
                            resp = s.recv(4096)
                            if len(resp) < 12: raise Exception("Incomplete auth response")
                            resp_len, resp_id, resp_type = struct.unpack('<iii', resp[:12])
                            
                            # Server schickt manchmal ein leeres Response-Paket voraus
                            if resp_type != 2:
                                resp = s.recv(4096)
                                if len(resp) < 12: raise Exception("Incomplete auth response 2")
                                resp_len, resp_id, resp_type = struct.unpack('<iii', resp[:12])
                                
                            if resp_type != 2 or resp_id == -1:
                                raise Exception("RCON Auth fehlgeschlagen")
                                
                            logger.info(f"[*] RCON Auth auf Port {port} erfolgreich.")
                            
                            # Optional: Vor DoExit erst SaveWorld senden
                            s.sendall(build_rcon_packet(2, 2, "SaveWorld"))
                            time.sleep(2)
                            
                            # Sende eigentlichen Shutdown Befehl
                            s.sendall(build_rcon_packet(3, 2, cmd))
                            logger.info(f"[+] RCON '{cmd}' erfolgreich gesendet.")
                            graceful = True
                            break
                    except Exception as e:
                        logger.debug(f"RCON Versuch auf Port {port} fehlgeschlagen: {e}")
            except Exception as e: logger.warning(f"[!] RCON Fehler: {e}")

        if not graceful:
            logger.info("[Recovery] Sende Soft-Kill...")
            for pid, p in procs.items():
                try: p.terminate()
                except: pass
                if platform.system() == "Windows": subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

        grace_seconds = manifest.get("shutdown", {}).get("grace_seconds", 120) if manifest else 120
        for i in range(grace_seconds):
            if not any(p.is_running() and p.status() not in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD] for p in procs.values()): break
            if i > 0 and i % 15 == 0: logger.info(f"[*] Warte auf sauberes Beenden ({i}s / {grace_seconds}s)...")
            time.sleep(1)

        if any(p.is_running() and p.status() not in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD] for p in procs.values()):
            logger.warning("[!] Ziehe Hard-Kill Notbremse...")
            for pid, p in procs.items():
                if p.is_running() and p.status() not in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                    try:
                        for child in p.children(recursive=True): child.kill()
                        p.kill()
                    except: pass
                    if platform.system() == "Windows": subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

        if plugin_id in self.processes:
            try: self.processes[plugin_id].terminate()
            except: pass
            del self.processes[plugin_id]

        return {"status": "success"}

    def get_stats(self, plugin_id):
        data = {"status": "offline", "cpu_percent": 0.0, "ram_mb": 0.0}
        if self.is_server_online(plugin_id):
            data["status"] = "online"
            try:
                target_procs = self.get_server_processes(plugin_id)
                if target_procs:
                    total_ram = 0
                    valid_procs = []
                    for p in target_procs.values():
                        try:
                            total_ram += p.memory_info().rss
                            p.cpu_percent(interval=None)
                            valid_procs.append(p)
                        except: pass

                    if valid_procs:
                        time.sleep(0.1)
                        total_cpu = sum((p.cpu_percent(interval=None) / psutil.cpu_count()) for p in valid_procs)
                        data["ram_mb"] = round(total_ram / (1024 * 1024), 2)
                        data["cpu_percent"] = round(total_cpu, 1)
            except: pass
        return data

# Instanzieren und exportieren
server_manager = ServerManager()
