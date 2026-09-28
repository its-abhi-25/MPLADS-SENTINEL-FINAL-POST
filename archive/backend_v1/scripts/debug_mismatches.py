"""
Investigate why 36 constituencies don't match.
Show both GeoJSON and dataset names for each state.
"""
import json
import re
from collections import defaultdict

GEOJSON_PATH = r'D:\Downloads\MPLADS_Sentinel_i18n\backend\data\processed\constituencies_raw.geojson'
REPORT_PATH = r'D:\Downloads\MPLADS_Sentinel_i18n\backend\data\processed\geojson_match_report.json'

with open(GEOJSON_PATH, encoding='utf-8') as f:
    geojson = json.load(f)
with open(REPORT_PATH, encoding='utf-8') as f:
    report = json.load(f)

# Get fallback states
fallback_states = set(e['state'] for e in report['centroid_fallback'])

# Group GeoJSON by state
geo_by_state = defaultdict(list)
for feat in geojson['features']:
    p = feat['properties']
    st = p.get('st_name', '')
    pc = p.get('pc_name', '')
    geo_by_state[st].append(pc)

# Show GeoJSON names for each fallback state
print("GEOJSON names vs Dataset names for fallback states:")
print("=" * 80)
for state in sorted(fallback_states):
    fallback_cons = [e['constituency'] for e in report['centroid_fallback'] if e['state'] == state]
    # Find GeoJSON state name
    geo_state_matches = [gs for gs in geo_by_state if gs.upper().replace('&', 'AND').replace(' ', '') in state.upper().replace('&', 'AND').replace(' ', '') or state.upper().replace('&', 'AND').replace(' ', '') in gs.upper().replace('&', 'AND').replace(' ', '')]
    print(f"\n{state}:")
    print(f"  Dataset fallbacks: {fallback_cons}")
    for gs in geo_state_matches:
        print(f"  GeoJSON state '{gs}' has: {sorted(geo_by_state[gs])}")
