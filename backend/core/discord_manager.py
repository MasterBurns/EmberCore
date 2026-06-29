import asyncio
import os
import json
import httpx
import discord
from discord.ext import commands
from discord import app_commands

from core.env import logger, DATA_ROOT

class DiscordManager:
    def __init__(self):
        self.bot = None
        self.bot_task = None
        self.is_running = False
        
        self.config_path = os.path.join(DATA_ROOT, "discord_config.json")
        self.pairing_key = None

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception: pass
        return {}

    def save_config(self, data):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def start_bot(self, token: str, pairing_key: str):
        if self.is_running:
            return

        self.pairing_key = pairing_key
        intents = discord.Intents.default()
        self.bot = commands.Bot(command_prefix="!", intents=intents)

        # Sicherheits-Check: Befehle dürfen NUR im gekoppelten Kanal ausgeführt werden
        def is_authorized(interaction: discord.Interaction):
            config = self.load_config()
            return config.get("linked", False) and interaction.channel_id == config.get("channel_id")

        @self.bot.event
        async def on_ready():
            logger.info(f"[*] Discord Bot eingeloggt als {self.bot.user}")
            try:
                synced = await self.bot.tree.sync()
                logger.info(f"[*] {len(synced)} Slash-Commands mit Discord synchronisiert.")
            except Exception as e:
                logger.error(f"Fehler beim Sync der Discord-Commands: {e}")

        # ---------------------------------------------------------
        # COMMAND: /link
        # ---------------------------------------------------------
        @self.bot.tree.command(name="link", description="Verknüpft diesen Discord-Kanal mit EmberCore.")
        @app_commands.describe(key="Dein Pairing-Schlüssel aus dem EmberCore Panel")
        async def link_command(interaction: discord.Interaction, key: str):
            if not self.pairing_key:
                await interaction.response.send_message("❌ Pairing-Modus nicht aktiv. Starte den Bot via Web-Panel neu.", ephemeral=True)
                return

            if key == self.pairing_key:
                config = self.load_config()
                config["linked"] = True
                config["guild_id"] = interaction.guild_id
                config["guild_name"] = interaction.guild.name
                config["channel_id"] = interaction.channel_id
                config["channel_name"] = interaction.channel.name
                
                self.save_config(config)
                self.pairing_key = None 

                await interaction.response.send_message(f"✅ **Erfolgreich!** EmberCore ist nun sicher an {interaction.channel.mention} gebunden.\nTippe `/servers`, um loszulegen!")
                logger.info(f"[*] Discord Pairing erfolgreich mit Server '{interaction.guild.name}' abgeschlossen.")
            else:
                await interaction.response.send_message("❌ Ungültiger Pairing-Key.", ephemeral=True)

        # ---------------------------------------------------------
        # COMMAND: /servers
        # ---------------------------------------------------------
        @self.bot.tree.command(name="servers", description="Listet alle installierten Gameserver auf.")
        async def list_servers(interaction: discord.Interaction):
            if not is_authorized(interaction):
                await interaction.response.send_message("❌ Dieser Kanal ist nicht autorisiert.", ephemeral=True)
                return
            
            await interaction.response.defer() # Wichtig, da API-Calls etwas dauern können
            from core.env import ACTIVE_PORT
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get(f"http://127.0.0.1:{ACTIVE_PORT}/api/plugins/installed")
                    servers = res.json() if res.status_code == 200 else []
                    
                    if not servers:
                        await interaction.followup.send("Es sind aktuell keine Server installiert.")
                        return
                        
                    embed = discord.Embed(title="🎮 EmberCore Server Liste", color=0xE67E22) # EmberCore Orange
                    for s in servers:
                        status_icon = "🟢 Online" if s['status'] == 'online' else "🔴 Offline"
                        embed.add_field(name=f"{s['server_name']}", value=f"ID: `{s['id']}`\nStatus: {status_icon}", inline=False)
                    await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ Interner API-Fehler: {e}")

        # ---------------------------------------------------------
        # COMMAND: /start
        # ---------------------------------------------------------
        @self.bot.tree.command(name="start", description="Startet einen Gameserver.")
        @app_commands.describe(server_id="Die ID des Servers (siehe /servers)")
        async def start_server(interaction: discord.Interaction, server_id: str):
            if not is_authorized(interaction):
                await interaction.response.send_message("❌ Nicht autorisiert.", ephemeral=True)
                return
                
            await interaction.response.defer()
            from core.env import ACTIVE_PORT
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.post(f"http://127.0.0.1:{ACTIVE_PORT}/api/server/start/{server_id}", timeout=10.0)
                    data = res.json()
                    if data.get("status") == "success":
                        await interaction.followup.send(f"✅ Start-Befehl für `{server_id}` wurde erfolgreich an das System gesendet!")
                    else:
                        await interaction.followup.send(f"⚠️ Konnte nicht starten: {data.get('message', 'Unbekannter Fehler.')}")
            except Exception as e:
                await interaction.followup.send(f"❌ API-Fehler: {e}")

        # ---------------------------------------------------------
        # COMMAND: /stop
        # ---------------------------------------------------------
        @self.bot.tree.command(name="stop", description="Stoppt einen Gameserver sicher (RCON).")
        @app_commands.describe(server_id="Die ID des Servers (siehe /servers)")
        async def stop_server(interaction: discord.Interaction, server_id: str):
            if not is_authorized(interaction):
                await interaction.response.send_message("❌ Nicht autorisiert.", ephemeral=True)
                return
                
            await interaction.response.defer()
            from core.env import ACTIVE_PORT
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.post(f"http://127.0.0.1:{ACTIVE_PORT}/api/server/stop/{server_id}", timeout=20.0)
                    data = res.json()
                    if data.get("status") == "success":
                        await interaction.followup.send(f"🛑 Server `{server_id}` wird jetzt sicher heruntergefahren!")
                    else:
                        await interaction.followup.send(f"⚠️ Fehler beim Stoppen: {data.get('message')}")
            except Exception as e:
                await interaction.followup.send(f"❌ API-Fehler: {e}")

        # ---------------------------------------------------------
        # COMMAND: /status
        # ---------------------------------------------------------
        @self.bot.tree.command(name="status", description="Zeigt Ressourcen wie CPU & RAM eines Servers.")
        @app_commands.describe(server_id="Die ID des Servers")
        async def server_status(interaction: discord.Interaction, server_id: str):
            if not is_authorized(interaction):
                await interaction.response.send_message("❌ Nicht autorisiert.", ephemeral=True)
                return
                
            await interaction.response.defer()
            from core.env import ACTIVE_PORT
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get(f"http://127.0.0.1:{ACTIVE_PORT}/api/server/stats/{server_id}", timeout=5.0)
                    if res.status_code != 200:
                        await interaction.followup.send("❌ Server-ID nicht gefunden.")
                        return
                        
                    data = res.json()
                    is_online = data.get('status') == 'online'
                    
                    embed = discord.Embed(
                        title=f"📊 Live-Status: {server_id}", 
                        color=0x2ECC71 if is_online else 0xE74C3C
                    )
                    embed.add_field(name="Status", value="🟢 Online" if is_online else "🔴 Offline", inline=False)
                    
                    if is_online:
                        embed.add_field(name="💻 CPU", value=f"{data.get('cpu_percent', 0)} %", inline=True)
                        embed.add_field(name="🧠 RAM", value=f"{data.get('ram_mb', 0)} MB", inline=True)
                    
                    disk = data.get("disk", {})
                    if disk:
                        embed.add_field(name="💾 Festplatte", value=f"{disk.get('server_mb', 0)} MB", inline=False)
                    
                    await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"❌ API-Fehler: {e}")

        self.is_running = True
        self.bot_task = asyncio.create_task(self.bot.start(token))

    async def stop_bot(self):
        if self.bot and self.is_running:
            logger.info("[-] Stoppe Discord Bot...")
            await self.bot.close()
            self.is_running = False
            if self.bot_task:
                self.bot_task.cancel()

discord_manager = DiscordManager()