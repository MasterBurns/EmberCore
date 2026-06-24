import { createApp, onMounted, onUnmounted } from 'vue';
import { store, api } from './store.js';

import Modals from './components/Modals.js';
import Sidebar from './components/Sidebar.js';
import SystemTab from './components/SystemTab.js';
import Marketplace from './components/Marketplace.js';
import ServerTab from './components/ServerTab.js';

const App = {
    components: { Modals, Sidebar, SystemTab, Marketplace, ServerTab },
    setup() {
        onMounted(() => {
            api.loadSystemInfo();
            api.checkSystemUpdate();
            api.fetchSysConfig();
            api.loadInstalledPlugins().then(() => {
                if (store.installedPlugins.length === 0) store.currentView = 'system_status';
            });

                window.statsInterval = setInterval(() => api.fetchStats(), 2000);
                setInterval(() => api.checkSystemUpdate(), 3600000);
        });

        onUnmounted(() => clearInterval(window.statsInterval));

        return { store };
    },
    template: `
    <Modals />

    <div v-if="store.isReconnecting" class="reconnect-overlay">
    <div class="animate-spin rounded-full h-16 w-16 border-4 border-orange-500 border-t-transparent mb-6"></div>
    <h2 class="text-2xl font-bold text-white tracking-widest uppercase mb-2">System Update läuft</h2>
    <p class="text-gray-400 text-sm">Bitte warten, EmberCore startet sich selbst neu...</p>
    </div>

    <Sidebar />

    <main class="flex-1 bg-gray-900/40 overflow-y-auto min-h-0 p-6 relative">
    <SystemTab v-if="store.currentView === 'system_status'" />
    <Marketplace v-if="store.currentView === 'marketplace'" />
    <ServerTab v-if="store.currentView === 'server'" />
    </main>
    `
};

createApp(App).mount('#app');
