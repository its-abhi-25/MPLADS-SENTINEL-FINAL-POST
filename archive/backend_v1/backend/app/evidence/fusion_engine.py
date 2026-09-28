"""
Evidence Fusion Engine
Combines multiple signals into investigation priorities with explanations.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from ..core.config import SIGNAL_WEIGHTS, PRIORITY_THRESHOLDS


def _to_native(val):
    if pd.isna(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    elif isinstance(val, (np.floating,)):
        f = float(val)
        if f != f or f == float('inf') or f == float('-inf'):
            return None
        return f
    elif isinstance(val, np.bool_):
        return bool(val)
    elif isinstance(val, np.ndarray):
        return val.tolist()
    return val


class EvidenceFusionEngine:
    def __init__(self, df: pd.DataFrame, weights: Optional[Dict[str, float]] = None):
        self.df = df
        self.weights = weights or SIGNAL_WEIGHTS
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def compute_priority(self) -> pd.DataFrame:
        df = self.df.copy()

        signal_cols = [
            ('cost_anomaly_score', 'COST_ANOMALY'),
            ('duplicate_score', 'DUPLICATE'),
            ('constituency_concentration_score', 'CONSTITUENCY_CONCENTRATION'),
            ('mp_concentration_score', 'MP_CONCENTRATION'),
            ('temporal_score', 'TEMPORAL'),
            ('lifecycle_score', 'LIFECYCLE'),
            ('data_quality_score', 'DATA_QUALITY'),
        ]

        weighted_sum = pd.Series(0.0, index=df.index)
        total_weight = pd.Series(0.0, index=df.index)
        evidence_count = pd.Series(0, index=df.index)
        active_signals_list = pd.Series('', index=df.index)

        for score_col, signal_type in signal_cols:
            if score_col not in df.columns:
                continue
            scores = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
            weight = self.weights.get(signal_type, 0.1)
            active = scores > 0.1
            weighted_sum += scores * weight * active.astype(float)
            total_weight += weight * active.astype(float)
            evidence_count += active.astype(int)
            active_signals_list = active_signals_list.where(~active, active_signals_list + ', ' + signal_type)

        active_signals_list = active_signals_list.str.lstrip(', ')

        df['priority_score'] = np.where(total_weight > 0, weighted_sum / total_weight, 0.0)

        non_dup_active = pd.Series(0, index=df.index)
        for score_col, signal_type in signal_cols:
            if signal_type == 'DUPLICATE' or score_col not in df.columns:
                continue
            scores = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
            non_dup_active += (scores > 0.1).astype(int)

        df['priority'] = 'LOW'
        df.loc[
            (df['priority_score'] >= PRIORITY_THRESHOLDS['HIGH_PRIORITY_REVIEW']) & (non_dup_active >= 2),
            'priority'
        ] = 'HIGH_PRIORITY_REVIEW'
        df.loc[
            (df['priority_score'] >= PRIORITY_THRESHOLDS['REVIEW_RECOMMENDED']) &
            (df['priority'] == 'LOW') & (non_dup_active >= 1),
            'priority'
        ] = 'REVIEW_RECOMMENDED'

        df['confidence'] = 'LOW'
        df.loc[evidence_count >= 2, 'confidence'] = 'MEDIUM'
        df.loc[evidence_count >= 3, 'confidence'] = 'HIGH'

        df['evidence_count'] = evidence_count
        df['active_signals'] = active_signals_list

        summary_parts = pd.Series('', index=df.index)
        for score_col, signal_type in signal_cols:
            explain_col = score_col.replace('_score', '_explanation')
            if explain_col in df.columns:
                scores = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
                mask = scores > 0.1
                summary_parts = summary_parts.where(
                    ~mask,
                    signal_type + ': ' + df[explain_col].fillna('')
                )
        df['evidence_summary'] = summary_parts

        self.df = df
        return df

    def _score_to_strength(self, score: float) -> str:
        if score > 0.7:
            return 'HIGH'
        elif score > 0.3:
            return 'MEDIUM'
        return 'LOW'

    def get_evidence_items(self, record_idx: int) -> List[Dict[str, Any]]:
        row = self.df.loc[record_idx]
        items = []
        signal_map = {
            'cost_anomaly_score': ('COST_ANOMALY', 'cost_anomaly_explanation'),
            'duplicate_score': ('DUPLICATE', 'duplicate_explanation'),
            'constituency_concentration_score': ('CONSTITUENCY_CONCENTRATION', 'constituency_concentration_explanation'),
            'mp_concentration_score': ('MP_CONCENTRATION', 'mp_concentration_explanation'),
            'temporal_score': ('TEMPORAL', 'temporal_explanation'),
            'lifecycle_score': ('LIFECYCLE', 'lifecycle_explanation'),
            'data_quality_score': ('DATA_QUALITY', 'data_quality_explanation'),
        }
        for score_col, (signal_type, explain_col) in signal_map.items():
            score = row.get(score_col, 0)
            if pd.notna(score) and float(score) > 0.1:
                items.append({
                    'signal_type': signal_type,
                    'signal_strength': self._score_to_strength(float(score)),
                    'score': round(float(score), 4),
                    'explanation': str(row.get(explain_col, '') or ''),
                    'weight': round(self.weights.get(signal_type, 0), 4),
                })
        return sorted(items, key=lambda x: -x['score'])

    def get_evidence_chain(self, record_idx: int) -> List[Dict[str, Any]]:
        row = self.df.loc[record_idx]
        chain = []

        chain.append({
            'step': 'SOURCE RECORD',
            'description': f"Record {row.get('Record ID', 'N/A')}",
            'details': {
                'mp': str(row.get('MP', '')),
                'constituency': str(row.get('Constituency', '')),
                'state': str(row.get('State', '')),
                'description': str(row.get('Work Description', '') or ''),
                'amount': str(row.get('Amount', '')),
                'date': str(row.get('Date', '')),
                'stage': str(row.get('Stage', '')),
            }
        })

        chain.append({
            'step': 'NORMALIZED DATA',
            'description': 'Text, numeric, and date normalization applied',
            'details': {
                'amount_numeric': _to_native(row.get('amount_numeric', None)),
                'date_parsed': str(row.get('date_parsed', '') or ''),
                'inferred_category': str(row.get('inferred_category', '') or ''),
                'category_confidence': _to_native(row.get('category_confidence', 0)),
                'amount_tier': str(row.get('amount_tier', '') or ''),
            }
        })

        chain.append({
            'step': 'PEER GROUP',
            'description': 'Contextual peer comparison',
            'details': {
                'peer_group_size': _to_native(row.get('peer_group_size', 0)),
                'peer_median': _to_native(row.get('peer_median', 0)),
                'peer_percentile': _to_native(row.get('peer_percentile', 0)),
                'deviation_ratio': _to_native(row.get('deviation_ratio', 0)),
            }
        })

        evidence_items = self.get_evidence_items(record_idx)
        chain.append({
            'step': 'SIGNALS',
            'description': f"{len(evidence_items)} anomaly signals detected",
            'details': evidence_items,
        })

        chain.append({
            'step': 'EVIDENCE FUSION',
            'description': 'Weighted combination of signals',
            'details': {
                'priority_score': _to_native(row.get('priority_score', 0)),
                'weights_used': {k: round(v, 4) for k, v in self.weights.items()},
            }
        })

        chain.append({
            'step': 'PRIORITY',
            'description': f"Assigned {row.get('priority', 'LOW')} priority",
            'details': {
                'priority': str(row.get('priority', 'LOW')),
                'confidence': str(row.get('confidence', 'LOW')),
                'evidence_count': _to_native(row.get('evidence_count', 0)),
            }
        })

        return chain
