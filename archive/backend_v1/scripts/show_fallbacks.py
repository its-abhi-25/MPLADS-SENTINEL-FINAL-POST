import json
with open(r'D:\Downloads\MPLADS_Sentinel_i18n\backend\data\processed\geojson_match_report.json') as f:
    r = json.load(f)
print("Centroid fallbacks (no real boundary):")
for e in r['centroid_fallback']:
    print(f"  {e['state']} / {e['constituency']} ({e['works']} works)")
