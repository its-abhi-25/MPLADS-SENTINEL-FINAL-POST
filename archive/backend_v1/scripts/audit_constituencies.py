"""Read-only audit of ALL constituencies in the MPLADS Sentinel project."""
import csv
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV = os.path.join(PROJECT_ROOT, "data", "raw", "MPLADS_Sentinel_FINAL-1.csv")
CACHE_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "location_coordinates.csv")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
GEOCODE_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "geocode_locations.py")


def load_dataset():
    """Load the main dataset and extract all (State, Constituency) pairs with stats."""
    pairs = defaultdict(lambda: {
        "work_count": 0,
        "total_allocation": 0.0,
        "risk_dist": defaultdict(int),
        "houses": set(),
    })
    with open(RAW_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            state = row.get("state", "").strip()
            constituency = row.get("constituency", "").strip()
            if not state or not constituency:
                continue
            key = (state, constituency)
            pairs[key]["work_count"] += 1
            try:
                pairs[key]["total_allocation"] += float(row.get("allocation_amount", 0) or 0)
            except (ValueError, TypeError):
                pass
            risk = row.get("status_normalized", "UNKNOWN").strip()
            pairs[key]["risk_dist"][risk] += 1
            house = row.get("house", "").strip()
            if house:
                pairs[key]["houses"].add(house)
    return pairs


def load_coordinate_cache():
    """Load the coordinate cache CSV."""
    cache = {}
    with open(CACHE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            state = row.get("State", "").strip()
            constituency = row.get("Constituency", "").strip()
            if state and constituency:
                key = (state, constituency)
                cache[key] = {
                    "latitude": row.get("Latitude", ""),
                    "longitude": row.get("Longitude", ""),
                    "level": row.get("Location_Level", ""),
                    "confidence": row.get("Confidence", ""),
                    "status": row.get("Geocoding_Status", ""),
                    "display_name": row.get("Display_Name", ""),
                }
    return cache


def check_env():
    """Check .env for Google API key."""
    if not os.path.exists(ENV_FILE):
        return False, "File does not exist"
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return False, "File is empty"
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "GOOGLE" in line.upper() or "API_KEY" in line.upper() or "GEOCODE" in line.upper():
            key_val = line.split("=", 1)
            if len(key_val) == 2:
                val = key_val[1].strip().strip('"').strip("'")
                if val:
                    return True, f"{key_val[0].strip()}=***present***"
    return False, "No Google API key found"


def check_geocode_method():
    """Check what geocoding method is configured in geocode_locations.py."""
    if not os.path.exists(GEOCODE_SCRIPT):
        return "Script not found"
    with open(GEOCODE_SCRIPT, "r", encoding="utf-8") as f:
        content = f.read()
    methods = []
    if "nominatim" in content.lower():
        methods.append("Nominatim (OpenStreetMap)")
    if "google" in content.lower():
        methods.append("Google Geocoding API")
    if "geocodio" in content.lower():
        methods.append("Geocodio")
    if "opencage" in content.lower():
        methods.append("OpenCage")
    return ", ".join(methods) if methods else "Unknown"


def find_similar_names(missing_state, missing_constituency, cache_keys):
    """Find cache entries with similar names that might match a missing constituency."""
    matches = []
    miss_clean = missing_constituency.upper().replace("(SC)", "").replace("(ST)", "").replace("(OBC)", "").strip()
    for (state, const), info in cache_keys.items():
        const_clean = const.upper().replace("(SC)", "").replace("(ST)", "").replace("(OBC)", "").strip()
        ratio = SequenceMatcher(None, miss_clean, const_clean).ratio()
        if ratio > 0.6 and state == missing_state:
            matches.append((state, const, ratio, info))
    matches.sort(key=lambda x: -x[2])
    return matches[:3]


def main():
    print("=" * 80)
    print("MPLADS SENTINEL - COMPLETE CONSTITUENCY AUDIT")
    print("=" * 80)

    # 1. Load data
    print("\n[1] Loading dataset...")
    pairs = load_dataset()
    total_pairs = len(pairs)
    total_works = sum(v["work_count"] for v in pairs.values())
    total_allocation = sum(v["total_allocation"] for v in pairs.values())
    print(f"    Total unique (State, Constituency) pairs: {total_pairs}")
    print(f"    Total works: {total_works:,}")
    print(f"    Total allocation: INR {total_allocation:,.2f}")

    # 2. Load coordinate cache
    print("\n[2] Loading coordinate cache...")
    cache = load_coordinate_cache()
    print(f"    Cache entries: {len(cache)}")

    # 3. Identify covered vs missing
    with_coords = []
    without_coords = []
    for key, info in sorted(pairs.items()):
        if key in cache:
            entry = cache[key]
            lat = entry.get("latitude", "")
            lon = entry.get("longitude", "")
            has_valid = lat and lon and lat != "" and lon != ""
            if has_valid:
                with_coords.append((key, info, entry))
            else:
                without_coords.append((key, info, "Cache entry has no coordinates"))
        else:
            without_coords.append((key, info, "No cache entry"))

    print(f"\n[3] COVERAGE SUMMARY:")
    print(f"    With coordinates: {len(with_coords)} ({len(with_coords)/total_pairs*100:.1f}%)")
    print(f"    Without coordinates: {len(without_coords)} ({len(without_coords)/total_pairs*100:.1f}%)")

    # 4. Risk distribution summary across all constituencies
    print(f"\n[4] RISK DISTRIBUTION (across all {total_pairs} constituencies):")
    risk_totals = defaultdict(int)
    for info in pairs.values():
        for risk, count in info["risk_dist"].items():
            risk_totals[risk] += count
    for risk, count in sorted(risk_totals.items(), key=lambda x: -x[1]):
        print(f"    {risk}: {count:,}")

    # 5. House distribution
    print(f"\n[5] HOUSE DISTRIBUTION:")
    house_totals = defaultdict(int)
    for info in pairs.values():
        for h in info["houses"]:
            house_totals[h] += 1
    for h, count in sorted(house_totals.items(), key=lambda x: -x[1]):
        print(f"    {h}: {count}")

    # 6. Coordinate precision levels
    print(f"\n[6] COORDINATE PRECISION LEVELS (for covered constituencies):")
    level_totals = defaultdict(int)
    for _, _, entry in with_coords:
        level_totals[entry.get("level", "UNKNOWN")] += 1
    for level, count in sorted(level_totals.items(), key=lambda x: -x[1]):
        print(f"    {level}: {count}")

    # 7. COMPLETE LIST of constituencies WITHOUT coordinates
    print(f"\n{'=' * 80}")
    print(f"[7] COMPLETE LIST OF CONSTITUENCIES WITHOUT COORDINATES ({len(without_coords)} total)")
    print(f"{'=' * 80}")
    print(f"{'#':>4}  {'State':<30}  {'Constituency':<45}  {'Works':>6}  {'Reason'}")
    print("-" * 120)

    state_pattern = defaultdict(int)
    for i, (key, info, reason) in enumerate(sorted(without_coords, key=lambda x: (x[0][0], x[0][1])), 1):
        state, const = key
        state_pattern[state] += 1
        print(f"{i:4d}  {state:<30}  {const:<45}  {info['work_count']:>6d}  {reason}")

    # 8. Patterns analysis
    print(f"\n{'=' * 80}")
    print("[8] PATTERNS IN MISSING CONSTITUENCIES")
    print(f"{'=' * 80}")

    # By state
    print("\n  By State:")
    for state, count in sorted(state_pattern.items(), key=lambda x: -x[1]):
        print(f"    {state}: {count}")

    # Check if Rajya Sabha
    rajya_sabha_only = 0
    lok_sabha_only = 0
    both = 0
    for key, info, reason in without_coords:
        houses = info["houses"]
        if "Rajya Sabha" in houses and "Lok Sabha" not in houses:
            rajya_sabha_only += 1
        elif "Lok Sabha" in houses and "Rajya Sabha" not in houses:
            lok_sabha_only += 1
        elif "Rajya Sabha" in houses and "Lok Sabha" in houses:
            both += 1

    print(f"\n  By House Type (among missing):")
    print(f"    Lok Sabha only: {lok_sabha_only}")
    print(f"    Rajya Sabha only: {rajya_sabha_only}")
    print(f"    Both: {both}")

    # Similar name matches
    print(f"\n  POTENTIAL NAME MATCHES (if geocoded name differs):")
    match_found = False
    for key, info, reason in without_coords:
        state, const = key
        similar = find_similar_names(state, const, cache)
        if similar:
            match_found = True
            print(f"    {state} / {const}")
            for s_state, s_const, ratio, s_info in similar:
                print(f"      -> Might match: {s_const} (similarity: {ratio:.0%}) [{s_info.get('status', '')}]")
    if not match_found:
        print("    No close name matches found in cache.")

    # 9. Environment check
    print(f"\n{'=' * 80}")
    print("[9] ENVIRONMENT CHECK")
    print(f"{'=' * 80}")
    has_key, detail = check_env()
    print(f"  Google API key in .env: {'YES' if has_key else 'NO'}")
    print(f"  Detail: {detail}")

    method = check_geocode_method()
    print(f"  Geocoding method in geocode_locations.py: {method}")

    # 10. Constituencies with HIGH risk and no coordinates
    high_risk_no_coords = []
    for key, info, reason in without_coords:
        unsanctioned = info["risk_dist"].get("UNSANCTIONED", 0)
        if unsanctioned > 0:
            high_risk_no_coords.append((key, info, unsanctioned))
    high_risk_no_coords.sort(key=lambda x: -x[2])

    if high_risk_no_coords:
        print(f"\n{'=' * 80}")
        print(f"[10] CONSTITUENCIES WITH UNSANCTIONED WORKS BUT NO COORDINATES ({len(high_risk_no_coords)})")
        print(f"{'=' * 80}")
        print(f"{'State':<30}  {'Constituency':<45}  {'Unsanctioned':>12}")
        print("-" * 90)
        for key, info, unsanctioned in high_risk_no_coords:
            state, const = key
            print(f"{state:<30}  {const:<45}  {unsanctioned:>12d}")

    print(f"\n{'=' * 80}")
    print("AUDIT COMPLETE")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
