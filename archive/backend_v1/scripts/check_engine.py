import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')

from app.core.engine import get_sentinel_engine

engine = get_sentinel_engine()
print(f"Is loaded: {engine.is_loaded}")
print(f"Fusion engine: {engine.fusion_engine}")
print(f"DF shape: {engine.df.shape if engine.df is not None else None}")
