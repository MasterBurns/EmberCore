import { store, api } from '../store.js';

export default {
    setup() { return { store, api }; },
    template: `
    <Transition name="modal">
    <div v-if="store.isLogViewerOpen" class="fixed inset-0 bg-black/90 z-[99999] flex flex-col p-4 sm:p-8 backdrop-blur-md">
    <div class="flex justify-between items-center mb-4">
    <h2 class="text-xl font-bold text-orange-500 uppercase tracking-widest">📄 System Log & Troubleshooting</h2>
    <div class="flex gap-4">
    <button @click="api.fetchSysLogs()" class="text-white bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded-lg font-bold transition cursor-pointer">Aktualisieren</button>
    <button @click="api.clearSysLogs()" class="text-red-400 border border-red-900/50 bg-red-900/30 hover:bg-red-900 px-4 py-2 rounded-lg font-bold transition cursor-pointer">Leeren</button>
    <button @click="store.isLogViewerOpen = false" class="text-white bg-orange-600 hover:bg-orange-500 px-4 py-2 rounded-lg font-bold transition cursor-pointer">Schließen (X)</button>
    </div>
    </div>
    <textarea id="log-viewer-textarea" readonly class="flex-1 w-full bg-black border border-gray-800 rounded-xl p-4 text-xs text-green-400 font-mono focus:outline-none resize-none whitespace-pre">{{ store.systemLogData }}</textarea>
    </div>
    </Transition>

    <Transition name="modal">
    <div v-if="store.uiModal.show" class="fixed inset-0 bg-black/80 z-[99999] flex items-center justify-center p-4 backdrop-blur-sm">
    <div class="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden flex flex-col transform transition-all scale-100">
    <div class="p-4 border-b border-gray-800 bg-gray-950 flex justify-between items-center">
    <h2 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
    <span v-if="store.uiModal.type === 'alert'" class="text-orange-500 text-xl">ℹ️</span>
    <span v-if="store.uiModal.type === 'confirm'" class="text-red-500 text-xl">⚠️</span>
    <span v-if="store.uiModal.type === 'prompt'" class="text-blue-500 text-xl">✏️</span>
    {{ store.uiModal.title }}
    </h2>
    </div>
    <div class="p-6 space-y-4">
    <p class="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{{ store.uiModal.message }}</p>
    <input v-if="store.uiModal.type === 'prompt'" id="modal-input" type="text" v-model="store.uiModal.inputVal" :placeholder="store.uiModal.placeholder" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-3 text-sm text-white focus:border-orange-500 outline-none font-mono" @keyup.enter="api.resolveModal(store.uiModal.inputVal)">
    </div>
    <div class="p-4 border-t border-gray-800 bg-gray-950 flex justify-end gap-3">
    <button v-if="store.uiModal.type !== 'alert'" @click="api.resolveModal(store.uiModal.type === 'prompt' ? null : false)" class="px-5 py-2.5 rounded-lg text-xs font-bold text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer">Abbrechen</button>
    <button v-if="store.uiModal.type === 'alert'" @click="api.resolveModal(true)" class="px-5 py-2.5 rounded-lg text-xs font-bold bg-orange-600 hover:bg-orange-500 text-white shadow-md transition cursor-pointer">Verstanden</button>
    <button v-if="store.uiModal.type === 'confirm'" @click="api.resolveModal(true)" class="px-5 py-2.5 rounded-lg text-xs font-bold bg-orange-600 hover:bg-orange-500 text-white shadow-md transition cursor-pointer">Bestätigen</button>
    <button v-if="store.uiModal.type === 'prompt'" @click="api.resolveModal(store.uiModal.inputVal)" class="px-5 py-2.5 rounded-lg text-xs font-bold bg-orange-600 hover:bg-orange-500 text-white shadow-md transition cursor-pointer">Speichern</button>
    </div>
    </div>
    </div>
    </Transition>
    `
};
