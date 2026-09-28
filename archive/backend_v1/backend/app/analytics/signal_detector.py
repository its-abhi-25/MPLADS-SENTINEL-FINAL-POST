"""
Anomaly Signal Detection Service - Optimized for 64K+ records
All signals use vectorized pandas operations for speed.
"""
import pandas as pd
import numpy as np
import re
import unicodedata


class SignalDetector:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def detect_all_signals(self) -> pd.DataFrame:
        df = self.df.copy()

        for col in ['cost_anomaly_score', 'cost_anomaly_explanation',
                     'peer_group_size', 'peer_median', 'peer_percentile', 'deviation_ratio',
                     'duplicate_score', 'duplicate_explanation', 'duplicate_group',
                     'constituency_concentration_score', 'constituency_concentration_explanation',
                     'mp_concentration_score', 'mp_concentration_explanation',
                     'temporal_score', 'temporal_explanation',
                     'lifecycle_score', 'lifecycle_explanation',
                     'data_quality_score', 'data_quality_explanation']:
            if col not in df.columns:
                if '_score' in col:
                    df[col] = 0.0
                elif '_group' in col:
                    df[col] = -1
                else:
                    df[col] = ''

        df = self._detect_cost_anomalies(df)
        df = self._detect_duplicates_fast(df)
        df = self._detect_concentration_fast(df)
        df = self._detect_temporal_fast(df)
        df = self._detect_lifecycle(df)
        df = self._detect_data_quality(df)

        self.df = df
        return df

    def _detect_cost_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'amount_numeric' not in df.columns:
            return df
        valid = df['amount_numeric'].notna()
        if valid.sum() == 0:
            return df

        grp = df[valid].groupby(['Constituency', 'inferred_category'])['amount_numeric']
        stats = grp.agg(['median', 'count']).reset_index()
        stats = stats[stats['count'] >= 3]
        if len(stats) == 0:
            return df

        grp_mad = grp.apply(lambda x: np.median(np.abs(x - np.median(x)))).reset_index()
        grp_mad.columns = ['Constituency', 'inferred_category', 'mad']
        grp_mad['mad'] = grp_mad['mad'].clip(lower=1.0)

        stats = stats.merge(grp_mad, on=['Constituency', 'inferred_category'], how='left')
        stats['mad'] = stats['mad'].fillna(1.0)

        merge_cols = ['Constituency', 'inferred_category', 'median', 'count', 'mad']
        df = df.merge(stats[merge_cols], on=['Constituency', 'inferred_category'], how='left', suffixes=('', '_peer'))

        valid_mask = valid & df['median'].notna()
        if valid_mask.sum() > 0:
            amt = df.loc[valid_mask, 'amount_numeric']
            med = df.loc[valid_mask, 'median']
            mad = df.loc[valid_mask, 'mad']

            dev_ratio = amt / med
            z = (amt - med).abs() / mad

            score = pd.Series(0.0, index=df.index)
            cond_high = (amt > med * 5) | (z > 6)
            score[valid_mask] = np.where(
                cond_high,
                np.minimum(1.0, np.maximum(
                    np.where(dev_ratio > 5, (dev_ratio - 5) / 5, 0),
                    np.where(z > 6, (z - 6) / 6, 0)
                )),
                0.0
            )

            pct = pd.Series(0.0, index=df.index)
            overall_amounts = np.sort(df.loc[valid, 'amount_numeric'].values)
            pct[valid_mask] = np.searchsorted(overall_amounts, amt.values) / len(overall_amounts) * 100

            df['cost_anomaly_score'] = score
            df['peer_group_size'] = df['count'].fillna(0).astype(int)
            df['peer_median'] = df['median'].fillna(0)
            df['peer_percentile'] = pct
            df['deviation_ratio'] = dev_ratio.fillna(0)

            explain_mask = score > 0.1
            df.loc[explain_mask, 'cost_anomaly_explanation'] = (
                'Rs.' + df.loc[explain_mask, 'amount_numeric'].round(0).astype(str) +
                ' vs peer median Rs.' + df.loc[explain_mask, 'median'].round(0).astype(str) +
                ' (' + df.loc[explain_mask, 'deviation_ratio'].round(1).astype(str) + 'x)'
            )

        df.drop(columns=['median', 'count', 'mad'], inplace=True, errors='ignore')
        return df

    def _detect_duplicates_fast(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'description_normalized' not in df.columns:
            return df

        grp = df.groupby(['MP', 'description_normalized']).size().reset_index(name='cnt')
        exact = grp[grp['cnt'] > 1][['MP', 'description_normalized']]
        if len(exact) > 0:
            merge = df.merge(exact, on=['MP', 'description_normalized'], how='inner')
            df.loc[merge.index, 'duplicate_score'] = 0.95
            df.loc[merge.index, 'duplicate_explanation'] = 'Exact description match within same MP'

        df['work_prefix60'] = df['description_normalized'].fillna('').str[:60]
        prefix_grp = df.groupby(['MP', 'work_prefix60']).size().reset_index(name='cnt')
        prefix_dup = prefix_grp[(prefix_grp['cnt'] >= 3) & (prefix_grp['work_prefix60'] != '')]
        if len(prefix_dup) > 0:
            merge2 = df.merge(prefix_dup, on=['MP', 'work_prefix60'], how='inner')
            score = np.minimum(0.7, 0.3 + merge2['cnt'] * 0.05)
            mask = df.loc[merge2.index, 'duplicate_score'] < 0.5
            real_idx = merge2.index[mask]
            df.loc[real_idx, 'duplicate_score'] = score[mask.values]
            df.loc[real_idx, 'duplicate_explanation'] = (
                'Similar prefix pattern (' + merge2.loc[mask, 'cnt'].astype(str) + ' works)'
            )

        df.drop(columns=['work_prefix60'], inplace=True, errors='ignore')
        return df

    def _detect_concentration_fast(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'amount_numeric' not in df.columns:
            return df

        const_cat = df.groupby(['Constituency', 'inferred_category']).agg(
            cnt=('Record ID', 'count')
        ).reset_index()
        avg = const_cat['cnt'].mean()
        const_cat['ratio'] = const_cat['cnt'] / avg
        const_cat['score'] = np.minimum(1.0, np.maximum(0.0, (const_cat['ratio'] - 3) / 4))
        flagged = const_cat[const_cat['score'] > 0.1]
        if len(flagged) > 0:
            merge = df.merge(flagged[['Constituency', 'inferred_category', 'score', 'cnt', 'ratio']],
                           on=['Constituency', 'inferred_category'], how='inner')
            df.loc[merge.index, 'constituency_concentration_score'] = merge['score'].values
            df.loc[merge.index, 'constituency_concentration_explanation'] = (
                merge['cnt'].astype(str) + ' works in ' + merge['Constituency'] + '/' + merge['inferred_category'] +
                ' (avg: ' + avg.round(0).astype(str) + ')'
            ).values

        mp_cat = df.groupby(['MP', 'inferred_category']).agg(
            cnt=('Record ID', 'count')
        ).reset_index()
        avg_mp = mp_cat['cnt'].mean()
        mp_cat['ratio'] = mp_cat['cnt'] / avg_mp
        mp_cat['score'] = np.minimum(1.0, np.maximum(0.0, (mp_cat['ratio'] - 3) / 5))
        flagged_mp = mp_cat[mp_cat['score'] > 0.1]
        if len(flagged_mp) > 0:
            merge2 = df.merge(flagged_mp[['MP', 'inferred_category', 'score', 'cnt']],
                            on=['MP', 'inferred_category'], how='inner')
            df.loc[merge2.index, 'mp_concentration_score'] = merge2['score'].values
            df.loc[merge2.index, 'mp_concentration_explanation'] = (
                "MP '" + merge2['MP'] + "' has " + merge2['cnt'].astype(str) +
                " '" + merge2['inferred_category'] + "' works (avg: " + avg_mp.round(0).astype(str) + ")"
            ).values

        return df

    def _detect_temporal_fast(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'date_parsed' not in df.columns:
            return df
        valid = df['date_parsed'].notna()
        if valid.sum() == 0:
            return df

        date_counts = df[valid]['date_parsed'].value_counts()
        avg = date_counts.mean()
        spike_dates = date_counts[date_counts > avg * 3]

        if len(spike_dates) > 0:
            for date_val, count in spike_dates.items():
                if count < 10:
                    continue
                mask = df['date_parsed'] == date_val
                score = min(1.0, (count - avg) / (avg * 4))
                df.loc[mask, 'temporal_score'] = score
                df.loc[mask, 'temporal_explanation'] = f"{count} works on {date_val.strftime('%d/%m/%Y')} (avg: {avg:.0f})"

        return df

    def _detect_lifecycle(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'Stage' not in df.columns:
            return df

        # Map stages to lifecycle concept:
        # RECOMMENDED (new) ≈ unsanctioned - works not yet sanctioned
        # SANCTIONED - works approved
        # COMPLETED - works done

        stage_set = df.groupby(['MP', 'Constituency'])['Stage'].apply(set).reset_index()

        # Check for full lifecycle: has both RECOMMENDED and SANCTIONED and COMPLETED
        stage_set['has_full_lifecycle'] = stage_set['Stage'].apply(
            lambda x: bool({'RECOMMENDED', 'SANCTIONED', 'COMPLETED'}.intersection(x))
            and 'SANCTIONED' in x and 'COMPLETED' in x
        )

        # Check for incomplete: SANCTIONED but no COMPLETED
        stage_set['has_sanctioned_no_complete'] = stage_set['Stage'].apply(
            lambda x: 'SANCTIONED' in x and 'COMPLETED' not in x
        )

        # Check for unusual: COMPLETED without SANCTIONED (or RECOMMENDED)
        stage_set['has_complete_no_sanitize'] = stage_set['Stage'].apply(
            lambda x: 'COMPLETED' in x and 'SANCTIONED' not in x and 'RECOMMENDED' not in x
        )

        # Flag works with SANCTIONED but no COMPLETED
        incomplete_san = stage_set[stage_set['has_sanctioned_no_complete']]
        if len(incomplete_san) > 0:
            merge = df.merge(incomplete_san[['MP', 'Constituency']], on=['MP', 'Constituency'], how='inner')
            san_mask = merge['Stage'] == 'SANCTIONED'
            df.loc[merge.index[san_mask], 'lifecycle_score'] = 0.3
            df.loc[merge.index[san_mask], 'lifecycle_explanation'] = 'SANCTIONED but not yet COMPLETED'

        # Flag works that completed without going through sanctioning
        no_sanitize = stage_set[stage_set['has_complete_no_sanitize']]
        if len(no_sanitize) > 0:
            merge2 = df.merge(no_sanitize[['MP', 'Constituency']], on=['MP', 'Constituency'], how='inner')
            complete_mask = merge2['Stage'] == 'COMPLETED'
            df.loc[merge2.index[complete_mask], 'lifecycle_score'] = 0.4
            df.loc[merge2.index[complete_mask], 'lifecycle_explanation'] = 'COMPLETED without SANCTIONED record'

        # Flag RECOMMENDED works where same MP+Constituency has COMPLETED works
        # This could indicate works stuck in pipeline
        has_complete = stage_set[stage_set['Stage'].apply(lambda x: 'COMPLETED' in x)]
        if len(has_complete) > 0:
            merge3 = df.merge(has_complete[['MP', 'Constituency']], on=['MP', 'Constituency'], how='inner')
            rec_mask = merge3['Stage'] == 'RECOMMENDED'
            existing_score = df.loc[merge3.index[rec_mask], 'lifecycle_score']
            # Only set if not already flagged higher
            new_mask = rec_mask & (existing_score.fillna(0) < 0.2)
            df.loc[merge3.index[new_mask], 'lifecycle_score'] = 0.2
            df.loc[merge3.index[new_mask], 'lifecycle_explanation'] = 'RECOMMENDED while COMPLETED works exist for same MP+Constituency'

        return df

    def _detect_data_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        df['data_quality_score'] = 0.0
        df['data_quality_explanation'] = ''

        if 'amount_numeric' in df.columns:
            very_low = df['amount_numeric'] < 10000
            df.loc[very_low, 'data_quality_score'] = 0.3
            df.loc[very_low, 'data_quality_explanation'] = 'Very low amount (<Rs.10,000)'

        dup_desc = df.duplicated(subset=['Work Description'], keep=False)
        df.loc[dup_desc, 'data_quality_score'] = df.loc[dup_desc, 'data_quality_score'].clip(lower=0) + 0.2
        df.loc[dup_desc, 'data_quality_explanation'] = df.loc[dup_desc, 'data_quality_explanation'].fillna('') + 'Exact description duplicate'

        df['data_quality_score'] = df['data_quality_score'].clip(0, 1)
        return df
