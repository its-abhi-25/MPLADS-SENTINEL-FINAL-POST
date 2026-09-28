import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')
import time

print("Starting...")
t0 = time.time()

from app.services.data_service import DataIngestionService
svc = DataIngestionService()
print(f"Loading CSV... {time.time()-t0:.1f}s")
svc.load_csv(r'C:\Users\Dell\SIH26\data\raw\MPLADS_Sentinel_FINAL-1.csv')
print(f"CSV loaded: {len(svc.raw_df)} rows {time.time()-t0:.1f}s")

print("Normalizing...")
df = svc.normalize_dataset()
print(f"Normalized: {time.time()-t0:.1f}s")

print("Signal detection...")
from app.analytics.signal_detector import SignalDetector
sd = SignalDetector(df)
df = sd.detect_all_signals()
print(f"Signals done: {time.time()-t0:.1f}s")

print("Evidence fusion...")
from app.evidence.fusion_engine import EvidenceFusionEngine
fe = EvidenceFusionEngine(df)
df = fe.compute_priority()
print(f"Fusion done: {time.time()-t0:.1f}s")

priority_counts = df['priority'].value_counts().to_dict()
print(f"\nPriority: {priority_counts}")
print(f"Total: {time.time()-t0:.1f}s")
