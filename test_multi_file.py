import sys, os, json
sys.path.append(os.path.abspath("backend"))
from core.config_manager import ConfigManager

os.makedirs("test_servers/conan_exiles/ConanSandbox/Saved/Config/WindowsServer", exist_ok=True)
with open("test_servers/conan_exiles/ConanSandbox/Saved/Config/WindowsServer/ServerSettings.ini", "w") as f:
    f.write("[ServerSettings]\nAdminPassword=OldAdmin\nMaxPlayers=20\n")

with open("test_servers/conan_exiles/ConanSandbox/Saved/Config/WindowsServer/Engine.ini", "w") as f:
    f.write("[OnlineSubsystem]\nServerPassword=OldPass\nServerName=OldName\n")

original_load = ConfigManager.load_manifest
def fake_manifest(plugin_id):
    return {
        "config_meta": {
            "file_path": "ConanSandbox/Saved/Config/WindowsServer/ServerSettings.ini",
            "format": "ini",
            "fields": [
                {"key": "ServerName", "section": "OnlineSubsystem", "file_path": "ConanSandbox/Saved/Config/WindowsServer/Engine.ini"},
                {"key": "ServerPassword", "section": "OnlineSubsystem", "file_path": "ConanSandbox/Saved/Config/WindowsServer/Engine.ini"},
                {"key": "MaxPlayers", "section": "ServerSettings"},
                {"key": "AdminPassword", "section": "ServerSettings"}
            ]
        }
    }
ConfigManager.load_manifest = fake_manifest

os.makedirs("data/conan_exiles", exist_ok=True)
with open("data/conan_exiles/desired_config.json", "w") as f:
    json.dump({
        "ServerName": "New EmberCore Server",
        "ServerPassword": "NewPassword123",
        "AdminPassword": "NewAdminPassword",
        "MaxPlayers": 40
    }, f)

import core.config_manager
core.config_manager.SERVERS_ROOT = "test_servers"
core.config_manager.DATA_ROOT = "data"

print("--- Testing get_full_live_config ---")
live = ConfigManager.get_full_live_config("conan_exiles")
print(live)

print("\n--- Testing apply_desired_config ---")
ConfigManager.apply_desired_config("conan_exiles")

print("\nEngine.ini:")
with open("test_servers/conan_exiles/ConanSandbox/Saved/Config/WindowsServer/Engine.ini", "r") as f: print(f.read())

print("\nServerSettings.ini:")
with open("test_servers/conan_exiles/ConanSandbox/Saved/Config/WindowsServer/ServerSettings.ini", "r") as f: print(f.read())
