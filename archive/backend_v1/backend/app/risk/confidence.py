"""
Confidence Score Calculator (v3.2)
Separates confidence from risk score.
Confidence reflects evidence completeness and contextual reliability.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple


class ConfidenceCalculator:
    """Computes confidence score based on evidence quality and completeness.
    
    Confidence is NOT the same as risk. It answers:
    "How strong and complete is the evidence supporting that assessment?"
    """
    
    REQUIRED_FIELDS = ['amount_numeric', 'date_parsed', 'Stage', 'MP', 'Constituency', 'State']
    
    def compute_confidence(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add confidence scores to all records."""
        df = df.copy()
        
        df['confidence_score'] = 0.0
        df['confidence_percent'] = 0.0
        df['confidence_reasons'] = ''
        
        df = self._compute_confidence_vectorized(df)
        
        df['confidence'] = 'LOW'
        df.loc[df['confidence_score'] >= 0.5, 'confidence'] = 'MEDIUM'
        df.loc[df['confidence_score'] >= 0.7, 'confidence'] = 'HIGH'
        
        return df
    
    def _compute_confidence_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute confidence using vectorized operations."""
        
        # ─── Factor 1: Field completeness (0 to 0.20) ──────────────
        required = ['amount_numeric', 'date_parsed', 'Stage', 'MP', 'Constituency', 'State']
        completeness = pd.Series(0.0, index=df.index)
        for f in required:
            if f in df.columns:
                completeness += (~df[f].isna() & (df[f].astype(str).str.strip() != '')).astype(float)
        completeness = completeness / len(required)
        df['confidence_score'] = completeness * 0.20
        
        # ─── Factor 2: Peer group size (0 to 0.20) ────────────────
        peer_size = df['peer_group_size'].fillna(0).astype(float)
        # Bounded logarithmic function - smaller contribution
        peer_size_score = np.minimum(0.20, np.log(1 + peer_size) / np.log(1 + 200) * 0.20)
        df['confidence_score'] += peer_size_score
        
        # ─── Factor 3: Peer group specificity (0 to 0.15) ──────────
        peer_level = df['peer_group_level'].fillna(0).astype(int)
        level_scores = {1: 0.15, 2: 0.12, 3: 0.08, 4: 0.04, 0: 0.0}
        specificity = peer_level.map(level_scores).fillna(0.0)
        df['confidence_score'] += specificity
        
        # ─── Factor 4: Peer dispersion (0 to 0.15) ────────────────
        peer_mad = df['peer_mad'].fillna(0).astype(float)
        peer_median = df['peer_median'].fillna(0).astype(float)
        valid_disp = (peer_median > 0) & (peer_mad > 0)
        cv_approx = np.where(valid_disp, peer_mad / peer_median, 1.0)
        dispersion_score = np.where(
            cv_approx < 0.2, 0.15,
            np.where(cv_approx < 0.5, 0.10,
                np.where(cv_approx < 1.0, 0.05, 0.0))
        )
        df['confidence_score'] += dispersion_score
        
        # ─── Factor 5: Category inference confidence (0 to 0.10) ───
        cat_confidence = df['category_confidence'].fillna(0).astype(float)
        df['confidence_score'] += cat_confidence * 0.10
        
        # ─── Factor 6: Signal reliability (0 to 0.10) ─────────────
        # Only count base independent signals (exclude pattern_score which is derived)
        base_signal_cols = [
            'cost_anomaly_score', 'description_similarity_score',
            'mp_concentration_score', 'constituency_pattern_score',
            'temporal_score', 'lifecycle_score',
        ]
        active_count = pd.Series(0, index=df.index)
        for col in base_signal_cols:
            if col in df.columns:
                active_count += (df[col].fillna(0) > 0.1).astype(int)
        # More active signals = more evidence = slightly higher confidence
        signal_score = np.minimum(0.10, active_count * 0.02)
        df['confidence_score'] += signal_score
        
        # Cap at 1.0
        df['confidence_score'] = df['confidence_score'].clip(0, 1)
        df['confidence_percent'] = (df['confidence_score'] * 100).round(1)
        
        return df
    
    def get_confidence_summary(self, score: float) -> Dict[str, Any]:
        """Get structured confidence summary for display."""
        if score >= 0.7:
            label = "HIGH"
        elif score >= 0.5:
            label = "MEDIUM"
        else:
            label = "LOW"
        
        return {
            'confidence_score': round(score, 4),
            'confidence_percent': round(score * 100, 1),
            'confidence_label': label,
        }
