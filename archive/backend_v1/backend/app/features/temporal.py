"""
Temporal Pattern Feature Engine
Detects unusual temporal clustering of works.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any


class TemporalEngine:
    """Detects temporal anomaly patterns."""
    
    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add temporal scores and explanations."""
        df = df.copy()
        
        for col in ['temporal_score', 'temporal_explanation']:
            if col not in df.columns:
                df[col] = 0.0 if '_score' in col else ''
        
        if 'date_parsed' not in df.columns:
            return df
        
        valid = df['date_parsed'].notna()
        if valid.sum() == 0:
            return df
        
        # Date-level clustering
        df = self._detect_date_spikes(df, valid)
        
        # Quarter-level clustering
        df = self._detect_quarter_spikes(df, valid)
        
        return df
    
    def _detect_date_spikes(self, df: pd.DataFrame, valid: pd.Series) -> pd.DataFrame:
        """Detect dates with unusually many works."""
        date_counts = df[valid]['date_parsed'].value_counts()
        avg = date_counts.mean()
        spike_dates = date_counts[date_counts > avg * 3]
        
        for date_val, count in spike_dates.items():
            if count < 10:
                continue
            mask = df['date_parsed'] == date_val
            score = min(1.0, (count - avg) / (avg * 4))
            df.loc[mask, 'temporal_score'] = np.maximum(
                df.loc[mask, 'temporal_score'], score
            )
            df.loc[mask, 'temporal_explanation'] = (
                f"{count} works on {date_val.strftime('%d/%m/%Y')} (average: {avg:.0f})"
            )
        
        return df
    
    def _detect_quarter_spikes(self, df: pd.DataFrame, valid: pd.Series) -> pd.DataFrame:
        """Detect quarters with unusually many works for an MP."""
        if 'year' not in df.columns or 'quarter' not in df.columns:
            return df
        
        mp_quarter = df[valid].groupby(['MP', 'year', 'quarter']).agg(
            count=('Record ID', 'count'),
            amount=('amount_numeric', lambda x: x.dropna().sum()),
            indices=('Record ID', list)
        ).reset_index()
        
        avg = mp_quarter['count'].mean()
        if avg <= 0:
            return df
        
        spikes = mp_quarter[mp_quarter['count'] > avg * 4]
        
        for _, row in spikes.iterrows():
            if row['count'] < 5:
                continue
            for idx in row['indices']:
                if idx in df.index:
                    score = min(1.0, (row['count'] - avg) / (avg * 5))
                    df.loc[idx, 'temporal_score'] = max(df.loc[idx, 'temporal_score'], score)
                    df.loc[idx, 'temporal_explanation'] = (
                        f"MP has {row['count']} works in {row['year']}/{row['quarter']} "
                        f"(average: {avg:.0f})"
                    )
        
        return df
