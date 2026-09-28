import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')
from app.core.engine import get_sentinel_engine
import pandas as pd

engine = get_sentinel_engine()
engine.load_and_analyze()

# Check coordinate loading
print("=== COORDINATE CACHE ===")
coord_df = pd.read_csv(r'C:\Users\Dell\SIH26\data\processed\location_coordinates.csv', dtype=str)
print(f"Total cached constituencies: {len(coord_df)}")
print(f"Unique states in cache: {coord_df['State'].nunique()}")
print(f"Sample states: {coord_df['State'].head(5).tolist()}")
print(f"Sample constituencies: {coord_df['Constituency'].head(5).tolist()}")

# Check dataset
print("\n=== DATASET ===")
df = engine.df
print(f"Total records: {len(df)}")
print(f"Unique constituencies: {df['Constituency'].nunique()}")
print(f"Unique states: {df['State'].nunique()}")
print(f"Sample states: {df['State'].head(5).tolist()}")
print(f"Sample constituencies: {df['Constituency'].head(5).tolist()}")

# Check coordinate matching
print("\n=== COORDINATE MATCHING ===")
cache_keys = set()
for _, row in coord_df.iterrows():
    state = (row.get("State") or "").strip()
    constituency = (row.get("Constituency") or "").strip()
    if state and constituency:
        cache_keys.add((state, constituency))

dataset_keys = set()
for _, row in df.iterrows():
    state = str(row.get("State", "")).strip()
    constituency = str(row.get("Constituency", "")).strip()
    if state and constituency and state != 'nan' and constituency != 'nan':
        dataset_keys.add((state, constituency))

matched = dataset_keys & cache_keys
unmatched = dataset_keys - cache_keys

print(f"Dataset unique (State, Constituency) pairs: {len(dataset_keys)}")
print(f"Cache unique (State, Constituency) pairs: {len(cache_keys)}")
print(f"Matched pairs: {len(matched)}")
print(f"Unmatched pairs: {len(unmatched)}")
if unmatched:
    print(f"Sample unmatched: {list(unmatched)[:10]}")

# Check how many records have matched coordinates
records_with_coords = 0
records_without_coords = 0
for _, row in df.iterrows():
    state = str(row.get("State", "")).strip()
    constituency = str(row.get("Constituency", "")).strip()
    if (state, constituency) in cache_keys:
        records_with_coords += 1
    else:
        records_without_coords += 1

print(f"\nRecords with matching coordinates: {records_with_coords}")
print(f"Records without matching coordinates: {records_without_coords}")

# Test map works with different limits
print("\n=== MAP WORKS AT DIFFERENT LIMITS ===")
for limit in [5, 100, 400, 500, 1000, 5000, 60359]:
    works = engine.get_map_works(limit=limit)
    print(f"limit={limit}: {len(works)} works returned")

# Check map data
map_data = engine.get_constituency_map_data()
print(f"\nMap data (constituencies with coords): {len(map_data)}")

# Check how many of top-400 by priority have coords
print("\n=== TOP 400 BY PRIORITY ===")
priority_order = {'HIGH_PRIORITY_REVIEW': 0, 'REVIEW_RECOMMENDED': 1, 'LOW': 2}
df_sorted = df.copy()
df_sorted['_priority_rank'] = df_sorted['priority'].map(priority_order).fillna(3)
df_sorted = df_sorted.sort_values(['_priority_rank', 'priority_score'], ascending=[True, False])
top400 = df_sorted.head(400)

has_coords = 0
no_coords = 0
for _, row in top400.iterrows():
    state = str(row.get("State", "")).strip()
    constituency = str(row.get("Constituency", "")).strip()
    if (state, constituency) in cache_keys:
        has_coords += 1
    else:
        no_coords += 1

print(f"Top 400 records: {has_coords} with coords, {no_coords} without coords")
