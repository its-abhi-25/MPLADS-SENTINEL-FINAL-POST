import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')
import time

print("Starting full pipeline test...")
t0 = time.time()

from app.services.data_service import DataIngestionService
svc = DataIngestionService()
svc.load_csv(r'C:\Users\Dell\SIH26\data\raw\MPLADS_Sentinel_FINAL-1.csv')
print(f"CSV loaded: {len(svc.raw_df)} rows in {time.time()-t0:.1f}s")

df = svc.normalize_dataset()
print(f"Normalized in {time.time()-t0:.1f}s")

from app.analytics.signal_detector import SignalDetector
sd = SignalDetector(df)
df = sd.detect_all_signals()
print(f"Signals done in {time.time()-t0:.1f}s")

from app.evidence.fusion_engine import EvidenceFusionEngine
fe = EvidenceFusionEngine(df)
df = fe.compute_priority()
print(f"Fusion done in {time.time()-t0:.1f}s")

pc = df['priority'].value_counts().to_dict()
print(f"\nPriority distribution: {pc}")
print(f"Total: {time.time()-t0:.1f}s")

# Test engine
from app.core.engine import get_sentinel_engine
engine = get_sentinel_engine()
result = engine.load_and_analyze()
print(f"\nEngine loaded: {result['records_analyzed']} records")

summary = engine.get_summary()
print(f"Summary total_records: {summary['total_records']}")
print(f"Summary total_amount: {summary['total_amount']}")
print(f"Summary high_priority: {summary['high_priority']}")
print(f"Summary review_recommended: {summary['review_recommended']}")
print(f"Summary normal: {summary['normal']}")
print(f"Stage distribution: {summary['stage_distribution']}")
print(f"Category distribution: {summary['category_distribution']}")
print(f"Top cost anomalies: {len(summary['top_signals']['cost_anomalies'])}")

# Test queue
queue = engine.get_investigation_queue({'page': 1, 'page_size': 5})
print(f"\nQueue total: {queue['total']}")
print(f"Queue page records: {len(queue['records'])}")
if queue['records']:
    r = queue['records'][0]
    print(f"First record: id={r['record_id']}, mp={r['mp_name']}, priority={r['priority']}, score={r['priority_score']}")

# Test record detail
if queue['records']:
    rid = queue['records'][0]['record_id']
    detail = engine.get_record_detail(rid)
    if detail:
        print(f"\nRecord detail: {detail['record_id']}")
        print(f"  Priority: {detail['priority']['priority']}")
        print(f"  Evidence items: {len(detail['evidence_items'])}")
        print(f"  Evidence chain: {len(detail['evidence_chain'])}")
        print(f"  Related records: {len(detail['related_records'])}")

# Test map data
map_data = engine.get_constituency_map_data()
print(f"\nMap constituencies with coordinates: {len(map_data)}")

map_works = engine.get_map_works(limit=10)
print(f"Map works (limit 10): {len(map_works)}")

# Test analytics
analytics = engine.get_analytics()
print(f"\nAnalytics keys: {list(analytics.keys())}")
print(f"State flags: {len(analytics.get('state_flags', {}))}")
print(f"Category flags: {len(analytics.get('category_flags', {}))}")

# Test data health
health = engine.get_data_health()
print(f"\nData health total: {health['total_records']}")
print(f"Data health source: {health['source_file']}")

# Test graph data
graph = engine.get_graph_data()
print(f"\nGraph nodes: {len(graph['nodes'])}")
print(f"Graph edges: {len(graph['edges'])}")

print(f"\n{'='*50}")
print(f"FULL PIPELINE TEST PASSED in {time.time()-t0:.1f}s")
print(f"{'='*50}")
