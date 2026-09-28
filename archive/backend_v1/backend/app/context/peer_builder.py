"""
Peer Group Builder (Optimized for 64K+ records)
Builds hierarchical peer groups with fallback levels for contextual comparison.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple


class PeerGroupBuilder:
    """Builds peer groups using hierarchical fallback for contextual baseline computation."""
    
    LEVELS = [
        ('State', 'Constituency', 'inferred_category', 'year'),
        ('State', 'inferred_category', 'year'),
        ('State', 'inferred_category'),
        ('inferred_category',),
    ]
    
    MIN_PEER_SIZE = 3
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
    
    def build_peer_groups(self) -> pd.DataFrame:
        """Assign each record to its best available peer group using vectorized ops."""
        df = self.df.copy()
        
        df['peer_group_level'] = 0
        df['peer_group_size'] = 0
        df['peer_group_key'] = ''
        
        for level_idx, group_cols in enumerate(self.LEVELS):
            available_cols = [c for c in group_cols if c in df.columns]
            if not available_cols:
                continue
            
            # Vectorized groupby + transform to get group sizes
            grp = df.groupby(available_cols)['Record ID'].transform('count')
            df['_temp_group_size'] = grp
            
            # Build group key
            df['_temp_group_key'] = df[available_cols].apply(
                lambda row: '|'.join(f'{c}={row[c]}' for c in available_cols), axis=1
            )
            
            # Assign to this level if: group is big enough AND record not yet assigned
            mask = (df['_temp_group_size'] >= self.MIN_PEER_SIZE) & (df['peer_group_size'] < self.MIN_PEER_SIZE)
            df.loc[mask, 'peer_group_level'] = level_idx + 1
            df.loc[mask, 'peer_group_size'] = df.loc[mask, '_temp_group_size']
            df.loc[mask, 'peer_group_key'] = df.loc[mask, '_temp_group_key']
        
        df.drop(columns=['_temp_group_size', '_temp_group_key'], inplace=True, errors='ignore')
        return df
