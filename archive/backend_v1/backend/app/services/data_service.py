"""
Data Ingestion and Normalization Service
Handles CSV loading, validation, normalization, category inference, and lifecycle linking.
Synchronized with mplads_ready.csv primary dataset.
"""
import pandas as pd
import numpy as np
import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
from ..core.config import WORK_CATEGORY_KEYWORDS


# Column mapping: CSV column names -> application column names
# Only applies if the CSV column name differs from the app-expected name.
COLUMN_MAP = {
    'mp_name': 'MP',
    'work': 'Work Description',
    'recommended_date': 'Date',
    'allocation_amount': 'Amount',
    'status_normalized': 'Stage',
}


class DataIngestionService:
    def __init__(self):
        self.raw_df = None
        self.normalized_df = None
        self.data_health = {}
        self.source_file = ""

    def load_csv(self, filepath: str) -> pd.DataFrame:
        self.source_file = filepath
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
            try:
                self.raw_df = pd.read_csv(filepath, encoding=encoding, dtype=str)
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        if self.raw_df is None:
            raise ValueError(f"Could not read CSV file: {filepath}")

        # Strip BOM from column names if present
        self.raw_df.columns = [c.lstrip('\ufeff') for c in self.raw_df.columns]

        # Map new column names to application-expected column names
        rename_map = {k: v for k, v in COLUMN_MAP.items() if k in self.raw_df.columns}
        self.raw_df = self.raw_df.rename(columns=rename_map)

        # Ensure Record ID exists and is string
        if 'Record ID' not in self.raw_df.columns:
            self.raw_df['Record ID'] = [f"MPL-{i:05d}" for i in range(1, len(self.raw_df) + 1)]
        else:
            self.raw_df['Record ID'] = self.raw_df['Record ID'].astype(str)

        self.raw_df = self.raw_df.reset_index(drop=True)
        return self.raw_df

    def compute_data_health(self) -> Dict[str, Any]:
        if self.raw_df is None:
            return {}
        df = self.raw_df
        total = len(df)

        missing = df.isnull().sum()
        missing_pct = (missing / total * 100).to_dict()

        empty_counts = {}
        for col in df.columns:
            empty_mask = df[col].astype(str).str.strip().isin(['', 'nan', 'None', 'N/A', '---', 'TBD', 'pending'])
            empty_counts[col] = int(empty_mask.sum())

        dup_cols = [c for c in df.columns if c != 'Record ID']
        duplicate_mask = df.duplicated(subset=dup_cols, keep=False)
        duplicates = int(duplicate_mask.sum())

        near_dup_mask = df.duplicated(subset=['MP', 'Work Description'], keep=False)
        near_duplicates = int(near_dup_mask.sum())

        stage_dist = df['Stage'].value_counts().to_dict() if 'Stage' in df.columns else {}
        state_dist = df['State'].value_counts().to_dict() if 'State' in df.columns else {}

        self.data_health = {
            'source_file': str(Path(self.source_file).name),
            'total_records': total,
            'valid_records': total - duplicates,
            'incomplete_records': int(empty_counts.get('Work Description', 0)) + int(empty_counts.get('Amount', 0)),
            'duplicate_candidates': duplicates,
            'near_duplicate_candidates': near_duplicates,
            'columns': list(df.columns),
            'missingness': {col: round(missing_pct.get(col, 0), 2) for col in df.columns},
            'empty_counts': empty_counts,
            'stage_distribution': stage_dist,
            'state_count': len(state_dist),
            'mp_count': df['MP'].nunique() if 'MP' in df.columns else 0,
            'constituency_count': df['Constituency'].nunique() if 'Constituency' in df.columns else 0,
        }
        return self.data_health

    def normalize_text(self, text: str) -> str:
        if pd.isna(text) or text == '':
            return ''
        text = unicodedata.normalize('NFKC', str(text))
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    def parse_amount(self, value: str) -> Tuple[Optional[float], str]:
        original = str(value).strip() if pd.notna(value) else ''
        if original in ['', 'nan', 'None', 'N/A', '---', 'TBD', 'pending']:
            return None, original
        cleaned = re.sub(r'[₹$Rs.\s]', '', original)
        cleaned = cleaned.replace(',', '').strip()
        try:
            return float(cleaned), original
        except ValueError:
            pass
        numbers = re.findall(r'[\d.]+', cleaned)
        if numbers:
            try:
                return float(numbers[0]), original
            except ValueError:
                pass
        return None, original

    def parse_date(self, value: str) -> Tuple[Optional[datetime], str]:
        original = str(value).strip() if pd.notna(value) else ''
        if original in ['', 'nan', 'None', 'N/A']:
            return None, original
        formats = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d.%m.%Y']
        for fmt in formats:
            try:
                return datetime.strptime(original, fmt), original
            except ValueError:
                continue
        return None, original

    def infer_category(self, description: str) -> Tuple[str, float]:
        desc_lower = description.lower()
        best_match = "Other"
        best_score = 0
        for category, keywords in WORK_CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > best_score:
                best_score = score
                best_match = category
        confidence = min(1.0, best_score / 3.0) if best_score > 0 else 0.0
        return best_match, confidence

    def normalize_dataset(self) -> pd.DataFrame:
        if self.raw_df is None:
            raise ValueError("No data loaded.")
        df = self.raw_df.copy()

        # Text normalization
        text_cols = ['MP', 'Work Description', 'Constituency', 'State']
        for col in text_cols:
            if col in df.columns:
                df[f'{col}_norm'] = df[col].apply(self.normalize_text)

        # Amount parsing - handle both numeric and string amounts
        if 'Amount' in df.columns:
            # Check if amounts are already numeric
            sample = df['Amount'].dropna().head(5)
            try:
                df['amount_numeric'] = pd.to_numeric(df['Amount'], errors='coerce')
                df['amount_original'] = df['Amount'].astype(str)
            except Exception:
                amount_data = df['Amount'].apply(self.parse_amount)
                df['amount_numeric'] = [x[0] for x in amount_data]
                df['amount_original'] = [x[1] for x in amount_data]

        # Date parsing
        if 'Date' in df.columns:
            date_data = df['Date'].apply(self.parse_date)
            df['date_parsed'] = [x[0] for x in date_data]
            df['date_original'] = [x[1] for x in date_data]
            df['year'] = df['date_parsed'].apply(lambda x: x.year if x else None)
            df['month'] = df['date_parsed'].apply(lambda x: x.month if x else None)
            df['quarter'] = df['date_parsed'].apply(lambda x: f"Q{(x.month - 1) // 3 + 1}" if x else None)

        # Category inference from work description
        cat_data = df['Work Description'].fillna('').apply(self.infer_category)
        df['inferred_category'] = [x[0] for x in cat_data]
        df['category_confidence'] = [x[1] for x in cat_data]

        # Amount tier
        if 'amount_numeric' in df.columns:
            df['amount_tier'] = df['amount_numeric'].apply(self._get_amount_tier)

        # Normalized description for duplicate detection
        df['description_normalized'] = df['Work Description'].fillna('').apply(
            lambda x: re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', x).lower().strip())
        )

        self.normalized_df = df
        return df

    def _get_amount_tier(self, amount):
        if pd.isna(amount):
            return 'UNKNOWN'
        if amount < 100000:
            return 'LOW'
        elif amount < 500000:
            return 'MEDIUM'
        elif amount < 2000000:
            return 'HIGH'
        else:
            return 'VERY_HIGH'

    def get_processed_data(self) -> pd.DataFrame:
        if self.normalized_df is not None:
            return self.normalized_df
        return self.raw_df
