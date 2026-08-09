import { reactive, computed } from 'vue';

export const store = reactive({
    currentView: 'system_status',
    serverTab: 'status',
    selectedPlugin: null,

    isActionLoading: false,
    serverActions: {},
    isSubscribing: null,
    loadingMessage: "",

    systemInfo: { version: "Laden...", build_date: "", history: [] },
    systemUpdateAvailable: false,
    isSystemUpdating: false,
    isReconnecting: false,

    systemServiceStats: { os: "Laden...", is_installed: false, is_running: false, main_pid: 0, watchdog_active: false, uptime_seconds: 0, cpu_percent: 0, ram_mb: 0 },
    sysConfig: { verbose_logging: false },

    installedPlugins: [],
    availablePlugins: [],

    serverStats: { status: "offline", cpu_percent: 0, ram_mb: 0, disk: null, update_info: { available: false } },
    consoleLogs: [],
    activeDiagnostics: [],
    activeMods: [],
    newModId: "",

    backupList: [],
    backupSchedule: { schedules: [], retention: {keep_latest: 5, keep_daily: 7, keep_weekly: 4, keep_monthly: 3} },
    newSchedType: "daily",
    newSchedVal: "",

    configData: { enabled: false, fields: [], unknown_fields: [], values: {} },
    configSearchText: "",
    configCollapsedFiles: {},
    listData: { enabled: false, lists: [] },
    networkData: { enabled: false, ports: [] },

    // UNTERBAU FÜR UNSERE NEUEN POPUPS
    uiModal: { show: false, type: 'alert', title: '', message: '', inputVal: '', placeholder: '', resolve: null },
    isLogViewerOpen: false,
    systemLogData: "Lade Logs...",
    sysConfig: { verbose_logging: false, allow_multiple_instances: false },
    startupData: { enabled: false, available_maps: [], selected_map: "" },
    discordWizard: { step: 1, appId: '', botToken: '', pairingKey: 'EMBER-' + Math.random().toString(36).substring(2, 10).toUpperCase() },
    backup_progress: { active: false, percent: 0 },
    devMode: false,
    
    ampImportTask: null,
    installTasks: {},
    installInterval: null,
    ampImportPath: "",
    ampImportMode: "move",
    pluginManifest: null,
    pollErrors: {}
});

export const categorizedPlugins = computed(() => {
    const map = {};
    store.installedPlugins.forEach(p => {
        if (p.is_dev && !store.sysConfig.dev_mode) return;
        if (!map[p.game_name]) map[p.game_name] = [];
        map[p.game_name].push(p);
    });
    return map;
});

export const currentServerData = computed(() => {
    return store.installedPlugins.find(p => p.id === store.selectedPlugin) || { server_name: "Server", game_name: "Unbekannt" };
});

export const filteredGroupedConfigFields = computed(() => {
    const search = store.configSearchText.toLowerCase().trim();
    const groups = {};
    
    const allFields = store.configData?.fields || [];
    allFields.forEach(f => {
        const val = String(store.configData.values[f.key] || '').toLowerCase();
        const keyMatch = f.key.toLowerCase().includes(search);
        const labelMatch = (f.label || '').toLowerCase().includes(search);
        const valMatch = val.includes(search);
        
        if (search === "" || keyMatch || labelMatch || valMatch) {
            const file = f.file || "Einstellung";
            if (!groups[file]) groups[file] = { fields: [], unknown_fields: [] };
            groups[file].fields.push(f);
        }
    });

    const allUnknowns = store.configData?.unknown_fields || [];
    allUnknowns.forEach(f => {
        const val = String(store.configData.values[f.key] || '').toLowerCase();
        const keyMatch = f.key.toLowerCase().includes(search);
        const valMatch = val.includes(search);
        
        if (search === "" || keyMatch || valMatch) {
            const file = f.file || "Einstellung";
            if (!groups[file]) groups[file] = { fields: [], unknown_fields: [] };
            groups[file].unknown_fields.push(f);
        }
    });

    return groups;
});

export const formatUptime = (seconds) => {
    if (!seconds) return "0s";
    const d = Math.floor(seconds / (3600*24));
    const h = Math.floor(seconds % (3600*24) / 3600);
    const m = Math.floor(seconds % 3600 / 60);
    const s = Math.floor(seconds % 60);
    let res = [];
    if (d > 0) res.push(d + "d");
    if (h > 0) res.push(h + "h");
    if (m > 0) res.push(m + "m");
    res.push(s + "s");
    return res.join(" ");
};

export const api = {
    // === GLOBALE DIALOG ENGINE ===
    alert(message, title="Information") { return new Promise((resolve) => { store.uiModal = { show: true, type: 'alert', title, message, inputVal: '', placeholder: '', resolve }; }); },
    confirm(message, title="Bitte bestätigen") { return new Promise((resolve) => { store.uiModal = { show: true, type: 'confirm', title, message, inputVal: '', placeholder: '', resolve }; }); },
    prompt(message, defaultVal="", placeholder="", title="Eingabe") { return new Promise((resolve) => { store.uiModal = { show: true, type: 'prompt', title, message, inputVal: defaultVal, placeholder, resolve }; setTimeout(() => { const el = document.getElementById('modal-input'); if(el) {el.focus(); el.select();} }, 50); }); },
    closeDialog(result) { if (store.uiModal.resolve) store.uiModal.resolve(result); store.uiModal.show = false; },

    async fetchSysLogs() {
        try {
            const res = await fetch('/api/system/logs');
            if (res.ok) {
                const data = await res.json();
                store.systemLogData = data.logs || "Bisher keine Logs vorhanden.";
                setTimeout(() => { const el = document.getElementById('log-viewer-textarea'); if(el) el.scrollTop = el.scrollHeight; }, 50);
            }
        } catch(e) { store.systemLogData = "Logbuch konnte nicht geladen werden."; }
    },
    openLogViewer() { store.isLogViewerOpen = true; store.systemLogData = "Lade Logs..."; this.fetchSysLogs(); },
    async clearSysLogs() { if (!(await this.confirm("Möchtest du das gesamte Logbuch unwiderruflich leeren?", "Logs leeren"))) return; try { await fetch('/api/system/logs/clear', { method: 'POST' }); await this.fetchSysLogs(); } catch(e) {} },
    async fetchSysConfig() { try { const res = await fetch('/api/system/settings'); if (res.ok) store.sysConfig = await res.json(); } catch(e) {} },
    async saveSysConfig() { try { await fetch('/api/system/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(store.sysConfig) }); this.alert("Die Logging-Einstellungen wurden gespeichert.", "System"); } catch(e) {} },
    openSystemTab() { store.currentView = 'system_status'; store.selectedPlugin = null; this.fetchServiceStatus(); this.fetchSysConfig(); },
    async fetchServiceStatus() { if (store.currentView !== 'system_status') return; try { const res = await fetch('/api/system/service/status'); if (res.ok) store.systemServiceStats = await res.json(); } catch (e) { store.systemServiceStats.main_pid = 0; } },
    async installService() { store.isActionLoading = true; try { const res = await fetch('/api/system/service/install', { method: 'POST' }); const data = await res.json(); await this.alert(data.message, "System Dienst"); setTimeout(() => this.fetchServiceStatus(), 3000); } catch (e) {} store.isActionLoading = false; },
    async uninstallService() { if (!(await this.confirm("Bist du sicher? EmberCore startet nach einem Server-Neustart dann nicht mehr automatisch!", "Dienst entfernen"))) return; store.isActionLoading = true; try { const res = await fetch('/api/system/service/uninstall', { method: 'POST' }); const data = await res.json(); await this.alert(data.message, "System Dienst"); setTimeout(() => this.fetchServiceStatus(), 3000); } catch (e) {} store.isActionLoading = false; },
    async startService() { store.isActionLoading = true; try { const res = await fetch('/api/system/service/start', { method: 'POST' }); const data = await res.json(); await this.alert(data.message, "System Dienst"); setTimeout(() => this.fetchServiceStatus(), 3000); } catch (e) {} store.isActionLoading = false; },
    async stopService() { store.isActionLoading = true; try { const res = await fetch('/api/system/service/stop', { method: 'POST' }); const data = await res.json(); await this.alert(data.message, "System Dienst"); setTimeout(() => this.fetchServiceStatus(), 3000); } catch (e) {} store.isActionLoading = false; },
    async loadSystemInfo() { try { const res = await fetch('/api/system/version'); if (res.ok) store.systemInfo = await res.json(); } catch (e) {} },
    async checkSystemUpdate() { try { const res = await fetch('/api/system/check-update'); if (res.ok) { const data = await res.json(); store.systemUpdateAvailable = data.update_available; } } catch (e) {} },
    async triggerSystemUpdate() {
        store.isSystemUpdating = true;
        try {
            const res = await fetch('/api/system/update', { method: 'POST' }); const data = await res.json();
            if (data.status === 'info') { await this.alert(data.message, "Kein Update"); store.isSystemUpdating = false; }
            else if (data.status === 'success') {
                store.isReconnecting = true;
                const pingInterval = setInterval(async () => { try { const ping = await fetch('/api/system/version'); if (ping.ok) { clearInterval(pingInterval); window.location.reload(true); } } catch (e) { } }, 2000);
            } else { await this.alert(data.message, "Update Fehler"); store.isSystemUpdating = false; }
        } catch (e) { await this.alert("Update-Server nicht erreichbar.", "Netzwerk Fehler"); store.isSystemUpdating = false; }
    },
    async loadInstalledPlugins() { 
        try {
            const cached = localStorage.getItem('embercore_plugins');
            if (cached) {
                store.installedPlugins = JSON.parse(cached);
                if (store.installedPlugins.length === 0) store.currentView = 'system_status';
            }
        } catch(e) {}
        
        return fetch('/api/plugins/installed').then(res => res.json()).then(data => {
            store.installedPlugins = data;
            localStorage.setItem('embercore_plugins', JSON.stringify(data));
            if (store.selectedPlugin && !store.installedPlugins.find(p => p.id === store.selectedPlugin)) this.openMarketplace(); 
        }).catch(() => {});
    },
    async fetchStats() {
        if (store.currentView === 'system_status') this.fetchServiceStatus();
        if (!store.selectedPlugin || store.currentView !== 'server') return;
        const currentPlugin = store.selectedPlugin;
        try {
            const res = await fetch(`/api/server/stats/${currentPlugin}`);
            if (!res.ok) throw new Error("Network response was not ok");
            const data = await res.json();
            if (store.selectedPlugin !== currentPlugin) return;
            store.serverStats = data; 
            this.loadInstalledPlugins(); 
            
            if (store.serverStats.status === 'online') { 
                const diagRes = await fetch(`/api/server/diagnostics/${currentPlugin}`); 
                if (diagRes.ok) {
                    const diagData = await diagRes.json();
                    if (store.selectedPlugin === currentPlugin) store.activeDiagnostics = diagData;
                }
            } else { 
                store.activeDiagnostics = []; 
            }
            if (store.serverTab === 'console' && store.serverStats.status === 'online') {
                const logRes = await fetch(`/api/server/logs/${currentPlugin}`);
                if (logRes.ok) {
                    const logData = await logRes.json(); 
                    if (store.selectedPlugin !== currentPlugin) return;
                    const oldLen = store.consoleLogs.length; store.consoleLogs = logData.logs;
                    if (logData.logs.length !== oldLen) { setTimeout(() => { const el = document.getElementById('console-output'); if(el) el.scrollTop = el.scrollHeight; }, 50); }
                }
            }
            store.pollErrors[currentPlugin] = 0;
        } catch (err) {
            store.pollErrors[currentPlugin] = (store.pollErrors[currentPlugin] || 0) + 1;
        }
    },
    async checkGameUpdate() { 
        const pId = store.selectedPlugin;
        this.setServerLoading(pId, "Frage Steam-Server nach neuer Version..."); 
        try { 
            const res = await fetch(`/api/server/check-updates/${pId}`, { method: 'POST' }); 
            const data = await res.json(); 
            await this.alert(data.message, "Update Check"); 
            this.fetchStats(); 
        } catch (e) { 
            await this.alert("Konnte Steam-Server nicht erreichen.", "Netzwerk Fehler"); 
        } 
        this.setServerLoading(pId, null); 
    },
    async selectServer(id) { 
        store.selectedPlugin = id; 
        store.currentView = "server"; 
        store.serverTab = "status"; 
        store.serverStats.disk = null; 
        store.listData = null;
        store.configData = { enabled: false, fields: [], unknown_fields: [], values: {} };
        store.originalConfigValues = null;
        store.startupData = { enabled: false, selected_map: '', show_external_console: false, show_in_discord: true };
        
        // UI-Latenz Eliminieren: Sofortiger Stats-Fetch ohne Disk
        fetch(`/api/server/stats/${id}?skip_disk=true`).then(res => res.json()).then(data => {
            if (store.selectedPlugin === id) store.serverStats = data;
        }).catch(() => {});
        
        const currentPlugin = store.selectedPlugin;
        // Map sofort laden
        const startRes = await fetch(`/api/server/startup/${currentPlugin}`);
        if (startRes.ok) {
            const startData = await startRes.json();
            if (store.selectedPlugin === currentPlugin) store.startupData = startData;
        }
        else store.startupData = { enabled: false, available_maps: [], selected_map: "" };

        // Manifest laden (für UI-Abhängigkeiten wie CurseForge vs Steam)
        try {
            const manifestRes = await fetch(`/api/server/manifest/${currentPlugin}`);
            if (manifestRes.ok) {
                const manifestData = await manifestRes.json();
                if (store.selectedPlugin === currentPlugin) store.pluginManifest = manifestData;
            } else {
                store.pluginManifest = null;
            }
        } catch(e) { store.pluginManifest = null; }
    },
    openConsoleTab() { store.serverTab = 'console'; this.fetchStats(); },
    async openConfigTab() {
        store.serverTab = 'config'; 
        
        const currentPlugin = store.selectedPlugin;
        // INI laden
        const res = await fetch(`/api/server/config/${currentPlugin}`);
        if (res.ok) {
            const data = await res.json();
            if (store.selectedPlugin !== currentPlugin) return;
            if (data.enabled && data.values) {
                data.fields.forEach(f => { if (f.type === 'boolean') { const val = data.values[f.key]; data.values[f.key] = (val === 1 || val === "1" || String(val).toLowerCase() === "true"); } });
                if (data.unknown_fields) { data.unknown_fields.forEach(f => { if (f.type === 'boolean') { const val = data.values[f.key]; data.values[f.key] = (val === true || String(val).toLowerCase() === "true"); } }); }
            }
            store.configData = data;
            if (data.values) store.originalConfigValues = JSON.parse(JSON.stringify(data.values));
            else store.originalConfigValues = null;
        }
    },
    async saveMap() {
        if (store.startupData?.enabled) {
            await fetch(`/api/server/startup/${store.selectedPlugin}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ selected_map: store.startupData.selected_map, show_external_console: store.startupData.show_external_console, show_in_discord: store.startupData.show_in_discord, custom_start_parameters: store.startupData.custom_start_parameters }) });
        }
    },
    async openListsTab() { store.serverTab = 'lists'; const res = await fetch(`/api/server/lists/${store.selectedPlugin}`); if (res.ok) store.listData = await res.json(); },
    async saveList(lst) { const payload = {}; payload[lst.id] = lst.content; await fetch(`/api/server/lists/${store.selectedPlugin}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); await this.alert("Die Liste wurde erfolgreich auf dem Server gespeichert.", "Liste gespeichert"); },
    async openNetworkTab() { store.serverTab = 'network'; const currentPlugin = store.selectedPlugin; const res = await fetch(`/api/server/network/${currentPlugin}`); if (res.ok) { const data = await res.json(); if (store.selectedPlugin === currentPlugin) store.networkData = data; } },
    async importSavegame() {
        const pId = store.selectedPlugin;
        const file = await new Promise(resolve => {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.zip';
            input.onchange = e => resolve(e.target.files[0]);
            input.click();
        });
        if (!file) return;

        this.setServerLoading(pId, "Lade Savegame hoch...");
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`/api/server/savegame/import/${pId}`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok) await this.alert(data.message, "Import erfolgreich");
            else await this.alert(data.detail, "Import fehlgeschlagen");
        } catch (e) {
            await this.alert("Upload fehlgeschlagen.", "Fehler");
        }
        this.setServerLoading(pId, null);
    },
    async saveNetworkPorts() {
        const pId = store.selectedPlugin;
        this.setServerLoading(pId, "Speichere Ports...");
        try {
            const res = await fetch(`/api/server/network/${pId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ports: store.networkData.ports })
            });
            const data = await res.json();
            await this.alert(data.message, data.status === "success" ? "Ports gespeichert" : "Fehler");
            
            // Reload network data directly
            if (data.status === "success") {
                await this.openNetworkTab();
            }
        } catch (e) {
            await this.alert("Netzwerkfehler beim Speichern der Ports.", "Fehler");
        } finally {
            this.setServerLoading(pId, null);
        }
    },
    async triggerNetworkSetup() { 
        const pId = store.selectedPlugin;
        this.setServerLoading(pId, "Erstelle und sende Firewall/Router Anweisung..."); 
        const res = await fetch(`/api/server/network/setup/${pId}`, { method: 'POST' }); 
        const data = await res.json(); 
        await this.alert(data.message, "Netzwerk Setup"); 
        this.setServerLoading(pId, null); 
    },
    openModsTab() { store.serverTab = 'mods'; this.fetchMods(); },
    async fetchMods() { const currentPlugin = store.selectedPlugin; const res = await fetch(`/api/server/mods/${currentPlugin}`); if (res.ok) { const data = await res.json(); if (store.selectedPlugin === currentPlugin) store.activeMods = data; } },
    async addMod() {
        const inputStr = store.newModId.trim();
        if (!inputStr) return;
        
        const modIds = inputStr.split(',').map(s => s.trim()).filter(s => s);
        if (modIds.length === 0) return;
        
        store.isActionLoading = true; 
        let errors = [];
        let successCount = 0;
        
        for (const modId of modIds) {
            store.loadingMessage = `Füge Mod ${modId} hinzu... (${successCount + 1}/${modIds.length})`;
            try {
                const res = await fetch(`/api/server/mods/add/${store.selectedPlugin}/${encodeURIComponent(modId)}`, { method: 'POST' }); 
                const data = await res.json();
                if(data.status === "error") {
                    errors.push(`Mod ${modId}: ${data.message}`);
                } else {
                    successCount++;
                }
            } catch (e) {
                errors.push(`Mod ${modId}: Netzwerkfehler`);
            }
        }
        
        if (errors.length > 0) {
            await this.alert("Einige Mods konnten nicht hinzugefügt werden:\n" + errors.join("\n"), "Workshop/CurseForge Fehler");
        }
        
        store.newModId = ""; store.isActionLoading = false; this.fetchMods();
    },
    async deleteMod(modId) {
        if (!(await this.confirm("Möchtest du diese Modifikation wirklich vom Server entfernen?", "Mod löschen"))) return;
        store.isActionLoading = true; store.loadingMessage = "Lösche Mod...";
        
        // Zuerst per normalem DELETE versuchen (für normale kurze IDs)
        try {
            // Wir verwenden POST mit Body als Fallback für extrem lange Strings, falls es die Route gibt.
            // Um das Problem des Users zu beheben, schicken wir einfach einen POST Request.
            const res = await fetch(`/api/server/mods/delete_bulk/${store.selectedPlugin}`, { 
                method: 'POST', 
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ mod_id: modId }) 
            });
            if (res.status === 404) {
                // Fallback für alte Backend-Versionen
                await fetch(`/api/server/mods/delete/${store.selectedPlugin}/${encodeURIComponent(modId)}`, { method: 'DELETE' });
            }
        } catch(e) {
            console.error(e);
        }
        
        store.isActionLoading = false;
        this.fetchMods(); 
    },
    openBackupTab() { store.serverTab = 'backups'; this.fetchBackups(); this.fetchBackupSchedule(); },
    async fetchBackups() { 
        const currentPlugin = store.selectedPlugin; 
        if(!currentPlugin) return;
        try {
            const res = await fetch(`/api/server/backup/list/${currentPlugin}`); 
            if (!res.ok) throw new Error("fetch fail");
            const data = await res.json(); 
            if (store.selectedPlugin === currentPlugin) store.backupList = data; 
            store.pollErrors[currentPlugin] = 0;
        } catch(e) {
            store.pollErrors[currentPlugin] = (store.pollErrors[currentPlugin] || 0) + 1;
        }
    },
    async fetchBackupSchedule() { 
        const currentPlugin = store.selectedPlugin; 
        if(!currentPlugin) return;
        try {
            const res = await fetch(`/api/server/backup/schedule/${currentPlugin}`); 
            if (!res.ok) throw new Error("fetch fail");
            const data = await res.json(); 
            if (store.selectedPlugin !== currentPlugin) return; 
            if (!data.schedules) data.schedules = []; 
            if (!data.retention) data.retention = {keep_latest: 5, keep_daily: 7, keep_weekly: 4, keep_monthly: 3}; 
            store.backupSchedule = data; 
            store.pollErrors[currentPlugin] = 0;
        } catch(e) {
            store.pollErrors[currentPlugin] = (store.pollErrors[currentPlugin] || 0) + 1;
        }
    },
    async subscribePlugin(plugin) {
        const customName = await this.prompt(`Bitte gib einen Namen für deinen neuen '${plugin.name}' Server ein:`, "Mein Server", "z.B. PvE The Island", "Neuen Server installieren");
        if (customName === null || customName.trim() === "") return;
        const exists = store.installedPlugins.find(p => p.server_name.toLowerCase() === customName.trim().toLowerCase());
        if (exists) { await this.alert("Ein Server mit diesem Namen existiert bereits!", "Fehler"); return; }
        store.isSubscribing = plugin.id;
        const downloadUrl = plugin.yaml_url || plugin.zip_url;
        const endpoint = `/api/plugins/subscribe/${plugin.id}?url=${encodeURIComponent(downloadUrl)}&server_name=${encodeURIComponent(customName.trim())}`;
        try {
            const res = await fetch(endpoint, { method: 'POST' }); const data = await res.json();
            if (data.status === "error") await this.alert(data.message || data.detail, "Installationsfehler");
            store.isSubscribing = null; await this.loadInstalledPlugins();
            if(data.status === "success" && data.instance_id) this.selectServer(data.instance_id);
        } catch (e) { await this.alert("Server-Paket konnte nicht heruntergeladen werden.", "Netzwerkfehler"); store.isSubscribing = null; }
    },
    async saveConfig() { 
        // INI speichern
        await fetch(`/api/server/config/${store.selectedPlugin}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(store.configData.values) }); 
        
        // NEU: Map speichern
        if (store.startupData.enabled) {
            await fetch(`/api/server/startup/${store.selectedPlugin}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ selected_map: store.startupData.selected_map, show_external_console: store.startupData.show_external_console, show_in_discord: store.startupData.show_in_discord }) });
        }
        
        this.loadInstalledPlugins(); 
        if (store.configData?.values) store.originalConfigValues = JSON.parse(JSON.stringify(store.configData.values));
        await this.alert("Die Konfiguration wurde erfolgreich gespeichert.", "Erfolg"); 
    },
    async installServer() {
        const pId = store.selectedPlugin;
        const res = await fetch(`/api/server/install/${pId}`, { method: 'POST' }); 
        const data = await res.json();
        if (data.status === 'error') {
            await this.alert(data.message, "Fehler");
            return;
        }
        this.pollInstallStatus();
    },
    async pollInstallStatus() {
        if (!store.installInterval) {
            store.installInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/api/server/install/status_all`);
                    if (!res.ok) throw new Error("fetch fail");
                    const data = await res.json();
                    
                    for (const [pId, task] of Object.entries(data)) {
                        const oldStatus = store.installTasks[pId]?.status;
                        store.installTasks[pId] = task;
                        
                        if (oldStatus && oldStatus !== 'completed' && task.status === 'completed' && task.auto_start) {
                            this._internalStartServer(pId);
                        }
                        
                        if (oldStatus && ["running", "queued"].includes(oldStatus) && !["running", "queued"].includes(task.status)) {
                            if (pId === store.selectedPlugin) this.fetchStats();
                        }
                    }
                    
                    // Bereinige gelöschte Tasks
                    for (const pId of Object.keys(store.installTasks)) {
                        if (!data[pId]) delete store.installTasks[pId];
                    }
                    store.pollErrors['__global__'] = 0;
                } catch(e) {
                    store.pollErrors['__global__'] = (store.pollErrors['__global__'] || 0) + 1;
                }
            }, 1500);
        }
    },
    async cancelInstall() {
        if (!store.selectedPlugin) return;
        await fetch(`/api/server/install/cancel/${store.selectedPlugin}`, { method: 'POST' });
    },
    setServerLoading(pId, msg) {
        if (msg) store.serverActions[pId] = { isLoading: true, message: msg };
        else delete store.serverActions[pId];
    },
    async startServer() { 
        this._internalStartServer(store.selectedPlugin);
    },
    async _internalStartServer(pId) {
        this.setServerLoading(pId, "Initialisiere Prozessumgebung..."); 
        const res = await fetch(`/api/server/start/${pId}`, { method: 'POST' }); 
        const data = await res.json(); 
        if(data.status === 'error') {
            await this.alert(data.message, "Start blockiert"); 
        } else if (data.status === 'info') {
            this.pollInstallStatus();
        }
        this.setServerLoading(pId, null);
        if (pId === store.selectedPlugin) setTimeout(() => this.fetchStats(), 1000); 
    },
    async stopServer() { 
        const pId = store.selectedPlugin;
        this.setServerLoading(pId, "Sende Shutdown Signal an Prozesse..."); 
        await fetch(`/api/server/stop/${pId}`, { method: 'POST' }); 
        this.setServerLoading(pId, null);
        setTimeout(() => this.fetchStats(), 500); 
    },
    async deleteServer() {
        const server = store.installedPlugins.find(p => p.id === store.selectedPlugin);
        const serverName = server ? server.server_name : 'Server';
        if (!(await this.confirm(`Möchtest du den Server '${serverName}' mitsamt aller Spieldateien und Backups komplett löschen? Das kann nicht rückgängig gemacht werden!`, "Server vernichten"))) return;
        try { const res = await fetch(`/api/server/delete/${store.selectedPlugin}`, { method: 'DELETE' }); const data = await res.json(); if(res.ok) { this.openMarketplace(); this.loadInstalledPlugins(); } else { await this.alert(data.detail || data.message, "Fehler"); } } catch(e){}
    },
    openLocalFolder() { fetch(`/api/server/open-folder/${store.selectedPlugin}`, { method: 'POST' }); },
    openMarketplace() { store.currentView = "marketplace"; store.selectedPlugin = null; fetch('/api/plugins/available').then(r => r.json()).then(d => store.availablePlugins = d).catch(() => {}); },
    addSchedule() { if(!store.newSchedVal) return; store.backupSchedule.schedules.push({ type: store.newSchedType, value: store.newSchedVal }); this.saveBackupSettings(); store.newSchedVal = ""; },
    removeSchedule(idx) { store.backupSchedule.schedules.splice(idx, 1); this.saveBackupSettings(); },
    async saveBackupSettings() { await fetch(`/api/server/backup/schedule/${store.selectedPlugin}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(store.backupSchedule) }); },
    async applyFix(fixType) { 
        const pId = store.selectedPlugin;
        this.setServerLoading(pId, "Wende Fix an..."); 
        const res = await fetch(`/api/server/diagnostics/fix/${pId}/${fixType}`, { method: 'POST' }); 
        const data = await res.json(); 
        await this.alert(data.message, "Absturz-Schutz"); 
        if (fixType === "update_server") this.pollInstallStatus();
        this.setServerLoading(pId, null);
        this.fetchStats(); 
    },
    async createBackup() { 
        const pId = store.selectedPlugin;
        this.setServerLoading(pId, "Erstelle Backup...");
        await fetch(`/api/server/backup/create/${pId}`, { method: 'POST' }); 
        this.fetchBackups(); 
        this.setServerLoading(pId, null);
    },
    async restoreBackup(filename) { if (!(await this.confirm(`Möchtest du das Backup '${filename}' wirklich einspielen?\n\nAlle aktuellen Fortschritte werden überschrieben!`, "Backup einspielen"))) return; await fetch(`/api/server/backup/restore/${store.selectedPlugin}/${filename}`, { method: 'POST' }); await this.alert("Das Rollback war erfolgreich.", "Erfolg"); },
    async deleteBackup(filename) { if (!(await this.confirm(`Soll das Backup unwiderruflich gelöscht werden?`, "Archiv löschen"))) return; await fetch(`/api/server/backup/delete/${store.selectedPlugin}/${filename}`, { method: 'DELETE' }); this.fetchBackups(); },
    
    async importSavegame() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.zip';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            if (!(await this.confirm(`Möchtest du den Spielstand aus '${file.name}' wirklich importieren?\n\nDie Ordnerstruktur wird automatisch korrigiert. Achtung: Dein bisheriger lokaler Fortschritt wird gnadenlos gelöscht/überschrieben!`, "Savegame Importieren"))) return;
            
            const pId = store.selectedPlugin;
            const formData = new FormData();
            formData.append("file", file);
            
            this.setServerLoading(pId, "Lade Savegame hoch...");
            try {
                const res = await fetch(`/api/server/backup/import/${pId}`, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.status === 'success') {
                    await this.alert(data.message, "Erfolg");
                } else {
                    await this.alert(data.message, "Fehler");
                }
            } catch (err) {
                await this.alert("Netzwerkfehler beim Upload.", "Fehler");
            } finally {
                this.setServerLoading(pId, null);
            }
        };
        input.click();
    },

    // NEU: Discord API Methoden
    async fetchDiscordSettings() {
        try {
            const res = await fetch('/api/system/discord');
            if (res.ok) {
                const data = await res.json();
                store.sysConfig.discord_linked = data.discord_linked;
                store.sysConfig.discord_guild_name = data.discord_guild_name;
                store.sysConfig.discord_channel_name = data.discord_channel_name;
            }
        } catch (e) {}
    },
    async saveDiscordSettings(appId, token) {
        store.isActionLoading = true;
        try {
            const payload = { app_id: appId, token: token, pairing_key: store.discordWizard.pairingKey };
            const res = await fetch('/api/system/discord/setup', { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' }, 
                body: JSON.stringify(payload) 
            });
            const data = await res.json();
            if (res.ok) {
                await this.alert("Der Bot-Prozess wurde gestartet! Gehe jetzt in deinen Discord und gib den /link Befehl ein.", "Bot Online");
                this.fetchDiscordSettings();
            } else {
                await this.alert(data.message || "Setup fehlgeschlagen.", "Fehler");
            }
        } catch (e) {
            await this.alert("Konnte den Bot nicht starten.", "Netzwerkfehler");
        }
        store.isActionLoading = false;
    },
    async unlinkDiscord() {
        if (!(await this.confirm("Möchtest du den Bot wirklich stoppen und die Verknüpfung aufheben?", "Discord trennen"))) return;
        try {
            await fetch('/api/system/discord/unlink', { method: 'POST' });
            store.sysConfig.discord_linked = false;
            store.discordWizard.step = 1; // Wizard zurücksetzen
            store.discordWizard.appId = '';
            store.discordWizard.botToken = '';
            await this.alert("Die Verbindung wurde erfolgreich getrennt.", "Getrennt");
        } catch(e) {}
    }
};
