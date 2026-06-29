import { store, api, currentServerData } from '../store.js';

export default {
    setup() { return { store, api, currentServerData }; },
    template: `
    <div class="max-w-5xl mx-auto space-y-6">
    <div class="flex justify-between items-center bg-gray-950 p-5 rounded-xl border border-gray-900 shadow-md">
    <div>
    <h1 class="text-2xl font-black text-white tracking-wide truncate">{{ currentServerData.server_name }}</h1>
    <p class="text-sm text-gray-500 font-mono mt-1">Engine: <span class="text-gray-400">{{ currentServerData.game_name }}</span></p>
    </div>
    <button @click="api.deleteServer()" class="h-10 px-5 rounded-lg font-bold transition cursor-pointer text-sm flex items-center justify-center bg-red-950/30 border border-red-900/50 hover:bg-red-900 hover:border-red-500 text-red-400 hover:text-white shadow-sm">🗑️ Server löschen</button>
    </div>
    <div class="flex flex-col md:flex-row gap-6 items-start">
    <nav class="w-full md:w-56 flex-shrink-0 flex flex-col space-y-1 bg-gray-950 p-3 rounded-xl border border-gray-900 shadow-md sticky top-6">
    <h3 class="text-[10px] font-bold text-gray-600 uppercase tracking-widest px-3 mb-2 mt-1">Verwaltung</h3>
    <button @click="store.serverTab = 'status'" :class="store.serverTab === 'status' ? 'bg-orange-600 text-white shadow-md' : 'text-gray-400 hover:bg-gray-900 hover:text-white'" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3">🖥️ Status</button>
    <button @click="api.openConsoleTab()" :class="store.serverTab === 'console' ? 'bg-orange-600 text-white shadow-md' : 'text-gray-400 hover:bg-gray-900 hover:text-white'" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3">📟 Konsole</button>
    <button @click="api.openConfigTab()" :class="store.serverTab === 'config' ? 'bg-orange-600 text-white shadow-md' : 'text-gray-400 hover:bg-gray-900 hover:text-white'" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3">⚙️ Einstellungen</button>
    <button @click="api.openListsTab()" :class="store.serverTab === 'lists' ? 'bg-orange-600 text-white shadow-md' : 'text-gray-400 hover:bg-gray-900 hover:text-white'" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3">📜 Listen</button>
    <button @click="api.openNetworkTab()" :class="store.serverTab === 'network' ? 'bg-orange-600 text-white shadow-md' : 'text-gray-400 hover:bg-gray-900 hover:text-white'" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3">🌐 Netzwerk</button>
    <button @click="api.openModsTab()" :class="store.serverTab === 'mods' ? 'bg-orange-600 text-white shadow-md' : 'text-gray-400 hover:bg-gray-900 hover:text-white'" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3">🔌 Mods</button>
    <button @click="api.openBackupTab()" :class="store.serverTab === 'backups' ? 'bg-orange-600 text-white shadow-md' : 'text-gray-400 hover:bg-gray-900 hover:text-white'" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3">💾 Backups</button>
    <div class="h-px bg-gray-800/60 my-3 mx-2"></div>
    <h3 class="text-[10px] font-bold text-gray-600 uppercase tracking-widest px-3 mb-2">Aktionen</h3>
    <button @click="api.openLocalFolder()" class="w-full text-left px-4 py-2.5 rounded-lg font-medium transition cursor-pointer text-sm flex items-center gap-3 text-gray-400 hover:bg-gray-900 hover:text-white">📂 Lokale Dateien</button>
    </nav>

    <div class="flex-1 min-w-0 w-full space-y-6">
    <div v-if="store.serverTab === 'status'" class="space-y-6">
    <div v-if="store.serverStats.update_info && store.serverStats.update_info.available" class="bg-blue-950/80 border border-blue-500 rounded-xl p-5 shadow-[0_0_15px_rgba(59,130,246,0.3)] flex justify-between items-center animate-pulse">
    <div><h3 class="text-blue-400 font-bold uppercase tracking-wider text-xs flex items-center gap-2">🔄 Spiel-Update auf Steam verfügbar!</h3><p class="text-xs text-blue-200 mt-1">Installierter Build: <span class="font-mono">{{ store.serverStats.update_info.local }}</span> | Aktuell auf Steam: <span class="font-mono">{{ store.serverStats.update_info.remote }}</span></p></div>
    <button @click="api.installServer()" :disabled="store.isActionLoading" class="bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-bold px-4 py-2 rounded transition cursor-pointer shadow">Jetzt aktualisieren</button>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
    <button @click="api.installServer()" :disabled="store.isActionLoading || store.serverStats.status === 'online'" :class="(store.serverStats.update_info && store.serverStats.update_info.available) ? 'bg-orange-600 hover:bg-orange-500 shadow-[0_0_15px_rgba(234,88,12,0.5)] border border-orange-400' : 'bg-blue-600 hover:bg-blue-500 border border-transparent'" class="disabled:bg-gray-950 disabled:border-gray-900 disabled:text-gray-700 text-white font-medium p-3 rounded-xl transition cursor-pointer text-sm flex flex-col items-center justify-center text-center"><span>{{ (store.serverStats.update_info && store.serverStats.update_info.available) ? '🔄 Update verfügbar' : '📦 Install / Update' }}</span></button>
    <button @click="api.checkGameUpdate()" :disabled="store.isActionLoading" class="bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium p-3 rounded-xl transition shadow cursor-pointer text-sm border border-gray-700">🔎 Update prüfen</button>
    <button @click="api.startServer()" :disabled="store.isActionLoading || store.serverStats.status === 'online'" class="bg-green-600 hover:bg-green-500 disabled:bg-gray-950 disabled:text-gray-700 text-white font-medium p-3 rounded-xl transition shadow cursor-pointer text-sm">▶️ Server Starten</button>
    <button @click="api.stopServer()" :disabled="store.isActionLoading || store.serverStats.status === 'offline'" class="bg-red-600 hover:bg-red-500 disabled:bg-gray-950 disabled:text-gray-700 text-white font-medium p-3 rounded-xl transition shadow cursor-pointer text-sm">⏹️ Server Stoppen</button>
    </div>
    <div v-if="store.isActionLoading" class="bg-gray-950 border border-gray-900 p-4 rounded-xl flex items-center space-x-3 text-sm text-gray-400"><div class="animate-spin rounded-full h-4 w-4 border-2 border-orange-500 border-t-transparent"></div><p>{{ store.loadingMessage }}</p></div>
    <div v-if="store.activeDiagnostics.length > 0" class="bg-red-950/80 border border-red-800 rounded-xl p-5 shadow-lg space-y-3">
    <h3 class="text-red-400 font-bold uppercase tracking-wider text-xs flex items-center gap-2">⚠️ Absturz-Schutz: Systemstörung im Log erkannt</h3>
    <div v-for="diag in store.activeDiagnostics" :key="diag.id" class="bg-black/30 p-3 rounded-lg flex justify-between items-center border border-red-900/40">
    <p class="text-xs text-red-200">{{ diag.message }}</p>
    <button @click="api.applyFix(diag.fix_type)" class="bg-red-700 hover:bg-red-600 text-white text-[11px] font-bold px-3 py-1.5 rounded transition cursor-pointer whitespace-nowrap ml-4">{{ diag.fix_label }}</button>
    </div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div class="bg-gray-950 p-5 rounded-xl border border-gray-900 shadow-inner flex flex-col justify-between">
    <p class="text-xs text-gray-500 font-bold uppercase tracking-wider mb-4 border-b border-gray-900 pb-2">Ressourcen-Nutzung</p>
    <div class="flex justify-between items-end">
    <div><p class="text-[10px] text-gray-600 font-bold uppercase">CPU-Auslastung</p><p class="text-3xl font-mono font-bold text-orange-400">{{ store.serverStats.status === 'online' ? store.serverStats.cpu_percent + ' %' : '---' }}</p></div>
    <div class="text-right"><p class="text-[10px] text-gray-600 font-bold uppercase">RAM-Verbrauch</p><p class="text-3xl font-mono font-bold text-blue-400">{{ store.serverStats.status === 'online' ? store.serverStats.ram_mb + ' MB' : '---' }}</p></div>
    </div>
    </div>
    <div class="bg-gray-950 p-5 rounded-xl border border-gray-900 shadow-inner flex flex-col justify-between">
    <div class="flex justify-between items-center border-b border-gray-900 pb-2 mb-4">
    <p class="text-xs text-gray-500 font-bold uppercase tracking-wider">Laufwerks-Analyse</p>
    <span v-if="store.serverStats.disk" class="text-[10px] bg-gray-900 px-2 py-1 rounded border border-gray-800 text-gray-400">Host frei: <strong class="text-white">{{ store.serverStats.disk.host_free_gb }} GB</strong></span>
    </div>
    <div v-if="store.serverStats.disk" class="space-y-3">
    <div class="flex justify-between text-sm"><span class="text-gray-400">Spieldateien:</span><span class="font-mono text-white">{{ store.serverStats.disk.server_mb }} MB</span></div>
    <div class="flex justify-between text-sm"><span class="text-gray-400">Archivierte Backups:</span><span class="font-mono text-white">{{ store.serverStats.disk.backup_mb }} MB</span></div>
    <div class="pt-2 border-t border-gray-900 flex justify-between items-center">
    <span class="text-xs font-semibold text-gray-500">Tägliches Wachstum (Trend):</span>
    <span :class="store.serverStats.disk.trend_mb_per_day > 0 ? 'text-red-400' : 'text-green-400'" class="font-mono text-sm font-bold flex items-center">
    <span v-if="store.serverStats.disk.trend_mb_per_day > 0">📈 +</span><span v-else>📉 </span>{{ store.serverStats.disk.trend_mb_per_day }} MB / Tag
    </span>
    </div>
    </div>
    </div>
    </div>
    </div>

    <div v-if="store.serverTab === 'console'" class="bg-gray-950 rounded-xl border border-gray-900 shadow-md flex flex-col h-[500px] overflow-hidden">
    <div class="p-4 border-b border-gray-900 flex justify-between items-center bg-gray-900/80">
    <div><h3 class="text-sm font-bold text-white uppercase tracking-wider">📟 Live Terminal</h3><p class="text-xs text-gray-500">Direkter stdout des Prozesses (nur bei Start über Web-UI)</p></div>
    </div>
    <div class="flex-1 p-4 overflow-y-auto font-mono text-xs text-gray-300 bg-[#0a0a0a]" id="console-output">
    <div v-for="(log, idx) in store.consoleLogs" :key="idx" class="whitespace-pre-wrap">{{ log }}</div>
    </div>
    </div>

    <div v-if="store.serverTab === 'config'" class="bg-gray-950 rounded-xl p-5 border border-gray-900 shadow-md space-y-4">
    <div v-if="store.configData.enabled" class="space-y-4">
    <div v-for="field in store.configData.fields" :key="field.key" class="flex flex-col space-y-2 border-b border-gray-900/50 pb-3">
    <label class="text-xs font-bold text-gray-400 uppercase tracking-wide">{{ field.label }}</label>
    <div v-if="field.type === 'boolean'" class="flex items-center pt-1">
    <label class="relative inline-flex items-center cursor-pointer">
    <input type="checkbox" v-model="store.configData.values[field.key]" class="sr-only peer">
    <div class="w-11 h-6 bg-gray-900 border border-gray-800 rounded-full peer peer-checked:after:translate-x-full after:bg-gray-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-600 after:absolute after:top-0.5 after:left-[2px]"></div>
    </label>
    <span class="text-xs text-gray-500 ml-3 font-mono font-bold">{{ store.configData.values[field.key] ? 'AKTIVIERT' : 'DEAKTIVIERT' }}</span>
    </div>
    <input v-if="field.type === 'text'" type="text" v-model="store.configData.values[field.key]" class="bg-gray-900 border border-gray-800 rounded-lg p-2 text-sm text-white focus:border-orange-500 outline-none w-full">
    <input v-if="field.type === 'number'" type="number" v-model.number="store.configData.values[field.key]" class="bg-gray-900 border border-gray-800 rounded-lg p-2 text-sm text-white focus:border-orange-500 outline-none w-full">
    </div>
    <div v-if="store.configData.unknown_fields && store.configData.unknown_fields.length > 0" class="pt-4 space-y-4">
    <div class="text-xs font-black text-orange-500 uppercase tracking-widest border-b border-orange-950/40 pb-2">Erweiterte Parameter (Dynamisch erkannt)</div>
    <div v-for="field in store.configData.unknown_fields" :key="field.key" class="flex flex-col space-y-2 border-b border-gray-900/50 pb-3">
    <label class="text-xs font-bold text-gray-500 font-mono">{{ field.key }}</label>
    <div v-if="field.type === 'boolean'" class="flex items-center pt-1">
    <label class="relative inline-flex items-center cursor-pointer">
    <input type="checkbox" v-model="store.configData.values[field.key]" class="sr-only peer">
    <div class="w-11 h-6 bg-gray-900 border border-gray-800 rounded-full peer peer-checked:after:translate-x-full after:bg-gray-400 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-900 after:absolute after:top-0.5 after:left-[2px]"></div>
    </label>
    <span class="text-xs text-gray-600 ml-3 font-mono">{{ store.configData.values[field.key] ? 'TRUE' : 'FALSE' }}</span>
    </div>
    <input v-if="field.type === 'text'" type="text" v-model="store.configData.values[field.key]" class="bg-gray-900 border border-gray-800 rounded-lg p-2 text-sm text-gray-400 focus:border-orange-900 outline-none w-full font-mono">
    <input v-if="field.type === 'number'" type="number" v-model.number="store.configData.values[field.key]" class="bg-gray-900 border border-gray-800 rounded-lg p-2 text-sm text-gray-400 focus:border-orange-900 outline-none w-full font-mono">
    </div>
    </div>
    <button @click="api.saveConfig()" class="w-full bg-orange-600 hover:bg-orange-500 text-white font-medium p-2.5 rounded-lg transition shadow-md mt-4 cursor-pointer text-sm">💾 Einstellungen speichern</button>
    </div>
    <div v-if="store.startupData && store.startupData.enabled" class="mb-2 p-4 bg-gray-900/40 border border-gray-800 rounded-lg shadow-inner">
            <h3 class="text-sm font-bold text-orange-500 uppercase tracking-widest border-b border-gray-800 pb-2 mb-4 flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                Karten-Auswahl (Map)
            </h3>
            <label class="block text-xs font-bold text-gray-400 uppercase mb-2">Aktive Welt</label>
            <select v-model="store.startupData.selected_map" class="w-full bg-gray-950 border border-gray-700 hover:border-gray-600 rounded-lg p-2.5 text-sm text-white focus:border-orange-500 outline-none cursor-pointer shadow-sm transition">
                <option v-for="map in store.startupData.available_maps" :key="map" :value="map">{{ map }}</option>
            </select>
            <p class="text-[10px] text-gray-500 mt-2">Änderungen werden erst nach einem Server-Neustart aktiv. Savegames sind oft kartenspezifisch!</p>
        </div>
        <div v-if="store.configData.enabled" class="space-y-4">
    <p v-else class="text-gray-500 text-sm text-center py-6">Dieses Profil besitzt keine editierbaren Web-Konfigurationen.</p>
    </div>

    <div v-if="store.serverTab === 'lists'" class="space-y-6">
    <div v-if="!store.listData.enabled" class="bg-gray-950 rounded-xl p-8 border border-gray-900 text-center text-gray-500 text-sm shadow-md">Dieses Spiel unterstützt noch keine Textlisten im Webinterface.</div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div v-for="lst in store.listData.lists" :key="lst.id" class="bg-gray-950 rounded-xl p-5 border border-gray-900 shadow-md flex flex-col h-96">
    <div class="flex justify-between items-center mb-2"><h3 class="text-sm font-bold text-white uppercase">{{ lst.name }}</h3><button @click="api.saveList(lst)" class="bg-orange-600 hover:bg-orange-500 text-white text-[10px] font-bold px-3 py-1.5 rounded cursor-pointer transition">SPEICHERN</button></div>
    <p class="text-[10px] text-gray-500 font-mono mb-3 uppercase tracking-wide">Ein Eintrag pro Zeile (z.B. SteamID)</p>
    <textarea v-model="lst.content" class="flex-1 w-full bg-[#0a0a0a] border border-gray-800 rounded p-3 text-xs text-gray-300 font-mono focus:border-orange-500 outline-none resize-none whitespace-pre"></textarea>
    </div>
    </div>
    </div>

    <div v-if="store.serverTab === 'network'" class="space-y-6">
    <div class="bg-gray-950 rounded-xl p-6 border border-gray-900 shadow-md space-y-4">
    <div><h3 class="text-lg font-black text-white uppercase tracking-wider">🌍 Netzwerk-Ports & Freigaben</h3><p class="text-sm text-gray-400 mt-1">Damit das Spiel aus dem Internet erreichbar ist, müssen die Ports deines PCs und Routers geöffnet sein.</p></div>
    <div v-if="!store.networkData.enabled" class="text-gray-500 text-sm py-4 border-t border-gray-900">Keine Ports für dieses Spiel im Manifest konfiguriert.</div>
    <div v-else class="space-y-6 border-t border-gray-900 pt-4">
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div v-for="port in store.networkData.ports" :key="port.port" class="bg-gray-900 border border-gray-800 p-4 rounded-xl flex items-center justify-between shadow-inner">
    <div><p class="text-xs text-gray-500 font-bold uppercase tracking-wide">{{ port.desc }}</p><p class="text-2xl font-mono text-white font-bold mt-1">{{ port.port }}</p></div>
    <span class="text-[10px] bg-orange-950/60 text-orange-400 border border-orange-900 px-2 py-1 rounded uppercase font-bold">{{ port.protocol }}</span>
    </div>
    </div>
    <div class="bg-gray-900/40 p-4 rounded-xl border border-gray-800 mt-4">
    <div class="flex justify-between items-center mb-3 border-b border-gray-800 pb-3"><h4 class="text-white font-bold text-sm">🛡️ Automatische Router- & Firewall-Freigabe</h4><button @click="api.triggerNetworkSetup()" :disabled="store.isActionLoading" class="bg-orange-600 hover:bg-orange-500 text-white text-xs font-bold px-4 py-2 rounded shadow cursor-pointer transition">Freigabe ausführen</button></div>
    <p class="text-xs text-gray-400 mb-2">EmberCore trägt die Ports in der <b>Windows Defender Firewall</b> ein und funkt parallel deinen <b>Router über UPnP an</b>.</p>
    <p class="text-[10px] text-orange-400 font-bold mt-2 bg-orange-950/30 p-2 rounded">WICHTIG: Erfordert danach den Klick auf "Ja" im Windows Administrator-Fenster (Schild-Symbol). UPnP muss im Router aktiviert sein!</p>
    </div>
    </div>
    </div>
    </div>

    <div v-if="store.serverTab === 'mods'" class="space-y-6">
    <div class="bg-gray-950 rounded-xl p-5 border border-gray-900 shadow-md space-y-4">
    <div><h3 class="text-sm font-bold text-white uppercase tracking-wider">🔌 Steam Workshop Modifikationen</h3></div>
    <div class="flex items-center space-x-2">
    <input type="text" placeholder="z.B. 880454836" v-model="store.newModId" class="bg-gray-900 border border-gray-800 text-sm text-white p-2 rounded-lg outline-none focus:border-orange-500 font-mono w-48">
    <button @click="api.addMod()" class="bg-orange-600 hover:bg-orange-500 text-xs font-semibold px-4 py-2.5 rounded-lg text-white transition cursor-pointer">➕ Mod hinzufügen</button>
    </div>
    </div>
    <div class="bg-gray-950 rounded-xl border border-gray-900 overflow-hidden shadow-md">
    <table class="w-full text-left border-collapse">
    <thead><tr class="bg-gray-900/40 border-b border-gray-900 text-gray-500 text-[10px] uppercase font-bold"><th class="p-3">Workshop ID</th><th class="p-3">Mod-Name</th><th class="p-3">Letztes Update</th><th class="p-3 text-right">Aktionen</th></tr></thead>
    <tbody class="divide-y divide-gray-900 text-xs text-gray-300">
    <tr v-for="mod in store.activeMods" :key="mod.id" class="hover:bg-gray-900/20">
    <td class="p-3 font-mono text-gray-500">{{ mod.id }}</td>
    <td class="p-3 font-bold text-white">{{ mod.name }}</td>
    <td class="p-3 text-blue-400 font-mono">{{ mod.version }}</td>
    <td class="p-3 text-right"><button @click="api.deleteMod(mod.id)" class="text-red-500 hover:text-red-400 transition cursor-pointer px-2">🗑️ Löschen</button></td>
    </tr>
    <tr v-if="store.activeMods.length === 0"><td colspan="4" class="p-6 text-center text-gray-600">Keine Modifikationen aktiv.</td></tr>
    </tbody>
    </table>
    </div>
    </div>

    <div v-if="store.serverTab === 'backups'" class="space-y-6">
    <div class="bg-gray-950 rounded-xl p-5 border border-gray-900 shadow-md space-y-4">
    <div class="flex justify-between items-center border-b border-gray-900 pb-3"><div><h3 class="text-sm font-bold text-white uppercase tracking-wider">🛡️ Speicherplatz-Optimierung</h3></div><button @click="api.saveBackupSettings()" class="bg-gray-900 hover:bg-gray-800 border border-gray-800 text-xs font-semibold px-4 py-2 rounded-lg text-gray-300 transition cursor-pointer">Speichern</button></div>
    <div class="space-y-3 pt-2">
    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800">
    <div><p class="text-sm font-bold text-white">Letzte Backups immer behalten</p><p class="text-[10px] text-gray-500 mt-1">Löscht niemals die neuesten X Sicherungen.</p></div>
    <div class="flex items-center space-x-2"><input type="number" v-model.number="store.backupSchedule.retention.keep_latest" class="w-16 bg-gray-950 border border-gray-700 rounded p-1.5 text-sm text-white text-center font-mono outline-none"><span class="text-xs text-gray-400 w-12">Stück</span></div>
    </div>
    <div class="flex items-center justify-between bg-gray-900/50 p-3 rounded-lg border border-gray-800">
    <div><p class="text-sm font-bold text-white">Tägliche Backups aufheben</p><p class="text-[10px] text-gray-500 mt-1">Archiviert das erste Backup jedes Tages.</p></div>
    <div class="flex items-center space-x-2"><input type="number" v-model.number="store.backupSchedule.retention.keep_daily" class="w-16 bg-gray-950 border border-gray-700 rounded p-1.5 text-sm text-white text-center font-mono outline-none"><span class="text-xs text-gray-400 w-12">Tage</span></div>
    </div>
    </div>
    </div>
    <div class="bg-gray-950 rounded-xl p-5 border border-gray-900 shadow-md space-y-4">
    <div><h3 class="text-sm font-bold text-white uppercase tracking-wider">⏱️ Automatisierungs-Pläne</h3></div>
    <div class="space-y-2">
    <div v-for="(sched, index) in store.backupSchedule.schedules" :key="index" class="flex justify-between items-center bg-gray-900 border border-gray-800 p-2 rounded-lg">
    <span class="text-sm text-gray-300">{{ sched.type === 'interval' ? 'Alle ' + sched.value + ' Stunden' : 'Täglich um ' + sched.value + ' Uhr' }}</span>
    <button @click="api.removeSchedule(index)" class="text-red-500 hover:text-red-400 text-xs px-2 cursor-pointer">✖ Entfernen</button>
    </div>
    <div class="flex items-center space-x-2 border-t border-gray-900 pt-3">
    <select v-model="store.newSchedType" class="bg-gray-900 border border-gray-800 text-xs text-white p-2 rounded outline-none w-32"><option value="daily">Feste Uhrzeit</option><option value="interval">Intervall (Std)</option></select>
    <input v-if="store.newSchedType === 'daily'" type="time" v-model="store.newSchedVal" class="bg-gray-900 border border-gray-800 text-xs text-white p-1.5 rounded outline-none">
    <input v-if="store.newSchedType === 'interval'" type="number" placeholder="z.B. 2" v-model="store.newSchedVal" class="bg-gray-900 border border-gray-800 text-xs text-white p-1.5 rounded outline-none w-16 text-center">
    <button @click="api.addSchedule()" class="bg-orange-600 hover:bg-orange-500 text-white text-xs px-3 py-2 rounded cursor-pointer transition">Hinzufügen</button>
    </div>
    </div>
    </div>
    <div class="bg-gray-950 rounded-xl border border-gray-900 overflow-hidden shadow-md">
    <div class="p-4 bg-gray-950 border-b border-gray-900 flex justify-between items-center"><h3 class="text-sm font-bold text-white uppercase tracking-wider">📦 Vorhandene Speicherstände</h3><button @click="api.createBackup()" class="bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition cursor-pointer">💾 Jetzt erstellen</button></div>
    <table class="w-full text-left border-collapse">
    <thead><tr class="bg-gray-900/40 border-b border-gray-900 text-gray-500 text-[10px] uppercase font-bold"><th class="p-3">Dateiname</th><th class="p-3 text-right">Größe</th><th class="p-3 text-right">Aktionen</th></tr></thead>
    <tbody class="divide-y divide-gray-900 text-xs text-gray-300">
    <tr v-for="bak in store.backupList" :key="bak.filename" class="hover:bg-gray-900/20">
    <td class="p-3 font-mono text-orange-400/80">{{ bak.filename }}</td>
    <td class="p-3 text-blue-400 font-semibold text-right">{{ bak.size_mb }} MB</td>
    <td class="p-3 text-right space-x-1">
    <button @click="api.restoreBackup(bak.filename)" class="bg-gray-900 hover:bg-green-950 border border-gray-800 text-gray-400 hover:text-green-400 px-2 py-1 rounded transition cursor-pointer">↩️ Einspielen</button>
    <button @click="api.deleteBackup(bak.filename)" class="bg-gray-900 hover:bg-red-950 border border-gray-800 text-gray-400 hover:text-red-400 px-2 py-1 rounded transition cursor-pointer">🗑️ Löschen</button>
    </td>
    </tr>
    <tr v-if="store.backupList.length === 0"><td colspan="3" class="p-6 text-center text-gray-600">Keine Backups vorhanden.</td></tr>
    </tbody>
    </table>
    </div>
    </div>
    </div>
    </div>
    </div>
    `
};
