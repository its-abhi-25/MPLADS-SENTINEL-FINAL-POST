"""
Pydantic models for MPLADS Sentinel v3.0
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PriorityLevel(str, Enum):
    LOW = "LOW"
    REVIEW_RECOMMENDED = "MODERATE"
    HIGH_PRIORITY_REVIEW = "HIGH"


class ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SignalType(str, Enum):
    COST_ANOMALY = "COST_ANOMALY"
    DESCRIPTION_SIMILARITY = "DESCRIPTION_SIMILARITY"
    MP_CONCENTRATION = "MP_CONCENTRATION"
    CONSTITUENCY_PATTERN = "CONSTITUENCY_PATTERN"
    TEMPORAL_ANOMALY = "TEMPORAL_ANOMALY"
    STAGE_CONSISTENCY = "STAGE_CONSISTENCY"
    CROSS_SIGNAL_PATTERN = "CROSS_SIGNAL_PATTERN"


class EvidenceItem(BaseModel):
    signal_type: str
    signal_label: Optional[str] = None
    signal_score: float
    signal_strength: str
    explanation: str
    observed_value: Optional[Any] = None
    expected_value: Optional[Any] = None
    peer_group_size: Optional[int] = None
    peer_group_level: Optional[int] = None
    # backward compat
    value: Optional[Any] = None
    baseline: Optional[Any] = None
    deviation: Optional[str] = None
    weight: Optional[float] = None


class RiskAssessment(BaseModel):
    risk_score: float
    risk_level: str
    confidence: float
    confidence_level: str
    active_signals: List[Dict[str, Any]]
    active_signal_count: int
    corroboration: Dict[str, Any]
    model_version: str
    generated_at: str


class ContextInfo(BaseModel):
    peer_group_size: int
    peer_group_level: int
    peer_group_key: str
    peer_group_level_name: str
    peer_median: float
    peer_mean: float
    peer_mad: float
    peer_iqr: float
    peer_percentile: float
    deviation_ratio: float
    project_amount: Optional[float] = None
    inferred_category: str
    state: str
    constituency: str
    year: Optional[int] = None


class RecordDetail(BaseModel):
    record_id: str
    source_record: Dict[str, Any]
    normalized_record: Dict[str, Any]
    risk_assessment: RiskAssessment
    context: ContextInfo
    evidence_items: List[EvidenceItem]
    evidence_chain: List[Dict[str, Any]]
    investigation_recommendation: str
    related_records: List[Dict[str, Any]] = []
    risk_history: List[Dict[str, Any]] = []


class DataHealth(BaseModel):
    source_file: str
    total_records: int
    valid_records: int
    incomplete_records: int
    duplicate_candidates: int
    malformed_values: int
    columns: List[str]
    missingness: Dict[str, float]
    enabled_signals: List[str]
    unavailable_signals: List[str]


class DashboardSummary(BaseModel):
    total_records: int
    total_amount: float
    risk_distribution: Dict[str, int]
    critical_count: int
    high_count: int
    moderate_count: int
    low_count: int
    average_risk: float
    high_risk_percentage: float
    average_confidence: float
    category_distribution: Dict[str, int]
    state_distribution: Dict[str, int]
    stage_distribution: Dict[str, int]
    model_version: str


class FilterParams(BaseModel):
    priority: Optional[str] = None
    risk_level: Optional[str] = None
    confidence: Optional[str] = None
    category: Optional[str] = None
    state: Optional[str] = None
    mp_name: Optional[str] = None
    search: Optional[str] = None
    sort_by: Optional[str] = "risk_score"
    sort_order: Optional[str] = "desc"
    page: int = 1
    page_size: int = 50
