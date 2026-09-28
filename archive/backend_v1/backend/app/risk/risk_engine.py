"""
Risk Engine (v3.1)
Main orchestrator that combines all risk components into final risk assessment.
Uses seven signals, proper thresholds, and corroboration based on independent BASE signals only.
Pattern Engine (derived) is NOT counted as an independent base signal.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from .signal_fusion import SignalFusionEngine
from .corroboration import CorroborationEngine
from .confidence import ConfidenceCalculator
from ..core.config import RISK_THRESHOLDS, MIN_CRITICAL_SIGNALS, MODEL_VERSION, SCORING_VERSION


class RiskEngine:
    """Orchestrates the complete risk scoring pipeline."""
    
    def __init__(self):
        self.signal_fusion = SignalFusionEngine()
        self.corroboration = CorroborationEngine()
        self.confidence_calc = ConfidenceCalculator()
    
    def compute_all_risks(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run the complete risk pipeline on the dataframe."""
        df = df.copy()
        
        # Step 1: Fuse signals into raw risk score (fixed denominator)
        df = self.signal_fusion.compute_risk_scores(df)
        
        # Step 2: Apply corroboration multiplier (uses base_signal_count)
        df = self.corroboration.compute_corroboration(df)
        
        # Step 3: Compute confidence (separate from risk)
        df = self.confidence_calc.compute_confidence(df)
        
        # Step 4: Assign risk levels using authoritative thresholds
        df['risk_level'] = 'LOW'
        df.loc[df['risk_score'] >= RISK_THRESHOLDS['MODERATE'], 'risk_level'] = 'MODERATE'
        df.loc[df['risk_score'] >= RISK_THRESHOLDS['HIGH'], 'risk_level'] = 'HIGH'
        df.loc[df['risk_score'] >= RISK_THRESHOLDS['CRITICAL'], 'risk_level'] = 'CRITICAL'
        
        # Step 5: CRITICAL must require meaningful corroboration from BASE signals
        # Pattern Engine is derived, not independent - do not count it
        critical_mask = df['risk_level'] == 'CRITICAL'
        base_count = df.get('base_signal_count', df['active_signal_count']).fillna(0).astype(int)
        insufficient_corroboration = base_count < MIN_CRITICAL_SIGNALS
        df.loc[critical_mask & insufficient_corroboration, 'risk_level'] = 'HIGH'
        
        # Step 6: Evidence count (base independent signals for corroboration)
        df['evidence_count'] = base_count
        
        # Step 7: Evidence summary (vectorized)
        df['evidence_summary'] = self._build_evidence_summaries_vectorized(df)
        
        # Step 8: Model metadata
        df['model_version'] = MODEL_VERSION
        df['scoring_version'] = SCORING_VERSION
        df['generated_at'] = datetime.now().isoformat()
        
        return df
    
    def compute_single_risk(self, row: pd.Series) -> Dict[str, Any]:
        """Compute risk for a single record and return structured result."""
        # Get active signals
        active_signals = self.signal_fusion.get_active_signals(row)
        
        # Count base independent signals (exclude Pattern Engine)
        base_count = sum(1 for s in active_signals if s.get('is_base', False))
        
        # Corroboration uses base signal count
        corroboration = self.corroboration.get_corroboration_info(base_count)
        
        # Risk score (already 0-1, convert to 0-100 for display)
        risk_score = float(row.get('risk_score', 0))
        risk_level = row.get('risk_level', 'LOW')
        confidence = float(row.get('confidence_score', 0))
        confidence_level = row.get('confidence', 'LOW')
        confidence_percent = float(row.get('confidence_percent', confidence * 100))
        
        # Peer group info
        peer_group_size = int(row.get('peer_group_size', 0))
        peer_group_level = int(row.get('peer_group_level', 0))
        
        # Cost anomaly details
        cost_deviation = float(row.get('cost_deviation_component', 0))
        cost_dispersion = float(row.get('cost_dispersion_component', 0))
        cost_reliability = float(row.get('cost_peer_reliability', 0))
        cost_robust_distance = float(row.get('cost_robust_distance', 0))
        
        return {
            'project_id': str(row.get('Record ID', '')),
            'risk_score': round(risk_score * 100, 1),
            'risk_level': risk_level,
            'confidence': round(confidence, 4),
            'confidence_percent': round(confidence_percent, 1),
            'confidence_level': confidence_level,
            'active_signals': active_signals,
            'active_signal_count': len(active_signals),
            'base_signal_count': base_count,
            'pattern_score': float(row.get('pattern_score', 0)) if pd.notna(row.get('pattern_score')) else 0,
            'corroboration_factor': corroboration['multiplier'],
            'peer_group_size': peer_group_size,
            'peer_group_level': peer_group_level,
            'context': {
                'peer_group_size': peer_group_size,
                'peer_group_level': peer_group_level,
                'peer_median': float(row.get('peer_median', 0)),
                'peer_mad': float(row.get('peer_mad', 0)),
                'peer_iqr': float(row.get('peer_iqr', 0)),
                'deviation_ratio': float(row.get('deviation_ratio', 0)),
                'cost_deviation_component': cost_deviation,
                'cost_dispersion_component': cost_dispersion,
                'cost_peer_reliability': cost_reliability,
                'cost_robust_distance': cost_robust_distance,
            },
            'corroboration': corroboration,
            'model_version': MODEL_VERSION,
            'scoring_version': SCORING_VERSION,
            'generated_at': datetime.now().isoformat(),
        }
    
    def _build_evidence_summary(self, row: pd.Series) -> str:
        """Build human-readable evidence summary."""
        parts = []
        
        if pd.notna(row.get('cost_anomaly_score')) and row['cost_anomaly_score'] > 0.1:
            parts.append(f"Cost anomaly: {row.get('cost_anomaly_explanation', '')}")
        
        if pd.notna(row.get('description_similarity_score')) and row['description_similarity_score'] > 0.1:
            parts.append(f"Description similarity: {row.get('description_similarity_explanation', '')}")
        
        if pd.notna(row.get('mp_concentration_score')) and row['mp_concentration_score'] > 0.1:
            parts.append(f"MP concentration: {row.get('mp_concentration_explanation', '')}")
        
        if pd.notna(row.get('constituency_pattern_score')) and row['constituency_pattern_score'] > 0.1:
            parts.append(f"Constituency pattern: {row.get('constituency_pattern_explanation', '')}")
        
        if pd.notna(row.get('temporal_score')) and row['temporal_score'] > 0.1:
            parts.append(f"Temporal: {row.get('temporal_explanation', '')}")
        
        if pd.notna(row.get('lifecycle_score')) and row['lifecycle_score'] > 0.1:
            parts.append(f"Stage consistency: {row.get('lifecycle_explanation', '')}")
        
        if pd.notna(row.get('pattern_score')) and row['pattern_score'] > 0.1:
            parts.append(f"Cross-signal pattern: {row.get('pattern_explanation', '')}")
        
        return ' | '.join(parts) if parts else 'No anomalous patterns detected'
    
    @staticmethod
    def _build_evidence_summaries_vectorized(df: pd.DataFrame) -> pd.Series:
        """Build evidence summaries using vectorized string operations."""
        parts = []
        
        signal_cols = [
            ('cost_anomaly_score', 'cost_anomaly_explanation', 'Cost anomaly'),
            ('description_similarity_score', 'description_similarity_explanation', 'Description similarity'),
            ('mp_concentration_score', 'mp_concentration_explanation', 'MP concentration'),
            ('constituency_pattern_score', 'constituency_pattern_explanation', 'Constituency pattern'),
            ('temporal_score', 'temporal_explanation', 'Temporal'),
            ('lifecycle_score', 'lifecycle_explanation', 'Stage consistency'),
            ('pattern_score', 'pattern_explanation', 'Cross-signal pattern'),
        ]
        
        result = pd.Series('No anomalous patterns detected', index=df.index)
        
        for score_col, expl_col, label in signal_cols:
            if score_col in df.columns and expl_col in df.columns:
                active = (df[score_col].fillna(0) > 0.1) & (df[expl_col].fillna('') != '')
                if active.any():
                    new_part = label + ': ' + df[expl_col].fillna('')
                    # Use pandas string methods
                    result = result.copy()
                    has_existing = (result != 'No anomalous patterns_detected')
                    combined = result + ' | ' + new_part
                    result = combined.where(active & has_existing, result.where(~active, new_part))
        
        return result
