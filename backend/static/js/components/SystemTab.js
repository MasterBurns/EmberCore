import { store, api, formatUptime } from '../store.js';

export default {
    setup() { return { store, api, formatUptime }; },
    template: `
    <div class="max-w-5xl mx-auto space-y-6">
    <div class="flex justify-between items-center bg-gray-950 p-5 rounded-xl border border-gray-900 shadow-md">
    <div>
    <h1 class="text-2xl font-black text-white tracking-wide truncate">EmberCore Hintergrund-Dienste</h1>
    <p class="text-sm text-gray-500 font-mono mt-1">Version: <span class="text-gray-400">{{ store.systemInfo.version }}</span></p>
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
    <div class="bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl space-y-5">
    <h3 class="text-sm font-bold text-white uppercase tracking-wider border-b border-gray-900 pb-2">🩺 Watchdog & Heartbeat Monitor</h3>
    <div class="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-900/50">
    <div><p class="text-sm font-bold text-white">Haupt-Prozess (EmberCore)</p><p class="text-[10px] text-gray-500">FastAPI & Background Tasks</p></div>
    <span class="text-green-400 font-mono text-sm font-bold">Aktiv (PID: {{ store.systemServiceStats.main_pid || '?' }})</span>
    </div>
    <div class="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-900/50">
    <div><p class="text-sm font-bold text-white">Watchdog-Daemon</p><p class="text-[10px] text-gray-500">Hang-Detection & OS Recovery</p></div>
    <span :class="store.systemServiceStats.watchdog_active ? 'text-green-400' : 'text-red-500'" class="font-mono text-sm font-bold">{{ store.systemServiceStats.watchdog_active ? 'Aktiv' : 'Fehlt' }}</span>
    </div>
    <div class="mt-6 border-t border-gray-900 pt-4">
    <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">🛠️ Fehlersuche & Logs</h3>
    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800 mb-3">
    <div><p class="text-sm font-bold text-gray-300">Verbose Logging</p><p class="text-[10px] text-gray-500">Zeichnet die Erkennung von Server-Prozessen live auf.</p></div>
    <label class="relative inline-flex items-center cursor-pointer">
    <input type="checkbox" v-model="store.sysConfig.verbose_logging" @change="api.saveSysConfig()" class="sr-only peer">
    <div class="w-11 h-6 bg-gray-950 border border-gray-700 rounded-full peer peer-checked:after:translate-x-full after:bg-gray-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-600 after:absolute after:top-0.5 after:left-[2px]"></div>
    </label>
    </div>
    <button @click="api.openLogViewer()" class="w-full bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold p-2.5 rounded-lg text-xs transition border border-gray-700 cursor-pointer">📄 System-Logbuch ansehen</button>
    </div>
    </div>
    <div class="bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl space-y-5 flex flex-col justify-between">
    <div>
    <h3 class="text-sm font-bold text-white uppercase tracking-wider border-b border-gray-900 pb-2">🖥️ OS Background Service</h3>
    <p class="text-xs text-gray-400 mt-3">Registriert EmberCore nativ im Betriebssystem (als <span class="font-bold text-orange-400">{{ store.systemServiceStats.os === 'Linux' ? 'Systemd Daemon' : 'Windows Service' }}</span>). EmberCore startet dann automatisch beim Server-Boot, noch bevor sich ein Benutzer anmeldet.</p>
    <div class="mt-4 flex items-center gap-3">
    <span class="text-sm text-gray-400">Dienst-Status:</span>
    <span v-if="!store.systemServiceStats.is_installed" class="px-2 py-1 rounded bg-gray-900 border border-gray-800 text-xs font-bold text-gray-500">Nicht Installiert</span>
    <span v-else-if="store.systemServiceStats.is_running" class="px-2 py-1 rounded bg-green-900/30 border border-green-800/50 text-xs font-bold text-green-400 animate-pulse">Running</span>
    <span v-else class="px-2 py-1 rounded bg-red-900/30 border border-red-800/50 text-xs font-bold text-red-400">Stopped</span>
    </div>
    </div>
    <div class="grid grid-cols-2 gap-3 pt-4">
    <button v-if="!store.systemServiceStats.is_installed" @click="api.installService()" :disabled="store.isActionLoading" class="col-span-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">Als Service Installieren</button>
    <template v-else>
    <button v-if="!store.systemServiceStats.is_running" @click="api.startService()" :disabled="store.isActionLoading" class="bg-green-600 hover:bg-green-500 text-white text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">▶️ Starten</button>
    <button v-else @click="api.stopService()" :disabled="store.isActionLoading" class="bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">⏹️ Stoppen</button>
    <button @click="api.uninstallService()" :disabled="store.isActionLoading" class="bg-gray-800 hover:bg-red-900/40 border border-gray-700 hover:border-red-800 hover:text-red-400 text-gray-300 text-sm font-bold py-2.5 rounded-lg transition shadow-md cursor-pointer">Deinstallieren</button>
    </template>
    </div>
    </div>
    <div class="col-span-1 md:col-span-2 bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl flex flex-col h-96">
    <p class="text-xs text-gray-500 uppercase font-bold tracking-wider border-b border-gray-900 pb-2 mb-4 flex justify-between items-center flex-shrink-0">
    <span>Versions-Historie</span>
    <span class="font-mono text-orange-400 lowercase font-normal hidden sm:inline">CPU: {{ store.systemServiceStats.cpu_percent }}% | RAM: {{ store.systemServiceStats.ram_mb }}MB | UP: {{ formatUptime(store.systemServiceStats.uptime_seconds) }}</span>
    </p>
    <div class="overflow-y-auto pr-2 space-y-4 flex-1">
    <div v-for="(release, index) in store.systemInfo.history" :key="index" class="space-y-2 pb-4 border-b border-gray-900/50 last:border-0">
    <div class="flex justify-between items-center"><span :class="index === 0 ? 'text-orange-400 font-bold' : 'text-gray-500 font-medium'" class="text-sm font-mono">{{ release.version }}</span><span class="text-[10px] text-gray-600">{{ release.build_date }}</span></div>
    <ul class="text-sm space-y-1"><li v-for="(log, i) in release.changelog" :key="i" class="flex gap-2"><span :class="index === 0 ? 'text-orange-500' : 'text-gray-700'">▶</span><span :class="index === 0 ? 'text-gray-300' : 'text-gray-500'">{{ log }}</span></li></ul>
    </div>
    </div>
    </div>
    </div>
    </div>
    `,
    methods: {
        async shutdownEmberCore() {
            // Asynchrones Custom-Popup über unsere globale API
            const isConfirmed = await this.api.confirm(
                "EmberCore beenden",
                "Möchtest du EmberCore wirklich komplett beenden?\n\nAlle laufenden Gameserver bleiben im Hintergrund aktiv, aber das Panel ist offline."
            );

            if (!isConfirmed) {
                return;
            }

            try {
                await fetch('/api/system/shutdown', { method: 'POST' });

                // Den Bildschirm verdunkeln und den Countdown anzeigen
                document.body.innerHTML = `
                <div style="height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #0b0f19; color: #fff; font-family: ui-sans-serif, system-ui, sans-serif;">
                <h1 style="color: #ef4444; font-size: 2rem; font-weight: bold; margin-bottom: 10px;">🔥 EmberCore offline</h1>
                <p style="color: #9ca3af;">Das Panel und die Hintergrund-Dienste wurden beendet.</p>
                <p id="countdown-text" style="color: #4b5563; font-size: 14px; margin-top: 20px; border: 1px solid #1f2937; padding: 5px 10px; border-radius: 5px;">Browserfenster schließt sich in 5 Sekunden...</p>
                </div>
                `;

                // 5 Sekunden Countdown starten
                let secondsLeft = 5;
                const countdownInterval = setInterval(() => {
                    secondsLeft--;
                    const textEl = document.getElementById('countdown-text');

                    if (textEl) {
                        textEl.innerText = `Browserfenster schließt sich in ${secondsLeft} Sekunden...`;
                    }

                    // Bei 0 versuchen, den Tab zu schließen
                    if (secondsLeft <= 0) {
                        clearInterval(countdownInterval);
                        window.close(); // Versuch 1: Normaler Close-Befehl

                        // Fallback für Browser, die das Schließen aus Sicherheitsgründen blockieren
                        setTimeout(() => {
                            if (textEl) textEl.innerText = "Du kannst dieses Fenster nun sicher schließen.";
                        }, 500);
                    }
                }, 1000);

            } catch (e) {
                console.error("Shutdown fehlgeschlagen", e);
            }
        }
    }
};
