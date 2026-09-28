"""
Statistical Baselines
Computes robust statistical baselines for peer group comparison.
Uses median, MAD, IQR instead of mean/z-score for non-normal distributions.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple


class BaselineComputer:
    """Computes robust statistical baselines for peer groups."""
    
    @staticmethod
    def compute_amount_baseline(amounts: pd.Series) -> Dict[str, Any]:
        """Compute robust baseline for a set of amounts."""
        if len(amounts) < 2:
            return {
                'median': float(amounts.iloc[0]) if len(amounts) == 1 else 0,
                'mean': float(amounts.mean()) if len(amounts) > 0 else 0,
                'mad': 0,
                'iqr': 0,
                'q25': 0,
                'q75': 0,
                'count': len(amounts),
                'min': float(amounts.min()) if len(amounts) > 0 else 0,
                'max': float(amounts.max()) if len(amounts) > 0 else 0,
            }
        
        median = float(amounts.median())
        mad = float(np.median(np.abs(amounts - median)))
        q25 = float(amounts.quantile(0.25))
        q75 = float(amounts.quantile(0.75))
        iqr = q75 - q25
        
        return {
            'median': median,
            'mean': float(amounts.mean()),
            'mad': mad,
            'iqr': iqr,
            'q25': q25,
            'q75': q75,
            'count': len(amounts),
            'min': float(amounts.min()),
            'max': float(amounts.max()),
        }
    
    @staticmethod
    def compute_deviation_score(value: float, baseline: Dict[str, Any]) -> float:
        """
        Compute how deviant a value is from the baseline.
        Returns score from 0 to 1.
        """
        if baseline['count'] < 2:
            return 0.0
        
        median = baseline['median']
        mad = baseline['mad']
        iqr = baseline['iqr']
        
        if median == 0:
            return 0.0
        
        # Deviation ratio from median
        dev_ratio = abs(value - median) / median if median > 0 else 0
        
        # MAD-based z-score (robust)
        if mad > 0:
            mad_z = abs(value - median) / mad
        else:
            mad_z = 0
        
        # IQR-based score
        if iqr > 0:
            iqr_score = max(0, (value - baseline['q75']) / iqr) if value > baseline['q75'] else 0
            iqr_score += max(0, (baseline['q25'] - value) / iqr) if value < baseline['q25'] else 0
        else:
            iqr_score = 0
        
        # Combine: use the more extreme of the measures
        # Map to 0-1 scale
        # At dev_ratio=2.0 (2x median), score ≈ 0.5
        # At dev_ratio=5.0 (5x median), score ≈ 0.9+
        ratio_score = min(1.0, max(0.0, (dev_ratio - 1.0) / 4.0))
        mad_score = min(1.0, max(0.0, (mad_z - 2.0) / 6.0))
        
        return min(1.0, max(ratio_score, mad_score, iqr_score * 0.5))
    
    @staticmethod
    def compute_percentile_rank(value: float, amounts: pd.Series) -> float:
        """Compute percentile rank of value within amounts."""
        if len(amounts) == 0:
            return 50.0
        sorted_amounts = np.sort(amounts.dropna().values)
        rank = np.searchsorted(sorted_amounts, value)
        return float(rank / len(sorted_amounts) * 100)
    
    @staticmethod
    def compute_concentration_baseline(counts: pd.Series) -> Dict[str, Any]:
        """Compute baseline for concentration analysis."""
        if len(counts) < 2:
            return {'mean': float(counts.mean()) if len(counts) > 0 else 0, 'median': 0, 'mad': 0, 'count': len(counts)}
        
        return {
            'mean': float(counts.mean()),
            'median': float(counts.median()),
            'mad': float(np.median(np.abs(counts - counts.median()))),
            'count': len(counts),
        }
