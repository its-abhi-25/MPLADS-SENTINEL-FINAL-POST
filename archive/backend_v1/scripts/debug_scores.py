import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')

from app.core.engine import SentinelEngine

engine = SentinelEngine()
result = engine.load_and_analyze()

df = engine.df

# Debug signal distributions
print("=== Signal Score Distributions ===")
for col in ['cost_anomaly_score', 'duplicate_score', 'concentration_score', 'temporal_score', 'missing_score', 'malformed_score']:
    vals = df[col]
    nonzero = (vals > 0.1).sum()
    high = (vals > 0.7).sum()
    med = ((vals > 0.3) & (vals <= 0.7)).sum()
    low = ((vals > 0.1) & (vals <= 0.3)).sum()
    print(f"{col}: {nonzero} >0.1 (H:{high} M:{med} L:{low})")

print(f"\n=== Priority Score Distribution ===")
print(f"Mean: {df['priority_score'].mean():.4f}")
print(f"Median: {df['priority_score'].median():.4f}")
print(f"Max: {df['priority_score'].max():.4f}")
print(f"Min: {df['priority_score'].min():.4f}")

# Show distribution
for threshold in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    count = (df['priority_score'] >= threshold).sum()
    print(f"  >= {threshold}: {count} records")
