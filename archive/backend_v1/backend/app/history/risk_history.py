"""
Risk History Tracker
Tracks changes in risk scores over time for dynamic risk assessment.
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class RiskHistoryTracker:
    """Tracks risk score changes over time."""
    
    def __init__(self, storage_path: str = None):
        if storage_path is None:
            if os.environ.get("VERCEL"):
                storage_path = str(Path("/tmp") / "mplads_data" / "risk_history.json")
            else:
                storage_path = str(Path(__file__).parent.parent.parent.parent / "data" / "risk_history.json")
        self.storage_path = Path(storage_path)
        self._history = self._load()
    
    def _load(self) -> Dict[str, List]:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(self._history, f, indent=2, default=str)
    
    def record_risk(self, record_id: str, risk_score: float, risk_level: str,
                    confidence: float, active_signals: List[str], model_version: str):
        """Record a risk assessment for a record."""
        if record_id not in self._history:
            self._history[record_id] = []
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'risk_score': risk_score,
            'risk_level': risk_level,
            'confidence': confidence,
            'active_signals': active_signals,
            'model_version': model_version,
        }
        
        self._history[record_id].append(entry)
        self._save()
    
    def get_history(self, record_id: str) -> List[Dict[str, Any]]:
        """Get risk history for a record."""
        return self._history.get(record_id, [])
    
    def get_latest(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent risk assessment for a record."""
        history = self.get_history(record_id)
        return history[-1] if history else None
    
    def get_trajectory(self, record_id: str) -> List[Dict[str, Any]]:
        """Get risk score trajectory over time."""
        history = self.get_history(record_id)
        return [
            {
                'timestamp': h['timestamp'],
                'risk_score': h['risk_score'],
                'risk_level': h['risk_level'],
            }
            for h in history
        ]