import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')
from app.core.engine import get_sentinel_engine
engine = get_sentinel_engine()
result = engine.load_and_analyze()
print('Engine loaded successfully:', result['records_analyzed'], 'records')

from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

tests_passed = 0
tests_total = 0

def test(name, method, url, check_fn=None):
    global tests_passed, tests_total
    tests_total += 1
    try:
        if method == 'GET':
            r = client.get(url)
        elif method == 'POST':
            r = client.post(url)
        else:
            r = client.get(url)
        status = r.status_code
        data = r.json() if status == 200 else {}
        msg = check_fn(data) if check_fn else 'OK'
        if status == 200:
            tests_passed += 1
            print(f'  PASS {name}: {msg}')
        else:
            print(f'  FAIL {name}: HTTP {status}')
    except Exception as e:
        print(f'  FAIL {name}: {e}')

test('health', 'GET', '/api/health', lambda d: f"status={d.get('status')}")
test('summary', 'GET', '/api/summary', lambda d: f"records={d.get('total_records')}, high={d.get('high_priority')}, review={d.get('review_recommended')}, low={d.get('normal')}")
test('queue', 'GET', '/api/queue?page=1&page_size=3', lambda d: f"total={d.get('total')}, page_records={len(d.get('records',[]))}")
test('map-data', 'GET', '/api/map-data', lambda d: f"constituencies={len(d)}")
test('map-works', 'GET', '/api/map-works?limit=5', lambda d: f"works={len(d)}")
test('map-filters', 'GET', '/api/map-filters', lambda d: f"states={len(d.get('states',[]))}, stages={d.get('stages')}")
test('states', 'GET', '/api/states', lambda d: f"count={len(d.get('states',[]))}")
test('stages', 'GET', '/api/stages', lambda d: f"stages={d.get('stages')}")
test('constituencies', 'GET', '/api/constituencies', lambda d: f"count={len(d.get('constituencies',[]))}")
test('mps', 'GET', '/api/mps', lambda d: f"count={len(d.get('mps',[]))}")
test('analytics', 'GET', '/api/analytics', lambda d: f"keys={list(d.keys())}")
test('data-health', 'GET', '/api/data-health', lambda d: f"source={d.get('source_file')}, total={d.get('total_records')}")
test('categories', 'GET', '/api/categories', lambda d: f"count={len(d.get('categories',[]))}")
test('graph-data', 'GET', '/api/graph-data', lambda d: f"nodes={len(d.get('nodes',[]))}, edges={len(d.get('edges',[]))}")

# Test record detail
r = client.get('/api/queue?page=1&page_size=1')
if r.status_code == 200 and r.json().get('records'):
    rid = r.json()['records'][0]['record_id']
    test(f'record/{rid}', 'GET', f'/api/record/{rid}', lambda d: f"evidence={len(d.get('evidence_items',[]))}, chain={len(d.get('evidence_chain',[]))}, related={len(d.get('related_records',[]))}")

print(f'\n{"="*50}')
print(f'API TESTS: {tests_passed}/{tests_total} PASSED')
print(f'{"="*50}')
