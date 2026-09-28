"""
Concentration Feature Engines (Split)
MP_CONCENTRATION: Measures unusual concentration of works by MP in a category.
CONSTITUENCY_PATTERN: Analyzes constituency-level patterns in categories and amounts.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any


class ConcentrationEngine:
    """Detects unusual concentration patterns - now produces two separate signals."""
    
    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add mp_concentration_score, constituency_pattern_score and explanations."""
        df = df.copy()
        
        for col in ['mp_concentration_score', 'mp_concentration_explanation',
                     'constituency_pattern_score', 'constituency_pattern_explanation']:
            if col not in df.columns:
                df[col] = 0.0 if '_score' in col else ''
        
        # MP + Category concentration
        df = self._compute_mp_concentration(df)
        
        # Constituency + Category pattern
        df = self._compute_constituency_pattern(df)
        
        return df
    
    def _compute_mp_concentration(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect unusual concentration of works by MP in a category."""
        mp_cat = df.groupby(['MP', 'inferred_category']).agg(
            cnt=('Record ID', 'count'),
            amount_sum=('amount_numeric', lambda x: x.dropna().sum()),
            amount_mean=('amount_numeric', lambda x: x.dropna().mean()),
        ).reset_index()
        
        # Compute national average per MP+Category
        avg = mp_cat['cnt'].mean()
        if avg <= 0:
            return df
        
        mp_cat['ratio'] = mp_cat['cnt'] / avg
        # Score: ratio > 3 means 3x average, score grows to 1.0 at ~8x
        mp_cat['score'] = np.minimum(1.0, np.maximum(0.0, (mp_cat['ratio'] - 3) / 5))
        
        flagged_mp = mp_cat[mp_cat['score'] > 0.1]
        
        if len(flagged_mp) > 0:
            merge = df.merge(flagged_mp[['MP', 'inferred_category', 'score', 'cnt', 'ratio']],
                           on=['MP', 'inferred_category'], how='inner')
            df.loc[merge.index, 'mp_concentration_score'] = merge['score'].values
            df.loc[merge.index, 'mp_concentration_explanation'] = (
                "MP '" + merge['MP'] + "' has " + merge['cnt'].astype(str) +
                " '" + merge['inferred_category'] + "' works " +
                "(avg: " + avg.round(0).astype(str) + ", ratio: " + merge['ratio'].round(1).astype(str) + "x)"
            ).values
        
        return df
    
    def _compute_constituency_pattern(self, df: pd.DataFrame) -> pd.DataFrame:
        """Analyze constituency-level patterns: repeated categories, unusual distributions."""
        # Pattern 1: Constituency with unusually high concentration in one category
        const_cat = df.groupby(['Constituency', 'inferred_category']).agg(
            cnt=('Record ID', 'count'),
            amount_sum=('amount_numeric', lambda x: x.dropna().sum()),
            amount_mean=('amount_numeric', lambda x: x.dropna().mean()),
            unique_mps=('MP', 'nunique'),
        ).reset_index()
        
        # Compute constituency total works
        const_total = df.groupby('Constituency').agg(
            total=('Record ID', 'count'),
        ).reset_index()
        
        const_cat = const_cat.merge(const_total, on='Constituency', how='left')
        
        # Category dominance: what fraction of constituency works are in this category
        const_cat['category_fraction'] = const_cat['cnt'] / const_cat['total'].clip(lower=1)
        
        # National average category fraction
        national_avg_frac = const_cat['category_fraction'].mean()
        
        # Score when a category dominates a constituency unusually
        const_cat['dominance_score'] = np.minimum(1.0, np.maximum(0.0,
            (const_cat['category_fraction'] - 0.5) / 0.4
        ))
        
        # Pattern 2: Unusual amount patterns per constituency+category
        # Compare mean amount in this constituency+category vs national
        national_cat_avg = df.groupby('inferred_category')['amount_numeric'].mean()
        const_cat['national_avg'] = const_cat['inferred_category'].map(national_cat_avg)
        const_cat['amount_ratio'] = np.where(
            const_cat['national_avg'] > 0,
            const_cat['amount_mean'] / const_cat['national_avg'],
            1.0
        )
        const_cat['amount_anomaly'] = np.minimum(1.0, np.maximum(0.0,
            (const_cat['amount_ratio'].abs() - 2.0) / 4.0
        ))
        
        # Combined constituency pattern score
        const_cat['score'] = np.maximum(const_cat['dominance_score'], const_cat['amount_anomaly'] * 0.5)
        
        flagged = const_cat[const_cat['score'] > 0.1]
        
        if len(flagged) > 0:
            merge = df.merge(flagged[['Constituency', 'inferred_category', 'score', 'cnt', 
                                       'category_fraction', 'amount_ratio']],
                           on=['Constituency', 'inferred_category'], how='inner')
            df.loc[merge.index, 'constituency_pattern_score'] = merge['score'].values
            df.loc[merge.index, 'constituency_pattern_explanation'] = (
                merge['Constituency'] + ": " + merge['cnt'].astype(str) + " '" + 
                merge['inferred_category'] + "' works (" + 
                (merge['category_fraction'] * 100).round(0).astype(str) + "% of total, " +
                "amount ratio: " + merge['amount_ratio'].round(1).astype(str) + "x national avg)"
            ).values
        
        return df
