"""
Cost Anomaly Feature Engine (v3.0, Vectorized)
Detects whether a project amount is unusual relative to its contextual peer group.
Uses nonlinear deviation magnitude, peer dispersion, and peer count.
Optimized for 64K+ records using vectorized pandas operations.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any


# Deviation cap for log transformation - at 90x ratio, score approaches 1.0
DEVIATION_CAP = 100.0


class CostAnomalyEngine:
    """Computes cost anomaly signals using peer-group context.
    
    The cost anomaly depends on THREE separate factors:
    1. Deviation Magnitude (how far from peer median)
    2. Peer Dispersion (how tightly clustered the peers are)
    3. Peer Count (how reliable the contextual comparison is)
    """
    
    def compute_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add cost anomaly scores and detailed explanations to the dataframe.
        Uses vectorized operations for performance on 64K+ records.
        """
        df = df.copy()
        
        # Initialize all required output columns
        for col in ['cost_anomaly_score', 'cost_anomaly_explanation',
                     'cost_deviation_component', 'cost_dispersion_component',
                     'cost_peer_reliability', 'cost_robust_distance']:
            if col not in df.columns:
                df[col] = 0.0 if '_score' in col or '_component' in col or '_reliability' in col or '_distance' in col else ''
        
        valid = df['amount_numeric'].notna() & (df['peer_group_size'] >= 3)
        
        if valid.sum() == 0:
            return df
        
        amount = df.loc[valid, 'amount_numeric'].astype(float)
        peer_median = df.loc[valid, 'peer_median'].astype(float)
        peer_mad = df.loc[valid, 'peer_mad'].astype(float)
        peer_iqr = df.loc[valid, 'peer_iqr'].astype(float)
        peer_group_size = df.loc[valid, 'peer_group_size'].astype(float)
        peer_level = df.loc[valid, 'peer_group_level'].astype(int)
        
        # Avoid division by zero
        safe_median = peer_median.clip(lower=1.0)
        ratio = amount / safe_median
        
        # ─── COMPONENT 1: Deviation Magnitude (vectorized) ─────────
        # Nonlinear/logarithmic transformation
        # At 1.0x: ~0, 1.2x: low, 2x: moderate, 5x: high, 10x+: very high
        deviation_component = np.where(
            ratio > 1.0,
            np.minimum(1.0, np.log(1 + ratio) / np.log(1 + DEVIATION_CAP)),
            0.0
        )
        
        # ─── COMPONENT 2: Dispersion Relationship (vectorized) ─────
        # Robust distance: how many MADs away from median
        safe_mad = peer_mad.clip(lower=1.0)
        robust_distance = np.abs(amount - peer_median) / safe_mad
        
        # Dispersion component: stronger anomaly when far outside a tight distribution
        dispersion_component = np.minimum(1.0, robust_distance / 15.0)
        
        # ─── COMPONENT 3: Peer Reliability (vectorized) ────────────
        # Bounded/saturating function of peer count
        peer_reliability = np.minimum(1.0, np.log(1 + peer_group_size) / np.log(1 + 80))
        
        # Peer group level bonus: more specific = more reliable
        level_bonus = peer_level.map({1: 0.05, 2: 0.03, 3: 0.01, 4: 0.0}).fillna(0)
        peer_reliability = np.minimum(1.0, peer_reliability + level_bonus)
        
        # ─── COMBINE COMPONENTS (vectorized) ───────────────────────
        signal_score = deviation_component * 0.6 + dispersion_component * 0.3 + peer_reliability * 0.1
        signal_score = np.clip(signal_score, 0, 1)
        
        # Assign results
        df.loc[valid, 'cost_anomaly_score'] = signal_score
        df.loc[valid, 'cost_deviation_component'] = deviation_component
        df.loc[valid, 'cost_dispersion_component'] = dispersion_component
        df.loc[valid, 'cost_peer_reliability'] = peer_reliability
        df.loc[valid, 'cost_robust_distance'] = robust_distance
        
        # Generate explanations (vectorized string operations)
        level_names = {1: 'State+Constituency+Category+Year', 2: 'State+Category+Year',
                       3: 'State+Category', 4: 'National Category'}
        df.loc[valid, 'cost_anomaly_explanation'] = self._build_explanations_vectorized(
            ratio.values, robust_distance.values, peer_group_size.values,
            peer_median.values, peer_level.values, df.loc[valid, 'cost_anomaly_explanation']
        )
        
        return df
    
    @staticmethod
    def _build_explanations_vectorized(ratio: np.ndarray, robust_dist: np.ndarray,
                                        peer_size: np.ndarray, peer_median: np.ndarray,
                                        peer_level: np.ndarray, existing: pd.Series) -> pd.Series:
        """Build explanations using vectorized string operations."""
        level_names = {1: 'State+Constituency+Category+Year', 2: 'State+Category+Year',
                       3: 'State+Category', 4: 'National Category'}
        
        explanations = []
        for i in range(len(ratio)):
            r = ratio[i]
            rd = robust_dist[i]
            ps = int(peer_size[i])
            pm = peer_median[i]
            pl = int(peer_level[i])
            ln = level_names.get(pl, 'peer group')
            
            # Dispersion description
            if rd < 2:
                disp = "a moderately dispersed peer distribution"
            elif rd < 5:
                disp = "a relatively tight peer distribution"
            elif rd < 15:
                disp = "a tightly clustered peer distribution"
            else:
                disp = "an extremely tight peer distribution"
            
            # Format ratio
            if r >= 10:
                r_str = f"{r:.0f}"
            elif r >= 2:
                r_str = f"{r:.1f}"
            else:
                r_str = f"{r:.2f}"
            
            # Distance label
            if rd < 2:
                dist_label = "slightly outside the normal range"
            elif rd < 5:
                dist_label = "notably outside the peer distribution"
            elif rd < 15:
                dist_label = "far outside the peer distribution"
            elif rd < 50:
                dist_label = "extremely far outside the peer distribution"
            else:
                dist_label = "approaching the extreme edge of the peer distribution"
            
            explanations.append(
                f"Project amount is {r_str}x the contextual peer median of "
                f"Rs.{pm:,.0f} and lies {dist_label} "
                f"{disp} ({ps} peers at {ln} level)."
            )
        
        return pd.Series(explanations, index=existing.index)
