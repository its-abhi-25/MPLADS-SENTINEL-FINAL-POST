"""
Main Sentinel Engine v2.0
Orchestrates the full analysis pipeline using modular components:
  Data Ingestion -> Context Engine -> Feature Engines -> Risk Engine -> Evidence Engine
"""
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from pathlib import Path
from ..services.data_service import DataIngestionService
from ..context.context_service import ContextService
from ..features.cost import CostAnomalyEngine
from ..features.text import TextSimilarityEngine
from ..features.concentration import ConcentrationEngine
from ..features.temporal import TemporalEngine
from ..features.lifecycle import LifecycleEngine
from ..features.patterns import PatternEngine
from ..risk.risk_engine import RiskEngine, MODEL_VERSION
from ..evidence.evidence_engine import EvidenceEngine
from ..evidence.explanations import ExplanationGenerator
from ..history.risk_history import RiskHistoryTracker
from ..core.config import RAW_CSV_PATH, COORDINATES_CSV_PATH, SIGNAL_WEIGHTS, MODEL_VERSION, SCORING_VERSION


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


def _safe_str(val, default=''):
    if pd.isna(val):
        return default
    return str(val)


class SentinelEngine:
    def __init__(self):
        self.data_service = DataIngestionService()
        self.df = None
        self.data_health = {}
        self.is_loaded = False
        self.coordinates = {}

        # Modular engines
        self.context_service = None
        self.cost_engine = CostAnomalyEngine()
        self.text_engine = TextSimilarityEngine()
        self.concentration_engine = ConcentrationEngine()
        self.temporal_engine = TemporalEngine()
        self.lifecycle_engine = LifecycleEngine()
        self.pattern_engine = PatternEngine()
        self.risk_engine = RiskEngine()
        self.evidence_engine = EvidenceEngine()
        self.explanation_generator = ExplanationGenerator()
        self.risk_history = RiskHistoryTracker()

    @staticmethod
    def _norm_constituency(name: str) -> str:
        import re
        return re.sub(r'\s+\(', '(', str(name)).strip()

    def _load_coordinates(self):
        self.coordinates = {}
        if not COORDINATES_CSV_PATH.exists():
            return
        try:
            coord_df = pd.read_csv(COORDINATES_CSV_PATH, dtype=str)
            for _, row in coord_df.iterrows():
                state = (row.get("State") or "").strip()
                constituency = (row.get("Constituency") or "").strip()
                lat = row.get("Latitude", "")
                lon = row.get("Longitude", "")
                level = (row.get("Location_Level") or "UNKNOWN").strip()
                status = (row.get("Geocoding_Status") or "unresolved").strip()
                if state and constituency:
                    norm_key = (state, self._norm_constituency(constituency))
                    self.coordinates[norm_key] = {
                        "latitude": float(lat) if lat else None,
                        "longitude": float(lon) if lon else None,
                        "location_level": level,
                        "geocoding_status": status,
                    }
        except Exception as e:
            print(f"[SENTINEL] Warning: Could not load coordinates: {e}")

    def load_and_analyze(self, filepath: str = None) -> Dict[str, Any]:
        if filepath is None:
            filepath = str(RAW_CSV_PATH)

        print("[SENTINEL] Step 1/7: Loading and validating data...")
        self.data_service.load_csv(filepath)
        self.data_health = self.data_service.compute_data_health()
        self.df = self.data_service.normalize_dataset()

        print("[SENTINEL] Step 2/7: Building context engine and peer groups...")
        self.context_service = ContextService(self.df)
        self.df = self.context_service.build_all_contexts()

        print("[SENTINEL] Step 3/7: Computing cost anomaly features...")
        self.df = self.cost_engine.compute_signals(self.df)

        print("[SENTINEL] Step 4/7: Computing text similarity features...")
        self.df = self.text_engine.compute_signals(self.df)

        print("[SENTINEL] Step 5/7: Computing concentration, temporal, lifecycle features...")
        self.df = self.concentration_engine.compute_signals(self.df)
        self.df = self.temporal_engine.compute_signals(self.df)
        self.df = self.lifecycle_engine.compute_signals(self.df)

        print("[SENTINEL] Step 6/7: Running cross-signal pattern engine...")
        self.df = self.pattern_engine.compute_signals(self.df)

        print("[SENTINEL] Step 7/7: Computing risk scores, corroboration, and confidence...")
        self.df = self.risk_engine.compute_all_risks(self.df)

        # Store evidence count for backward compatibility
        self.df['evidence_count'] = self.df['active_signal_count'].fillna(0).astype(int)

        # Load coordinates
        self._load_coordinates()

        # Record risk history for top-flagged records
        self._record_risk_history()

        self.is_loaded = True

        high_count = int((self.df['risk_level'] == 'CRITICAL').sum()) + int((self.df['risk_level'] == 'HIGH').sum())
        print(f"[SENTINEL] Analysis complete. {len(self.df)} records processed. "
              f"{high_count} high/critical investigation priorities identified.")

        return {
            'status': 'success',
            'records_analyzed': len(self.df),
            'data_health': self.data_health,
        }

    def _record_risk_history(self):
        """Record initial risk history for high-priority records."""
        if self.df is None:
            return
        high_risk = self.df[self.df['risk_score'] >= 0.6]
        for idx, row in high_risk.head(500).iterrows():
            record_id = _safe_str(row.get('Record ID'))
            if record_id:
                active = [s.strip() for s in str(row.get('active_signals_list', '')).split(',') if s.strip()]
                self.risk_history.record_risk(
                    record_id=record_id,
                    risk_score=float(row.get('risk_score', 0)),
                    risk_level=str(row.get('risk_level', 'LOW')),
                    confidence=float(row.get('confidence_score', 0)),
                    active_signals=active,
                    model_version=MODEL_VERSION,
                )

    def get_summary(self) -> Dict[str, Any]:
        if not self.is_loaded:
            return {}
        df = self.df

        total = len(df)
        critical = int((df['risk_level'] == 'CRITICAL').sum())
        high = int((df['risk_level'] == 'HIGH').sum())
        moderate = int((df['risk_level'] == 'MODERATE').sum())
        low = int((df['risk_level'] == 'LOW').sum())

        valid_amounts = df['amount_numeric'].dropna()
        total_amount = float(valid_amounts.sum()) if len(valid_amounts) > 0 else 0

        avg_risk = float(df['risk_score'].mean()) * 100 if total > 0 else 0
        high_risk_pct = round((critical + high) / total * 100, 1) if total > 0 else 0
        avg_confidence = float(df['confidence_score'].mean()) * 100 if total > 0 else 0

        # Top cost anomalies
        top_cost = []
        if 'cost_anomaly_score' in df.columns:
            top_nlargest = df.nlargest(5, 'cost_anomaly_score')
            for _, row in top_nlargest.iterrows():
                top_cost.append({
                    'Record ID': _safe_str(row.get('Record ID')),
                    'MP': _safe_str(row.get('MP')),
                    'Constituency': _safe_str(row.get('Constituency')),
                    'Work Description': _safe_str(row.get('Work Description'))[:80],
                    'Amount': _safe_str(row.get('Amount')),
                    'cost_anomaly_score': _to_native(row.get('cost_anomaly_score', 0)),
                    'cost_anomaly_explanation': _safe_str(row.get('cost_anomaly_explanation')),
                })

        risk_dist = df['risk_level'].value_counts().to_dict()

        return {
            'total_records': total,
            'total_amount': total_amount,
            'risk_distribution': risk_dist,
            'critical_count': critical,
            'high_count': high,
            'moderate_count': moderate,
            'low_count': low,
            'high_priority': critical + high,  # backward compat
            'review_recommended': moderate,  # backward compat
            'normal': low,  # backward compat
            'flag_rate': critical + high,
            'average_risk': round(avg_risk, 1),
            'high_risk_percentage': high_risk_pct,
            'average_confidence': round(avg_confidence, 1),
            'category_distribution': df['inferred_category'].value_counts().to_dict(),
            'state_distribution': df['State'].head(20).value_counts().to_dict(),
            'stage_distribution': df['Stage'].value_counts().to_dict(),
            'priority_distribution': df['risk_level'].value_counts().to_dict(),
            'top_signals': {
                'cost_anomalies': top_cost,
            },
            'model_version': MODEL_VERSION,
        }

    def get_investigation_queue(self, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.is_loaded:
            return {'records': [], 'total': 0}
        df = self.df.copy()

        if filters:
            if filters.get('priority'):
                df = df[df['risk_level'] == filters['priority']]
            if filters.get('confidence'):
                df = df[df['confidence'] == filters['confidence']]
            if filters.get('category'):
                df = df[df['inferred_category'] == filters['category']]
            if filters.get('state'):
                df = df[df['State'] == filters['state']]
            if filters.get('constituency'):
                df = df[df['Constituency'].str.contains(filters['constituency'], case=False, na=False)]
            if filters.get('mp_name'):
                df = df[df['MP'].str.contains(filters['mp_name'], case=False, na=False)]
            if filters.get('stage'):
                df = df[df['Stage'] == filters['stage']]
            if filters.get('search'):
                s = filters['search'].lower()
                df = df[
                    df['MP'].str.lower().str.contains(s, na=False) |
                    df['Work Description'].str.lower().str.contains(s, na=False) |
                    df['Constituency'].str.lower().str.contains(s, na=False) |
                    df['Record ID'].str.lower().str.contains(s, na=False)
                ]

        sort_by = filters.get('sort_by', 'risk_score') if filters else 'risk_score'
        sort_order = filters.get('sort_order', 'desc') if filters else 'desc'

        # Map legacy sort names
        sort_map = {
            'priority_score': 'risk_score',
            'cost_anomaly_score': 'cost_anomaly_score',
        }
        sort_by = sort_map.get(sort_by, sort_by)

        if sort_by in df.columns:
            df = df.sort_values(sort_by, ascending=(sort_order == 'asc'))

        total = len(df)
        page = filters.get('page', 1) if filters else 1
        page_size = filters.get('page_size', 50) if filters else 50
        start = (page - 1) * page_size
        end = start + page_size
        page_df = df.iloc[start:end]

        records = []
        for idx, row in page_df.iterrows():
            records.append({
                'record_id': _safe_str(row.get('Record ID')),
                'mp_name': _safe_str(row.get('MP')),
                'description': _safe_str(row.get('Work Description')),
                'category': _safe_str(row.get('inferred_category')),
                'amount': _safe_str(row.get('Amount')),
                'amount_numeric': _to_native(row.get('amount_numeric', None)),
                'constituency': _safe_str(row.get('Constituency')),
                'state': _safe_str(row.get('State')),
                'date': _safe_str(row.get('Date')),
                'stage': _safe_str(row.get('Stage')),
                'priority': _safe_str(row.get('risk_level', 'LOW')),
                'risk_level': _safe_str(row.get('risk_level', 'LOW')),
                'confidence': _safe_str(row.get('confidence', 'LOW')),
                'confidence_score': _to_native(row.get('confidence_score', 0)),
                'confidence_percent': _to_native(row.get('confidence_percent', 0)),
                'risk_score': _to_native(row.get('risk_score', 0)),
                'priority_score': _to_native(row.get('risk_score', 0)),  # backward compat
                'evidence_count': _to_native(row.get('evidence_count', 0)),
                'active_signal_count': _to_native(row.get('active_signal_count', 0)),
                'base_signal_count': _to_native(row.get('base_signal_count', 0)),
                'evidence_summary': _safe_str(row.get('evidence_summary')),
                'active_signals': _safe_str(row.get('active_signals_list')),
                'model_version': _safe_str(row.get('model_version')),
            })

        return {
            'records': records,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        }

    def get_record_detail(self, record_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_loaded:
            return None
        mask = self.df['Record ID'] == record_id
        if not mask.any():
            return None
        idx = self.df[mask].index[0]
        row = self.df.loc[idx]

        # Compute structured evidence
        evidence_items = self.evidence_engine.get_evidence_items(row)
        evidence_chain = self.evidence_engine.get_evidence_chain(row)

        # Context
        context = self.context_service.get_context_for_record(idx) if self.context_service else {}

        # Risk result
        risk_result = self.risk_engine.compute_single_risk(row)

        # Investigation recommendation
        recommendation = self.explanation_generator.generate_investigation_recommendation(evidence_items)

        detail = {
            'record_id': record_id,
            'source_record': {
                'record_id': _safe_str(row.get('Record ID')),
                'mp': _safe_str(row.get('MP')),
                'constituency': _safe_str(row.get('Constituency')),
                'state': _safe_str(row.get('State')),
                'description': _safe_str(row.get('Work Description')),
                'amount': _safe_str(row.get('Amount')),
                'date': _safe_str(row.get('Date')),
                'stage': _safe_str(row.get('Stage')),
            },
            'normalized_record': {
                'amount_numeric': _to_native(row.get('amount_numeric', None)),
                'date_parsed': str(row.get('date_parsed', '') or ''),
                'inferred_category': _safe_str(row.get('inferred_category')),
                'category_confidence': _to_native(row.get('category_confidence', 0)),
                'amount_tier': _safe_str(row.get('amount_tier')),
            },
            'risk_assessment': risk_result,
            'context': context,
            'evidence_items': evidence_items,
            'evidence_chain': evidence_chain,
            'investigation_recommendation': recommendation,
            # Backward compatibility
            'derived_features': {
                'peer_group_size': context.get('peer_group_size', 0),
                'peer_median': context.get('peer_median', 0),
                'peer_percentile': context.get('peer_percentile', 0),
                'deviation_ratio': context.get('deviation_ratio', 0),
            },
            'priority': {
                'priority': risk_result.get('risk_level', 'LOW'),
                'risk_level': risk_result.get('risk_level', 'LOW'),
                'confidence': risk_result.get('confidence_level', 'LOW'),
                'confidence_score': risk_result.get('confidence', 0),
                'priority_score': risk_result.get('risk_score', 0) / 100,
                'risk_score': risk_result.get('risk_score', 0),
                'evidence_count': risk_result.get('active_signal_count', 0),
                'evidence_summary': self.evidence_engine.get_evidence_items(row).__repr__()[:200] if evidence_items else '',
            },
        }

        related = self._find_related_records(idx)
        detail['related_records'] = related

        # Risk history
        history = self.risk_history.get_history(record_id)
        detail['risk_history'] = history[-10:] if history else []

        return detail

    def _find_related_records(self, idx: int, max_related: int = 10) -> List[Dict[str, Any]]:
        row = self.df.loc[idx]
        related = []
        seen = set()

        same_mp_cat = self.df[
            (self.df['MP'] == row['MP']) &
            (self.df['inferred_category'] == row['inferred_category']) &
            (self.df.index != idx)
        ].head(5)

        for ridx, rrow in same_mp_cat.iterrows():
            rid = _safe_str(rrow.get('Record ID'))
            if rid not in seen:
                seen.add(rid)
                related.append({
                    'record_id': rid,
                    'mp_name': _safe_str(rrow.get('MP')),
                    'description': _safe_str(rrow.get('Work Description')),
                    'category': _safe_str(rrow.get('inferred_category')),
                    'amount': _safe_str(rrow.get('Amount')),
                    'stage': _safe_str(rrow.get('Stage')),
                    'relationship': 'Same MP, Same Category',
                    'risk_level': _safe_str(rrow.get('risk_level', 'LOW')),
                    'priority': _safe_str(rrow.get('risk_level', 'LOW')),
                    'risk_score': _to_native(rrow.get('risk_score', 0)),
                })

        dup_score = row.get('description_similarity_score', 0)
        if pd.notna(dup_score) and float(dup_score) > 0.3:
            dup_records = self.df[
                (self.df['MP'] == row['MP']) &
                (self.df['description_normalized'] == row.get('description_normalized', '')) &
                (self.df.index != idx)
            ].head(5)
            for ridx, rrow in dup_records.iterrows():
                rid = _safe_str(rrow.get('Record ID'))
                if rid not in seen:
                    seen.add(rid)
                    related.append({
                        'record_id': rid,
                        'mp_name': _safe_str(rrow.get('MP')),
                        'description': _safe_str(rrow.get('Work Description')),
                        'category': _safe_str(rrow.get('inferred_category')),
                        'amount': _safe_str(rrow.get('Amount')),
                        'stage': _safe_str(rrow.get('Stage')),
                        'relationship': 'Potential Duplicate',
                        'risk_level': _safe_str(rrow.get('risk_level', 'LOW')),
                        'priority': _safe_str(rrow.get('risk_level', 'LOW')),
                        'risk_score': _to_native(rrow.get('risk_score', 0)),
                    })

        same_const = self.df[
            (self.df['Constituency'] == row['Constituency']) &
            (self.df['inferred_category'] == row['inferred_category']) &
            (self.df['Record ID'] != row['Record ID'])
        ].nlargest(3, 'amount_numeric') if 'amount_numeric' in self.df.columns else pd.DataFrame()

        for ridx, rrow in same_const.iterrows():
            rid = _safe_str(rrow.get('Record ID'))
            if rid not in seen:
                seen.add(rid)
                related.append({
                    'record_id': rid,
                    'mp_name': _safe_str(rrow.get('MP')),
                    'description': _safe_str(rrow.get('Work Description')),
                    'category': _safe_str(rrow.get('inferred_category')),
                    'amount': _safe_str(rrow.get('Amount')),
                    'stage': _safe_str(rrow.get('Stage')),
                    'relationship': 'Same Constituency, Same Category',
                    'risk_level': _safe_str(rrow.get('risk_level', 'LOW')),
                    'priority': _safe_str(rrow.get('risk_level', 'LOW')),
                    'risk_score': _to_native(rrow.get('risk_score', 0)),
                })

        return related[:max_related]

    def get_analytics(self) -> Dict[str, Any]:
        if not self.is_loaded:
            return {}
        df = self.df

        risk_dist = df['risk_level'].value_counts().to_dict()
        stage_dist = df['Stage'].value_counts().to_dict()
        category_dist = df['inferred_category'].value_counts().to_dict()

        amount_by_risk = {}
        for level in ['CRITICAL', 'HIGH', 'MODERATE', 'LOW']:
            subset = df[df['risk_level'] == level]['amount_numeric'].dropna()
            if len(subset) > 0:
                amount_by_risk[level] = {
                    'mean': float(subset.mean()),
                    'median': float(subset.median()),
                    'min': float(subset.min()),
                    'max': float(subset.max()),
                }

        state_flags = df.groupby('State').agg(
            flagged=('risk_level', lambda x: (x.isin(['HIGH', 'CRITICAL'])).sum()),
            total=('Record ID', 'count')
        )
        state_flags['flag_rate'] = (state_flags['flagged'] / state_flags['total'] * 100).round(1)
        state_flags = state_flags.sort_values('flag_rate', ascending=False).to_dict('index')

        const_flags = df.groupby('Constituency').agg(
            flagged=('risk_level', lambda x: (x.isin(['HIGH', 'CRITICAL'])).sum()),
            total=('Record ID', 'count')
        )
        const_flags['flag_rate'] = (const_flags['flagged'] / const_flags['total'] * 100).round(1)
        const_flags = const_flags[const_flags['total'] >= 10].sort_values('flag_rate', ascending=False).head(20).to_dict('index')

        mp_stats = df.groupby('MP').agg(
            flagged=('risk_level', lambda x: (x.isin(['HIGH', 'CRITICAL'])).sum()),
            total=('Record ID', 'count')
        )
        mp_stats['flag_rate'] = (mp_stats['flagged'] / mp_stats['total'] * 100).round(1)
        mp_stats = mp_stats[mp_stats['total'] >= 5].sort_values('flag_rate', ascending=False).head(15).to_dict('index')

        category_flags = df.groupby('inferred_category').agg(
            flagged=('risk_level', lambda x: (x.isin(['HIGH', 'CRITICAL'])).sum()),
            total=('Record ID', 'count')
        )
        category_flags['flag_rate'] = (category_flags['flagged'] / category_flags['total'] * 100).round(1)
        category_flags = category_flags.sort_values('flag_rate', ascending=False).to_dict('index')

        valid_amounts = df['amount_numeric'].dropna()
        if len(valid_amounts) > 0:
            p95 = float(valid_amounts.quantile(0.95))
            p99 = float(valid_amounts.quantile(0.99))
            bins = [0, 50000, 100000, 300000, 500000, 1000000, 2000000, p95, p99, float(valid_amounts.max())]
            bins = sorted(set(bins))
            hist, _ = np.histogram(valid_amounts, bins=bins)
            amount_histogram = {f"Rs.{int(bins[i]):,}-{int(bins[i+1]):,}": int(hist[i]) for i in range(len(hist))}
        else:
            amount_histogram = {}

        signal_dist = {}
        signal_cols = [
            ('cost_anomaly_score', 'cost_anomaly'),
            ('description_similarity_score', 'description_similarity'),
            ('mp_concentration_score', 'mp_concentration'),
            ('constituency_pattern_score', 'constituency_pattern'),
            ('temporal_score', 'temporal'),
            ('lifecycle_score', 'stage_consistency'),
            ('pattern_score', 'cross_signal_pattern'),
        ]
        for col, name in signal_cols:
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors='coerce').fillna(0)
                signal_dist[name] = {
                    'HIGH': int((vals > 0.7).sum()),
                    'MEDIUM': int(((vals > 0.3) & (vals <= 0.7)).sum()),
                    'LOW': int((vals <= 0.3).sum()),
                }

        # Confidence distribution
        conf_dist = df['confidence'].value_counts().to_dict()
        avg_confidence = float(df['confidence_score'].mean()) * 100 if len(df) > 0 else 0

        return {
            'priority_distribution': risk_dist,
            'risk_distribution': risk_dist,
            'stage_distribution': stage_dist,
            'category_distribution': category_dist,
            'amount_by_priority': amount_by_risk,
            'amount_by_risk': amount_by_risk,
            'state_flags': state_flags,
            'constituency_flags': const_flags,
            'mp_stats': mp_stats,
            'category_flags': category_flags,
            'signal_distribution': signal_dist,
            'amount_histogram': amount_histogram,
            'confidence_distribution': conf_dist,
            'average_confidence': round(avg_confidence, 1),
            'model_version': MODEL_VERSION,
        }

    def get_data_health(self) -> Dict[str, Any]:
        if not self.is_loaded:
            return {}
        health = self.data_health.copy()
        df = self.df

        health['signals_enabled'] = [
            'COST_ANOMALY', 'DESCRIPTION_SIMILARITY', 'MP_CONCENTRATION',
            'CONSTITUENCY_PATTERN', 'TEMPORAL_ANOMALY', 'STAGE_CONSISTENCY',
            'CROSS_SIGNAL_PATTERN',
        ]
        health['signals_unavailable'] = [
            'Contractor Analysis (no contractor data in source)',
            'Tender/Procurement Analysis (no tender data in source)',
            'Payment Transaction Analysis (no payment data in source)',
            'Beneficiary Analysis (no beneficiary data in source)',
            'Implementing Agency Analysis (no agency data in source)',
            'Work-level GPS Anomaly Detection (only constituency-level coordinates available)',
            'Physical Progress Verification (no progress percentage data in source)',
        ]
        health['category_inference'] = {
            'total': len(df),
            'inferred': int(df['inferred_category'].notna().sum()),
            'categories': df['inferred_category'].value_counts().to_dict(),
        }

        # Add risk distribution summary
        health['risk_summary'] = {
            'critical': int((df['risk_level'] == 'CRITICAL').sum()),
            'high': int((df['risk_level'] == 'HIGH').sum()),
            'moderate': int((df['risk_level'] == 'MODERATE').sum()),
            'low': int((df['risk_level'] == 'LOW').sum()),
        }

        # Add confidence summary
        health['confidence_summary'] = {
            'high': int((df['confidence'] == 'HIGH').sum()),
            'medium': int((df['confidence'] == 'MEDIUM').sum()),
            'low': int((df['confidence'] == 'LOW').sum()),
            'average': round(float(df['confidence_score'].mean()) * 100, 1),
        }

        return health

    def get_constituency_map_data(self, state: str = None, priority: str = None,
                                   stage: str = None, search: str = None) -> List[Dict[str, Any]]:
        """Return constituency-level aggregates for choropleth map.

        Supports the same filter parameters as get_map_works so that the
        constituency layer and the KPI bar stay perfectly synchronised.
        """
        if not self.is_loaded:
            return []
        df = self.df.copy()

        if state:
            df = df[df['State'] == state]
        if priority:
            df = df[df['risk_level'] == priority]
        if stage:
            df = df[df['Stage'] == stage]
        if search:
            s = search.lower()
            df = df[
                df['MP'].str.lower().str.contains(s, na=False) |
                df['Work Description'].str.lower().str.contains(s, na=False) |
                df['Constituency'].str.lower().str.contains(s, na=False) |
                df['Record ID'].str.lower().str.contains(s, na=False)
            ]

        grouped = df.groupby(['State', 'Constituency']).agg(
            total=('Record ID', 'count'),
            flagged=('risk_level', lambda x: (x.isin(['HIGH', 'CRITICAL'])).sum()),
            critical=('risk_level', lambda x: (x == 'CRITICAL').sum()),
            high=('risk_level', lambda x: (x == 'HIGH').sum()),
            moderate=('risk_level', lambda x: (x == 'MODERATE').sum()),
            low=('risk_level', lambda x: (x == 'LOW').sum()),
            total_amount=('amount_numeric', lambda x: x.dropna().sum()),
            avg_risk=('risk_score', 'mean'),
            mps=('MP', lambda x: ', '.join(x.unique()[:3])),
            stages=('Stage', lambda x: ', '.join(x.value_counts().head(3).index.tolist())),
        ).reset_index()
        grouped['flag_rate'] = (grouped['flagged'] / grouped['total'] * 100).round(1)
        grouped['avg_risk_pct'] = (grouped['avg_risk'] * 100).round(1)

        # Financial exposure: sum of amounts for HIGH + CRITICAL works
        high_crit_mask = df['risk_level'].isin(['HIGH', 'CRITICAL'])
        if high_crit_mask.any():
            exposure = df[high_crit_mask].groupby(['State', 'Constituency'])['amount_numeric'].sum().reset_index()
            exposure.columns = ['State', 'Constituency', 'financial_exposure']
            grouped = grouped.merge(exposure, on=['State', 'Constituency'], how='left')
        else:
            grouped['financial_exposure'] = 0
        grouped['financial_exposure'] = grouped['financial_exposure'].fillna(0)

        # Average confidence for the constituency
        conf_means = df.groupby(['State', 'Constituency'])['confidence_score'].mean().reset_index()
        conf_means.columns = ['State', 'Constituency', 'avg_confidence']
        grouped = grouped.merge(conf_means, on=['State', 'Constituency'], how='left')
        grouped['avg_confidence'] = grouped['avg_confidence'].fillna(0)
        grouped['avg_confidence_pct'] = (grouped['avg_confidence'] * 100).round(1)

        # Multi-signal count: average active_signal_count per constituency
        if 'active_signal_count' in df.columns:
            sig_means = df.groupby(['State', 'Constituency'])['active_signal_count'].mean().reset_index()
            sig_means.columns = ['State', 'Constituency', 'avg_signals']
            grouped = grouped.merge(sig_means, on=['State', 'Constituency'], how='left')
        else:
            grouped['avg_signals'] = 0
        grouped['avg_signals'] = grouped['avg_signals'].fillna(0).round(1)

        # Add coordinates
        grouped['latitude'] = None
        grouped['longitude'] = None
        grouped['location_level'] = 'UNKNOWN'
        grouped['geocoding_status'] = 'unresolved'

        for idx, row in grouped.iterrows():
            key = (row['State'], self._norm_constituency(row['Constituency']))
            coord = self.coordinates.get(key, {})
            if coord:
                grouped.at[idx, 'latitude'] = coord.get('latitude')
                grouped.at[idx, 'longitude'] = coord.get('longitude')
                grouped.at[idx, 'location_level'] = coord.get('location_level', 'UNKNOWN')
                grouped.at[idx, 'geocoding_status'] = coord.get('geocoding_status', 'unresolved')

        result = grouped[grouped['latitude'].notna()].to_dict('records')
        return result

    def get_constituency_intelligence(self, state: str, constituency: str) -> Optional[Dict[str, Any]]:
        """Return deep intelligence for a single constituency drill-down."""
        if not self.is_loaded:
            return None
        df = self.df
        mask = (df['State'] == state) & (df['Constituency'] == constituency)
        subset = df[mask]
        if subset.empty:
            return None

        total = len(subset)
        valid_amounts = subset['amount_numeric'].dropna()
        total_amount = float(valid_amounts.sum()) if len(valid_amounts) > 0 else 0

        critical = int((subset['risk_level'] == 'CRITICAL').sum())
        high = int((subset['risk_level'] == 'HIGH').sum())
        moderate = int((subset['risk_level'] == 'MODERATE').sum())
        low = int((subset['risk_level'] == 'LOW').sum())
        flagged = critical + high
        priority_rate = round(flagged / total * 100, 1) if total > 0 else 0
        avg_risk = round(float(subset['risk_score'].mean()) * 100, 1) if total > 0 else 0
        avg_confidence = round(float(subset['confidence_score'].mean()) * 100, 1) if total > 0 else 0

        # Financial exposure
        high_crit_mask = subset['risk_level'].isin(['HIGH', 'CRITICAL'])
        financial_exposure = float(subset[high_crit_mask]['amount_numeric'].dropna().sum()) if high_crit_mask.any() else 0

        # Stage distribution
        stage_dist = subset['Stage'].value_counts().to_dict()

        # Top signal contributors
        signal_cols = [
            ('cost_anomaly_score', 'Cost Anomaly'),
            ('description_similarity_score', 'Description Similarity'),
            ('mp_concentration_score', 'MP Concentration'),
            ('constituency_pattern_score', 'Constituency Pattern'),
            ('temporal_score', 'Temporal Anomaly'),
            ('lifecycle_score', 'Stage Consistency'),
            ('pattern_score', 'Cross-Signal Pattern'),
        ]
        signal_summary = []
        for col, name in signal_cols:
            if col in subset.columns:
                vals = pd.to_numeric(subset[col], errors='coerce').fillna(0)
                high_count = int((vals > 0.7).sum())
                avg_val = round(float(vals.mean()) * 100, 1)
                if high_count > 0:
                    signal_summary.append({
                        'signal': name,
                        'high_count': high_count,
                        'avg_score': avg_val,
                    })
        signal_summary.sort(key=lambda x: x['high_count'], reverse=True)

        # Confidence breakdown
        conf_dist = subset['confidence'].value_counts().to_dict()

        # Top 10 priority works
        top_works = []
        top_n = subset.nlargest(10, 'risk_score')
        for _, row in top_n.iterrows():
            top_works.append({
                'record_id': _safe_str(row.get('Record ID')),
                'description': _safe_str(row.get('Work Description'))[:120],
                'amount': _to_native(row.get('amount_numeric', None)),
                'risk_level': _safe_str(row.get('risk_level', 'LOW')),
                'risk_score': _to_native(row.get('risk_score', 0)),
                'mp': _safe_str(row.get('MP')),
                'stage': _safe_str(row.get('Stage')),
            })

        # Category distribution
        cat_dist = subset['inferred_category'].value_counts().to_dict()

        # MP list
        mps = [m for m in subset['MP'].unique() if m and str(m) != 'nan']

        return {
            'state': state,
            'constituency': constituency,
            'total_works': total,
            'total_amount': total_amount,
            'critical_count': critical,
            'high_count': high,
            'moderate_count': moderate,
            'low_count': low,
            'flagged_count': flagged,
            'priority_rate': priority_rate,
            'average_risk': avg_risk,
            'average_confidence': avg_confidence,
            'financial_exposure': financial_exposure,
            'stage_distribution': stage_dist,
            'category_distribution': cat_dist,
            'signal_summary': signal_summary,
            'confidence_distribution': conf_dist,
            'top_priority_works': top_works,
            'mps': sorted(mps),
        }

    def get_geographic_coverage(self) -> Dict[str, Any]:
        """Return geographic coverage statistics."""
        if not self.is_loaded:
            return {}

        # Load geojson to check matches
        geojson_path = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "constituencies.geojson"
        report_path = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "geojson_match_report.json"

        real_boundary = 0
        centroid_fallback = 0
        total_geojson = 0

        if report_path.exists():
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                summary = report.get('summary', {})
                real_boundary = summary.get('real_boundary_features', 0)
                centroid_fallback = summary.get('centroid_fallback', 0)
                total_geojson = summary.get('total_dataset_constituencies', 0)
            except Exception:
                pass

        total_dataset = len(self.df['Constituency'].dropna().unique()) if self.df is not None else 0

        real_pct = round(real_boundary / total_dataset * 100, 1) if total_dataset > 0 else 0
        centroid_pct = round(centroid_fallback / total_dataset * 100, 1) if total_dataset > 0 else 0

        return {
            'total_constituencies': total_dataset,
            'real_boundary_count': real_boundary,
            'real_boundary_pct': real_pct,
            'centroid_fallback_count': centroid_fallback,
            'centroid_fallback_pct': centroid_pct,
            'total_coverage_pct': round(real_pct + centroid_pct, 1),
        }

    def get_geojson_data(self) -> Optional[Dict[str, Any]]:
        """Load and return the constituency GeoJSON for map rendering."""
        geojson_path = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "constituencies.geojson"
        if not geojson_path.exists():
            return None
        try:
            with open(geojson_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def get_map_works(self, state: str = None, constituency: str = None,
                       priority: str = None, stage: str = None,
                       search: str = None, limit: int = 40000) -> List[Dict[str, Any]]:
        """
        Returns map-ready work records matching the given filters.

        `limit` is a performance safeguard, not a content filter: it is set
        high enough (40,000) to comfortably exceed the largest single
        risk-level band in the real dataset (LOW ~37.8k, MODERATE ~22.3k,
        HIGH ~3.9k, CRITICAL ~15), so in practice every filtered view --
        by risk level, state, stage or search -- returns its COMPLETE
        matching set, never a silently-truncated slice. The cap only
        engages for the literal "everything, no filter at all" request
        against the full ~64k-row dataset.

        If that cap ever does need to engage, the reduction is a
        proportional stratified sample BY STATE (not a global
        risk-score-first cut), so the map keeps reflecting the real
        national geographic spread instead of collapsing onto whichever
        few states happen to contain the highest-scored works. No
        coordinates are invented and no works are duplicated -- this only
        controls which subset of the real, already-geocoded rows is
        returned.
        """
        if not self.is_loaded:
            return []
        df = self.df.copy()

        if state:
            df = df[df['State'] == state]
        if constituency:
            df = df[df['Constituency'].str.contains(constituency, case=False, na=False)]
        if priority:
            df = df[df['risk_level'] == priority]
        if stage:
            df = df[df['Stage'] == stage]
        if search:
            s = search.lower()
            df = df[
                df['MP'].str.lower().str.contains(s, na=False) |
                df['Work Description'].str.lower().str.contains(s, na=False) |
                df['Constituency'].str.lower().str.contains(s, na=False) |
                df['Record ID'].str.lower().str.contains(s, na=False)
            ]

        priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MODERATE': 2, 'LOW': 3}

        if len(df) > limit:
            # Proportional stratified sample by State: each state keeps the
            # same share of the map it has in the real filtered data, so no
            # state can crowd out the rest just for having more high-score
            # works. Within each state's quota, the highest-risk works are
            # kept first (a state's own allocation is still risk-prioritised).
            state_counts = df['State'].value_counts()
            quotas = (state_counts / state_counts.sum() * limit).round().astype(int)
            # Every state with at least one real matching record gets at
            # least one marker in the sample -- a state with only 2-3
            # total works nationally (e.g. Lakshadweep) would otherwise
            # round down to a zero quota and vanish from the default view
            # entirely, which would misrepresent geographic coverage even
            # though the sampling itself is proportionally correct.
            quotas = quotas.clip(lower=1)
            # Rounding (and the min-1 floor above) can drift the total
            # somewhat off `limit`; correct by trimming the largest quotas
            # rather than biasing one arbitrary state.
            drift = int(quotas.sum() - limit)
            if drift > 0:
                # Remove the surplus from the biggest quotas first so no
                # state is pushed below its fair share, and never below 1.
                order = quotas.sort_values(ascending=False).index
                for st in order:
                    if drift <= 0:
                        break
                    reducible = quotas[st] - 1
                    take = min(reducible, drift)
                    if take > 0:
                        quotas[st] -= take
                        drift -= take

            df['_priority_rank'] = df['risk_level'].map(priority_order).fillna(4)
            parts = []
            for st, quota in quotas.items():
                if quota <= 0:
                    continue
                sub = df[df['State'] == st].sort_values(['_priority_rank', 'risk_score'], ascending=[True, False])
                parts.append(sub.head(int(quota)))
            df = pd.concat(parts) if parts else df.head(0)
            df = df.sort_values(['_priority_rank', 'risk_score'], ascending=[True, False])
            df = df.drop(columns=['_priority_rank'])
        else:
            df['_priority_rank'] = df['risk_level'].map(priority_order).fillna(4)
            df = df.sort_values(['_priority_rank', 'risk_score'], ascending=[True, False])
            df = df.drop(columns=['_priority_rank'])

        works = []
        for idx, row in df.iterrows():
            state_val = _safe_str(row.get('State'))
            const_val = _safe_str(row.get('Constituency'))
            coord = self.coordinates.get((state_val, self._norm_constituency(const_val)), {})
            lat = coord.get('latitude')
            lon = coord.get('longitude')
            if lat is None or lon is None:
                continue

            works.append({
                'record_id': _safe_str(row.get('Record ID')),
                'latitude': lat,
                'longitude': lon,
                'location_level': coord.get('location_level', 'UNKNOWN'),
                'state': state_val,
                'constituency': const_val,
                'mp': _safe_str(row.get('MP')),
                'description': _safe_str(row.get('Work Description'))[:120],
                'amount': _to_native(row.get('amount_numeric', None)),
                'stage': _safe_str(row.get('Stage')),
                'category': _safe_str(row.get('inferred_category')),
                'risk_level': _safe_str(row.get('risk_level', 'LOW')),
                'priority': _safe_str(row.get('risk_level', 'LOW')),
                'risk_score': _to_native(row.get('risk_score', 0)),
                'priority_score': _to_native(row.get('risk_score', 0)),
                'confidence_score': _to_native(row.get('confidence_score', 0)),
                'confidence_percent': _to_native(row.get('confidence_percent', 0)),
                'evidence_count': _to_native(row.get('evidence_count', 0)),
                'active_signal_count': _to_native(row.get('active_signal_count', 0)),
                'base_signal_count': _to_native(row.get('base_signal_count', 0)),
                'evidence_summary': _safe_str(row.get('evidence_summary')),
                'date': _safe_str(row.get('Date')),
            })

        return works

    def get_map_filters(self) -> Dict[str, Any]:
        if not self.is_loaded:
            return {}
        df = self.df
        stages = [s for s in df['Stage'].unique() if s and str(s) != 'nan']
        return {
            'states': sorted([s for s in df['State'].unique() if s and str(s) != 'nan']),
            'stages': sorted(stages),
            'risk_levels': ['CRITICAL', 'HIGH', 'MODERATE', 'LOW'],
            'priorities': ['CRITICAL', 'HIGH', 'MODERATE', 'LOW'],  # backward compat
            'total_constituencies': df['Constituency'].nunique(),
            'total_works': len(df),
        }

    def get_graph_data(self) -> Dict[str, Any]:
        if not self.is_loaded:
            return {'nodes': [], 'edges': []}
        df = self.df
        nodes = []
        edges = []
        node_ids = set()

        def add_node(nid, ntype, label, **kwargs):
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append({'id': nid, 'type': ntype, 'label': label, **kwargs})

        mp_ids = df['MP'].unique()
        for mp in mp_ids[:30]:
            nid = f"mp_{mp}"
            add_node(nid, 'MP', mp, count=int(df[df['MP'] == mp].shape[0]))

        const_ids = df['Constituency'].unique()
        for const in const_ids[:30]:
            nid = f"const_{const}"
            add_node(nid, 'Constituency', const, count=int(df[df['Constituency'] == const].shape[0]))

        cat_ids = df['inferred_category'].unique()
        for cat in cat_ids:
            nid = f"cat_{cat}"
            add_node(nid, 'Category', cat, count=int(df[df['inferred_category'] == cat].shape[0]))

        top_mps = df['MP'].value_counts().head(15).index
        for mp in top_mps:
            mp_constituencies = df[df['MP'] == mp]['Constituency'].unique()
            for const in mp_constituencies[:2]:
                mp_nid = f"mp_{mp}"
                const_nid = f"const_{const}"
                if mp_nid in node_ids and const_nid in node_ids:
                    edges.append({
                        'source': mp_nid,
                        'target': const_nid,
                        'type': 'represents',
                        'label': 'Represents',
                    })

        for const in df['Constituency'].value_counts().head(15).index:
            const_cats = df[df['Constituency'] == const]['inferred_category'].value_counts().head(3).index
            for cat in const_cats:
                const_nid = f"const_{const}"
                cat_nid = f"cat_{cat}"
                if const_nid in node_ids and cat_nid in node_ids:
                    edges.append({
                        'source': const_nid,
                        'target': cat_nid,
                        'type': 'has_works',
                        'label': 'Has Works',
                    })

        return {'nodes': nodes, 'edges': edges}

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get overall risk summary for dashboard."""
        if not self.is_loaded:
            return {}
        df = self.df
        return {
            'total_records': len(df),
            'risk_distribution': df['risk_level'].value_counts().to_dict(),
            'average_risk': round(float(df['risk_score'].mean()) * 100, 1),
            'average_confidence': round(float(df['confidence_score'].mean()) * 100, 1),
            'critical_count': int((df['risk_level'] == 'CRITICAL').sum()),
            'high_count': int((df['risk_level'] == 'HIGH').sum()),
            'model_version': MODEL_VERSION,
        }

    def get_top_risk(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get top risk records."""
        if not self.is_loaded:
            return []
        df = self.df.nlargest(limit, 'risk_score')
        return [{
            'record_id': _safe_str(row.get('Record ID')),
            'mp': _safe_str(row.get('MP')),
            'constituency': _safe_str(row.get('Constituency')),
            'state': _safe_str(row.get('State')),
            'description': _safe_str(row.get('Work Description'))[:100],
            'amount': _to_native(row.get('amount_numeric', None)),
            'risk_score': round(float(row.get('risk_score', 0)) * 100, 1),
            'risk_level': _safe_str(row.get('risk_level', 'LOW')),
            'confidence': round(float(row.get('confidence_score', 0)) * 100, 1),
            'active_signal_count': int(row.get('active_signal_count', 0)),
        } for _, row in df.iterrows()]

    def get_context(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Get context for a specific record."""
        if not self.is_loaded or not self.context_service:
            return None
        mask = self.df['Record ID'] == record_id
        if not mask.any():
            return None
        idx = self.df[mask].index[0]
        return self.context_service.get_context_for_record(idx)

    def get_signals(self, record_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get signals for a specific record."""
        if not self.is_loaded:
            return None
        mask = self.df['Record ID'] == record_id
        if not mask.any():
            return None
        row = self.df[mask].iloc[0]
        return self.evidence_engine.get_evidence_items(row)

    def get_evidence(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Get full evidence for a specific record."""
        if not self.is_loaded:
            return None
        mask = self.df['Record ID'] == record_id
        if not mask.any():
            return None
        row = self.df[mask].iloc[0]
        return {
            'evidence_items': self.evidence_engine.get_evidence_items(row),
            'evidence_chain': self.evidence_engine.get_evidence_chain(row),
        }

    def get_investigations(self) -> List[Dict[str, Any]]:
        """Get investigation queue items."""
        return self.get_investigation_queue({
            'sort_by': 'risk_score',
            'sort_order': 'desc',
            'page': 1,
            'page_size': 50,
        }).get('records', [])

    def recalculate_risk(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Recalculate risk for a single record."""
        if not self.is_loaded:
            return None
        mask = self.df['Record ID'] == record_id
        if not mask.any():
            return None
        idx = self.df[mask].index[0]
        row = self.df.loc[idx]

        risk_result = self.risk_engine.compute_single_risk(row)
        evidence_items = self.evidence_engine.get_evidence_items(row)

        # Record in history
        active = [e['signal_type'] for e in evidence_items]
        self.risk_history.record_risk(
            record_id=record_id,
            risk_score=risk_result['risk_score'] / 100,
            risk_level=risk_result['risk_level'],
            confidence=risk_result['confidence'] / 100,
            active_signals=active,
            model_version=MODEL_VERSION,
        )

        return {
            'record_id': record_id,
            'risk_result': risk_result,
            'evidence_items': evidence_items,
        }

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        return []

    # ── MP Performance (preserved from v1) ──────────────────────────

    def _build_entity_profile(self, df: pd.DataFrame, entity_type: str) -> Dict[str, Any]:
        if df.empty:
            return {'error': 'No records found'}

        total = len(df)
        valid_amounts = df['amount_numeric'].dropna()
        total_amount = float(valid_amounts.sum()) if len(valid_amounts) > 0 else 0.0
        avg_amount = float(valid_amounts.mean()) if len(valid_amounts) > 0 else 0.0

        stage_dist = df['Stage'].value_counts().to_dict()
        stage_amounts = {}
        for stage in df['Stage'].unique():
            if pd.isna(stage):
                continue
            s = str(stage)
            subset = df[df['Stage'] == stage]['amount_numeric'].dropna()
            stage_amounts[s] = float(subset.sum()) if len(subset) > 0 else 0.0

        completed_count = stage_dist.get('COMPLETED', 0)
        sanctioned_count = stage_dist.get('SANCTIONED', 0)
        recommended_count = stage_dist.get('RECOMMENDED', 0)

        cat_dist = df['inferred_category'].value_counts().to_dict()
        cat_amounts = {}
        for cat in df['inferred_category'].unique():
            if pd.isna(cat):
                continue
            subset = df[df['inferred_category'] == cat]['amount_numeric'].dropna()
            cat_amounts[str(cat)] = float(subset.sum()) if len(subset) > 0 else 0.0

        risk_dist = df['risk_level'].value_counts().to_dict()
        critical_count = risk_dist.get('CRITICAL', 0)
        high_count = risk_dist.get('HIGH', 0)
        moderate_count = risk_dist.get('MODERATE', 0)
        low_count = risk_dist.get('LOW', 0)

        signal_summary = {}
        signal_cols = [
            ('cost_anomaly_score', 'cost_anomaly'),
            ('description_similarity_score', 'description_similarity'),
            ('mp_concentration_score', 'mp_concentration'),
            ('constituency_pattern_score', 'constituency_pattern'),
            ('temporal_score', 'temporal'),
            ('lifecycle_score', 'stage_consistency'),
            ('pattern_score', 'cross_signal_pattern'),
        ]
        for col, name in signal_cols:
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors='coerce').fillna(0)
                active_count = int((vals > 0.1).sum())
                high_count_s = int((vals > 0.7).sum())
                if active_count > 0:
                    signal_summary[name] = {
                        'active_count': active_count,
                        'high_count': high_count_s,
                    }

        trend = []
        if 'year' in df.columns and df['year'].notna().any():
            time_df = df[df['year'].notna()].copy()
            time_df['year'] = time_df['year'].astype(int)
            if 'quarter' in time_df.columns and time_df['quarter'].notna().any():
                q_clean = time_df['quarter'].str.replace('Q', '', regex=False).astype(int)
                time_df = time_df.assign(_q=q_clean)
                grouped = time_df.groupby(['year', '_q']).agg(
                    works=('Record ID', 'count'),
                    amount=('amount_numeric', lambda x: x.dropna().sum()),
                ).reset_index().sort_values(['year', '_q'])
                for _, row in grouped.iterrows():
                    trend.append({
                        'period': f"{int(row['year'])}-Q{int(row['_q'])}",
                        'year': int(row['year']),
                        'quarter': int(row['_q']),
                        'works': int(row['works']),
                        'amount': float(row['amount']),
                    })
            else:
                grouped = time_df.groupby('year').agg(
                    works=('Record ID', 'count'),
                    amount=('amount_numeric', lambda x: x.dropna().sum()),
                ).reset_index().sort_values('year')
                for _, row in grouped.iterrows():
                    trend.append({
                        'period': str(int(row['year'])),
                        'year': int(row['year']),
                        'quarter': None,
                        'works': int(row['works']),
                        'amount': float(row['amount']),
                    })

        top_works = []
        top_n = df.nlargest(10, 'risk_score') if 'risk_score' in df.columns else df.head(10)
        for _, row in top_n.iterrows():
            top_works.append({
                'record_id': _safe_str(row.get('Record ID')),
                'description': _safe_str(row.get('Work Description'))[:120],
                'amount': _to_native(row.get('amount_numeric', None)),
                'stage': _safe_str(row.get('Stage')),
                'category': _safe_str(row.get('inferred_category')),
                'risk_level': _safe_str(row.get('risk_level', 'LOW')),
                'risk_score': _to_native(row.get('risk_score', 0)),
                'evidence_count': _to_native(row.get('evidence_count', 0)),
            })

        flagged_count = critical_count + high_count
        risk_rate = round(flagged_count / total * 100, 1) if total > 0 else 0.0

        amount_by_risk = {}
        for p in ['CRITICAL', 'HIGH', 'MODERATE', 'LOW']:
            subset = df[df['risk_level'] == p]['amount_numeric'].dropna()
            if len(subset) > 0:
                amount_by_risk[p] = {
                    'count': int(len(subset)),
                    'total': float(subset.sum()),
                    'mean': float(subset.mean()),
                }

        return {
            'total_works': total,
            'completed_works': completed_count,
            'sanctioned_works': sanctioned_count,
            'recommended_works': recommended_count,
            'completion_rate': round(completed_count / total * 100, 1) if total > 0 else 0.0,
            'total_recorded_amount': total_amount,
            'average_work_amount': avg_amount,
            'completed_amount': stage_amounts.get('COMPLETED', 0.0),
            'stage_distribution': stage_dist,
            'stage_amounts': stage_amounts,
            'category_distribution': cat_dist,
            'category_amounts': cat_amounts,
            'risk_distribution': risk_dist,
            'critical_count': critical_count,
            'high_priority_count': high_count,
            'review_recommended_count': moderate_count,
            'low_risk_count': low_count,
            'high_priority': critical_count + high_count,
            'review_recommended': moderate_count,
            'normal': low_count,
            'risk_rate': risk_rate,
            'amount_by_priority': amount_by_risk,
            'signal_summary': signal_summary,
            'trend': trend,
            'top_flagged_works': top_works,
        }

    def get_mp_performance(self, mp_name: str) -> Dict[str, Any]:
        if not self.is_loaded:
            return {'error': 'Dataset not loaded'}
        df = self.df[self.df['MP'] == mp_name].copy()
        if df.empty:
            return {'error': f'No records found for MP: {mp_name}'}
        profile = self._build_entity_profile(df, 'mp')
        profile['mp_name'] = mp_name
        profile['constituency'] = _safe_str(df['Constituency'].mode().iloc[0]) if len(df) > 0 else ''
        profile['state'] = _safe_str(df['State'].mode().iloc[0]) if len(df) > 0 else ''
        return profile

    def get_constituency_performance(self, constituency_name: str) -> Dict[str, Any]:
        if not self.is_loaded:
            return {'error': 'Dataset not loaded'}
        df = self.df[self.df['Constituency'] == constituency_name].copy()
        if df.empty:
            return {'error': f'No records found for constituency: {constituency_name}'}
        profile = self._build_entity_profile(df, 'constituency')
        profile['constituency_name'] = constituency_name
        profile['state'] = _safe_str(df['State'].mode().iloc[0]) if len(df) > 0 else ''
        mps = [m for m in df['MP'].unique() if m and str(m) != 'nan']
        profile['mps'] = sorted(mps)
        return profile

    def _build_comparison(self, df: pd.DataFrame, group_col: str, names: List[str]) -> Dict[str, Any]:
        if not self.is_loaded:
            return {'error': 'Dataset not loaded'}
        results = []
        for name in names:
            subset = df[df[group_col] == name].copy()
            if subset.empty:
                results.append({'name': name, 'error': 'No records found'})
                continue
            profile = self._build_entity_profile(subset, group_col)
            profile['name'] = name
            results.append(profile)
        return {'comparison': results, 'entity_type': group_col}

    def get_mp_comparison(self, mp_names: List[str]) -> Dict[str, Any]:
        return self._build_comparison(self.df, 'MP', mp_names)

    def get_constituency_comparison(self, constituency_names: List[str]) -> Dict[str, Any]:
        return self._build_comparison(self.df, 'Constituency', constituency_names)


_sentinel_engine = None

def get_sentinel_engine() -> SentinelEngine:
    global _sentinel_engine
    if _sentinel_engine is None:
        _sentinel_engine = SentinelEngine()
    return _sentinel_engine
