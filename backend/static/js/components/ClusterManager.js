import { api } from '../store.js';

export default {
    setup() { return { api }; },
    template: `
    <div class="flex flex-col h-full p-6 w-full text-gray-100 relative">

    <div v-if="showCreateModal" class="fixed inset-0 bg-black/70 flex items-center justify-center z-[9999] p-4 transition-all animate-fadeIn">
    <div class="bg-[#111827] border border-gray-800 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
    <h3 class="text-xl font-bold text-white flex items-center gap-2">
    <svg class="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
    Neuen Cluster konfigurieren
    </h3>
    <div class="space-y-4">
    <div>
    <label class="block text-xs font-bold uppercase tracking-wider text-gray-400 mb-1.5">Cluster Name</label>
    <input type="text" v-model="newClusterName" placeholder="z.B. Mein PvP Cluster" class="w-full bg-gray-950 border border-gray-800 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition">
    </div>
    <div>
    <label class="block text-xs font-bold uppercase tracking-wider text-gray-400 mb-1.5">Spiel-Infrastruktur (Dropdown)</label>
    <select v-model="newClusterGame" class="w-full bg-gray-950 border border-gray-800 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition cursor-pointer">
    <option value="" disabled>Bitte ein Spiel wählen...</option>
    <option v-for="game in availableGames" :key="game" :value="game">{{ game }}</option>
    </select>
    </div>
    <div>
    <label class="block text-xs font-bold uppercase tracking-wider text-gray-400 mb-1.5">Speicherort / Custom Path (Optional)</label>
    <input type="text" v-model="newClusterPath" placeholder="z.B. D:/ARK_Cluster (Leer lassen für Standard)" class="w-full bg-gray-950 border border-gray-800 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition font-mono">
    </div>
    </div>
    <div class="flex justify-end gap-3 pt-2">
    <button @click="closeCreateModal" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium rounded-lg transition cursor-pointer">Abbrechen</button>
    <button @click="submitNewCluster" :disabled="!newClusterName || !newClusterGame" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition cursor-pointer">Cluster erstellen</button>
    </div>
    </div>
    </div>

    <div v-if="showConfigSyncModal" class="fixed inset-0 bg-black/70 flex items-center justify-center z-[9999] p-4 transition-all animate-fadeIn">
    <div class="bg-[#111827] border border-gray-800 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
    <h3 class="text-xl font-bold text-white flex items-center gap-2">
    <svg class="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
    Massen-Config-Abgleich
    </h3>
    <p class="text-xs text-gray-400">
    Wähle aus, welcher Server als <b>Sicherheits-Vorlage</b> dienen soll. Seine Ernteraten, Taming-Multiplikatoren und Mod-Einstellungen werden auf alle anderen Instanzen überschrieben. Namen und IP/Ports bleiben geschützt!
    </p>
    <div>
    <label class="block text-xs font-bold uppercase tracking-wider text-gray-400 mb-1.5">Master-Vorlage wählen</label>
    <select v-model="masterConfigPluginId" class="w-full bg-gray-950 border border-gray-800 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500 transition cursor-pointer">
    <option value="" disabled>Server aussuchen...</option>
    <option v-for="memberId in activeClusterMembers" :key="memberId" :value="memberId">
    {{ getServerName(memberId) }}
    </option>
    </select>
    </div>
    <div class="flex justify-end gap-3 pt-2">
    <button @click="closeConfigSyncModal" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium rounded-lg transition cursor-pointer">Abbrechen</button>
    <button @click="submitConfigSync" :disabled="!masterConfigPluginId || isConfigSyncing" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition cursor-pointer">
    {{ isConfigSyncing ? 'Abgleich läuft...' : 'Jetzt synchronisieren' }}
    </button>
    </div>
    </div>
    </div>

    <div v-if="showModSyncModal" class="fixed inset-0 bg-black/70 flex items-center justify-center z-[9999] p-4 transition-all animate-fadeIn">
    <div class="bg-[#111827] border border-gray-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[90vh] flex flex-col">
    <h3 class="text-xl font-bold text-white flex items-center gap-2 shrink-0">
    <svg class="w-6 h-6 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
    Mod-Sync: {{ activeSyncClusterName }}
    </h3>
    <div class="flex-1 overflow-y-auto min-h-0 border border-gray-800 rounded-lg bg-gray-950 p-2 space-y-2">
    <div v-if="clusterModPool.length === 0" class="text-center text-gray-500 text-sm p-6 italic">
    In diesem Cluster sind aktuell noch keine Mods installiert.<br>Füge zuerst über das Server-Dashboard Mods zu einem Server hinzu!
    </div>
    <label v-for="mod in clusterModPool" :key="mod.id" class="flex items-center gap-3 p-3 bg-gray-900 border border-gray-800 rounded-lg hover:border-gray-700 cursor-pointer transition">
    <input type="checkbox" :value="mod.id" v-model="selectedSyncModIds" class="w-4 h-4 text-orange-500 bg-black border-gray-700 rounded focus:ring-orange-500 focus:ring-2 cursor-pointer">
    <div class="flex-1 min-w-0">
    <p class="text-sm font-bold text-gray-200 truncate">{{ mod.name }}</p>
    <p class="text-[10px] text-gray-500 font-mono mt-0.5">ID: {{ mod.id }} | Bisher auf {{ mod.active_on.length }} Server(n) aktiv</p>
    </div>
    </label>
    </div>
    <div class="flex justify-end gap-3 pt-2 shrink-0">
    <button @click="closeModSyncModal" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium rounded-lg transition cursor-pointer">Abbrechen</button>
    <button @click="submitModSync" class="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium rounded-lg transition cursor-pointer" :disabled="isSyncing">Apply</button>
    </div>
    </div>
    </div>

    <div class="flex justify-between items-center mb-6">
    <h2 class="text-2xl font-bold text-white flex items-center gap-2">
    <svg class="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
    Cluster Verwaltung
    </h2>
    <button @click="openCreateModal" class="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg shadow transition flex items-center gap-2 font-medium cursor-pointer">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
    Neuen Cluster erstellen
    </button>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-0 w-full">
    <div class="col-span-1 bg-[#111827] border border-gray-800 rounded-xl flex flex-col overflow-hidden">
    <div class="bg-gray-800/60 px-4 py-3 border-b border-gray-700"><h5 class="font-semibold text-gray-200">Isolierte Server</h5></div>
    <div class="p-4 flex-1 overflow-y-auto" @dragover.prevent @drop="removeFromClusterDrop">
    <div v-for="server in safeUnassignedServers" :key="server.id" class="p-3 mb-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg cursor-grab active:cursor-grabbing shadow-sm transition" draggable="true" @dragstart="startDrag($event, server)" @dragend="endDrag($event)">
    <h6 class="font-medium text-gray-200 flex items-center gap-2">{{ server.server_name }}</h6>
    <div class="text-xs text-orange-400 mt-1 uppercase font-semibold text-[10px]">{{ server.game_name }}</div>
    </div>
    <div v-if="safeUnassignedServers.length === 0" class="text-center text-gray-500 mt-10 text-sm italic">Keine isolierten Server.</div>
    </div>
    </div>

    <div class="col-span-3 overflow-y-auto pr-2">
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">

    <div v-for="(cluster, cId) in safeClusters" :key="cId" class="bg-[#111827] border-2 border-gray-800 rounded-xl flex flex-col overflow-hidden transition-all duration-200" :class="{ 'border-blue-500 bg-gray-800/40': dragTarget === cId }" @dragover.prevent="dragEnter(cId)" @dragleave="dragLeave" @drop="onDrop($event, cId)">

    <div class="px-4 py-3 border-b border-gray-800 flex justify-between items-center bg-gray-800/40">
    <div>
    <h5 class="font-bold text-blue-400 flex items-center gap-2">{{ cluster.name }}</h5>
    <span class="text-[10px] text-orange-500 font-bold uppercase tracking-wider bg-orange-950/40 px-2 py-0.5 rounded border border-orange-900/30">{{ cluster.game_name }}</span>
    </div>
    </div>

    <div class="px-4 py-3 bg-gray-900/50 border-b border-gray-800 flex gap-2">
    <button @click="openConfigSyncModal(cId)" :disabled="!cluster.members || cluster.members.length < 2" class="flex-1 flex items-center justify-center gap-2 bg-gray-800 hover:bg-blue-600 disabled:opacity-40 disabled:hover:bg-gray-800 disabled:cursor-not-allowed text-gray-300 hover:text-white border border-gray-700 hover:border-blue-500 rounded text-xs font-bold py-2 transition shadow-sm cursor-pointer">
    ⚙️ Configs anpassen
    </button>
    <button @click="openModSyncModal(cId, cluster.name)" class="flex-1 flex items-center justify-center gap-2 bg-gray-800 hover:bg-orange-600 text-gray-300 hover:text-white border border-gray-700 hover:border-orange-500 rounded text-xs font-bold py-2 transition shadow-sm cursor-pointer">
    🔌 Mods synchronisieren
    </button>
    <button @click="deleteCluster(cId, cluster.name)" class="flex items-center justify-center px-3 bg-red-950/30 hover:bg-red-600 text-red-400 hover:text-white border border-red-900/50 hover:border-red-500 rounded transition shadow-sm cursor-pointer" title="Cluster komplett auflösen">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
    </button>
    </div>

    <div class="p-4 flex-1">
    <div @click="openSystemFolder(cId)" title="Im Systemordner öffnen" class="text-xs text-gray-500 hover:text-gray-300 mb-4 bg-black/20 p-2.5 rounded border border-gray-800/60 hover:border-blue-500/50 break-all flex items-center gap-2.5 font-mono cursor-pointer transition shadow-inner">
    <svg class="w-4 h-4 shrink-0 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path></svg>
    {{ cluster.shared_dir }}
    </div>

    <div v-for="memberId in (cluster.members || [])" :key="memberId" class="p-3 mb-2 bg-gray-800 border border-gray-700 rounded-lg flex justify-between items-center shadow-sm">
    <div>
    <div class="font-medium text-gray-200 text-sm">{{ getServerName(memberId) }}</div>
    <div class="text-[11px] text-green-400 mt-1 flex items-center gap-1 font-semibold">🖥️ Im Cluster aktiv</div>
    </div>
    <button @click="removeFromCluster(memberId)" class="text-gray-500 hover:text-red-400 transition p-1 cursor-pointer"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button>
    </div>
    <div v-if="!cluster.members || cluster.members.length === 0" class="text-center text-gray-600 py-8 border-2 border-dashed border-gray-800 rounded-lg text-sm bg-black/5">Zonenhülle leer</div>
    </div>
    </div>
    </div>
    </div>
    </div>
    </div>
    `,
    data() {
        return {
            servers: [], clusters: {}, draggedServer: null, dragTarget: null,
            showCreateModal: false, newClusterName: '', newClusterGame: '', newClusterPath: '',
            showModSyncModal: false, activeSyncClusterId: null, activeSyncClusterName: '', clusterModPool: [], selectedSyncModIds: [], isSyncing: false,
            showConfigSyncModal: false, activeConfigClusterId: null, masterConfigPluginId: '', isConfigSyncing: false
        }
    },
    computed: {
        safeServers() { return Array.isArray(this.servers) ? this.servers : []; },
        safeClusters() { return (this.clusters && typeof this.clusters === 'object' && !Array.isArray(this.clusters)) ? this.clusters : {}; },
        safeUnassignedServers() {
            const assignedIds = new Set();
            for (const key in this.safeClusters) {
                const c = this.safeClusters[key];
                if (c && Array.isArray(c.members)) c.members.forEach(id => assignedIds.add(id));
            }
            return this.safeServers.filter(s => s && s.id && !assignedIds.has(s.id));
        },
        availableGames() { return [...new Set(this.safeServers.map(s => s.game_name))].filter(Boolean); },
        activeClusterMembers() {
            if (!this.activeConfigClusterId || !this.safeClusters[this.activeConfigClusterId]) return [];
            return this.safeClusters[this.activeConfigClusterId].members || [];
        }
    },
    methods: {
        getServerById(id) { return this.safeServers.find(s => s && s.id === id) || { id: id, server_name: id, game_name: 'Unbekannt' }; },
        getServerName(id) { return this.getServerById(id).server_name || id; },
        async loadData() {
            try {
                const resServers = await fetch('/api/plugins/installed').then(r => r.ok ? r.json() : []);
                const resClusters = await fetch('/api/clusters').then(r => r.ok ? r.json() : {});
                this.servers = resServers; this.clusters = resClusters;
            } catch (e) { this.servers = []; this.clusters = {}; }
        },

        openCreateModal() {
            this.newClusterName = ''; this.newClusterPath = '';
            this.newClusterGame = this.availableGames.length > 0 ? this.availableGames[0] : '';
            this.showCreateModal = true;
        },
        closeCreateModal() { this.showCreateModal = false; },

        async submitNewCluster() {
            if (!this.newClusterName || !this.newClusterGame) return;
            const cId = this.newClusterName.toLowerCase().replace(/[^a-z0-9]/g, '_') + "_" + this.newClusterGame.toLowerCase().replace(/[^a-z0-9]/g, '_');
            try {
                const res = await fetch('/api/clusters/create', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ cluster_id: cId, name: this.newClusterName, game_name: this.newClusterGame, custom_path: this.newClusterPath || "" })
                }).then(r => r.json());
                if (res.status === 'success') { this.showCreateModal = false; await this.loadData(); }
                else { await api.alert(res.message, "Fehler"); }
            } catch (e) { await api.alert("Server-Kommunikationsfehler.", "Netzwerkfehler"); }
        },

        openConfigSyncModal(clusterId) {
            this.activeConfigClusterId = clusterId;
            this.masterConfigPluginId = this.activeClusterMembers.length > 0 ? this.activeClusterMembers[0] : '';
            this.showConfigSyncModal = true;
            this.isConfigSyncing = false;
        },
        closeConfigSyncModal() {
            this.showConfigSyncModal = false;
        },
        async submitConfigSync() {
            this.isConfigSyncing = true;
            try {
                const res = await fetch(`/api/clusters/config/sync/${this.activeConfigClusterId}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ master_plugin_id: this.masterConfigPluginId })
                }).then(r => r.json());

                if (res.status === 'success') {
                    this.showConfigSyncModal = false;
                    await api.alert(res.message, "INI-Abgleich erfolgreich!");
                } else {
                    await api.alert(res.message, "Fehler beim Abgleich");
                }
            } catch (e) {
                await api.alert("Fehler bei der Kommunikation mit dem Patcher.", "Netzwerkfehler");
            }
            this.isConfigSyncing = false;
        },

        async openModSyncModal(clusterId, clusterName) {
            this.activeSyncClusterId = clusterId; this.activeSyncClusterName = clusterName || 'Unbenannt';
            this.clusterModPool = []; this.selectedSyncModIds = []; this.showModSyncModal = true; this.isSyncing = false;
            try {
                const res = await fetch(`/api/clusters/mods/${clusterId}`).then(r => r.json());
                if (res.mods) { this.clusterModPool = res.mods; this.selectedSyncModIds = this.clusterModPool.map(m => m.id); }
            } catch (e) { console.error(e); }
        },
        closeModSyncModal() { this.showModSyncModal = false; },
        async submitModSync() {
            this.isSyncing = true;
            try {
                const res = await fetch(`/api/clusters/mods/sync/${this.activeSyncClusterId}`, {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ mod_ids: this.selectedSyncModIds })
                }).then(r => r.json());
                if (res.status === 'success') { this.showModSyncModal = false; await api.alert(res.message, "Mods synchronisiert!"); }
                else { await api.alert(res.message, "Fehler"); }
            } catch (e) { await api.alert("Die Synchronisierung ist fehlgeschlagen.", "Netzwerkfehler"); }
            this.isSyncing = false;
        },

        async deleteCluster(clusterId, clusterName) {
            const isConfirmed = await api.confirm(`Möchtest du den Cluster '${clusterName}' wirklich auflösen?\n\nAlle zugeordneten Server werden sofort wieder isoliert.`, "Cluster auflösen?");
            if (!isConfirmed) return;
            try {
                const res = await fetch(`/api/clusters/delete/${clusterId}`, { method: 'DELETE' }).then(r => r.json());
                if (res.status === 'success') await this.loadData();
                else await api.alert(res.message, "Fehler");
            } catch (e) { await api.alert("Der Cluster konnte nicht aufgelöst werden.", "Fehler"); }
        },
        async openSystemFolder(clusterId) {
            try {
                const res = await fetch(`/api/clusters/open-folder/${clusterId}`, { method: 'POST' }).then(r => r.json());
                if (res.status !== 'success') await api.alert(res.message, "Fehler");
            } catch (e) { await api.alert("Der Ordner konnte nicht geöffnet werden.", "Fehler"); }
        },
        startDrag(event, server) { if (!server) return; this.draggedServer = server; event.dataTransfer.dropEffect = 'move'; event.dataTransfer.effectAllowed = 'move'; setTimeout(() => { if(event.target) event.target.classList.add('opacity-40'); }, 0); },
        endDrag(event) { if(event.target) event.target.classList.remove('opacity-40'); this.dragTarget = null; },
        dragEnter(cId) { this.dragTarget = cId; },
        dragLeave() { this.dragTarget = null; },
        async onDrop(event, clusterId) {
            this.dragTarget = null; const server = this.draggedServer; const cluster = this.safeClusters[clusterId]; if (!server || !cluster) return;
            if (server.game_name !== cluster.game_name) { await api.alert(`Du kannst keinen '${server.game_name}' Server in einen Cluster für '${cluster.game_name}' schieben!`, "Aktion blockiert"); this.draggedServer = null; return; }
            try {
                const res = await fetch(`/api/clusters/assign/${clusterId}/${server.id}`, { method: 'POST' }).then(r => r.json());
                if (res.status === 'success') await this.loadData();
                else await api.alert(res.message, "Fehler");
            } catch(e) { console.error(e); }
            this.draggedServer = null;
        },
        async removeFromClusterDrop(event) { const server = this.draggedServer; if (!server) return; await this.removeFromCluster(server.id); this.draggedServer = null; },
        async removeFromCluster(pluginId) { try { const res = await fetch(`/api/clusters/remove/${pluginId}`, { method: 'POST' }).then(r => r.json()); if (res.status === 'success') await this.loadData(); } catch(e) { console.error(e); } }
    },
    mounted() { this.loadData(); }
}
