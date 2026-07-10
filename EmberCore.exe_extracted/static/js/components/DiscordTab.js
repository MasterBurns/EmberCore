import { store, api } from '../store.js';

export default {
    setup() { 
        // Lokaler State für den Wizard, falls er nicht schon im Store liegt
        if (!store.discordWizard) {
            store.discordWizard = {
                step: 1,
                appId: '',
                botToken: '',
                pairingKey: 'EMBER-' + Math.random().toString(36).substring(2, 10).toUpperCase()
            };
        }
        return { store, api }; 
    },
    computed: {
        oauthLink() {
            // Generiert den Einladungslink vollautomatisch mit den Rechten: 
            // Nachrichten senden/lesen, Embeds, Slash-Commands (Int: 2147551232)
            if (!this.store.discordWizard.appId) return '#';
            return `https://discord.com/oauth2/authorize?client_id=${this.store.discordWizard.appId}&permissions=2147551232&scope=bot%20applications.commands`;
        }
    },
    template: `
    <div class="max-w-4xl mx-auto space-y-6">
        
        <!-- Header & Status -->
        <div class="flex justify-between items-center bg-gray-950 p-5 rounded-xl border border-gray-900 shadow-md">
            <div>
                <h1 class="text-2xl font-black text-white tracking-wide truncate">Discord-Bot Integration</h1>
                <p class="text-sm text-gray-500 font-mono mt-1">Steuere deine Gameserver sicher von unterwegs.</p>
            </div>
            <div :class="store.sysConfig?.discord_linked ? 'bg-green-900/30 border-green-800 text-green-400' : 'bg-gray-900 border-gray-800 text-gray-500'" class="px-4 py-2 rounded-lg border font-bold text-sm flex items-center gap-2 shadow-sm">
                <span v-if="store.sysConfig?.discord_linked" class="animate-pulse">🟢 Verbunden</span>
                <span v-else>⚪ Nicht eingerichtet</span>
            </div>
        </div>

        <!-- Wizard Container -->
        <div v-if="!store.sysConfig?.discord_linked" class="bg-gray-950 rounded-xl border border-gray-900 shadow-xl overflow-hidden flex flex-col md:flex-row">
            
            <!-- Sidebar Progress -->
            <div class="bg-gray-900/50 w-full md:w-64 p-6 border-b md:border-b-0 md:border-r border-gray-900">
                <h3 class="text-xs font-bold text-gray-500 uppercase tracking-widest mb-6">Setup Assistent</h3>
                <ul class="space-y-4 relative">
                    <li :class="store.discordWizard.step >= 1 ? 'text-orange-400' : 'text-gray-600'" class="flex items-center gap-3 text-sm font-bold transition-colors"><span class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] border" :class="store.discordWizard.step >= 1 ? 'border-orange-500 bg-orange-950/50' : 'border-gray-700'">1</span> App erstellen</li>
                    <li :class="store.discordWizard.step >= 2 ? 'text-orange-400' : 'text-gray-600'" class="flex items-center gap-3 text-sm font-bold transition-colors"><span class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] border" :class="store.discordWizard.step >= 2 ? 'border-orange-500 bg-orange-950/50' : 'border-gray-700'">2</span> Token sichern</li>
                    <li :class="store.discordWizard.step >= 3 ? 'text-orange-400' : 'text-gray-600'" class="flex items-center gap-3 text-sm font-bold transition-colors"><span class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] border" :class="store.discordWizard.step >= 3 ? 'border-orange-500 bg-orange-950/50' : 'border-gray-700'">3</span> Bot einladen</li>
                    <li :class="store.discordWizard.step >= 4 ? 'text-orange-400' : 'text-gray-600'" class="flex items-center gap-3 text-sm font-bold transition-colors"><span class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] border" :class="store.discordWizard.step >= 4 ? 'border-orange-500 bg-orange-950/50' : 'border-gray-700'">4</span> Pairing</li>
                </ul>
            </div>

            <!-- Content Area -->
            <div class="p-8 flex-1 min-w-0">
                
                <!-- SCHRITT 1 -->
                <div v-if="store.discordWizard.step === 1" class="space-y-5 animate-fade-in">
                    <h2 class="text-xl font-bold text-white">Schritt 1: Die Discord-App erstellen</h2>
                    <p class="text-sm text-gray-400">Um EmberCore an Discord anzubinden, benötigst du einen eigenen Bot. Keine Sorge, das dauert nur eine Minute.</p>
                    
                    <div class="bg-gray-900 border border-gray-800 p-4 rounded-lg space-y-3">
                        <ol class="text-sm text-gray-300 list-decimal pl-4 space-y-1">
                            <li>Öffne das offizielle <a href="https://discord.com/developers/applications" target="_blank" class="text-blue-400 hover:underline font-bold">Discord Developer Portal</a>.</li>
                            <li>Klicke oben rechts auf <b>New Application</b>.</li>
                            <li>Gib dem Bot einen Namen (z.B. <i>EmberCore Admin</i>) und bestätige.</li>
                            <li>Kopiere die <b>Application ID</b> und füge sie unten ein.</li>
                        </ol>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase mb-2">Application ID (Client ID)</label>
                        <input type="text" v-model="store.discordWizard.appId" placeholder="z.B. 112233445566778899" class="w-full bg-[#0a0a0a] border border-gray-800 rounded-lg p-3 text-sm text-white focus:border-orange-500 outline-none font-mono">
                    </div>

                    <button @click="store.discordWizard.step = 2" :disabled="!store.discordWizard.appId" class="mt-4 bg-orange-600 hover:bg-orange-500 disabled:bg-gray-800 disabled:text-gray-500 text-white font-bold px-6 py-2.5 rounded-lg transition shadow-md cursor-pointer text-sm">Weiter zu Schritt 2 ➡️</button>
                </div>

                <!-- SCHRITT 2 -->
                <div v-if="store.discordWizard.step === 2" class="space-y-5 animate-fade-in">
                    <h2 class="text-xl font-bold text-white">Schritt 2: Das geheime Bot-Token</h2>
                    <p class="text-sm text-gray-400">Das Token ist das Passwort für deinen Bot. Ohne dieses Token kann EmberCore sich nicht bei Discord anmelden.</p>
                    
                    <div class="bg-gray-900 border border-gray-800 p-4 rounded-lg space-y-3">
                        <ol class="text-sm text-gray-300 list-decimal pl-4 space-y-1">
                            <li>Klicke im Discord Developer Portal links im Menü auf <b>Bot</b>.</li>
                            <li>Klicke auf den Button <b>Reset Token</b> (und bestätige mit "Yes, do it!").</li>
                            <li>Kopiere den angezeigten kryptischen Code und füge ihn unten ein.</li>
                        </ol>
                    </div>

                    <div class="bg-red-950/30 border border-red-900/50 p-3 rounded-lg flex items-start gap-3">
                        <span class="text-red-500 text-xl">⚠️</span>
                        <p class="text-xs text-red-200 mt-0.5"><b>Geheimhaltungspflicht:</b> Teile dieses Token niemals mit anderen! Jeder, der dieses Token besitzt, hat die volle Kontrolle über deinen Discord-Bot.</p>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-gray-400 uppercase mb-2">Bot Token</label>
                        <input type="password" v-model="store.discordWizard.botToken" placeholder="MTEyMj... (Dein Token)" class="w-full bg-[#0a0a0a] border border-gray-800 rounded-lg p-3 text-sm text-white focus:border-orange-500 outline-none font-mono">
                    </div>

                    <div class="flex gap-3 mt-4">
                        <button @click="store.discordWizard.step = 1" class="bg-gray-800 hover:bg-gray-700 text-white font-bold px-4 py-2.5 rounded-lg transition cursor-pointer text-sm">⬅️ Zurück</button>
                        <button @click="store.discordWizard.step = 3" :disabled="!store.discordWizard.botToken" class="bg-orange-600 hover:bg-orange-500 disabled:bg-gray-800 disabled:text-gray-500 text-white font-bold px-6 py-2.5 rounded-lg transition shadow-md cursor-pointer text-sm">Weiter zu Schritt 3 ➡️</button>
                    </div>
                </div>

                <!-- SCHRITT 3 -->
                <div v-if="store.discordWizard.step === 3" class="space-y-5 animate-fade-in">
                    <h2 class="text-xl font-bold text-white">Schritt 3: Bot auf deinen Server einladen</h2>
                    <p class="text-sm text-gray-400">Wir haben deinen persönlichen Einladungslink generiert. Dieser Link beinhaltet bereits alle nötigen Rechte (Slash-Commands, Nachrichten lesen/schreiben).</p>
                    
                    <div class="bg-blue-950/30 border border-blue-900/50 p-4 rounded-lg flex flex-col gap-2">
                        <h4 class="text-blue-400 font-bold text-sm flex items-center gap-2">💡 Best Practice Tipp: Der isolierte Kanal</h4>
                        <p class="text-xs text-blue-200">Bevor du den Bot einlädst, erstelle in deinem Discord einen privaten Textkanal (z.B. <b>#server-konsole</b>). Bearbeite die Kanal-Berechtigungen so, dass nur du und vertrauenswürdige Admins ihn sehen können. Lade den Bot dann <b>nur in diesen Kanal</b> ein.</p>
                    </div>

                    <div class="py-4">
                        <a :href="oauthLink" target="_blank" class="w-full block text-center bg-[#5865F2] hover:bg-[#4752C4] text-white font-bold px-6 py-4 rounded-xl transition shadow-lg cursor-pointer">
                            🤖 Jetzt klicken, um den Bot einzuladen
                        </a>
                    </div>

                    <div class="flex gap-3 mt-4">
                        <button @click="store.discordWizard.step = 2" class="bg-gray-800 hover:bg-gray-700 text-white font-bold px-4 py-2.5 rounded-lg transition cursor-pointer text-sm">⬅️ Zurück</button>
                        <button @click="store.discordWizard.step = 4" class="bg-orange-600 hover:bg-orange-500 text-white font-bold px-6 py-2.5 rounded-lg transition shadow-md cursor-pointer text-sm">Bot ist auf dem Server ➡️</button>
                    </div>
                </div>

                <!-- SCHRITT 4 -->
                <div v-if="store.discordWizard.step === 4" class="space-y-5 animate-fade-in">
                    <h2 class="text-xl font-bold text-white">Schritt 4: Das sichere Pairing</h2>
                    <p class="text-sm text-gray-400">Fast geschafft! EmberCore startet jetzt den Bot im Hintergrund. Um sicherzugehen, dass niemand Fremdes deinen Server steuert, müssen wir die Instanz autorisieren.</p>
                    
                    <button @click="api.saveDiscordSettings(store.discordWizard.appId, store.discordWizard.botToken)" class="w-full bg-gray-900 border border-gray-700 hover:border-gray-500 text-white font-bold px-6 py-3 rounded-lg transition cursor-pointer text-sm flex justify-center items-center gap-2">
                        <span>⚙️ EmberCore Bot-Prozess jetzt starten</span>
                    </button>

                    <div class="bg-gray-900 border border-gray-800 p-5 rounded-xl space-y-4 mt-6">
                        <h4 class="text-sm font-bold text-gray-300">Dein einmaliger Pairing-Schlüssel:</h4>
                        <div class="bg-[#0a0a0a] p-4 rounded border border-gray-700 text-center select-all">
                            <span class="text-3xl font-mono font-black text-orange-500 tracking-widest">{{ store.discordWizard.pairingKey }}</span>
                        </div>
                        <p class="text-xs text-gray-400 text-center">Gehe in deinen neuen Discord-Kanal und tippe exakt diesen Befehl ein:</p>
                        <div class="bg-[#0a0a0a] p-2 rounded border border-gray-800 text-center font-mono text-gray-300 text-sm">
                            /link key:{{ store.discordWizard.pairingKey }}
                        </div>
                    </div>

                    <div class="flex gap-3 mt-4">
                        <button @click="store.discordWizard.step = 3" class="bg-gray-800 hover:bg-gray-700 text-white font-bold px-4 py-2.5 rounded-lg transition cursor-pointer text-sm">⬅️ Zurück</button>
                    </div>
                </div>

            </div>
        </div>

        <!-- Ansicht, wenn bereits verbunden -->
        <div v-if="store.sysConfig?.discord_linked" class="bg-gray-950 p-6 rounded-xl border border-gray-900 shadow-xl space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="space-y-4">
                    <h3 class="text-sm font-bold text-white uppercase tracking-wider border-b border-gray-900 pb-2">Bot Status</h3>
                    <div class="flex items-center gap-4 bg-gray-900/50 p-4 rounded-lg border border-gray-800">
                        <div class="w-12 h-12 rounded-full bg-[#5865F2] flex items-center justify-center text-white text-xl shadow-lg">🤖</div>
                        <div>
                            <p class="font-bold text-white">EmberCore Admin</p>
                            <p class="text-xs text-green-400 font-mono mt-1">Latenz: 42ms | Websocket: Aktiv</p>
                        </div>
                    </div>
                </div>
                <div class="space-y-4">
                    <h3 class="text-sm font-bold text-white uppercase tracking-wider border-b border-gray-900 pb-2">Verknüpfter Server</h3>
                    <div class="bg-gray-900/50 p-4 rounded-lg border border-gray-800 space-y-2">
                        <p class="text-xs text-gray-500 uppercase font-bold">Gilde (Server)</p>
                        <p class="text-sm text-gray-300 font-bold truncate">{{ store.sysConfig.discord_guild_name || 'MyGamingCommunity' }}</p>
                        <p class="text-xs text-gray-500 uppercase font-bold mt-2">Autotisierter Kanal</p>
                        <p class="text-sm text-gray-300 font-mono">#{{ store.sysConfig.discord_channel_name || 'server-konsole' }}</p>
                    </div>
                </div>
            </div>
            
            <button @click="api.unlinkDiscord()" class="w-full bg-red-950/30 border border-red-900/50 hover:bg-red-900 hover:text-white text-red-400 font-bold px-6 py-3 rounded-lg transition cursor-pointer text-sm">
                🔌 Verbindung trennen & Token löschen
            </button>
        </div>

    </div>
    `
};