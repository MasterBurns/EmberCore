import os

class ConfigManager:
    def read_key_value_config(self, file_path: str, fields: list) -> dict:
        """Liest eine .cfg oder .ini Datei aus und extrahiert die gewünschten Felder."""
        result = {}
        # Initialisiere mit Standardwerten aus dem Manifest
        for field in fields:
            result[field['key']] = field.get('default', '')

        if not os.path.exists(file_path):
            return result

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue

            # Trenne bei Leerzeichen oder Gleichheitszeichen (unterstützt cfg und ini)
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().strip('"') # Entferne eventuelle Anführungszeichen

                # Wenn der Key im Manifest definiert ist, nimm ihn auf
                if key in result:
                    result[key] = val
        return result

    def write_key_value_config(self, file_path: str, data: dict):
        """Schreibt die modifizierten Einstellungen sauber zurück in die Datei."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        lines = ["// Generiert durch EmberCore Web-Interface\n"]
        for key, val in data.items():
            # Setze Strings in Anführungszeichen, Zahlen normal
            if isinstance(val, str) and " " in val:
                lines.append(f'{key} "{val}"\n')
            else:
                lines.append(f'{key} {val}\n')

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return {"status": "success", "message": "Konfiguration erfolgreich gespeichert."}
