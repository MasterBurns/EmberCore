import { store, api } from '../store.js';

export default {
    setup() { return { store, api }; },
    template: `
    <div class="max-w-4xl mx-auto space-y-6">
    <div><h1 class="text-2xl font-black text-white tracking-tight">Neuen Server hinzufügen</h1><p class="text-sm text-gray-400">Einen neuen Server aus einer Vorlage erstellen.</p></div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div v-for="plugin in store.availablePlugins" :key="plugin.id" class="bg-gray-950 rounded-xl border border-gray-900 p-5 flex flex-col justify-between shadow-xl transition hover:border-gray-800">
    <div class="space-y-3">
    <div class="flex justify-between items-start"><span class="text-[10px] bg-orange-950/60 text-orange-400 border border-orange-900/40 px-2 py-0.5 rounded font-bold uppercase tracking-wider">{{ plugin.category }}</span><span class="text-xs text-gray-600 font-mono">v{{ plugin.version }}</span></div>
    <h3 class="text-lg font-bold text-white">{{ plugin.name }}</h3><p class="text-xs text-gray-400 leading-relaxed">{{ plugin.description }}</p>
    </div>
    <div class="mt-6 border-t border-gray-900 pt-4">
    <button @click="api.subscribePlugin(plugin)" :disabled="store.isSubscribing === plugin.id" class="w-full bg-orange-600 hover:bg-orange-500 disabled:bg-gray-900 text-white font-medium p-2 rounded-lg transition cursor-pointer text-sm">
    {{ store.isSubscribing === plugin.id ? '⏳ Herunterladen...' : '➕ Server erstellen' }}
    </button>
    </div>
    </div>
    </div>
    </div>
    `
};
