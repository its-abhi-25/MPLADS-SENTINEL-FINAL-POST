"""
Prepare Parliamentary Constituency GeoJSON for the Sentinel Investigation Map.

Downloads constituency boundary geometry from a public data source,
normalizes names against the MPLADS dataset, validates the match, and
saves the result to backend/data/processed/constituencies.geojson.

Usage:
    python scripts/prepare_constituency_geojson.py          # full run
    python scripts/prepare_constituency_geojson.py --validate  # validate only (no download)
"""
import csv
import json
import os
import re
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "backend" / "data" / "raw" / "mplads_ready.csv"
OUTPUT_DIR = PROJECT_ROOT / "backend" / "data" / "processed"
OUTPUT_GEOJSON = OUTPUT_DIR / "constituencies.geojson"
OUTPUT_REPORT = OUTPUT_DIR / "geojson_match_report.json"

# Public GeoJSON sources for Indian parliamentary constituencies
# These are well-known open data sources for Indian election boundaries
GEOJSON_SOURCES = [
    {
        "name": "datameet_2024",
        "url": "https://raw.githubusercontent.com/datameet/maps/master/Election/Parliamentary_Constituencies/parliamentary_constituencies.json",
        "name_key": "pc_name",
        "state_key": "st_name",
    },
    {
        "name": "ecil_simplified",
        "url": "https://raw.githubusercontent.com/subins2000/parliamentary_constituencies_geojson/master/parliamentary_constituencies.json",
        "name_key": "NAME",
        "state_key": "STATE",
    },
    {
        "name": "wikidata_simplified",
        "url": "https://raw.githubusercontent.com/nicholasjpaterno/indian-parliamentary-constituencies/main/parliamentary_constituencies.geojson",
        "name_key": "name",
        "state_key": "state",
    },
]


def load_dataset_constituencies():
    """Extract unique (State, Constituency) pairs from the MPLADS dataset."""
    pairs = defaultdict(lambda: {"count": 0})
    with open(RAW_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            state = (row.get("State") or "").strip()
            constituency = (row.get("Constituency") or "").strip()
            if state and constituency:
                key = (state, constituency)
                pairs[key]["count"] += 1
    return dict(pairs)


def normalize_name(name):
    """Normalize constituency/feature name for matching."""
    if not name:
        return ""
    s = str(name).strip().upper()
    # Remove common suffixes for matching
    s = re.sub(r'\(SC\)', '', s)
    s = re.sub(r'\(ST\)', '', s)
    s = re.sub(r'\(OBC\)', '', s)
    s = re.sub(r'\(GEN\)', '', s)
    s = re.sub(r'\(EWS\)', '', s)
    # Remove state suffixes commonly found in GeoJSON names
    s = re.sub(r'\s*-\s*MH$', '', s)
    s = re.sub(r'\s*-\s*BR$', '', s)
    s = re.sub(r'\s*-\s*UP$', '', s)
    s = re.sub(r'\s*-\s*HP$', '', s)
    s = re.sub(r'\s*-\s*MP$', '', s)
    # Normalize whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    # Normalize special characters
    s = s.replace('&', 'AND')
    s = s.replace('-', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_state(state):
    """Normalize state name for matching."""
    if not state:
        return ""
    s = str(state).strip().upper()
    # Common state name normalizations
    replacements = {
        "ORISSA": "ODISHA",
        "UTTARANCHAL": "UTTARAKHAND",
        "PONDICHERRY": "PUDUCHERRY",
        "CHATTISGARH": "CHHATTISGARH",
        "NCT OF DELHI": "DELHI",
    }
    for old, new in replacements.items():
        if old in s:
            s = new
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def create_bounding_box_polygon(centroid_lat, centroid_lon, size_km=25):
    """Create a simple square polygon around a centroid point.
    Used as fallback when no real geometry is available."""
    # Approximate degrees per km at Indian latitudes
    lat_deg = size_km / 111.0
    lon_deg = size_km / (111.0 * abs(__import__('math').cos(__import__('math').radians(centroid_lat))))
    
    return [[
        [centroid_lon - lon_deg, centroid_lat - lat_deg],
        [centroid_lon + lon_deg, centroid_lat - lat_deg],
        [centroid_lon + lon_deg, centroid_lat + lat_deg],
        [centroid_lon - lon_deg, centroid_lat + lat_deg],
        [centroid_lon - lon_deg, centroid_lat - lat_deg],
    ]]


def try_download_geojson(source):
    """Attempt to download GeoJSON from a source."""
    print(f"  Trying source: {source['name']}...")
    try:
        req = urllib.request.Request(source["url"], headers={
            "User-Agent": "MPLADS-Sentinel/2.0 (constituency-map-prep)"
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            if "features" in data and len(data["features"]) > 0:
                print(f"    -> Downloaded {len(data['features'])} features")
                return data
            else:
                print(f"    -> No features found in response")
                return None
    except Exception as e:
        print(f"    -> Failed: {e}")
        return None


def match_features(dataset_pairs, geojson_data, name_key, state_key):
    """Match dataset constituencies against GeoJSON features."""
    # Build lookup from normalized GeoJSON names
    geo_lookup = {}
    ambiguous = {}
    
    for feature in geojson_data.get("features", []):
        props = feature.get("properties", {})
        geo_name = props.get(name_key, "")
        geo_state = props.get(state_key, "")
        
        norm_s = normalize_state(geo_state)
        norm_c = normalize_name(geo_name)
        key = (norm_s, norm_c)
        
        # Build also a "plain" lookup without state (for disambiguation)
        plain_key = norm_c
        
        if plain_key not in ambiguous:
            ambiguous[plain_key] = set()
        ambiguous[plain_key].add(norm_s)
        
        geo_lookup[key] = feature
    
    # Now match dataset pairs
    results = {
        "exact_match": [],
        "normalized_match": [],
        "ambiguous_match": [],
        "unmatched": [],
        "state_fallback": [],
    }
    
    matched_features = {}
    
    for (state, constituency), info in dataset_pairs.items():
        norm_s = normalize_state(state)
        norm_c = normalize_name(constituency)
        key = (norm_s, norm_c)
        
        if key in geo_lookup:
            results["exact_match"].append({
                "state": state,
                "constituency": constituency,
                "works": info["count"],
                "geojson_key": key,
            })
            matched_features[key] = geo_lookup[key]
        elif len(ambiguous.get(norm_c, set())) == 1:
            # Only one state has this constituency name -- safe match
            for feature in geojson_data.get("features", []):
                props = feature.get("properties", {})
                if normalize_name(props.get(name_key, "")) == norm_c:
                    f_state = normalize_state(props.get(state_key, ""))
                    results["normalized_match"].append({
                        "state": state,
                        "constituency": constituency,
                        "works": info["count"],
                        "matched_state": f_state,
                    })
                    matched_features[(norm_s, norm_c)] = feature
                    break
        elif norm_c in ambiguous and len(ambiguous[norm_c]) > 1:
            results["ambiguous_match"].append({
                "state": state,
                "constituency": constituency,
                "works": info["count"],
                "possible_states": list(ambiguous[norm_c]),
            })
        else:
            results["unmatched"].append({
                "state": state,
                "constituency": constituency,
                "works": info["count"],
            })
    
    return results, matched_features


def build_output_geojson(dataset_pairs, geojson_data, matched_features, 
                          source_name, name_key, state_key, coord_cache_path):
    """Build the final GeoJSON with dataset metadata attached."""
    # Load coordinate cache for fallback
    coord_cache = {}
    if coord_cache_path.exists():
        try:
            with open(coord_cache_path, "r", encoding="utf-8") as f:
                coord_cache = json.load(f)
        except:
            pass
    
    features = []
    matched_keys = set()
    
    # Features from GeoJSON that matched dataset
    for (norm_s, norm_c), feature in matched_features.items():
        props = feature.get("properties", {})
        # Find original dataset pair
        for (state, constituency), info in dataset_pairs.items():
            if normalize_state(state) == norm_s and normalize_name(constituency) == norm_c:
                props["dataset_state"] = state
                props["dataset_constituency"] = constituency
                props["dataset_works"] = info["count"]
                props["match_type"] = "matched"
                matched_keys.add((state, constituency))
                feature["properties"] = props
                features.append(feature)
                break
    
    # For unmatched dataset pairs, use coordinate cache centroids
    for (state, constituency), info in dataset_pairs.items():
        if (state, constituency) not in matched_keys:
            cache_key = f"{state}|{constituency}"
            cached = coord_cache.get(cache_key, {})
            lat = cached.get("latitude")
            lon = cached.get("longitude")
            location_level = cached.get("location_level", "UNKNOWN")
            
            if lat and lon:
                poly = create_bounding_box_polygon(lat, lon)
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": poly,
                    },
                    "properties": {
                        "dataset_state": state,
                        "dataset_constituency": constituency,
                        "dataset_works": info["count"],
                        "match_type": "centroid_fallback",
                        "location_level": location_level,
                        "centroid_lat": lat,
                        "centroid_lon": lon,
                    },
                }
                features.append(feature)
    
    geojson = {
        "type": "FeatureCollection",
        "properties": {
            "source": source_name,
            "total_features": len(features),
            "total_dataset_constituencies": len(dataset_pairs),
            "generated_by": "MPLADS Sentinel",
        },
        "features": features,
    }
    
    return geojson


def main():
    validate_only = "--validate" in sys.argv
    
    print("=" * 60)
    print("MPLADS Sentinel - Constituency GeoJSON Preparation")
    print("=" * 60)
    
    # Step 1: Load dataset
    print("\n[1] Loading MPLADS dataset...")
    dataset_pairs = load_dataset_constituencies()
    print(f"    Found {len(dataset_pairs)} unique (State, Constituency) pairs")
    
    # Step 2: Download GeoJSON (or use existing)
    geojson_data = None
    source_info = None
    
    if OUTPUT_GEOJSON.exists() and not validate_only:
        print(f"\n[2] Found existing GeoJSON at {OUTPUT_GEOJSON}")
        with open(OUTPUT_GEOJSON, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        if "features" in geojson_data:
            print(f"    Contains {len(geojson_data['features'])} features")
        else:
            geojson_data = None
    
    if geojson_data is None and not validate_only:
        print("\n[2] Downloading constituency boundary GeoJSON...")
        for source in GEOJSON_SOURCES:
            geojson_data = try_download_geojson(source)
            if geojson_data:
                source_info = source
                break
        
        if geojson_data is None:
            print("\n    WARNING: Could not download GeoJSON from any source.")
            print("    Generating centroid-based fallback polygons...")
            geojson_data = {"type": "FeatureCollection", "features": []}
            source_info = {"name": "centroid_fallback", "name_key": "name", "state_key": "state"}
            
            # Load coordinate cache and create centroid polygons
            coord_cache = {}
            coord_path = OUTPUT_DIR / "geocode_cache.json"
            if coord_path.exists():
                with open(coord_path, "r", encoding="utf-8") as f:
                    coord_cache = json.load(f)
            
            for (state, constituency), info in dataset_pairs.items():
                cache_key = f"{state}|{constituency}"
                cached = coord_cache.get(cache_key, {})
                lat = cached.get("latitude")
                lon = cached.get("longitude")
                location_level = cached.get("location_level", "UNKNOWN")
                
                if lat and lon:
                    poly = create_bounding_box_polygon(lat, lon)
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": poly,
                        },
                        "properties": {
                            "dataset_state": state,
                            "dataset_constituency": constituency,
                            "dataset_works": info["count"],
                            "match_type": "centroid_fallback",
                            "location_level": location_level,
                            "centroid_lat": lat,
                            "centroid_lon": lon,
                        },
                    }
                    geojson_data["features"].append(feature)
            
            print(f"    Generated {len(geojson_data['features'])} centroid polygons")
    
    if validate_only and OUTPUT_GEOJSON.exists():
        print(f"\n[2] Loading existing GeoJSON from {OUTPUT_GEOJSON}")
        with open(OUTPUT_GEOJSON, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        source_info = geojson_data.get("properties", {})
    
    # Step 3: Match features
    print("\n[3] Matching dataset constituencies against GeoJSON...")
    name_key = (source_info or {}).get("name_key", "name")
    state_key = (source_info or {}).get("state_key", "state")
    
    # If GeoJSON features already have dataset_ properties (from previous run), use those
    has_dataset_props = any(
        "dataset_state" in f.get("properties", {}) 
        for f in geojson_data.get("features", [])
    )
    
    if has_dataset_props:
        print("    GeoJSON already contains dataset properties - validating directly...")
        results = {
            "exact_match": [],
            "normalized_match": [],
            "ambiguous_match": [],
            "unmatched": [],
            "state_fallback": [],
        }
        matched_count = 0
        for feature in geojson_data["features"]:
            props = feature.get("properties", {})
            ds = props.get("dataset_state", "")
            dc = props.get("dataset_constituency", "")
            mt = props.get("match_type", "")
            if (ds, dc) in dataset_pairs:
                info = dataset_pairs[(ds, dc)]
                entry = {
                    "state": ds,
                    "constituency": dc,
                    "works": info["count"],
                }
                if mt == "centroid_fallback":
                    results["state_fallback"].append(entry)
                else:
                    results["exact_match"].append(entry)
                matched_count += 1
        
        # Find unmatched
        found = {(f["properties"]["dataset_state"], f["properties"]["dataset_constituency"]) 
                 for f in geojson_data["features"] if "dataset_state" in f.get("properties", {})}
        for (state, constituency), info in dataset_pairs.items():
            if (state, constituency) not in found:
                results["unmatched"].append({
                    "state": state,
                    "constituency": constituency,
                    "works": info["count"],
                })
    else:
        results, matched_features = match_features(dataset_pairs, geojson_data, name_key, state_key)
        
        # Build output with dataset properties
        output_geojson = build_output_geojson(
            dataset_pairs, geojson_data, matched_features,
            (source_info or {}).get("name", "unknown"),
            name_key, state_key,
            OUTPUT_DIR / "geocode_cache.json"
        )
        
        # Save
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_GEOJSON, "w", encoding="utf-8") as f:
            json.dump(output_geojson, f, indent=1, ensure_ascii=False)
        print(f"    Saved to {OUTPUT_GEOJSON}")
    
    # Step 4: Validation report
    total_matched = len(results["exact_match"]) + len(results["normalized_match"])
    total_ambiguous = len(results["ambiguous_match"])
    total_unmatched = len(results["unmatched"])
    total_fallback = len(results["state_fallback"])
    total_constituencies = len(dataset_pairs)
    total_works = sum(v["count"] for v in dataset_pairs.values())
    
    matched_works = sum(e["works"] for e in results["exact_match"] + results["normalized_match"] + results["state_fallback"])
    unmatched_works = sum(e["works"] for e in results["unmatched"] + results["ambiguous_match"])
    
    report = {
        "summary": {
            "total_dataset_constituencies": total_constituencies,
            "total_dataset_works": total_works,
            "exact_match_count": len(results["exact_match"]),
            "normalized_match_count": len(results["normalized_match"]),
            "ambiguous_match_count": total_ambiguous,
            "unmatched_count": total_unmatched,
            "state_fallback_count": total_fallback,
            "constituency_match_rate": round((total_matched + total_fallback) / total_constituencies * 100, 1) if total_constituencies > 0 else 0,
            "works_match_rate": round(matched_works / total_works * 100, 1) if total_works > 0 else 0,
            "source": (source_info or {}).get("name", "centroid_fallback"),
        },
        "details": results,
    }
    
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 60}")
    print("VALIDATION REPORT")
    print(f"{'=' * 60}")
    print(f"Total dataset constituencies: {total_constituencies}")
    print(f"Exact matches:               {len(results['exact_match'])}")
    print(f"Normalized matches:          {len(results['normalized_match'])}")
    print(f"Ambiguous matches:           {total_ambiguous}")
    print(f"Unmatched:                   {total_unmatched}")
    print(f"Centroid fallback:           {total_fallback}")
    print(f"Constituency match rate:     {report['summary']['constituency_match_rate']}%")
    print(f"Works coverage rate:         {report['summary']['works_match_rate']}%")
    
    if results["unmatched"]:
        print(f"\nUnmatched constituencies:")
        for e in results["unmatched"][:20]:
            print(f"  - {e['state']} / {e['constituency']} ({e['works']} works)")
        if len(results["unmatched"]) > 20:
            print(f"  ... and {len(results['unmatched']) - 20} more")
    
    print(f"\nOutput files:")
    print(f"  GeoJSON:   {OUTPUT_GEOJSON}")
    print(f"  Report:    {OUTPUT_REPORT}")
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
