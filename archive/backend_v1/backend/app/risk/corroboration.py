"""
Corroboration Multiplier (v3.1)
Computes a corroboration factor based on number of independent BASE signals.
Pattern Engine (derived) is NOT counted as an independent base signal.
More independent base signals = higher confidence in the anomaly.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any


# Corroboration multipliers based on independent BASE signal count
CORROBORATION_LEVELS = {
    0: 0.0,    # No signals
    1: 0.90,   # Single signal - moderate confidence
    2: 1.00,   # Two signals - baseline
    3: 1.08,   # Three signals - slightly boosted
    4: 1.15,   # Four+ signals - strongly corroborated
}


class CorroborationEngine:
    """Computes corroboration multiplier based on independent BASE signal count."""
    
    def compute_corroboration(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add corroboration multiplier to risk scores.
        
        Uses base_signal_count (independent signals only, excluding Pattern Engine)
        to determine the corroboration multiplier.
        """
        df = df.copy()
        
        # Use base_signal_count if available, fall back to active_signal_count
        if 'base_signal_count' in df.columns:
            base_count = df['base_signal_count'].fillna(0).astype(int)
        else:
            base_count = df['active_signal_count'].fillna(0).astype(int)
        
        # Create multiplier series - cap at 4+ for max multiplier
        capped_count = base_count.clip(upper=4)
        multiplier = pd.Series(1.0, index=df.index)
        for count, mult in CORROBORATION_LEVELS.items():
            multiplier[capped_count == count] = mult
        
        df['corroboration_multiplier'] = multiplier
        df['corroboration_base_count'] = base_count
        df['risk_score_raw'] = df['risk_score'].copy()
        df['risk_score'] = (df['risk_score'] * multiplier).clip(0, 1)
        
        return df
    
    def get_corroboration_info(self, base_count: int) -> Dict[str, Any]:
        """Get corroboration details for display."""
        capped = min(base_count, 4)
        multiplier = CORROBORATION_LEVELS.get(capped, 0.0)
        
        if base_count == 0:
            description = "No independent base signals detected"
        elif base_count == 1:
            description = "Single independent signal - moderate investigation priority"
        elif base_count == 2:
            description = "Two independent base signals corroborate the finding"
        elif base_count == 3:
            description = "Three independent base signals strengthen the finding"
        else:
            description = f"{base_count} independent base signals strongly corroborate"
        
        return {
            'active_count': base_count,
            'multiplier': multiplier,
            'description': description,
        }
