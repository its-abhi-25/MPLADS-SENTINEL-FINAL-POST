import urllib.request
import json

url = 'https://raw.githubusercontent.com/datameet/maps/master/parliamentary-constituencies/india_pc_2019_simplified.geojson'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode('utf-8'))

with open(r'D:\Downloads\MPLADS_Sentinel_i18n\backend\data\processed\constituencies_raw.geojson', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)

print("Downloaded", len(data["features"]), "features")
states = set()
for feat in data["features"]:
    states.add(feat["properties"].get("st_name", ""))
print("Unique states in GeoJSON:", sorted(states))
print("Total features:", len(data["features"]))
