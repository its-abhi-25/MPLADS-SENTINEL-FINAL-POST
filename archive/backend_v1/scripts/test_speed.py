import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')
import time

print("Starting...", flush=True)
t0 = time.time()

from app.services.data_service import DataIngestionService
svc = DataIngestionService()
print(f"Loading CSV...", flush=True)
svc.load_csv(r'C:\Users\Dell\SIH26\data\raw\MPLADS_Sentinel_FINAL-1.csv')
print(f"CSV loaded: {len(svc.raw_df)} rows in {time.time()-t0:.1f}s", flush=True)

print("Normalizing...", flush=True)
df = svc.normalize_dataset()
print(f"Normalized in {time.time()-t0:.1f}s", flush=True)

print("Cost anomaly...", flush=True)
from app.analytics.signal_detector import SignalDetector
sd = SignalDetector(df)

# Test each signal separately
df2 = sd._detect_cost_anomalies(df.copy())
print(f"Cost done in {time.time()-t0:.1f}s", flush=True)

df2 = sd._detect_duplicates_fast(df2)
print(f"Duplicates done in {time.time()-t0:.1f}s", flush=True)

df2 = sd._detect_concentration_fast(df2)
print(f"Concentration done in {time.time()-t0:.1f}s", flush=True)

df2 = sd._detect_temporal_fast(df2)
print(f"Temporal done in {time.time()-t0:.1f}s", flush=True)

df2 = sd._detect_lifecycle(df2)
print(f"Lifecycle done in {time.time()-t0:.1f}s", flush=True)

df2 = sd._detect_data_quality(df2)
print(f"Data quality done in {time.time()-t0:.1f}s", flush=True)

print("Evidence fusion...", flush=True)
from app.evidence.fusion_engine import EvidenceFusionEngine
fe = EvidenceFusionEngine(df2)
df3 = fe.compute_priority()
print(f"Fusion done in {time.time()-t0:.1f}s", flush=True)

pc = df3['priority'].value_counts().to_dict()
print(f"Priority: {pc}", flush=True)
print(f"Total: {time.time()-t0:.1f}s", flush=True)
