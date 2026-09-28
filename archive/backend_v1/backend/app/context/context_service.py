"""
Context Service (Optimized for 64K+ records)
Orchestrates context building for each project record.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from .peer_builder import PeerGroupBuilder


class ContextService:
    """Orchestrates context building and peer comparison for projects."""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.peer_builder = PeerGroupBuilder(df)
    
    def build_all_contexts(self) -> pd.DataFrame:
        """Build peer groups and compute baselines for all records."""
        df = self.peer_builder.build_peer_groups()
        df = self._compute_peer_baselines_vectorized(df)
        return df
    
    def _compute_peer_baselines_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute amount baselines per peer group using vectorized groupby."""
        df['peer_median'] = 0.0
        df['peer_mean'] = 0.0
        df['peer_mad'] = 0.0
        df['peer_iqr'] = 0.0
        df['peer_q25'] = 0.0
        df['peer_q75'] = 0.0
        df['peer_percentile'] = 50.0
        df['deviation_ratio'] = 0.0
        
        valid = df['amount_numeric'].notna() & (df['peer_group_size'] >= 3)
        if valid.sum() == 0:
            return df
        
        # Use vectorized groupby for medians
        grp_key = 'peer_group_key'
        
        # Compute group medians
        group_medians = df.loc[valid].groupby(grp_key)['amount_numeric'].median()
        group_medians.name = '_grp_median'
        
        # Compute group MADs
        def mad(x):
            med = np.median(x)
            return np.median(np.abs(x - med))
        
        group_mads = df.loc[valid].groupby(grp_key)['amount_numeric'].apply(mad)
        group_mads.name = '_grp_mad'
        
        # Compute group stats
        group_q25 = df.loc[valid].groupby(grp_key)['amount_numeric'].quantile(0.25)
        group_q25.name = '_grp_q25'
        group_q75 = df.loc[valid].groupby(grp_key)['amount_numeric'].quantile(0.75)
        group_q75.name = '_grp_q75'
        group_mean = df.loc[valid].groupby(grp_key)['amount_numeric'].mean()
        group_mean.name = '_grp_mean'
        
        # Merge all group stats
        stats = pd.concat([group_medians, group_mads, group_q25, group_q75, group_mean], axis=1)
        stats['_grp_iqr'] = stats['_grp_q75'] - stats['_grp_q25']
        
        # Merge back to main df
        df = df.merge(stats, left_on=grp_key, right_index=True, how='left', suffixes=('', '_stat'))
        
        # Fill baseline values
        mask = valid & df['_grp_median'].notna()
        df.loc[mask, 'peer_median'] = df.loc[mask, '_grp_median']
        df.loc[mask, 'peer_mean'] = df.loc[mask, '_grp_mean']
        df.loc[mask, 'peer_mad'] = df.loc[mask, '_grp_mad'].clip(lower=1.0)
        df.loc[mask, 'peer_iqr'] = df.loc[mask, '_grp_iqr']
        df.loc[mask, 'peer_q25'] = df.loc[mask, '_grp_q25']
        df.loc[mask, 'peer_q75'] = df.loc[mask, '_grp_q75']
        
        # Compute deviation ratio
        dev_mask = mask & (df['peer_median'] > 0)
        df.loc[dev_mask, 'deviation_ratio'] = df.loc[dev_mask, 'amount_numeric'] / df.loc[dev_mask, 'peer_median']
        
        # Compute percentile ranks per group
        for key, grp in df.loc[valid].groupby(grp_key):
            if len(grp) < 3:
                continue
            amounts = grp['amount_numeric'].dropna().values
            sorted_amounts = np.sort(amounts)
            for idx in grp.index:
                val = df.loc[idx, 'amount_numeric']
                if pd.notna(val):
                    rank = np.searchsorted(sorted_amounts, val)
                    df.loc[idx, 'peer_percentile'] = rank / len(sorted_amounts) * 100
        
        # Drop temp columns
        df.drop(columns=['_grp_median', '_grp_mad', '_grp_q25', '_grp_q75', '_grp_mean', '_grp_iqr'],
                inplace=True, errors='ignore')
        
        return df
    
    def get_context_for_record(self, record_idx: int) -> Dict[str, Any]:
        """Get full context for a single record."""
        row = self.df.loc[record_idx]
        
        return {
            'peer_group_size': int(row.get('peer_group_size', 0)),
            'peer_group_level': int(row.get('peer_group_level', 0)),
            'peer_group_key': str(row.get('peer_group_key', '')),
            'peer_group_level_name': self._level_name(int(row.get('peer_group_level', 0))),
            'peer_median': float(row.get('peer_median', 0)),
            'peer_mean': float(row.get('peer_mean', 0)),
            'peer_mad': float(row.get('peer_mad', 0)),
            'peer_iqr': float(row.get('peer_iqr', 0)),
            'peer_percentile': float(row.get('peer_percentile', 50)),
            'deviation_ratio': float(row.get('deviation_ratio', 0)),
            'project_amount': float(row.get('amount_numeric', 0)) if pd.notna(row.get('amount_numeric')) else None,
            'inferred_category': str(row.get('inferred_category', '')),
            'state': str(row.get('State', '')),
            'constituency': str(row.get('Constituency', '')),
            'year': int(row.get('year', 0)) if pd.notna(row.get('year')) else None,
        }
    
    @staticmethod
    def _level_name(level: int) -> str:
        names = {
            0: 'No peer group',
            1: 'State + Constituency + Category + Year',
            2: 'State + Category + Year',
            3: 'State + Category',
            4: 'National Category',
        }
        return names.get(level, 'Unknown')
