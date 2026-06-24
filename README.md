# 🔥 EmberCore - Game Server Manager

EmberCore ist ein leichtgewichtiger, hochgradig robuster und vollständig zustandsloser Game Server Manager für Windows und Linux. Entwickelt, um die typischen Schmerzpunkte von selbstgehosteten Dedicated Servern (wie Zombie-Prozesse, korrupte Savegames und komplexe Mod-Updates) endgültig zu beseitigen.

Anstatt auf aufgeblähte Build-Prozesse zu setzen, kombiniert EmberCore ein pfeilschnelles **Python FastAPI Backend** mit einem modularen **Vue 3 Frontend (Native ES-Modules)** – komplett ohne Node.js, Webpack oder sonstige Abhängigkeiten.

---

## 📖 Einleitung

Wer schon einmal Game-Server (wie Conan Exiles, Ark oder Space Engineers) selbst gehostet hat, kennt die Probleme: Abgespaltene Child-Prozesse, die nach einem Crash des Managers als Geister auf dem System weiterlaufen, zerschossene Datenbanken durch harte Restarts oder das mühsame manuelle Aktualisieren von Dutzenden Steam Workshop Mods.

EmberCore löst diese Probleme durch eine kompromisslose Architektur. Das System verlässt sich nicht auf ein fehleranfälliges internes Gedächtnis, sondern fungiert als intelligenter System-Scanner. Es überwacht aktiv offene Netzwerk-Ports und Prozess-Hierarchien, adoptiert verwaiste Server automatisch und fährt diese über dynamisch ausgelesene RCON-Passwörter so sanft herunter, wie es in professionellen Rechenzentren üblich ist.

## ✨ Kern-Features

### 🧬 Stateless Process Recovery (Waisen-Adoption)
EmberCore hat kein lokales "Gedächtnis", das kaputtgehen kann. Startet der Manager neu, durchkämmt er in Millisekunden das Betriebssystem nach Pfaden, Startparametern und **offenen Netzwerk-Ports**. Laufende Game-Server (selbst wenn sie sich vom ursprünglichen Launcher entkoppelt haben) werden sofort identifiziert, im Dashboard wieder eingebunden und können nahtlos weiter verwaltet werden. Keine Zombie-Prozesse mehr.

### 🛑 Graceful 3-Stufen-Shutdown
Harte Kills (`taskkill /F`) zerstören Savegames. EmberCore nutzt stattdessen eine smarte 3-Stufen-Eskalation:
1. **RCON Gold-Standard:** EmberCore liest das aktuelle Admin-Passwort dynamisch aus der Live-Konfiguration des Servers (z. B. `ServerSettings.ini`) und sendet native C++ RCON-Befehle (wie `CloseServer`) an den Spieleserver für einen sicheren Exit.
2. **OS Soft-Kill:** Sanftes OS-Signal (`WM_CLOSE` / `SIGTERM`), bei dem der Anwendung Zeit zum Speichern eingeräumt wird.
3. **Hard-Kill:** Gnadenloser System-Kill als absolute Notbremse, falls der Server sich nach 15 Sekunden komplett aufgehängt hat.

### ⚙️ Echte OS-Hintergrunddienste
Keine temporären Konsolenfenster. EmberCore installiert sich auf Knopfdruck als nativer Systemdienst (via **Systemd** auf Linux oder **WinSW** auf Windows). Server starten automatisch und zuverlässig mit dem Betriebssystem, noch bevor sich ein Nutzer anmeldet.

### 🔌 Automatisches Mod- & SteamCMD-Management
SteamCMD ist tief in den Core integriert. Updates für Spiel-Engines und Modifikationen (Steam Workshop) laufen vollautomatisch. EmberCore kettet dabei alle Mod-Downloads in einen einzigen, hocheffizienten SteamCMD-Befehl und spart so massiv Zeit beim Server-Start.

### 🛡️ Smart Watchdog & Auto-Updater
* **Watchdog:** Ein abgekoppelter Hintergrundprozess überwacht das Backend auf Hänger und startet es im Notfall automatisch neu.
* **Auto-Update:** Updates für EmberCore können direkt aus GitHub via 1-Click im UI bezogen werden. EmberCore pausiert sich selbst, löst die Dateisperren des Betriebssystems, entpackt die Dateien und bootet sauber neu.

### 💾 Backup-Scheduler & Speicher-Analyse
Ein integriertes Backupsystem mit intelligenter Retention-Policy (Behalte die letzten X, sowie tägliche/wöchentliche/monatliche Sicherungen). Inklusive Live-Berechnung des täglichen Speicherwachstums (Trend-Analyse) der Instanzen.

### 🌐 Zero-Config Network Setup (Windows)
Das Freigeben von Servern für Freunde ist eine Sache von Sekunden. EmberCore liest die benötigten Ports aus dem Spiel-Manifest, konfiguriert automatisch die Windows Defender Firewall und funkt den heimischen Router via **UPnP** an, um die Portweiterleitung selbstständig einzurichten.

### 🚑 Deep Diagnostics (Absturz-Schutz)
EmberCore liest den stdout der Server live mit. Treten bekannte Engine-Bugs auf (z. B. Unreal Engine 5 Encryption Ciphers), erkennt der Manager das Muster im Log, warnt den Admin im Dashboard und bietet direkt eine One-Click-Lösung (z.B. das Umstellen auf eine passwortfreie Whitelist) an.

---

## 🛠️ Tech Stack

* **Backend:** Python 3, FastAPI, Uvicorn, psutil
* **Frontend:** Vue 3 (Composition API), TailwindCSS – *100% Native ES-Modules, Zero Build-Steps!*
* **Service Wrapper:** WinSW (.NET) für Windows, Systemd für Linux.

---
