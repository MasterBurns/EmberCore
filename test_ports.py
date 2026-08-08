import re
arg = "TheIsland_WP?listen?Port=7777?QueryPort=27015?RCONEnabled=True?RCONPort=27020"
new_ports = [{"desc": "Game Port", "port": 7778}, {"desc": "Steam Query Port", "port": 27016}]

parts = arg.split("?")
new_parts = []
for p in parts:
    updated = False
    for p_obj in new_ports:
        desc = p_obj.get("desc", "").lower()
        if "game" in desc and p.lower().startswith("port="):
            new_parts.append(f"Port={p_obj['port']}")
            updated = True
            break
        elif "query" in desc and p.lower().startswith("queryport="):
            new_parts.append(f"QueryPort={p_obj['port']}")
            updated = True
            break
    if not updated:
        new_parts.append(p)
print("?".join(new_parts))
