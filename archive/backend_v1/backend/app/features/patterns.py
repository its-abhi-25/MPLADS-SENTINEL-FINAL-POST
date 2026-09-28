"""
Cross-Signal Pattern Engine (v3.0, Optimized)
Detects combinations of independent signals that corroborate each other.
Uses seven authoritative signals.
Optimized for 64K+ records using vectorized operations.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple


class PatternEngine:
    """Detects corroborated multi-signal patterns."""
    
    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add cross-signal pattern scores and explanations."""
        df = df.copy()
        
        for col in ['pattern_score', 'pattern_explanation']:
            if col not in df.columns:
                df[col] = 0.0 if '_score' in col else ''
        
        df = self._detect_corroborated_patterns_vectorized(df)
        
        return df
    
    def _detect_corroborated_patterns_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect combinations of signals that together form stronger patterns.
        Uses vectorized operations for performance.
        """
        
        # Seven authoritative signal columns and their thresholds
        signal_cols = {
            'cost_anomaly_score': ('COST_ANOMALY', 0.3),
            'description_similarity_score': ('DESCRIPTION_SIMILARITY', 0.3),
            'mp_concentration_score': ('MP_CONCENTRATION', 0.3),
            'constituency_pattern_score': ('CONSTITUENCY_PATTERN', 0.3),
            'temporal_score': ('TEMPORAL_ANOMALY', 0.3),
            'lifecycle_score': ('STAGE_CONSISTENCY', 0.2),
        }
        
        # Vectorized: build a matrix of which signals are active
        active_matrix = {}
        for col, (name, threshold) in signal_cols.items():
            if col in df.columns:
                active_matrix[name] = (df[col].fillna(0) >= threshold).astype(int)
        
        # Count active signals per record
        active_count = sum(active_matrix.values())
        
        # Need at least 2 independent signals for a pattern
        has_pattern = active_count >= 2
        
        if not has_pattern.any():
            return df
        
        # Compute base pattern score from number of signals
        base = np.where(active_count >= 2, 0.3 + (active_count - 2) * 0.15, 0.0)
        
        # Boost for high-cost + duplicate combination
        if 'COST_ANOMALY' in active_matrix and 'DESCRIPTION_SIMILARITY' in active_matrix:
            both = (active_matrix['COST_ANOMALY'] + active_matrix['DESCRIPTION_SIMILARITY']) == 2
            base = np.where(both, base + 0.1, base)
        
        # Boost for temporal clustering
        if 'TEMPORAL_ANOMALY' in active_matrix:
            has_temporal = active_matrix['TEMPORAL_ANOMALY'] == 1
            base = np.where(has_temporal, base + 0.05, base)
        
        # Boost for concentration patterns
        if 'MP_CONCENTRATION' in active_matrix or 'CONSTITUENCY_PATTERN' in active_matrix:
            has_conc = np.zeros(len(df), dtype=bool)
            if 'MP_CONCENTRATION' in active_matrix:
                has_conc = has_conc | (active_matrix['MP_CONCENTRATION'] == 1).values
            if 'CONSTITUENCY_PATTERN' in active_matrix:
                has_conc = has_conc | (active_matrix['CONSTITUENCY_PATTERN'] == 1).values
            base = np.where(has_conc, base + 0.05, base)
        
        # Boost for stage consistency anomalies
        if 'STAGE_CONSISTENCY' in active_matrix:
            has_lifecycle = active_matrix['STAGE_CONSISTENCY'] == 1
            base = np.where(has_lifecycle, base + 0.05, base)
        
        # Cap at 1.0
        pattern_score = np.minimum(1.0, base)
        
        # Assign only to records with patterns
        df.loc[has_pattern, 'pattern_score'] = pattern_score[has_pattern]
        
        # Build explanations (vectorized string building)
        explanations = pd.Series('', index=df.index)
        for i in df[has_pattern].index:
            active = [name for name, col_active in active_matrix.items() 
                      if (col_active.iloc[i] if hasattr(col_active, 'iloc') else col_active[i])]
            count = int(active_count.iloc[i] if hasattr(active_count, 'iloc') else active_count[i])
            explanations.iloc[df.index.get_loc(i)] = (
                f"Corroborated pattern: {', '.join(active)} "
                f"({count} independent signals)"
            )
        
        df['pattern_explanation'] = explanations
        
        return df
