import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')

from app.core.engine import SentinelEngine

engine = SentinelEngine()
engine.load_and_analyze()

detail = engine.get_record_detail("1")

if detail:
    print(f"Record: {detail['record_id']}")
    print(f"Priority: {detail['priority']['priority']}")
    print(f"Evidence items: {len(detail['evidence_items'])}")
    for item in detail['evidence_items']:
        print(f"  {item['signal_type']}: {item['explanation'][:80]}")
    print(f"\nRelated records: {len(detail['related_records'])}")
else:
    print("Record not found")
