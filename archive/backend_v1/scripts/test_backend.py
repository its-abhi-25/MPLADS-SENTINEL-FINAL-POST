import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')

from app.core.engine import get_sentinel_engine

engine = get_sentinel_engine()
result = engine.load_and_analyze()

print(f"Records analyzed: {result['records_analyzed']}")
print(f"Total records: {result['data_health']['total_records']}")
print(f"Valid records: {result['data_health']['valid_records']}")

summary = engine.get_summary()
print(f"\nPriority distribution:")
for k, v in summary['priority_distribution'].items():
    print(f"  {k}: {v}")

print(f"\nTop cost anomalies:")
for item in summary['top_signals']['cost_anomalies'][:3]:
    print(f"  {item['Record ID']}: Rs.{item['Amount']} - {item['cost_anomaly_explanation'][:60]}")

print("\nBackend test passed!")
