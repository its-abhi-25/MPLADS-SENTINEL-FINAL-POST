"""
Geocode unique MPLADS locations using Nominatim (OpenStreetMap).

Reads data/raw/MPLADS_Sentinel_FINAL-1.csv, extracts unique (State, Constituency) pairs,
geocodes each unique location, and saves results to data/processed/location_coordinates.csv.

Uses caching: if a location already has coordinates in the cache, the API is not called.

Usage:
    python scripts/geocode_locations.py              # Geocode all unique locations
    python scripts/geocode_locations.py --test       # Test with first 20 locations
    python scripts/geocode_locations.py --status     # Show cache status
"""
import csv
import json
import os
import sys
import time
import re
from pathlib import Path
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RAW_CSV = PROJECT_ROOT / "data" / "raw" / "MPLADS_Sentinel_FINAL-1.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
CACHE_FILE = OUTPUT_DIR / "location_coordinates.csv"
CACHE_JSON = OUTPUT_DIR / "geocode_cache.json"

# Nominatim settings
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_DELAY = 1.1  # seconds between requests (Nominatim requires >= 1s)
MAX_RETRIES = 3

# Valid coordinate ranges
LAT_MIN, LAT_MAX = -90, 90
LON_MIN, LON_MAX = -180, 180


def load_cache():
    """Load existing coordinate cache from JSON file."""
    if CACHE_JSON.exists():
        with open(CACHE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    """Save coordinate cache to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_JSON, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def extract_unique_locations():
    """Read CSV and extract unique (State, Constituency) pairs with counts."""
    locations = defaultdict(lambda: {"count": 0, "mps": set()})

    with open(RAW_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            state = (row.get("state") or row.get("State") or "").strip()
            constituency = (row.get("constituency") or row.get("Constituency") or "").strip()
            mp = (row.get("mp_name") or row.get("MP") or "").strip()
            if state and constituency:
                key = (state, constituency)
                locations[key]["count"] += 1
                if mp:
                    locations[key]["mps"].add(mp)

    return locations


def normalize_query(state, constituency):
    """Create a normalized search query for geocoding."""
    # Clean up common suffixes for better geocoding results
    const_clean = constituency.strip()

    # Common Indian constituency suffixes
    suffixes = ["(SC)", "(ST)", "(OBC)", "(GEN)", "(EWS)"]
    for suffix in suffixes:
        const_clean = const_clean.replace(suffix, "").strip()

    # Build query: "Constituency, State, India"
    query = f"{const_clean}, {state}, India"
    return query


def validate_coordinates(lat, lon):
    """Check if coordinates are within valid ranges and not zero."""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        if not (LAT_MIN <= lat_f <= LAT_MAX):
            return False
        if not (LON_MIN <= lon_f <= LON_MAX):
            return False
        # Reject 0,0
        if lat_f == 0.0 and lon_f == 0.0:
            return False
        return True
    except (TypeError, ValueError):
        return False


def geocode_nominatim(query, retries=MAX_RETRIES):
    """Geocode a location using Nominatim API. Returns (lat, lon, display_name) or None."""
    import urllib.request
    import urllib.parse

    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "in",
    })
    url = f"{NOMINATIM_URL}?{params}"

    headers = {
        "User-Agent": "MPLADS-Sentinel/1.0 (investigation-portal)"
    }

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data and len(data) > 0:
                    result = data[0]
                    lat = result.get("lat")
                    lon = result.get("lon")
                    display = result.get("display_name", "")
                    if validate_coordinates(lat, lon):
                        return float(lat), float(lon), display
            return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  [ERROR] Geocoding failed after {retries} attempts: {e}")
                return None
    return None


def geocode_location(state, constituency, cache):
    """Geocode a location, checking cache first."""
    cache_key = f"{state}|{constituency}"

    # Check cache
    if cache_key in cache:
        cached = cache[cache_key]
        if cached.get("status") == "resolved":
            return cached

    # Build query
    query = normalize_query(state, constituency)

    # Determine precision based on query
    precision = "CONSTITUENCY"

    # Call Nominatim
    result = geocode_nominatim(query)

    if result:
        lat, lon, display_name = result
        cache_entry = {
            "state": state,
            "constituency": constituency,
            "location_query": query,
            "normalized_location": f"{constituency}, {state}",
            "latitude": lat,
            "longitude": lon,
            "location_level": precision,
            "confidence": "MEDIUM",
            "status": "resolved",
            "display_name": display_name,
        }
    else:
        # Try fallback: just state name
        state_query = f"{state}, India"
        state_result = geocode_nominatim(state_query)
        time.sleep(REQUEST_DELAY)

        if state_result:
            lat, lon, display_name = state_result
            cache_entry = {
                "state": state,
                "constituency": constituency,
                "location_query": query,
                "normalized_location": f"{constituency}, {state}",
                "latitude": lat,
                "longitude": lon,
                "location_level": "STATE",
                "confidence": "LOW",
                "status": "approximate",
                "display_name": display_name,
            }
        else:
            cache_entry = {
                "state": state,
                "constituency": constituency,
                "location_query": query,
                "normalized_location": f"{constituency}, {state}",
                "latitude": None,
                "longitude": None,
                "location_level": "UNKNOWN",
                "confidence": "NONE",
                "status": "unresolved",
                "display_name": "",
            }

    cache[cache_key] = cache_entry
    return cache_entry


def save_csv(cache):
    """Save cache as CSV for the backend."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "State", "Constituency", "Location_Query", "Normalized_Location",
        "Latitude", "Longitude", "Location_Level", "Confidence",
        "Geocoding_Status", "Display_Name",
    ]
    with open(CACHE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key, entry in sorted(cache.items()):
            writer.writerow({
                "State": entry.get("state", ""),
                "Constituency": entry.get("constituency", ""),
                "Location_Query": entry.get("location_query", ""),
                "Normalized_Location": entry.get("normalized_location", ""),
                "Latitude": entry.get("latitude", ""),
                "Longitude": entry.get("longitude", ""),
                "Location_Level": entry.get("location_level", ""),
                "Confidence": entry.get("confidence", ""),
                "Geocoding_Status": entry.get("status", ""),
                "Display_Name": entry.get("display_name", ""),
            })


def show_status(cache):
    """Display cache statistics."""
    total = len(cache)
    resolved = sum(1 for v in cache.values() if v.get("status") == "resolved")
    approximate = sum(1 for v in cache.values() if v.get("status") == "approximate")
    unresolved = sum(1 for v in cache.values() if v.get("status") == "unresolved")
    print(f"\nCache Status:")
    print(f"  Total locations: {total}")
    print(f"  Resolved: {resolved}")
    print(f"  Approximate (state-level): {approximate}")
    print(f"  Unresolved: {unresolved}")
    if total > 0:
        print(f"  Coverage: {(resolved + approximate) / total * 100:.1f}%")


def main():
    test_mode = "--test" in sys.argv
    status_mode = "--status" in sys.argv

    # Load cache
    cache = load_cache()

    if status_mode:
        show_status(cache)
        return

    # Extract unique locations
    print("Extracting unique locations from MPLADS_Sentinel_FINAL-1.csv...")
    locations = extract_unique_locations()
    total_unique = len(locations)
    total_works = sum(v["count"] for v in locations.values())
    print(f"Found {total_unique} unique (State, Constituency) pairs across {total_works:,} works")

    if test_mode:
        # Take first 20 locations
        test_locations = dict(list(locations.items())[:20])
        print(f"\n[TEST MODE] Geocoding {len(test_locations)} locations...\n")
        locations = test_locations
    else:
        print(f"\nGeocoding all {total_unique} locations...\n")

    # Geocode each unique location
    start_time = time.time()
    resolved_count = 0
    cached_count = 0
    failed_count = 0

    for i, ((state, constituency), info) in enumerate(sorted(locations.items())):
        cache_key = f"{state}|{constituency}"
        is_cached = cache_key in cache and cache[cache_key].get("status") in ("resolved", "approximate")

        if is_cached:
            cached_count += 1
            status_char = "C"  # cached
        else:
            result = geocode_location(state, constituency, cache)
            if result.get("status") in ("resolved", "approximate"):
                resolved_count += 1
                status_char = "OK"
            else:
                failed_count += 1
                status_char = "FAIL"
            time.sleep(REQUEST_DELAY)

        # Progress indicator
        progress = (i + 1) / len(locations) * 100
        print(f"  [{i+1:4d}/{len(locations)}] ({progress:5.1f}%) [{status_char:4s}] {state} / {constituency}")

        # Save every 50 locations
        if (i + 1) % 50 == 0:
            save_cache(cache)
            save_csv(cache)

    # Final save
    save_cache(cache)
    save_csv(cache)

    elapsed = time.time() - start_time
    print(f"\nGeocoding complete in {elapsed:.1f}s")
    print(f"  Newly geocoded: {resolved_count}")
    print(f"  From cache: {cached_count}")
    print(f"  Failed: {failed_count}")

    show_status(cache)

    print(f"\nOutput files:")
    print(f"  Cache: {CACHE_JSON}")
    print(f"  CSV:   {CACHE_FILE}")


if __name__ == "__main__":
    main()
