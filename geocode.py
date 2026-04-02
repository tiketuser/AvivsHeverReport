"""
Standalone geocoding script — run once to add lat/lng to restaurants.json.
Uses Nominatim (OpenStreetMap), free, no API key.
Caches results in docs/geocache.json so re-runs are fast.
Rate: 1 request/second as required by Nominatim policy.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
RESTAURANTS_PATH = os.path.join(DOCS_DIR, "restaurants.json")
GEOCACHE_PATH = os.path.join(DOCS_DIR, "geocache.json")


def load_geocache():
    if os.path.exists(GEOCACHE_PATH):
        with open(GEOCACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_geocache(cache):
    with open(GEOCACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def geocode_address(address, cache):
    if not address or "אינטרנטית" in address:
        return None, None

    if address in cache:
        cached = cache[address]
        return cached.get("lat"), cached.get("lng")

    query = address + ", ישראל"
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "HeverReport/1.0 (personal project)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode("utf-8"))
        if results:
            lat = float(results[0]["lat"])
            lng = float(results[0]["lon"])
            cache[address] = {"lat": lat, "lng": lng}
            return lat, lng
    except Exception as e:
        print(f"  Error geocoding '{address}': {e}")

    cache[address] = {"lat": None, "lng": None}
    return None, None


def main():
    with open(RESTAURANTS_PATH, encoding="utf-8") as f:
        restaurants = json.load(f)

    cache = load_geocache()
    total = len(restaurants)
    geocoded = 0
    new_requests = 0

    print(f"Geocoding {total} restaurants...")

    for i, r in enumerate(restaurants):
        address = r.get("address", "")

        # Already has valid coords from a previous run
        if r.get("lat") is not None:
            geocoded += 1
            continue

        already_cached = address in cache

        lat, lng = geocode_address(address, cache)
        r["lat"] = lat
        r["lng"] = lng

        if lat is not None:
            geocoded += 1

        if not already_cached and address and "אינטרנטית" not in address:
            new_requests += 1
            time.sleep(1.1)  # Nominatim rate limit

        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{total} — {geocoded} geocoded so far")
            save_geocache(cache)
            # Save progress to restaurants.json periodically
            with open(RESTAURANTS_PATH, "w", encoding="utf-8") as f:
                json.dump(restaurants, f, ensure_ascii=False, indent=2)

    save_geocache(cache)
    with open(RESTAURANTS_PATH, "w", encoding="utf-8") as f:
        json.dump(restaurants, f, ensure_ascii=False, indent=2)

    print(f"Done. {geocoded}/{total} restaurants have coordinates. Made {new_requests} new API calls.")


if __name__ == "__main__":
    main()
