import csv
from collections import Counter, defaultdict

filepath = r'C:\Users\Dell\SIH26\data\raw\MPLADS_Sentinel_FINAL-1.csv'
with open(filepath, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Amount stats by stage
print('=== AMOUNT BY STAGE ===')
for stage in ['UNSANCTIONED', 'SANCTIONED', 'COMPLETED', 'ONGOING']:
    amounts = [float(r['allocation_amount']) for r in rows if r.get('status_normalized') == stage]
    amounts.sort()
    print(f'{stage}: n={len(amounts)}, min=Rs.{amounts[0]:,.0f}, median=Rs.{amounts[len(amounts)//2]:,.0f}, max=Rs.{amounts[-1]:,.0f}')

# Check for potential lifecycle patterns
print('\n=== CONSTITUENCY-MP STAGE COMBOS ===')
mp_const_stages = defaultdict(set)
for r in rows:
    key = (r.get('mp_name', ''), r.get('constituency', ''))
    mp_const_stages[key].add(r.get('status_normalized', ''))
multi_stage = {k: v for k, v in mp_const_stages.items() if len(v) > 1}
print(f'MP+Constituency with multiple stages: {len(multi_stage)} out of {len(mp_const_stages)}')

# Check repeated similar works
print('\n=== REPEATED WORK PATTERNS ===')
mp_works = defaultdict(list)
for r in rows:
    mp_works[r.get('mp_name', '')].append(r)

high_repeat_mps = []
for mp, works in mp_works.items():
    desc_prefixes = Counter(w.get('work', '')[:30] for w in works)
    most_common_count = desc_prefixes.most_common(1)[0][1] if desc_prefixes else 0
    if most_common_count >= 5:
        high_repeat_mps.append((mp, most_common_count, len(works)))

high_repeat_mps.sort(key=lambda x: -x[1])
print(f'MPs with 5+ similar work descriptions: {len(high_repeat_mps)}')
for mp, count, total in high_repeat_mps[:5]:
    print(f'  {mp}: {count} similar out of {total} total')

# Top amounts
amounts = [(float(r.get('allocation_amount', 0)), r) for r in rows]
amounts.sort(key=lambda x: -x[0])
print('\n=== TOP 10 HIGHEST AMOUNTS ===')
for amt, r in amounts[:10]:
    desc = r.get('work', '')[:60]
    print(f'  Rs.{amt:>12,.0f} | {r.get("state", "")} | {r.get("mp_name", "")} | {r.get("constituency", "")} | {r.get("status_normalized", "")} | {desc}')

# Stage transition check: same MP+Constituency+similar desc across stages
print('\n=== POTENTIAL LIFECYCLE LINKS ===')
key_works = defaultdict(list)
for r in rows:
    key = (r.get('mp_name', ''), r.get('constituency', ''), r.get('work', '')[:40].lower())
    key_works[key].append(r)

lifecycle_candidates = {k: v for k, v in key_works.items() if len(v) > 1 and len(set(r.get('status_normalized', '') for r in v)) > 1}
print(f'Works with same MP+Constituency+similar desc across multiple stages: {len(lifecycle_candidates)}')
for k, v in list(lifecycle_candidates.items())[:3]:
    stages = [r.get('status_normalized', '') for r in v]
    print(f'  {k[0]} - {k[1]}: {stages} ({len(v)} records)')
