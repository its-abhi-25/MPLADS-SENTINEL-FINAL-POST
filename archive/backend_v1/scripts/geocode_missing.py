"""
Geocode the 26 missing real Lok Sabha constituencies using Nominatim.
Does NOT touch existing cache entries. Does NOT modify the source CSV.
"""
import csv
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_CSV = PROJECT_ROOT / "data" / "processed" / "location_coordinates.csv"
CACHE_JSON = PROJECT_ROOT / "data" / "processed" / "geocode_cache.json"
DATASET_CSV = PROJECT_ROOT / "data" / "raw" / "MPLADS_Sentinel_FINAL-1.csv"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_DELAY = 1.1
LAT_MIN, LAT_MAX = -90, 90
LON_MIN, LON_MAX = -180, 180

# The 26 real Lok Sabha constituencies that need geocoding
# (State, Constituency) — derived from audit
MISSING_CONSTITUENCIES = [
    ("Assam", "KALIABOR"),
    ("Assam", "KARIMGANJ (SC)"),
    ("Assam", "MANGALDOI"),
    ("Assam", "SILCHAR"),
    ("Assam", "TEZPUR"),
    ("Assam", "AUTONOMOUS DISTRICT (ST)"),
    ("Bihar", "MUNGER"),
    ("Bihar", "PASCHIM CHAMPARAN"),
    ("Bihar", "SARAN"),
    ("Jharkhand", "HAZARIBAGH"),
    ("Jharkhand", "RAJMAHAL (ST)"),
    ("Jharkhand", "SINGHBHUM (ST)"),
    ("Karnataka", "GULBARGA (SC)"),
    ("Odisha", "BERHAMPUR"),
    ("Odisha", "DHENKANAL"),
    ("Rajasthan", "JODHPUR"),
    ("Rajasthan", "TONK-SAWAI MADHOPUR"),
    ("Punjab", "KHADOOR SAHIB"),
    ("Tamil Nadu", "SALEM"),
    ("Telangana", "SECUNDERABAD"),
    ("Andhra Pradesh", "VISAKHAPATNAM"),
    ("Maharashtra", "BULDHANA"),
    ("Uttar Pradesh", "BANSGAON (SC)"),
    ("Uttar Pradesh", "DOMARIYAGANJ"),
    ("Uttar Pradesh", "SAMBHAL"),
    ("Uttar Pradesh", "SHRAWASTI"),
]

# Alternate search queries for tricky names
ALTERNATE_QUERIES = {
    "KALIABOR": ["Kaliabor, Assam, India", "Kaliabor constituency, Assam, India"],
    "KARIMGANJ (SC)": ["Karimganj, Assam, India", "Karimganj constituency, Assam, India"],
    "MANGALDOI": ["Mangaldai, Assam, India", "Mangaldoi, Assam, India"],
    "SILCHAR": ["Silchar, Assam, India", "Silchar constituency, Assam, India"],
    "TEZPUR": ["Tezpur, Assam, India", "Tezpur constituency, Assam, India"],
    "AUTONOMOUS DISTRICT (ST)": ["Autonomous District, Assam, India", "Diphu, Assam, India"],
    "MUNGER": ["Munger, Bihar, India", "Munger constituency, Bihar, India"],
    "PASCHIM CHAMPARAN": ["West Champaran, Bihar, India", "Bettiah, Bihar, India"],
    "SARAN": ["Saran, Bihar, India", "Chhapra, Bihar, India"],
    "HAZARIBAGH": ["Hazaribagh, Jharkhand, India", "Hazaribagh constituency, Jharkhand, India"],
    "RAJMAHAL (ST)": ["Rajmahal, Jharkhand, India", "Rajmahal constituency, Jharkhand, India"],
    "SINGHBHUM (ST)": ["Singhbhum, Jharkhand, India", "Singhbum, Jharkhand, India", "Chaibasa, Jharkhand, India"],
    "GULBARGA (SC)": ["Gulbarga, Karnataka, India", "Kalaburagi, Karnataka, India"],
    "BERHAMPUR": ["Berhampur, Odisha, India", "Brahmapur, Odisha, India"],
    "DHENKANAL": ["Dhenkanal, Odisha, India", "Dhenkanal constituency, Odisha, India"],
    "JODHPUR": ["Jodhpur, Rajasthan, India", "Jodhpur constituency, Rajasthan, India"],
    "TONK-SAWAI MADHOPUR": ["Tonk, Rajasthan, India", "Sawai Madhopur, Rajasthan, India"],
    "KHADOOR SAHIB": ["Tarn Taran, Punjab, India", "Khadoor Sahib, Punjab, India"],
    "SALEM": ["Salem, Tamil Nadu, India", "Salem constituency, Tamil Nadu, India"],
    "SECUNDERABAD": ["Secunderabad, Telangana, India", "Secunderabad constituency, Telangana, India"],
    "VISAKHAPATNAM": ["Visakhapatnam, Andhra Pradesh, India", "Visakhapatnam constituency, Andhra Pradesh, India"],
    "BULDHANA": ["Buldhana, Maharashtra, India", "Buldhana constituency, Maharashtra, India"],
    "BANSGAON (SC)": ["Bansgaon, Uttar Pradesh, India", "Bansgaon constituency, Uttar Pradesh, India"],
    "DOMARIYAGANJ": ["Domariyaganj, Uttar Pradesh, India", "Domariyaganj constituency, Uttar Pradesh, India"],
    "SAMBHAL": ["Sambhal, Uttar Pradesh, India", "Sambhal constituency, Uttar Pradesh, India"],
    "SHRAWASTI": ["Shrawasti, Uttar Pradesh, India", "Shravasti, Uttar Pradesh, India"],
}


def validate_coordinates(lat, lon):
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        if not (LAT_MIN <= lat_f <= LAT_MAX):
            return False
        if not (LON_MIN <= lon_f <= LON_MAX):
            return False
        if lat_f == 0.0 and lon_f == 0.0:
            return False
        # Basic India bounds check
        if not (6.0 <= lat_f <= 37.5 and 68.0 <= lon_f <= 97.5):
            return False
        return True
    except (TypeError, ValueError):
        return False


def geocode_nominatim(query):
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "in",
    })
    url = f"{NOMINATIM_URL}?{params}"
    headers = {"User-Agent": "MPLADS-Sentinel/1.0 (investigation-portal)"}
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
        print(f"  [ERROR] {e}")
        return None


def load_existing_cache():
    """Load existing coordinates from CSV."""
    existing = {}
    if CACHE_CSV.exists():
        with open(CACHE_CSV, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                state = (row.get("State") or "").strip()
                constituency = (row.get("Constituency") or "").strip()
                if state and constituency:
                    existing[(state, constituency)] = {
                        "State": state,
                        "Constituency": constituency,
                        "Location_Query": row.get("Location_Query", ""),
                        "Normalized_Location": row.get("Normalized_Location", ""),
                        "Latitude": row.get("Latitude", ""),
                        "Longitude": row.get("Longitude", ""),
                        "Location_Level": row.get("Location_Level", ""),
                        "Confidence": row.get("Confidence", ""),
                        "Geocoding_Status": row.get("Geocoding_Status", ""),
                        "Display_Name": row.get("Display_Name", ""),
                    }
    return existing


def save_cache(existing):
    """Save updated cache to CSV."""
    fieldnames = [
        "State", "Constituency", "Location_Query", "Normalized_Location",
        "Latitude", "Longitude", "Location_Level", "Confidence",
        "Geocoding_Status", "Display_Name"
    ]
    with open(CACHE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(existing.keys()):
            writer.writerow(existing[key])


def main():
    existing = load_existing_cache()
    print(f"Existing cache entries: {len(existing)}")

    newly_geocoded = []
    still_missing = []

    for state, constituency in MISSING_CONSTITUENCIES:
        key = (state, constituency)
        if key in existing:
            print(f"  [SKIP] {state} / {constituency} — already in cache")
            continue

        print(f"  [GEOCODING] {state} / {constituency}...")

        # Try primary query: "ConstituencyName, State, India"
        clean_name = constituency.replace("(SC)", "").replace("(ST)", "").strip()
        primary_query = f"{clean_name}, {state}, India"
        result = geocode_nominatim(primary_query)

        # Try alternate queries if primary fails
        if result is None and constituency in ALTERNATE_QUERIES:
            for alt_query in ALTERNATE_QUERIES[constituency]:
                time.sleep(REQUEST_DELAY)
                result = geocode_nominatim(alt_query)
                if result:
                    break

        if result:
            lat, lon, display_name = result
            # Determine precision from display name
            precision = "CONSTITUENCY"
            if "district" in display_name.lower():
                precision = "DISTRICT"

            entry = {
                "State": state,
                "Constituency": constituency,
                "Location_Query": primary_query,
                "Normalized_Location": f"{constituency}, {state}",
                "Latitude": str(lat),
                "Longitude": str(lon),
                "Location_Level": precision,
                "Confidence": "MEDIUM",
                "Geocoding_Status": "resolved",
                "Display_Name": display_name,
            }
            existing[key] = entry
            newly_geocoded.append((state, constituency, lat, lon))
            print(f"    -> RESOLVED: {lat:.6f}, {lon:.6f} ({precision})")
        else:
            still_missing.append((state, constituency))
            print(f"    -> FAILED: Could not geocode")

        time.sleep(REQUEST_DELAY)

    # Save updated cache
    save_cache(existing)
    print(f"\nCache updated: {len(existing)} total entries")
    print(f"Newly geocoded: {len(newly_geocoded)}")
    print(f"Still missing: {len(still_missing)}")

    if still_missing:
        print("\nStill unresolved constituencies:")
        for state, constituency in still_missing:
            print(f"  - {state} / {constituency}")

    if newly_geocoded:
        print("\nNewly geocoded constituencies:")
        for state, constituency, lat, lon in newly_geocoded:
            print(f"  - {state} / {constituency}: {lat:.6f}, {lon:.6f}")


if __name__ == "__main__":
    main()
