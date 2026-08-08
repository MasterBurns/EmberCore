import os
import json
import httpx
import re
from core.env import DATA_ROOT, SERVERS_ROOT, sys_config, logger

async def resolve_curseforge_mods(plugin_id: str, mod_ids: list) -> dict:
    """
    Versucht, CurseForge Mod-Namen aufzulösen.
    Priorität: 1. Lokale Dateien (ModsUserData JSONs), 2. Web-Scraping, 3. CurseForge API
    Gibt ein Dict zurück: {mod_id: "Aufgelöster Name"}
    """
    results = {}
    remaining_ids = set(mod_ids)
    
    server_dir = os.path.join(SERVERS_ROOT, plugin_id)
    mods_user_data_dir = os.path.join(server_dir, "ShooterGame", "ModsUserData")
    mods_dir = os.path.join(server_dir, "ShooterGame", "Mods")

    # 1. Lokaler Scan (ModsUserData)
    if os.path.exists(mods_user_data_dir):
        for dp, _, fn in os.walk(mods_user_data_dir):
            for f in fn:
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(dp, f), "r", encoding="utf-8", errors="ignore") as file:
                            data = json.load(file)
                            # CFCore hat oft die ModID als String oder Int
                            m_id = str(data.get("id") or data.get("modId") or data.get("ModId") or "")
                            if m_id in remaining_ids:
                                name = data.get("name") or data.get("title") or data.get("modName") or data.get("displayName")
                                if name:
                                    results[m_id] = str(name).strip()
                                    remaining_ids.remove(m_id)
                    except Exception: pass
                    
    # Fallback für .pak Dateien, falls Name nicht aus JSON gelesen wurde
    if os.path.exists(mods_dir):
        for f in os.listdir(mods_dir):
            if f.endswith(".pak"):
                base = f[:-4]
                # Wenn der Name die ID enthält oder anderweitig zuordbar wäre (sehr heuristisch)
                # Oft heißen die Dateien einfach <id>.pak
                if base in remaining_ids:
                    # Da der Dateiname nur die ID ist, bringt das als Name wenig.
                    # Aber wenn der Dateiname anders lautet, z.B. MyMod_12345.pak
                    pass 

    # 2. Web-Scraping Fallback
    if remaining_ids:
        async with httpx.AsyncClient() as client:
            for m_id in list(remaining_ids):
                try:
                    res = await client.get(f"https://www.curseforge.com/projects/{m_id}", timeout=5.0)
                    if res.status_code == 200:
                        # Suche nach og:title
                        match = re.search(r'<meta property="og:title" content="([^"]+)"', res.text)
                        if match:
                            raw_title = match.group(1)
                            # Suffix bereinigen
                            clean_title = re.sub(r'\s*-\s*ARK:\s*Survival\s*Ascended.*$', '', raw_title, flags=re.IGNORECASE)
                            clean_title = re.sub(r'\s*-\s*CurseForge$', '', clean_title, flags=re.IGNORECASE).strip()
                            if clean_title:
                                results[m_id] = clean_title
                                remaining_ids.remove(m_id)
                except Exception:
                    pass

    # 3. Offizielle API (falls Key vorhanden)
    api_key = sys_config.get("curseforge_api_key", "").strip()
    if remaining_ids and api_key:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.curseforge.com/v1/mods",
                    json={"modIds": [int(x) for x in remaining_ids if str(x).isdigit()]},
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    timeout=5.0
                )
                if res.status_code == 200:
                    data = res.json()
                    for mod_data in data.get("data", []):
                        m_id = str(mod_data.get("id"))
                        name = mod_data.get("name")
                        if m_id in remaining_ids and name:
                            results[m_id] = name
                            remaining_ids.remove(m_id)
        except Exception:
            pass
            
    return results

async def refresh_mod_metadata(plugin_id: str) -> dict:
    """
    Lädt die mods_db.json, filtert nach unaufgelösten Namen und löst sie auf.
    Gibt {status, resolved_count} zurück.
    """
    mods_file = os.path.join(DATA_ROOT, plugin_id, "mods_db.json")
    if not os.path.exists(mods_file):
        return {"status": "success", "resolved_count": 0}
        
    try:
        with open(mods_file, "r", encoding="utf-8") as f:
            mods = json.load(f)
    except Exception as e:
        logger.error(f"[ModMeta] Fehler beim Lesen der mods_db.json für {plugin_id}: {e}")
        return {"status": "error", "message": "mods_db.json konnte nicht gelesen werden"}
        
    ids_to_resolve = []
    for m in mods:
        name = m.get("name", "")
        # Erkennung von Platzhaltern
        if name.startswith("CurseForge Mod (") or name.startswith("Imported Mod (") or name.startswith("Mod (") or name == "unbekannt":
            ids_to_resolve.append(str(m.get("id")))
            
    if not ids_to_resolve:
        return {"status": "success", "resolved_count": 0}
        
    resolved_names = await resolve_curseforge_mods(plugin_id, ids_to_resolve)
    
    if not resolved_names:
        return {"status": "success", "resolved_count": 0}
        
    resolved_count = 0
    for m in mods:
        m_id = str(m.get("id"))
        if m_id in resolved_names:
            m["name"] = resolved_names[m_id]
            resolved_count += 1
            
    if resolved_count > 0:
        try:
            with open(mods_file, "w", encoding="utf-8") as f:
                json.dump(mods, f, indent=2)
        except Exception as e:
            logger.error(f"[ModMeta] Fehler beim Speichern der mods_db.json für {plugin_id}: {e}")
            
    return {"status": "success", "resolved_count": resolved_count}
