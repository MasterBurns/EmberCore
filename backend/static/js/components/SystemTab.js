import { store, api, formatUptime } from '../store.js';

export default {
    setup() { 
        return { store, api, formatUptime }; 
    },
    data() {
        return { discoveredInstances: [], isDiscovering: false, discoveryTried: false };
    },
    template: `
    <div class="max-w-5xl mx-auto space-y-6">

        <div class="flex justify-between items-center bg-gray-950 p-5 rounded-xl border border-gray-900 shadow-md">
            <div>
                <h1 class="text-2xl font-black text-white tracking-wide truncate">EmberCore Hintergrund-Dienste</h1>
                <p class="text-sm text-gray-500 font-mono mt-1">Version: <span class="text-gray-400">{{ store.systemInfo?.version || 'Lade...' }}</span></p>
            </div>

            <div class="flex items-center gap-3">
                <button @click="api.triggerSystemUpdate()" :disabled="store.isSystemUpdating" class="h-10 px-5 rounded-lg font-bold transition cursor-pointer text-sm flex items-center justify-center bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-500 text-white shadow-sm">
                    {{ store.isSystemUpdating ? 'Suche Update...' : '🔄 Update prüfen' }}
                </button>
                <button @click="shutdownEmberCore" class="h-10 px-5 rounded-lg font-bold transition cursor-pointer text-sm flex items-center justify-center bg-red-600 hover:bg-red-500 text-white shadow-sm gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path>
                    </svg>
                    EmberCore stoppen
                </button>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">

            <div class="space-y-6">
                
                <div class="bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl space-y-5">
                    <h3 class="text-sm font-bold text-white uppercase tracking-wider border-b border-gray-900 pb-2">🩺 Watchdog & Heartbeat Monitor</h3>

                    <div class="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-900/50">
                        <div>
                            <p class="text-sm font-bold text-white">Haupt-Prozess (EmberCore)</p>
                            <p class="text-[10px] text-gray-500">FastAPI & Background Tasks</p>
                        </div>
                        <span class="text-green-400 font-mono text-sm font-bold">Aktiv (PID: {{ store.systemServiceStats?.main_pid || '?' }})</span>
                    </div>

                    <div class="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-900/50">
                        <div>
                            <p class="text-sm font-bold text-white">Watchdog-Daemon</p>
                            <p class="text-[10px] text-gray-500">Hang-Detection & OS Recovery</p>
                        </div>
                        <span :class="store.systemServiceStats?.watchdog_active ? 'text-green-400' : 'text-red-500'" class="font-mono text-sm font-bold">{{ store.systemServiceStats?.watchdog_active ? 'Aktiv' : 'Fehlt' }}</span>
                    </div>
                </div>

                <div class="bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl space-y-5">
                    <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider border-b border-gray-900 pb-2">🛠️ System-Verhalten & Logs</h3>

                    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800">
                        <div>
                            <p class="text-sm font-bold text-gray-300">Mehrere Instanzen zulassen</p>
                            <p class="text-[10px] text-gray-500 mt-0.5">Deaktiviert den Auto-Attach.</p>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer shrink-0">
                            <input type="checkbox" v-model="store.sysConfig.allow_multiple_instances" @change="api.saveSysConfig()" class="sr-only peer">
                            <div class="w-11 h-6 bg-gray-950 border border-gray-700 rounded-full peer peer-checked:after:translate-x-full after:bg-gray-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-600 after:absolute after:top-0.5 after:left-[2px]"></div>
                        </label>
                    </div>

                    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800">
                        <div>
                            <p class="text-sm font-bold text-gray-300">Verbose Logging</p>
                            <p class="text-[10px] text-gray-500 mt-0.5">Live-Output im Terminal.</p>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer shrink-0">
                            <input type="checkbox" v-model="store.sysConfig.verbose_logging" @change="api.saveSysConfig()" class="sr-only peer">
                            <div class="w-11 h-6 bg-gray-950 border border-gray-700 rounded-full peer peer-checked:after:translate-x-full after:bg-gray-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-600 after:absolute after:top-0.5 after:left-[2px]"></div>
                        </label>
                    </div>
                    
                    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800">
                        <div>
                            <p class="text-sm font-bold text-gray-300">Developer Mode</p>
                            <p class="text-[10px] text-gray-500 mt-0.5">Zeigt Dev-Testserver in der Sidebar.</p>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer shrink-0">
                            <input type="checkbox" v-model="store.sysConfig.dev_mode" @change="api.saveSysConfig()" class="sr-only peer">
                            <div class="w-11 h-6 bg-gray-950 border border-gray-700 rounded-full peer peer-checked:after:translate-x-full after:bg-gray-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-600 after:absolute after:top-0.5 after:left-[2px]"></div>
                        </label>
                    </div>

                    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800">
                        <div class="w-full">
                            <p class="text-sm font-bold text-gray-300">AMP Discovery Pfade</p>
                            <p class="text-[10px] text-gray-500 mt-0.5">Zusätzliche Pfade (kommagetrennt) für die automatische AMP-Instanz-Suche.</p>
                            <input type="text" v-model="store.sysConfig.amp_discovery_paths" @blur="api.saveSysConfig()" placeholder="z.B. /mnt/amp/instances" class="mt-2 w-full bg-gray-950 border border-gray-700 text-xs text-white p-2 rounded outline-none focus:border-orange-500 font-mono">
                        </div>
                    </div>
                    
                    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800">
                        <div class="w-full">
                            <p class="text-sm font-bold text-gray-300">CurseForge API Key (Optional)</p>
                            <p class="text-[10px] text-gray-500 mt-0.5">Für die offizielle ASA Mod-Namensauflösung.</p>
                            <input type="password" v-model="store.sysConfig.curseforge_api_key" @blur="api.saveSysConfig()" placeholder="x-api-key..." class="mt-2 w-full bg-gray-950 border border-gray-700 text-xs text-white p-2 rounded outline-none focus:border-orange-500 font-mono">
                        </div>
                    </div>

                    <button @click="api.openLogViewer()" class="w-full bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold p-2.5 rounded-lg text-xs transition border border-gray-700 cursor-pointer">📄 System-Logbuch ansehen</button>
                </div>

            </div>

            <div class="bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl space-y-5 flex flex-col justify-between">
                <div>
                    <h3 class="text-sm font-bold text-white uppercase tracking-wider border-b border-gray-900 pb-2">🖥️ OS Background Service</h3>
                    <p class="text-xs text-gray-400 mt-3">Registriert EmberCore nativ im Betriebssystem (als <span class="font-bold text-orange-400">{{ store.systemServiceStats?.os === 'Linux' ? 'Systemd Daemon' : 'Windows Service' }}</span>). EmberCore startet dann automatisch beim Server-Boot, noch bevor sich ein Benutzer anmeldet.</p>
                    <div class="mt-4 flex items-center gap-3">
                        <span class="text-sm text-gray-400">Dienst-Status:</span>
                        <span v-if="!store.systemServiceStats?.is_installed" class="px-2 py-1 rounded bg-gray-900 border border-gray-800 text-xs font-bold text-gray-500">Nicht Installiert</span>
                        <span v-else-if="store.systemServiceStats?.is_running" class="px-2 py-1 rounded bg-green-900/30 border border-green-800/50 text-xs font-bold text-green-400 animate-pulse">Running</span>
                        <span v-else class="px-2 py-1 rounded bg-red-900/30 border border-red-800/50 text-xs font-bold text-red-400">Stopped</span>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-3 pt-4">
                    <button v-if="!store.systemServiceStats?.is_installed" @click="api.installService()" :disabled="store.isActionLoading" class="col-span-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">Als Service Installieren</button>
                    <template v-else>
                        <button v-if="!store.systemServiceStats?.is_running" @click="api.startService()" :disabled="store.isActionLoading" class="bg-green-600 hover:bg-green-500 text-white text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">▶️ Starten</button>
                        <button v-else @click="api.stopService()" :disabled="store.isActionLoading" class="bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">⏹️ Stoppen</button>
                        <button @click="api.uninstallService()" :disabled="store.isActionLoading" class="bg-gray-800 hover:bg-red-900/40 border border-gray-700 hover:border-red-800 hover:text-red-400 text-gray-300 text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">Deinstallieren</button>
                    </template>
                </div>
            </div>

            <div class="col-span-1 md:col-span-2 bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl space-y-5">
                <h3 class="text-sm font-bold text-white uppercase tracking-wider border-b border-gray-900 pb-2">📦 AMP (CubeCoders) Importer</h3>
                <p class="text-xs text-gray-400 mt-2">Importiere bestehende ARK: Survival Ascended Server aus einer bestehenden AMP-Installation. Gib dazu den absoluten Pfad zum AMP-Instanzordner (z.B. <span class="font-mono text-gray-500">C:\\AMPDatastore\\Instances\\ASA01</span>) an.</p>
                
                <div class="space-y-4">
                    <div class="flex justify-between items-center">
                        <button @click="discoverInstances" :disabled="isDiscovering" class="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-bold py-2 px-4 rounded-lg border border-gray-700 transition flex items-center gap-2">
                            <svg v-if="isDiscovering" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                            AMP-Instanzen suchen
                        </button>
                    </div>

                    <div v-if="discoveryTried && discoveredInstances.length === 0" class="text-xs text-orange-400 bg-orange-950/30 p-3 rounded-lg border border-orange-900/50">
                        Keine Instanzen gefunden. Prüfe ggf. die AMP Discovery Pfade in den Einstellungen.
                    </div>
                    
                    <div v-if="discoveredInstances.length > 0" class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
                        <div v-for="inst in discoveredInstances" :key="inst.instance_path" class="bg-gray-900 border border-gray-800 rounded-lg p-3 flex flex-col justify-between">
                            <div>
                                <p class="text-sm font-bold text-white truncate" :title="inst.session_name">{{ inst.session_name || inst.instance_name }}</p>
                                <p class="text-[10px] text-gray-500 mt-1">Map: {{ inst.map }} | Port: {{ inst.port }}</p>
                                <p class="text-[10px] text-gray-600 mt-1 truncate" :title="inst.instance_path">{{ inst.instance_path }}</p>
                            </div>
                            <button @click="selectInstance(inst.instance_path)" class="mt-3 w-full bg-gray-800 hover:bg-gray-700 text-white text-xs font-bold py-1.5 rounded transition">Auswählen</button>
                        </div>
                    </div>
                    
                    <input type="text" v-model="store.ampImportPath" placeholder="Absoluter Pfad zur AMP-Instanz..." class="w-full bg-gray-900 border border-gray-800 text-sm text-white p-3 rounded-lg outline-none focus:border-orange-500 font-mono">
                    
                    <div class="flex items-center gap-4 bg-gray-900/50 p-3 rounded-lg border border-gray-800">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" v-model="store.ampImportMode" value="move" class="accent-orange-600">
                            <span class="text-sm text-gray-300 font-bold">Verschieben (Schnell)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" v-model="store.ampImportMode" value="copy" class="accent-orange-600">
                            <span class="text-sm text-gray-300 font-bold">Kopieren (Safe, dauert länger)</span>
                        </label>
                    </div>

                    <button v-if="!store.ampImportTask || store.ampImportTask.status === 'completed' || store.ampImportTask.status === 'error'" @click="importAmpServer" :disabled="store.isActionLoading || !store.ampImportPath" class="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-500 text-white font-bold py-3 rounded-lg transition shadow-md cursor-pointer flex items-center justify-center gap-2">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg>
                        AMP Server Importieren
                    </button>
                    
                    <div v-if="store.ampImportTask && store.ampImportTask.status === 'running'" class="mt-4 bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
                        <div class="flex justify-between text-sm text-gray-300 font-bold">
                            <span>{{ store.ampImportTask.message }}</span>
                            <span class="text-orange-400">{{ store.ampImportTask.progress }}%</span>
                        </div>
                        <div class="w-full bg-gray-800 rounded-full h-3 overflow-hidden shadow-inner">
                            <div class="bg-orange-500 h-3 rounded-full transition-all duration-300 relative overflow-hidden" :style="{ width: store.ampImportTask.progress + '%' }">
                                <div class="absolute top-0 left-0 bottom-0 right-0 bg-white/20 animate-pulse"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-span-1 md:col-span-2 bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl flex flex-col h-96">
                <p class="text-xs text-gray-500 uppercase font-bold tracking-wider border-b border-gray-900 pb-2 mb-4 flex justify-between items-center flex-shrink-0">
                    <span>Versions-Historie</span>
                    <span class="font-mono text-orange-400 lowercase font-normal hidden sm:inline">CPU: {{ store.systemServiceStats?.cpu_percent || 0 }}% | RAM: {{ store.systemServiceStats?.ram_mb || 0 }}MB | UP: {{ formatUptime(store.systemServiceStats?.uptime_seconds || 0) }}</span>
                </p>
                <div class="overflow-y-auto pr-2 space-y-4 flex-1">
                    <div v-for="(release, index) in store.systemInfo?.history || []" :key="index" class="space-y-2 pb-4 border-b border-gray-900/50 last:border-0">
                        <div class="flex justify-between items-center"><span :class="index === 0 ? 'text-orange-400 font-bold' : 'text-gray-500 font-medium'" class="text-sm font-mono">{{ release.version }}</span><span class="text-[10px] text-gray-600">{{ release.build_date }}</span></div>
                        <ul class="text-sm space-y-1"><li v-for="(log, i) in release.changelog" :key="i" class="flex gap-2"><span :class="index === 0 ? 'text-orange-500' : 'text-gray-700'">▶</span><span :class="index === 0 ? 'text-gray-300' : 'text-gray-500'">{{ log }}</span></li></ul>
                    </div>
                </div>
            </div>

        </div>
    </div>
    `,
    methods: {
        async discoverInstances() {
            this.isDiscovering = true;
            this.discoveryTried = false;
            try {
                const res = await fetch('/api/system/importer/discover');
                const data = await res.json();
                if (data.status === 'success') {
                    this.discoveredInstances = data.instances || [];
                    this.discoveryTried = true;
                } else {
                    api.alert(data.message, 'Fehler bei der Suche');
                }
            } catch (e) {
                console.error(e);
                api.alert('Netzwerkfehler', 'Fehler');
            }
            this.isDiscovering = false;
        },
        selectInstance(path) {
            store.ampImportPath = path;
        },
        async importAmpServer() {
            if (!store.ampImportPath) return;
            store.isActionLoading = true;
            try {
                const res = await fetch('/api/system/importer/amp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: store.ampImportPath, mode: store.ampImportMode || 'move' })
                });
                const data = await res.json();
                
                if (data.status === 'success' && data.task_id) {
                    store.ampImportTask = { status: 'running', progress: 0, message: data.message };
                    
                    // Start polling
                    const pollInterval = setInterval(async () => {
                        try {
                            const statusRes = await fetch(`/api/system/importer/status/${data.task_id}`);
                            const statusData = await statusRes.json();
                            
                            store.ampImportTask = statusData;
                            
                            if (statusData.status === 'completed') {
                                clearInterval(pollInterval);
                                store.isActionLoading = false;
                                api.alert(statusData.message, '✅ Import Erfolgreich');
                                store.ampImportPath = '';
                                store.ampImportTask = null; // Reset UI
                                api.loadInstalledPlugins(); // Refresh servers
                            } else if (statusData.status === 'error') {
                                clearInterval(pollInterval);
                                store.isActionLoading = false;
                                api.alert(statusData.message, '❌ Import Fehlgeschlagen');
                                store.ampImportTask = null;
                            }
                        } catch (e) {
                            console.error("Polling error", e);
                        }
                    }, 1000);
                } else {
                    store.isActionLoading = false;
                    api.alert(data.message, '❌ Import Fehlgeschlagen');
                }
            } catch (e) {
                store.isActionLoading = false;
                api.alert(e.message, '❌ Fehler');
            }
        },
        async shutdownEmberCore() {
            // Gefixt: Direkter Zugriff auf 'api', da wir es als ES-Module importiert haben. 
            // Vermeidet Kontex-Verluste bei 'this' in reinen Vanilla-JS Objekten.
            const isConfirmed = await api.confirm(
                "EmberCore beenden",
                "Möchtest du EmberCore wirklich komplett beenden?\n\nAlle laufenden Gameserver bleiben im Hintergrund aktiv, aber das Panel ist offline."
            );

            if (!isConfirmed) return;

            try {
                await fetch('/api/system/shutdown', { method: 'POST' });
                document.body.innerHTML = `
                <div style="height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #0b0f19; color: #fff; font-family: ui-sans-serif, system-ui, sans-serif;">
                    <h1 style="color: #ef4444; font-size: 2rem; font-weight: bold; margin-bottom: 10px;">🔥 EmberCore offline</h1>
                    <p style="color: #9ca3af;">Das Panel und die Hintergrund-Dienste wurden beendet.</p>
                    <p id="countdown-text" style="color: #4b5563; font-size: 14px; margin-top: 20px; border: 1px solid #1f2937; padding: 5px 10px; border-radius: 5px;">Browserfenster schließt sich in 5 Sekunden...</p>
                </div>
                `;

                let secondsLeft = 5;
                const countdownInterval = setInterval(() => {
                    secondsLeft--;
                    const textEl = document.getElementById('countdown-text');
                    if (textEl) textEl.innerText = `Browserfenster schließt sich in ${secondsLeft} Sekunden...`;
                    if (secondsLeft <= 0) {
                        clearInterval(countdownInterval);
                        window.close();
                        setTimeout(() => { if (textEl) textEl.innerText = "Du kannst dieses Fenster nun sicher schließen."; }, 500);
                    }
                }, 1000);
            } catch (e) {
                console.error("Shutdown fehlgeschlagen", e);
            }
        }
    }
};