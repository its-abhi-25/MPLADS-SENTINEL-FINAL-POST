"""
Evidence Engine (v3.0)
Generates structured evidence for each record with full traceability.
Uses seven authoritative signals.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional


class EvidenceEngine:
    """Generates structured evidence items for each record."""
    
    SIGNAL_MAP = {
        'cost_anomaly_score': {
            'type': 'COST_ANOMALY',
            'label': 'Cost Anomaly',
            'explanation_col': 'cost_anomaly_explanation',
        },
        'description_similarity_score': {
            'type': 'DESCRIPTION_SIMILARITY',
            'label': 'Description Similarity',
            'explanation_col': 'description_similarity_explanation',
        },
        'mp_concentration_score': {
            'type': 'MP_CONCENTRATION',
            'label': 'MP Concentration',
            'explanation_col': 'mp_concentration_explanation',
        },
        'constituency_pattern_score': {
            'type': 'CONSTITUENCY_PATTERN',
            'label': 'Constituency Pattern',
            'explanation_col': 'constituency_pattern_explanation',
        },
        'temporal_score': {
            'type': 'TEMPORAL_ANOMALY',
            'label': 'Temporal Anomaly',
            'explanation_col': 'temporal_explanation',
        },
        'lifecycle_score': {
            'type': 'STAGE_CONSISTENCY',
            'label': 'Stage Consistency',
            'explanation_col': 'lifecycle_explanation',
        },
        'pattern_score': {
            'type': 'CROSS_SIGNAL_PATTERN',
            'label': 'Cross-Signal Pattern',
            'explanation_col': 'pattern_explanation',
        },
    }
    
    def get_evidence_items(self, row: pd.Series) -> List[Dict[str, Any]]:
        """Generate structured evidence items for a record."""
        items = []
        
        for score_col, config in self.SIGNAL_MAP.items():
            if score_col not in row.index:
                continue
            
            score = float(row[score_col]) if pd.notna(row[score_col]) else 0
            if score <= 0.1:
                continue
            
            explanation = str(row.get(config['explanation_col'], '')) or ''
            
            # Build detailed evidence item
            evidence = {
                'signal_type': config['type'],
                'signal_label': config['label'],
                'signal_score': round(score, 4),
                'signal_strength': self._score_to_strength(score),
                'explanation': explanation,
                'observed_value': self._get_observed_value(row, config['type']),
                'expected_value': self._get_expected_value(row, config['type']),
                'peer_group_size': int(row.get('peer_group_size', 0)),
                'peer_group_level': int(row.get('peer_group_level', 0)),
            }
            
            # Add cost anomaly specific details
            if config['type'] == 'COST_ANOMALY':
                evidence['project_amount'] = float(row.get('amount_numeric', 0)) if pd.notna(row.get('amount_numeric')) else None
                evidence['peer_median'] = float(row.get('peer_median', 0))
                evidence['deviation_ratio'] = float(row.get('deviation_ratio', 0))
                evidence['peer_mad'] = float(row.get('peer_mad', 0))
                evidence['peer_iqr'] = float(row.get('peer_iqr', 0))
                evidence['robust_distance'] = float(row.get('cost_robust_distance', 0))
                evidence['deviation_component'] = float(row.get('cost_deviation_component', 0))
                evidence['dispersion_component'] = float(row.get('cost_dispersion_component', 0))
                evidence['peer_reliability'] = float(row.get('cost_peer_reliability', 0))
            
            items.append(evidence)
        
        return sorted(items, key=lambda x: -x['signal_score'])
    
    def get_evidence_chain(self, row: pd.Series) -> List[Dict[str, Any]]:
        """Generate the full evidence chain for traceability."""
        chain = []
        
        # Step 1: Source Record
        chain.append({
            'step': 'SOURCE RECORD',
            'description': f"Record {row.get('Record ID', 'N/A')}",
            'details': {
                'record_id': str(row.get('Record ID', '')),
                'mp': str(row.get('MP', '')),
                'constituency': str(row.get('Constituency', '')),
                'state': str(row.get('State', '')),
                'description': str(row.get('Work Description', '') or ''),
                'amount': str(row.get('Amount', '')),
                'date': str(row.get('Date', '')),
                'stage': str(row.get('Stage', '')),
            }
        })
        
        # Step 2: Normalized Data
        chain.append({
            'step': 'NORMALIZED DATA',
            'description': 'Text, numeric, and date normalization applied',
            'details': {
                'amount_numeric': float(row['amount_numeric']) if pd.notna(row.get('amount_numeric')) else None,
                'date_parsed': str(row.get('date_parsed', '') or ''),
                'inferred_category': str(row.get('inferred_category', '') or ''),
                'category_confidence': float(row.get('category_confidence', 0)),
                'amount_tier': str(row.get('amount_tier', '') or ''),
            }
        })
        
        # Step 3: Context Engine
        chain.append({
            'step': 'CONTEXT ENGINE',
            'description': 'Contextual peer comparison established',
            'details': {
                'peer_group_size': int(row.get('peer_group_size', 0)),
                'peer_group_level': int(row.get('peer_group_level', 0)),
                'peer_group_key': str(row.get('peer_group_key', '')),
                'peer_median': float(row.get('peer_median', 0)),
                'peer_mad': float(row.get('peer_mad', 0)),
                'peer_iqr': float(row.get('peer_iqr', 0)),
                'deviation_ratio': float(row.get('deviation_ratio', 0)),
            }
        })
        
        # Step 4: Signal Detection
        evidence_items = self.get_evidence_items(row)
        chain.append({
            'step': 'SIGNAL DETECTION',
            'description': f"{len(evidence_items)} anomaly signals detected",
            'details': evidence_items,
        })
        
        # Step 5: Signal Fusion
        chain.append({
            'step': 'SIGNAL FUSION',
            'description': 'Weighted combination of seven independent signals',
            'details': {
                'risk_score': float(row.get('risk_score', 0)),
                'corroboration_multiplier': float(row.get('corroboration_multiplier', 1)),
                'active_signal_count': int(row.get('active_signal_count', 0)),
                'scoring_version': str(row.get('scoring_version', '')),
            }
        })
        
        # Step 6: Risk Assessment
        chain.append({
            'step': 'RISK ASSESSMENT',
            'description': f"Risk level: {row.get('risk_level', 'LOW')}",
            'details': {
                'risk_score': round(float(row.get('risk_score', 0)) * 100, 1),
                'risk_level': str(row.get('risk_level', 'LOW')),
                'confidence': round(float(row.get('confidence_score', 0)) * 100, 1),
                'confidence_level': str(row.get('confidence', 'LOW')),
                'model_version': str(row.get('model_version', '')),
                'scoring_version': str(row.get('scoring_version', '')),
            }
        })
        
        return chain
    
    def _score_to_strength(self, score: float) -> str:
        if score > 0.7:
            return 'HIGH'
        elif score > 0.3:
            return 'MEDIUM'
        return 'LOW'
    
    def _get_observed_value(self, row: pd.Series, signal_type: str) -> Any:
        if signal_type == 'COST_ANOMALY':
            return float(row.get('amount_numeric', 0)) if pd.notna(row.get('amount_numeric')) else None
        return None
    
    def _get_expected_value(self, row: pd.Series, signal_type: str) -> Any:
        if signal_type == 'COST_ANOMALY':
            return float(row.get('peer_median', 0))
        return None
