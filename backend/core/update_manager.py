import os
import httpx
import zipfile
import io
import shutil

class UpdateManager:
    def __init__(self, base_dir):
        # Basisverzeichnis ist der /backend Ordner
        self.base_dir = base_dir
        self.plugins_dir = os.path.join(self.base_dir, "plugins")

    async def install_or_update_plugin_from_zip(self, plugin_id: str, zip_url: str):
        """
        Lädt ein Plugin-ZIP von einer URL herunter und entpackt es
        direkt in den plugins/ Ordner.
        """
        print(f"[*] Rufe Update für Plugin '{plugin_id}' von URL ab...")

        target_plugin_dir = os.path.join(self.plugins_dir, plugin_id)

        try:
            # 1. ZIP asynchron in den Arbeitsspeicher laden (keine Mülldateien auf der Platte)
            async with httpx.AsyncClient() as client:
                response = await client.get(zip_url, follow_redirects=True)
                if response.status_code != 200:
                    return {"status": "error", "message": f"Download fehlgeschlagen. Status: {response.status_code}"}

                zip_data = response.content

            # 2. Backup des alten Plugin-Ordners machen, falls er existiert (Sicherheit geht vor!)
            if os.path.exists(target_plugin_dir):
                backup_dir = target_plugin_dir + "_bak"
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir)
                os.rename(target_plugin_dir, backup_dir)

            # 3. ZIP-Archiv im Speicher öffnen und entpacken
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zip_ref:
                # Wir erstellen den Ordner neu
                os.makedirs(target_plugin_dir, exist_ok=True)

                # Hier ein kleiner Trick: Oft packt GitHub beim ZIP-Export einen Master-Ordner oben drüber.
                # Wir entpacken es sauber. Für v0.1 gehen wir davon aus, dass im ZIP direkt die manifest.yaml liegt.
                zip_ref.extractall(target_plugin_dir)

            # 4. Wenn alles geklappt hat, das alte Backup löschen
            backup_dir = target_plugin_dir + "_bak"
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)

            print(f"[+] Plugin '{plugin_id}' erfolgreich via ZIP aktualisiert/installiert!")
            return {"status": "success", "message": f"Plugin {plugin_id} erfolgreich aktualisiert."}

        except Exception as e:
            # Falls was schiefging und wir ein Backup haben: Rollback!
            backup_dir = target_plugin_dir + "_bak"
            if os.path.exists(backup_dir) and not os.path.exists(target_plugin_dir):
                os.rename(backup_dir, target_plugin_dir)

            return {"status": "error", "message": f"Fehler beim Plugin-Update: {str(e)}"}
