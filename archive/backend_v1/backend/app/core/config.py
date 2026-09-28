"""
Sentinel Configuration
Signal weights, thresholds, category keywords, and data paths.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

RAW_CSV_PATH = RAW_DATA_DIR / "mplads_ready.csv"
COORDINATES_CSV_PATH = PROCESSED_DATA_DIR / "location_coordinates.csv"

# Signal weights (must sum to 1.0)
# Seven authoritative signals for the current-data risk engine
SIGNAL_WEIGHTS = {
    "COST_ANOMALY": 0.25,
    "DESCRIPTION_SIMILARITY": 0.20,
    "MP_CONCENTRATION": 0.10,
    "CONSTITUENCY_PATTERN": 0.10,
    "TEMPORAL_ANOMALY": 0.10,
    "STAGE_CONSISTENCY": 0.10,
    "CROSS_SIGNAL_PATTERN": 0.15,
}

# Column names for each signal's score in the dataframe
SIGNAL_COLUMNS = {
    "COST_ANOMALY": "cost_anomaly_score",
    "DESCRIPTION_SIMILARITY": "description_similarity_score",
    "MP_CONCENTRATION": "mp_concentration_score",
    "CONSTITUENCY_PATTERN": "constituency_pattern_score",
    "TEMPORAL_ANOMALY": "temporal_score",
    "STAGE_CONSISTENCY": "lifecycle_score",
    "CROSS_SIGNAL_PATTERN": "pattern_score",
}

# Risk level thresholds (0-1 scale)
# CRITICAL must require meaningful corroboration
RISK_THRESHOLDS = {
    "CRITICAL": 0.85,
    "HIGH": 0.65,
    "MODERATE": 0.40,
    "LOW": 0.0,
}

# Minimum peer group size for reliable comparison
MIN_PEER_GROUP_SIZE = 3

# Similarity threshold for text matching
SIMILARITY_THRESHOLD = 0.75

# Corroboration multipliers
# Independent means different anomaly dimensions
CORROBORATION_LEVELS = {
    0: 0.0,
    1: 0.90,
    2: 1.00,
    3: 1.08,
    4: 1.15,
}

# Minimum independent signals for CRITICAL risk level
MIN_CRITICAL_SIGNALS = 3

# Model version
MODEL_VERSION = "risk_engine_v3.0"
SCORING_VERSION = "risk_scoring_v3.0"

# Work category keywords for classification
WORK_CATEGORY_KEYWORDS = {
    "Road & Infrastructure": [
        "road", "bridge", "culvert", "pathway", "highway", "flyover",
        "pavement", "cc road", "c.c.road", "bitumen", "tar road",
        "concrete road", "pucca road", "kuccha road", "street",
    ],
    "Water & Sanitation": [
        "water", "well", "bore", "tank", "pipeline", "drainage",
        "drain", "sewerage", "toilet", "sanitation", "nala", "kuva",
        "sincchai", "sichai", "hand pump", "overhead tank",
    ],
    "Community Building": [
        "community hall", "community bhavan", "cultural bhavan",
        "community center", "function hall", "sabha bhawan",
        "meeting hall", "community complex", "samuhik", "grih",
    ],
    "Education": [
        "school", "college", "classroom", "library", "education",
        "computer center", "study", "vidyalaya", "vidya", "shala",
        "tuition", "training center",
    ],
    "Health": [
        "hospital", "health", "medical", "dispensary", "phc",
        "sub-center", "clinic", "ambulance", "phage", "aushadhi",
    ],
    "Electricity & Lighting": [
        "electric", "electricity", "light", "led", "solar",
        "street light", "high mast", "transformer", "ht/lt",
        "pole", "wiring", "electrification",
    ],
    "Park & Environment": [
        "park", "garden", "tree", "plantation", "green",
        "environment", "playground", "children park",
    ],
    "Sports & Culture": [
        "stadium", "sports", "culture", "cultural", "auditorium",
        "museum", "theatre",
    ],
    "Other Infrastructure": [
        "boundary wall", "compound wall", "fencing", "shed",
        "building", "construction", "repair", "renovation",
        "maintenance", "installation",
    ],
}
