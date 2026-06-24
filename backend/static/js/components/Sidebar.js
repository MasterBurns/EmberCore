import { store, api, categorizedPlugins } from '../store.js';

export default {
    setup() { return { store, api, categorizedPlugins }; },
    template: `
    <aside class="w-64 bg-gray-950 border-r border-gray-900 flex flex-col justify-between shadow-xl flex-shrink-0 h-full z-10">
    <div class="p-4 flex-1 overflow-y-auto space-y-6">
    <div class="flex items-center space-x-2 pb-4 border-b border-gray-900 cursor-pointer group relative" @click="api.openSystemTab()">
    <span class="text-xl font-black tracking-wider text-orange-500 group-hover:text-orange-400 transition">🔥 EMBERCORE</span>
    <span :class="store.systemUpdateAvailable ? 'bg-blue-600 text-white border-blue-500 animate-pulse' : 'bg-gray-900 border-gray-800 text-gray-500'" class="text-[10px] border px-1.5 py-0.5 rounded font-mono transition">{{ store.systemInfo.version }}</span>
    <span v-if="store.systemUpdateAvailable" class="absolute -top-1 -right-1 flex h-3 w-3"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span><span class="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span></span>
    </div>
    <div class="space-y-1">
    <button @click="api.openSystemTab()" :class="store.currentView === 'system_status' ? 'bg-gray-900 border-orange-500 text-orange-400 font-semibold' : 'border-transparent hover:bg-gray-900/50 text-gray-400'" class="w-full text-left p-2.5 rounded-lg border text-sm transition flex justify-between items-center cursor-pointer">
    <span>⚙️ System & Service</span>
    <span v-if="store.systemUpdateAvailable" class="flex h-2 w-2 relative"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span></span>
    </button>
    </div>
    <div class="space-y-5 pt-2 border-t border-gray-900/50">
    <div v-for="(instances, gameName) in categorizedPlugins" :key="gameName" class="space-y-1">
    <h3 class="text-xs font-bold text-gray-500 uppercase tracking-widest px-2 mb-2">{{ gameName }}</h3>
    <button v-for="plugin in instances" :key="plugin.id" @click="api.selectServer(plugin.id)" :class="store.selectedPlugin === plugin.id && store.currentView === 'server' ? 'bg-gray-900 border-orange-500 text-orange-400 font-semibold' : 'border-transparent hover:bg-gray-900/50 text-gray-400'" class="w-full text-left p-2.5 rounded-lg border text-sm transition flex justify-between items-center cursor-pointer">
    <span class="truncate pr-2">🖥️ {{ plugin.server_name }}</span>
    <span :class="plugin.status === 'online' ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500 shadow-red-500/50'" class="h-2 w-2 rounded-full shadow-sm flex-shrink-0"></span>
    </button>
    </div>
    </div>
    </div>
    <div class="p-4 border-t border-gray-900 bg-gray-950 flex-shrink-0">
    <button @click="api.openMarketplace()" :class="store.currentView === 'marketplace' ? 'bg-orange-600 text-white border-orange-500' : 'bg-gray-900 border-gray-800 hover:border-gray-700 text-gray-300'" class="w-full p-3 rounded-xl border text-center font-bold text-lg transition flex items-center justify-center space-x-2 shadow-md cursor-pointer">
    <span>➕</span><span class="text-sm tracking-wide uppercase">Server hinzufügen</span>
    </button>
    </div>
    </aside>
    `
};
