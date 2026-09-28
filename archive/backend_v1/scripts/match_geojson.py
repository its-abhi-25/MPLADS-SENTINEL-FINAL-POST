"""
Final constituency matching with explicit name aliases.
"""
import csv
import json
import re
import math
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "backend" / "data" / "raw" / "mplads_ready.csv"
RAW_GEOJSON = PROJECT_ROOT / "backend" / "data" / "processed" / "constituencies_raw.geojson"
OUTPUT_GEOJSON = PROJECT_ROOT / "backend" / "data" / "processed" / "constituencies.geojson"
OUTPUT_REPORT = PROJECT_ROOT / "backend" / "data" / "processed" / "geojson_match_report.json"
COORD_CACHE = PROJECT_ROOT / "backend" / "data" / "processed" / "geocode_cache.json"

# Explicit name aliases: dataset constituency -> GeoJSON pc_name
# Used when the names differ between sources despite being the same seat
CONSTITUENCY_ALIASES = {
    ("Andhra Pradesh", "ANAKAPALLE"): "Anakapalli",
    ("Andhra Pradesh", "ANANTAPUR"): "Anantapuramu",
    ("Assam", "GUWAHATI"): "Gauhati",
    ("Assam", "Sonitpur"): "Tezpur",
    ("Bihar", "PURNEA"): "Purnia",
    ("Bihar", "UJJARPUR"): "Ujiarpur",
    ("Chhattisgarh", "JANJGIR CHAMPA(SC)"): "Janjgir",
    ("Chhattisgarh", "SARGUJA(ST)"): "Surguja",
    ("Delhi", "CHANDINI CHOWK"): "Chandni Chowk",
    ("Haryana", "SONEPAT"): "Sonipat",
    ("Jammu And Kashmir", "BARAMULLAH"): "Baramulla",
    ("Karnataka", "BELGAUM"): "Belagavi",
    ("Karnataka", "CHIKKODI"): "Chikodi",
    ("Karnataka", "DAVANAGERE"): "Davangere",
    ("Karnataka", "HASSAN"): "Haasan",
    ("Kerala", "MAVELIKKARA(SC)"): "Mavelikara",
    ("Madhya Pradesh", "MANDSOUR"): "Mandsaur",
    ("Punjab", "BHATINDA"): "Bathinda",
    ("Punjab", "FIROZPUR"): "Firozepur",
    ("Tamil Nadu", "DHARAMAPURI"): "Dharmapuri",
    ("Tamil Nadu", "KANNIYAKUMARI"): "Kanyakumari",
    ("Tamil Nadu", "MAYILADUTHURAI"): "Mayiladuturai",
    ("Tamil Nadu", "THOOTHUKKUDI"): "Thoothukudi",
    ("Tamil Nadu", "TIRUVALLUR(SC)"): "Thiruvallur",
    ("Telangana", "BHONGIR"): "Bhuvanagiri",
    ("Telangana", "CHELVELLA"): "Chevella",
    ("Telangana", "PEDDAPALLE"): "Peddapalli",
    ("Telangana", "WARANGEL(SC)"): "Warangal",
    ("Uttarakhand", "HARDWAR"): "Haridwar",
    ("Uttarakhand", "NAINITAL UDHAM SINGH NAG."): "Nainital-Udhamsingh Nagar",
    ("West Bengal", "ARAMBAG(SC)"): "Arambagh",
    ("West Bengal", "BARRACKPUR"): "Barrackpore",
    ("West Bengal", "COOCHBEHAR(SC)"): "Cooch Behar",
    ("West Bengal", "JOYNAGAR(SC)"): "Jaynagar",
    # Delimitation changes (2023/2024): these constituencies were renamed/split
    ("Assam", "Darrang-Udalguri"): "Mangaldoi",  # roughly same area
    ("Assam", "Diphu (ST)"): "Autonomous District",  # similar coverage
}


def load_dataset():
    pairs = defaultdict(lambda: {"count": 0})
    with open(RAW_CSV, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            state = (row.get("State") or "").strip()
            constituency = (row.get("Constituency") or "").strip()
            if state and constituency:
                pairs[(state, constituency)]["count"] += 1
    return dict(pairs)


def norm_state(s):
    s = str(s).strip()
    mapping = {
        "ORISSA": "Odisha", "Orissa": "Odisha",
        "UTTARANCHAL": "Uttarakhand",
        "PONDICHERRY": "Puducherry",
        "CHATTISGARH": "Chhattisgarh",
        "NCT OF DELHI": "Delhi",
        "ANDAMAN AND NICOBAR ISLANDS": "Andaman & Nicobar",
        "JAMMU AND KASHMIR": "Jammu & Kashmir",
    }
    upper = s.upper()
    for k, v in mapping.items():
        if upper == k.upper():
            return v
    return s


def norm_constituency(name):
    if not name:
        return ""
    s = str(name).strip()
    s = re.sub(r'\s*\(SC\)\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*\(ST\)\s*', '', s, flags=re.IGNORECASE)
    s = s.upper()
    s = s.replace('&', 'AND')
    s = s.replace('-', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def create_centroid_polygon(lat, lon, size_km=25):
    lat_deg = size_km / 111.0
    lon_deg = size_km / (111.0 * abs(math.cos(math.radians(lat))))
    return [[
        [lon - lon_deg, lat - lat_deg],
        [lon + lon_deg, lat - lat_deg],
        [lon + lon_deg, lat + lat_deg],
        [lon - lon_deg, lat + lat_deg],
        [lon - lon_deg, lat - lat_deg],
    ]]


def main():
    dataset = load_dataset()
    with open(RAW_GEOJSON, "r", encoding="utf-8") as f:
        geojson = json.load(f)
    coord_cache = {}
    if COORD_CACHE.exists():
        with open(COORD_CACHE, "r", encoding="utf-8") as f:
            coord_cache = json.load(f)

    # Build GeoJSON lookup by (state, normalized_name) and by state->name mapping
    geo_by_state_name = {}
    geo_state_pc = {}
    for feat in geojson["features"]:
        p = feat["properties"]
        st = p.get("st_name", "")
        pc = p.get("pc_name", "")
        ns = norm_state(st)
        nc = norm_constituency(pc)
        geo_state_pc[(ns, nc)] = feat
        # Also store by (state, exact pc_name) for alias matching
        if ns not in geo_by_state_name:
            geo_by_state_name[ns] = {}
        geo_by_state_name[ns][pc] = feat
        geo_by_state_name[ns][pc.upper()] = feat
        geo_by_state_name[ns][nc] = feat

    exact_match = []
    alias_match = []
    normalized_match = []
    centroid_fallback = []
    unmatched = []
    matched_features = []

    for (state, constituency), info in sorted(dataset.items()):
        ns = norm_state(state)
        nc = norm_constituency(constituency)

        # 1. Direct exact match
        if (ns, nc) in geo_state_pc:
            feat = dict(geo_state_pc[(ns, nc)])
            feat["properties"] = dict(feat["properties"])
            feat["properties"]["dataset_state"] = state
            feat["properties"]["dataset_constituency"] = constituency
            feat["properties"]["dataset_works"] = info["count"]
            feat["properties"]["match_type"] = "exact"
            matched_features.append(feat)
            exact_match.append({"state": state, "constituency": constituency, "works": info["count"]})
            continue

        # 2. Alias match
        alias_pc = CONSTITUENCY_ALIASES.get((state, constituency))
        if alias_pc and ns in geo_by_state_name:
            # Find feature by alias name
            found_feat = None
            for key in [alias_pc, alias_pc.upper(), norm_constituency(alias_pc)]:
                if key in geo_by_state_name[ns]:
                    found_feat = geo_by_state_name[ns][key]
                    break
            if found_feat:
                feat = dict(found_feat)
                feat["properties"] = dict(feat["properties"])
                feat["properties"]["dataset_state"] = state
                feat["properties"]["dataset_constituency"] = constituency
                feat["properties"]["dataset_works"] = info["count"]
                feat["properties"]["match_type"] = "alias"
                feat["properties"]["geojson_pc_name"] = found_feat["properties"].get("pc_name", "")
                matched_features.append(feat)
                alias_match.append({
                    "state": state, "constituency": constituency,
                    "works": info["count"], "geojson_name": found_feat["properties"].get("pc_name", ""),
                })
                continue

        # 3. Centroid fallback
        cache_key = f"{state}|{constituency}"
        cached = coord_cache.get(cache_key, {})
        lat = cached.get("latitude")
        lon = cached.get("longitude")
        loc_level = cached.get("location_level", "UNKNOWN")
        if lat and lon:
            poly = create_centroid_polygon(lat, lon)
            feat = {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": poly},
                "properties": {
                    "dataset_state": state,
                    "dataset_constituency": constituency,
                    "dataset_works": info["count"],
                    "match_type": "centroid_fallback",
                    "location_level": loc_level,
                    "centroid_lat": lat,
                    "centroid_lon": lon,
                },
            }
            matched_features.append(feat)
            centroid_fallback.append({
                "state": state, "constituency": constituency, "works": info["count"],
            })
        else:
            unmatched.append({
                "state": state, "constituency": constituency, "works": info["count"],
            })

    # Build output
    output = {
        "type": "FeatureCollection",
        "properties": {
            "source": "datameet_india_pc_2019_simplified",
            "source_note": "Third-party visualization data, not official ECI GIS. Boundaries from datameet/maps (CC-BY-SA 2.5 India).",
            "total_features": len(matched_features),
            "total_dataset_constituencies": len(dataset),
        },
        "features": matched_features,
    }

    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=1, ensure_ascii=False)

    total = len(dataset)
    total_works = sum(v["count"] for v in dataset.values())
    real_boundary = len(exact_match) + len(alias_match)
    matched_works = sum(e["works"] for e in exact_match + alias_match + centroid_fallback)

    report = {
        "summary": {
            "total_dataset_constituencies": total,
            "total_dataset_works": total_works,
            "geojson_source_features": 543,
            "exact_match": len(exact_match),
            "alias_match": len(alias_match),
            "centroid_fallback": len(centroid_fallback),
            "unmatched": len(unmatched),
            "real_boundary_features": real_boundary,
            "real_boundary_pct": round(real_boundary / total * 100, 1),
            "total_coverage_pct": round((real_boundary + len(centroid_fallback)) / total * 100, 1),
            "works_coverage_pct": round(matched_works / total_works * 100, 1),
        },
        "exact_match": exact_match,
        "alias_match": alias_match,
        "centroid_fallback": centroid_fallback,
        "unmatched": unmatched,
    }

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"{'='*60}")
    print("FINAL VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"Dataset constituencies:       {total}")
    print(f"GeoJSON source features:      543")
    print(f"Exact matches:                {len(exact_match)}")
    print(f"Alias matches:                {len(alias_match)}")
    print(f"Real boundary features:       {real_boundary} ({report['summary']['real_boundary_pct']}%)")
    print(f"Centroid fallback:            {len(centroid_fallback)}")
    print(f"Unmatched:                    {len(unmatched)}")
    print(f"Total coverage:               {report['summary']['total_coverage_pct']}%")
    print(f"Works coverage:               {report['summary']['works_coverage_pct']}%")

    if alias_match:
        print(f"\nAlias matches:")
        for e in alias_match:
            print(f"  {e['state']} / {e['constituency']} -> {e['geojson_name']}")

    if centroid_fallback:
        print(f"\nCentroid fallbacks ({len(centroid_fallback)}):")
        for e in centroid_fallback:
            print(f"  {e['state']} / {e['constituency']} ({e['works']} works)")

    if unmatched:
        print(f"\nUnmatched ({len(unmatched)}):")
        for e in unmatched:
            print(f"  {e['state']} / {e['constituency']} ({e['works']} works)")


if __name__ == "__main__":
    main()
