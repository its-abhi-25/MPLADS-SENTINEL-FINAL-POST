"""
Stage Consistency Feature Engine
Analyzes lifecycle patterns using available stages:
RECOMMENDED, SANCTIONED, COMPLETED.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any


class LifecycleEngine:
    """Detects stage consistency anomalies."""
    
    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add lifecycle scores and explanations."""
        df = df.copy()
        
        for col in ['lifecycle_score', 'lifecycle_explanation']:
            if col not in df.columns:
                df[col] = 0.0 if '_score' in col else ''
        
        if 'Stage' not in df.columns:
            return df
        
        # Group by MP+Constituency and analyze stage patterns
        stage_groups = df.groupby(['MP', 'Constituency'])['Stage'].apply(set).reset_index()
        stage_groups.columns = ['MP', 'Constituency', 'stages']
        
        # Find MP+Constituency combos with incomplete lifecycle
        # SANCTIONED but no COMPLETED
        sanctioned_no_complete = stage_groups[
            stage_groups['stages'].apply(lambda x: 'SANCTIONED' in x and 'COMPLETED' not in x)
        ]
        
        if len(sanctioned_no_complete) > 0:
            merge = df.merge(sanctioned_no_complete[['MP', 'Constituency']], 
                           on=['MP', 'Constituency'], how='inner')
            san_mask = merge['Stage'] == 'SANCTIONED'
            df.loc[merge.index[san_mask], 'lifecycle_score'] = 0.3
            df.loc[merge.index[san_mask], 'lifecycle_explanation'] = (
                'SANCTIONED but not yet COMPLETED for this MP+Constituency'
            )
        
        # COMPLETED without SANCTIONED
        complete_no_sanitize = stage_groups[
            stage_groups['stages'].apply(
                lambda x: 'COMPLETED' in x and 'SANCTIONED' not in x and 'RECOMMENDED' not in x
            )
        ]
        
        if len(complete_no_sanitize) > 0:
            merge2 = df.merge(complete_no_sanitize[['MP', 'Constituency']], 
                            on=['MP', 'Constituency'], how='inner')
            complete_mask = merge2['Stage'] == 'COMPLETED'
            df.loc[merge2.index[complete_mask], 'lifecycle_score'] = np.maximum(
                df.loc[merge2.index[complete_mask], 'lifecycle_score'], 0.4
            )
            df.loc[merge2.index[complete_mask], 'lifecycle_explanation'] = (
                'COMPLETED without SANCTIONED record'
            )
        
        # RECOMMENDED while COMPLETED works exist
        has_complete = stage_groups[
            stage_groups['stages'].apply(lambda x: 'COMPLETED' in x)
        ]
        
        if len(has_complete) > 0:
            merge3 = df.merge(has_complete[['MP', 'Constituency']], 
                            on=['MP', 'Constituency'], how='inner')
            rec_mask = merge3['Stage'] == 'RECOMMENDED'
            existing = df.loc[merge3.index[rec_mask], 'lifecycle_score']
            new_mask = rec_mask & (existing.fillna(0) < 0.2)
            df.loc[merge3.index[new_mask], 'lifecycle_score'] = 0.2
            df.loc[merge3.index[new_mask], 'lifecycle_explanation'] = (
                'RECOMMENDED while COMPLETED works exist for same MP+Constituency'
            )
        
        return df
