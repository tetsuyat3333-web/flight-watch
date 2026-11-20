"""Which connections are acceptable: same airline, same alliance, or same airline group.
Anything else (or a fare Google marks as separate tickets / self-transfer) is excluded.
Names are matched case-insensitively as substrings of Google Flights' airline names.
Edit these lists if an airline changes alliance."""
import json

GROUPS = {
    "star": [
        "lufthansa", "swiss", "austrian", "brussels airlines", "edelweiss", "eurowings", "discover",
        "ita airways", "turkish", "ana", "all nippon", "lot", "tap ", "tap air", "aegean", "croatia",
        "singapore airlines", "thai", "eva air", "air china", "shenzhen", "asiana", "air india",
        "united", "air canada", "air new zealand", "ethiopian", "egyptair", "south african",
        "copa", "avianca",
    ],
    "oneworld": [
        "japan airlines", "jal", "british airways", "iberia", "aer lingus", "finnair", "qatar",
        "cathay", "american", "qantas", "royal jordanian", "srilankan", "malaysia airlines",
        "alaska", "royal air maroc", "oman air", "fiji",
    ],
    "skyteam": [
        "klm", "air france", "transavia", "delta", "korean air", "china eastern", "china airlines",
        "vietnam airlines", "saudia", "aeromexico", "kenya airways", "garuda", "xiamen",
        "virgin atlantic", "sas", "scandinavian", "air europa", "tarom", "middle east airlines",
        "aerolineas argentinas",
    ],
}

SEPARATE_MARKERS = ["separate ticket", "self transfer", "self-transfer", "別々", "別の航空券", "自己乗り継ぎ", "selbst"]


def group_of(name: str):
    n = (name or "").lower().strip()
    for g, names in GROUPS.items():
        for key in names:
            k = key.strip()
            # short codes must match the whole name, longer ones as substring
            if (len(k) <= 3 and n == k) or (len(k) > 3 and key in n + " "):
                return g
    return None


def is_allowed(option: dict) -> bool:
    blob = json.dumps(option, ensure_ascii=False).lower()
    if any(m in blob for m in SEPARATE_MARKERS):
        return False
    airlines = {s.get("airline", "") for s in option.get("flights", [])}
    if len(airlines) <= 1:
        return True
    groups = {group_of(a) for a in airlines}
    return None not in groups and len(groups) == 1
