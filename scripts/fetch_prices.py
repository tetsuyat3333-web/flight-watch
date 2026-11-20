"""FRA -> Tokyo (HND/NRT) round-trip price fetcher.

Runs in GitHub Actions every 3 hours. Calls SerpApi's Google Flights engine,
records the cheapest overall fare and the cheapest nonstop fare, and writes:
  data/latest.json   - the most recent full result (top flights)
  data/history.json  - one row per run (for the chart)
  alert.md           - only when a new record low is found (workflow opens an issue)
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from airlines import is_allowed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def fetch(api_key: str) -> dict:
    params = {
        "engine": "google_flights",
        "departure_id": ",".join(CONFIG["from"]),
        "arrival_id": ",".join(CONFIG["to"]),
        "outbound_date": CONFIG["outbound_date"],
        "return_date": CONFIG["return_date"],
        "type": "1",  # round trip
        "adults": str(CONFIG.get("adults", 1)),
        "travel_class": "1",  # economy
        "currency": "EUR",
        "hl": "ja",
        "gl": "de",
        "api_key": api_key,
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def summarize(option: dict) -> dict:
    segs = option.get("flights", [])
    first, last = segs[0], segs[-1]
    airlines = []
    for s in segs:
        a = s.get("airline")
        if a and a not in airlines:
            airlines.append(a)
    return {
        "price": option.get("price"),
        "airlines": airlines,
        "stops": len(segs) - 1,
        "dep_airport": first["departure_airport"]["id"],
        "dep_time": first["departure_airport"].get("time"),
        "arr_airport": last["arrival_airport"]["id"],
        "arr_time": last["arrival_airport"].get("time"),
        "duration_min": option.get("total_duration"),
        "layovers": [l.get("id") for l in option.get("layovers", [])],
        "flight_numbers": [s.get("flight_number") for s in segs],
    }


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main() -> int:
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("SERPAPI_KEY is not set", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    history = load(DATA / "history.json", [])

    try:
        res = fetch(api_key)
    except Exception as e:  # network / quota errors: record and exit cleanly
        history.append({"t": now, "error": str(e)[:200]})
        (DATA / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
        print("fetch failed:", e, file=sys.stderr)
        return 0

    if res.get("error"):
        history.append({"t": now, "error": str(res["error"])[:200]})
        (DATA / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
        print("api error:", res["error"], file=sys.stderr)
        return 0

    raw = [o for o in res.get("best_flights", []) + res.get("other_flights", []) if o.get("price") and o.get("flights")]
    options = [o for o in raw if is_allowed(o)]
    excluded = len(raw) - len(options)
    flights = sorted((summarize(o) for o in options), key=lambda f: f["price"])
    nonstop = [f for f in flights if f["stops"] == 0]

    home = CONFIG.get("home", "FRA")
    home_flights = [f for f in flights if f["dep_airport"] == home]
    best = flights[0] if flights else None
    best_nonstop = nonstop[0] if nonstop else None
    best_home = home_flights[0] if home_flights else None
    best_home_nonstop = next((f for f in home_flights if f["stops"] == 0), None)
    insights = res.get("price_insights", {})

    # record lows before this run
    prev_low = min((h["best"]["price"] for h in history if h.get("best")), default=None)
    prev_ns_low = min((h["nonstop"]["price"] for h in history if h.get("nonstop")), default=None)

    row = {
        "t": now,
        "best": best,
        "nonstop": best_nonstop,
        "home": best_home,
        "home_nonstop": best_home_nonstop,
        "price_level": insights.get("price_level"),
        "typical_range": insights.get("typical_price_range"),
    }
    history.append(row)

    latest = {
        "t": now,
        "config": CONFIG,
        "best": best,
        "nonstop": best_nonstop,
        "home": best_home,
        "home_nonstop": best_home_nonstop,
        "flights": flights[:20],
        "excluded_self_transfer": excluded,
        "price_insights": insights,
    }
    (DATA / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")

    # alerts: new record low overall / nonstop, or nonstop under the target set in config.json
    lines = []
    if best and prev_low is not None and best["price"] < prev_low:
        lines.append(f"- 全体の最安値を更新: **€{best['price']}**(前回までの最安 €{prev_low}){best['dep_airport']}発・{', '.join(best['airlines'])}・経由{best['stops']}回・{best['arr_airport']}着")
    if best_nonstop and prev_ns_low is not None and best_nonstop["price"] < prev_ns_low:
        lines.append(f"- 直行便の最安値を更新: **€{best_nonstop['price']}**(前回までの最安 €{prev_ns_low}){best_nonstop['dep_airport']}発・{', '.join(best_nonstop['airlines'])}・{best_nonstop['arr_airport']}着")
    target = CONFIG.get("nonstop_alert_eur")
    if best_nonstop and target and best_nonstop["price"] <= target:
        lines.append(f"- 直行便が目標 €{target} 以下: **€{best_nonstop['price']}**({', '.join(best_nonstop['airlines'])})")
    if lines:
        dep = (best or best_nonstop)["dep_airport"].lower()
        body = "\n".join(lines) + f"\n\n予約(Skyscanner): {CONFIG['skyscanner_url'].format(dep=dep)}\n"
        (ROOT / "alert.md").write_text(body, encoding="utf-8")

    print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
