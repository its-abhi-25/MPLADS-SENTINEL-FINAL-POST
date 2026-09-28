"""
Signal Fusion Engine (v3.1)
Combines seven signals into a unified risk score
using weighted combination with fixed total weight denominator.
Pattern Engine (derived) is tracked separately from base independent signals.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional


# Seven signal definitions with authoritative weights (must sum to 1.0)
SIGNAL_WEIGHTS = {
    'cost_anomaly_score': {'weight': 0.25, 'name': 'COST_ANOMALY', 'label': 'Cost Anomaly'},
    'description_similarity_score': {'weight': 0.20, 'name': 'DESCRIPTION_SIMILARITY', 'label': 'Description Similarity'},
    'mp_concentration_score': {'weight': 0.10, 'name': 'MP_CONCENTRATION', 'label': 'MP Concentration'},
    'constituency_pattern_score': {'weight': 0.10, 'name': 'CONSTITUENCY_PATTERN', 'label': 'Constituency Pattern'},
    'temporal_score': {'weight': 0.10, 'name': 'TEMPORAL_ANOMALY', 'label': 'Temporal Anomaly'},
    'lifecycle_score': {'weight': 0.10, 'name': 'STAGE_CONSISTENCY', 'label': 'Stage Consistency'},
    'pattern_score': {'weight': 0.15, 'name': 'CROSS_SIGNAL_PATTERN', 'label': 'Cross-Signal Pattern'},
}

# Base independent signals (Pattern Engine is derived, not independent)
BASE_SIGNAL_KEYS = {
    'cost_anomaly_score', 'description_similarity_score',
    'mp_concentration_score', 'constituency_pattern_score',
    'temporal_score', 'lifecycle_score',
}

# Minimum score threshold for a signal to be considered "active"
ACTIVE_THRESHOLD = 0.1

# Fixed total weight (all signals sum to 1.0)
FIXED_TOTAL_WEIGHT = 1.0


class SignalFusionEngine:
    """Combines seven signals into a unified risk score with fixed weight denominator."""
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.signal_weights = SIGNAL_WEIGHTS.copy()
        if weights:
            for k, v in weights.items():
                if k in self.signal_weights:
                    self.signal_weights[k]['weight'] = v
    
    def compute_risk_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute risk scores for all records using fixed total weight denominator.
        
        Uses FIXED_TOTAL_WEIGHT (1.0) as denominator so that inactive signals
        do not inflate the score of remaining active signals. A single active
        Cost signal at 0.95 with weight 0.25 produces 0.95 * 0.25 / 1.0 = 0.2375,
        not 0.95.
        """
        df = df.copy()
        
        # Initialize columns
        df['risk_score'] = 0.0
        df['active_signal_count'] = 0
        df['base_signal_count'] = 0
        df['active_signals_list'] = ''
        df['weighted_sum'] = 0.0
        df['total_weight'] = FIXED_TOTAL_WEIGHT
        
        # Track which signals are available for each record
        for signal_col, config in self.signal_weights.items():
            if signal_col not in df.columns:
                continue
            
            scores = pd.to_numeric(df[signal_col], errors='coerce').fillna(0)
            weight = config['weight']
            active = scores > ACTIVE_THRESHOLD
            
            df['risk_score'] = df['risk_score'] + scores * weight * active.astype(float)
            df['active_signal_count'] = df['active_signal_count'] + active.astype(int)
            
            # Count base independent signals only (exclude Pattern Engine)
            if signal_col in BASE_SIGNAL_KEYS:
                df['base_signal_count'] = df['base_signal_count'] + active.astype(int)
            
            # Build active signals list
            signal_name = config['name']
            df['active_signals_list'] = df['active_signals_list'].where(
                ~active, 
                df['active_signals_list'] + ', ' + signal_name
            )
        
        df['active_signals_list'] = df['active_signals_list'].str.lstrip(', ')
        
        # Normalize by FIXED total weight (1.0), NOT by sum of active weights.
        # This prevents a single active signal from dominating the score.
        df['risk_score'] = df['risk_score'] / FIXED_TOTAL_WEIGHT
        
        # Cap at 1.0
        df['risk_score'] = df['risk_score'].clip(0, 1)
        
        return df
    
    def get_active_signals(self, row: pd.Series) -> List[Dict[str, Any]]:
        """Get list of active signals for a record."""
        signals = []
        for signal_col, config in self.signal_weights.items():
            if signal_col in row.index:
                score = float(row[signal_col]) if pd.notna(row[signal_col]) else 0
                if score > ACTIVE_THRESHOLD:
                    signals.append({
                        'signal_type': config['name'],
                        'signal_label': config['label'],
                        'score': round(score, 4),
                        'weight': config['weight'],
                        'weighted_contribution': round(score * config['weight'], 4),
                        'is_base': signal_col in BASE_SIGNAL_KEYS,
                    })
        return sorted(signals, key=lambda x: -x['score'])
