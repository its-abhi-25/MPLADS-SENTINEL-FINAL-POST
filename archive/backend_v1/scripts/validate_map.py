import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')
from app.core.engine import get_sentinel_engine
import pandas as pd
import re

def norm(s):
    return re.sub(r'\s+\(', '(', str(s)).strip()

engine = get_sentinel_engine()
engine.load_and_analyze()

# Reload coordinates from updated cache
engine._load_coordinates()

# Check coordinate loading
print("=== UPDATED COORDINATE CACHE ===")
print(f"Total loaded coordinate pairs: {len(engine.coordinates)}")

# Check dataset
df = engine.df
print(f"\n=== DATASET ===")
print(f"Total records: {len(df)}")
print(f"Unique constituencies: {df['Constituency'].nunique()}")

# Check matching using normalized keys
dataset_keys = set()
for _, row in df.iterrows():
    state = str(row.get("State", "")).strip()
    constituency = str(row.get("Constituency", "")).strip()
    if state and constituency and state != 'nan' and constituency != 'nan':
        dataset_keys.add((state, norm(constituency)))

cache_keys = set(engine.coordinates.keys())

matched = dataset_keys & cache_keys
unmatched = dataset_keys - cache_keys

print(f"\n=== COVERAGE ===")
print(f"Dataset unique (State, Constituency) pairs: {len(dataset_keys)}")
print(f"Matched with coordinates: {len(matched)}")
print(f"Unmatched: {len(unmatched)}")
print(f"Coverage: {len(matched)/len(dataset_keys)*100:.1f}%")

if unmatched:
    print(f"\nStill unmatched:")
    for state, const in sorted(unmatched):
        # Check if it's a Rajya Sabha entry
        is_rs = 'rajya sabha' in const.lower() or 'nominated' in const.lower()
        tag = " [RAJYA SABHA - not geocodable]" if is_rs else ""
        print(f"  - {state} / {const}{tag}")

# Separate Rajya Sabha from real constituencies
real_unmatched = [(s, c) for s, c in unmatched if 'rajya sabha' not in c.lower() and 'nominated' not in c.lower()]
rs_unmatched = [(s, c) for s, c in unmatched if 'rajya sabha' in c.lower() or 'nominated' in c.lower()]
print(f"\nReal Lok Sabha constituencies still unmatched: {len(real_unmatched)}")
print(f"Rajya Sabha entries (not geocodable): {len(rs_unmatched)}")

# Count records with coordinates
records_with = 0
records_without = 0
for _, row in df.iterrows():
    state = str(row.get("State", "")).strip()
    constituency = str(row.get("Constituency", "")).strip()
    if (state, norm(constituency)) in cache_keys:
        records_with += 1
    else:
        records_without += 1

print(f"\nRecords with coordinates: {records_with}")
print(f"Records without coordinates: {records_without}")
print(f"Record coverage: {records_with/len(df)*100:.1f}%")

# Test map data
map_data = engine.get_constituency_map_data()
print(f"\n=== MAP DATA ===")
print(f"Constituencies with coords (map-data): {len(map_data)}")

# Test map works at different limits
print(f"\n=== MAP WORKS ===")
for limit in [100, 400, 1000, 5000]:
    works = engine.get_map_works(limit=limit)
    print(f"limit={limit}: {len(works)} works returned")

print(f"\n=== VALIDATION COMPLETE ===")
