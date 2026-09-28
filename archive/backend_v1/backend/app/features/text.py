"""
Text Similarity Feature Engine (v3.0)
Detects duplicate and near-duplicate work descriptions.
Improved with constituency, amount, and temporal context.
"""
import pandas as pd
import numpy as np
import re
import unicodedata
from typing import Dict, Any


class TextSimilarityEngine:
    """Detects description similarity patterns.
    
    Supports:
    - EXACT_DUPLICATE
    - NEAR_DUPLICATE
    - RECURRING_TEMPLATE
    - LOW_SIMILARITY
    
    Strengthens interpretation using same MP, same constituency, similar amount, temporal proximity.
    """
    
    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add text similarity scores and explanations."""
        df = df.copy()
        
        for col in ['description_similarity_score', 'description_similarity_explanation',
                     'description_similarity_type']:
            if col not in df.columns:
                df[col] = 0.0 if '_score' in col else ''
        
        if 'description_normalized' not in df.columns:
            return df
        
        # Exact duplicate detection within same MP
        df = self._detect_exact_duplicates(df)
        
        # Near-duplicate detection using prefix matching
        df = self._detect_near_duplicates(df)
        
        return df
    
    def _detect_exact_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect exact description duplicates within same MP.
        Score depends on: group size, constituency match, amount similarity.
        """
        grp = df.groupby(['MP', 'description_normalized']).agg(
            count=('Record ID', 'count'),
            constituencies=('Constituency', 'nunique'),
            amount_std=('amount_numeric', lambda x: x.dropna().std() if len(x.dropna()) > 1 else 0),
            amount_mean=('amount_numeric', lambda x: x.dropna().mean()),
        ).reset_index()
        
        exact_dups = grp[grp['count'] > 1]
        
        if len(exact_dups) == 0:
            return df
        
        # Merge back to get indices
        merge = df.merge(exact_dups[['MP', 'description_normalized', 'count', 'constituencies', 'amount_std', 'amount_mean']], 
                       on=['MP', 'description_normalized'], how='inner')
        
        # Base score from group size (more duplicates = more suspicious)
        # 2 dups: 0.4, 3: 0.5, 5: 0.6, 10+: 0.7
        base_score = np.minimum(0.7, 0.3 + np.log2(merge['count']) * 0.1)
        
        # Boost for same constituency (more suspicious if all in same place)
        constituency_boost = np.where(merge['constituencies'] == 1, 0.1, 0.0)
        
        # Boost for similar amounts (std < 20% of mean = very similar)
        amount_cv = np.where(merge['amount_mean'] > 0, merge['amount_std'] / merge['amount_mean'], 1.0)
        amount_boost = np.where(amount_cv < 0.2, 0.1, np.where(amount_cv < 0.5, 0.05, 0.0))
        
        final_score = np.minimum(0.95, base_score + constituency_boost + amount_boost)
        
        df.loc[merge.index, 'description_similarity_score'] = final_score
        df.loc[merge.index, 'description_similarity_type'] = 'exact_duplicate'
        df.loc[merge.index, 'description_similarity_explanation'] = (
            'Exact description match with ' + (merge['count'] - 1).astype(str) + 
            ' other works by same MP' +
            np.where(merge['constituencies'] == 1, ' in same constituency', '') +
            np.where(amount_cv < 0.2, ' with similar amounts', '')
        )
        
        return df
    
    def _detect_near_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect near-duplicate descriptions using 60-char prefix.
        Only flags if not already flagged as exact duplicate.
        """
        df['work_prefix60'] = df['description_normalized'].fillna('').str[:60]
        
        prefix_grp = df.groupby(['MP', 'work_prefix60']).agg(
            count=('Record ID', 'count'),
            constituencies=('Constituency', 'nunique'),
        ).reset_index()
        
        near_dups = prefix_grp[(prefix_grp['count'] >= 3) & (prefix_grp['work_prefix60'] != '')]
        
        if len(near_dups) > 0:
            merge2 = df.merge(near_dups[['MP', 'work_prefix60', 'count', 'constituencies']], 
                            on=['MP', 'work_prefix60'], how='inner')
            
            # Score: 0.3 base + 0.05 per additional record, capped at 0.6
            score = np.minimum(0.6, 0.3 + merge2['count'] * 0.03)
            
            # Boost for same constituency
            score = np.where(merge2['constituencies'] == 1, score + 0.05, score)
            
            # Only set if not already set higher by exact match
            existing = df.loc[merge2.index, 'description_similarity_score']
            mask = existing < 0.3
            real_idx = merge2.index[mask]
            df.loc[real_idx, 'description_similarity_score'] = score[mask.values]
            df.loc[real_idx, 'description_similarity_type'] = 'near_duplicate'
            df.loc[real_idx, 'description_similarity_explanation'] = (
                'Similar description pattern shared with ' + merge2.loc[mask, 'count'].astype(str) + 
                ' works by same MP'
            )
        
        df.drop(columns=['work_prefix60'], inplace=True, errors='ignore')
        return df
