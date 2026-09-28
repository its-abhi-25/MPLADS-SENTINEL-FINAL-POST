"""
API Routes for MPLADS Sentinel v2.0
Preserves all existing endpoints, adds new risk/evidence/context endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ..core.engine import get_sentinel_engine
import json
import os
from datetime import datetime
from pathlib import Path

router = APIRouter()

if os.environ.get("VERCEL"):
    AUDIT_FILE = Path("/tmp") / "mplads_data" / "audit_trail.json"
else:
    AUDIT_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "audit_trail.json"


def _load_audit():
    if AUDIT_FILE.exists():
        with open(AUDIT_FILE, 'r') as f:
            return json.load(f)
    return []


def _save_audit(entries):
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_FILE, 'w') as f:
        json.dump(entries, f, indent=2, default=str)


# ── Health & System ──────────────────────────────────────────────

@router.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "MPLADS Sentinel", "version": "2.0"}


@router.post("/api/load")
async def load_dataset(filepath: Optional[str] = None):
    engine = get_sentinel_engine()
    try:
        result = engine.load_and_analyze(filepath)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Dashboard ────────────────────────────────────────────────────

@router.get("/api/summary")
async def get_summary():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_summary()


# ── Investigation Queue ──────────────────────────────────────────

@router.get("/api/queue")
async def get_investigation_queue(
    priority: Optional[str] = None,
    risk_level: Optional[str] = None,
    confidence: Optional[str] = None,
    category: Optional[str] = None,
    state: Optional[str] = None,
    constituency: Optional[str] = None,
    mp_name: Optional[str] = None,
    stage: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "risk_score",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50,
):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    filters = {
        'priority': priority or risk_level, 'confidence': confidence, 'category': category,
        'state': state, 'constituency': constituency, 'mp_name': mp_name,
        'stage': stage, 'search': search, 'sort_by': sort_by,
        'sort_order': sort_order, 'page': page, 'page_size': page_size,
    }
    filters = {k: v for k, v in filters.items() if v is not None}
    return engine.get_investigation_queue(filters)


@router.get("/api/record/{record_id}")
async def get_record_detail(record_id: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    detail = engine.get_record_detail(record_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found.")
    return detail


# ── Risk Endpoints ───────────────────────────────────────────────

@router.get("/api/risk/{project_id}")
async def get_risk(project_id: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    detail = engine.get_record_detail(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    return {
        'project': detail.get('source_record', {}),
        'risk_assessment': detail.get('risk_assessment', {}),
        'context': detail.get('context', {}),
        'evidence_items': detail.get('evidence_items', []),
        'investigation_recommendation': detail.get('investigation_recommendation', ''),
    }


@router.get("/api/risk/top")
async def get_risk_top(limit: int = 20):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_top_risk(limit)


@router.get("/api/risk/summary")
async def get_risk_summary():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_risk_summary()


# ── Signals & Evidence ──────────────────────────────────────────

@router.get("/api/signals/{project_id}")
async def get_signals(project_id: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    signals = engine.get_signals(project_id)
    if signals is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    return {'project_id': project_id, 'signals': signals}


@router.get("/api/evidence/{project_id}")
async def get_evidence(project_id: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    evidence = engine.get_evidence(project_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    return {'project_id': project_id, **evidence}


# ── Context ──────────────────────────────────────────────────────

@router.get("/api/context/{project_id}")
async def get_context(project_id: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    context = engine.get_context(project_id)
    if context is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    return {'project_id': project_id, **context}


# ── Analytics ────────────────────────────────────────────────────

@router.get("/api/analytics")
async def get_analytics():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_analytics()


@router.get("/api/analytics/overview")
async def get_analytics_overview():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_analytics()


@router.get("/api/analytics/trends")
async def get_analytics_trends():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_analytics()


# ── Investigations ──────────────────────────────────────────────

@router.get("/api/investigations")
async def get_investigations():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_investigations()


@router.get("/api/investigations/{investigation_id}")
async def get_investigation(investigation_id: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    detail = engine.get_record_detail(investigation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found.")
    return detail


# ── Recalculate ─────────────────────────────────────────────────

@router.post("/api/risk/recalculate/{project_id}")
async def recalculate_risk(project_id: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    result = engine.recalculate_risk(project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    return result


# ── Data & Filters (preserved) ──────────────────────────────────

@router.get("/api/data-health")
async def get_data_health():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_data_health()


@router.get("/api/categories")
async def get_categories():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    categories = sorted([c for c in engine.df['inferred_category'].unique() if c and str(c) != 'nan'])
    return {"categories": categories}


@router.get("/api/states")
async def get_states():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    states = sorted([s for s in engine.df['State'].unique() if s and str(s) != 'nan'])
    return {"states": states}


@router.get("/api/constituencies")
async def get_constituencies():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    df = engine.df[['State', 'Constituency']].dropna().drop_duplicates().sort_values(['State', 'Constituency'])
    constituencies = [{'State': str(row['State']), 'Constituency': str(row['Constituency'])} for _, row in df.iterrows()]
    return {"constituencies": constituencies}


@router.get("/api/mps")
async def get_mps():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    mps = sorted([m for m in engine.df['MP'].unique() if m and str(m) != 'nan'])
    return {"mps": mps}


@router.get("/api/stages")
async def get_stages():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    stages = sorted([s for s in engine.df['Stage'].unique() if s and str(s) != 'nan'])
    return {"stages": stages}


# ── Map (preserved + enhanced) ──────────────────────────────

@router.get("/api/map-data")
async def get_map_data(
    state: Optional[str] = None,
    priority: Optional[str] = None,
    risk_level: Optional[str] = None,
    stage: Optional[str] = None,
    search: Optional[str] = None,
):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_constituency_map_data(
        state=state, priority=priority or risk_level,
        stage=stage, search=search,
    )


@router.get("/api/map-works")
async def get_map_works(
    state: Optional[str] = None,
    constituency: Optional[str] = None,
    priority: Optional[str] = None,
    risk_level: Optional[str] = None,
    stage: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 40000,
):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_map_works(
        state=state, constituency=constituency, priority=priority or risk_level,
        stage=stage, search=search, limit=limit,
    )


@router.get("/api/map-filters")
async def get_map_filters():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_map_filters()


@router.get("/api/geojson")
async def get_geojson():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    data = engine.get_geojson_data()
    if data is None:
        raise HTTPException(status_code=404, detail="GeoJSON not available.")
    return data


@router.get("/api/geographic-coverage")
async def get_geographic_coverage():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_geographic_coverage()


@router.get("/api/constituency-intelligence")
async def get_constituency_intelligence(
    state: str = Query(..., description="State name"),
    constituency: str = Query(..., description="Constituency name"),
):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    result = engine.get_constituency_intelligence(state, constituency)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {constituency}, {state}.")
    return result


@router.get("/api/graph-data")
async def get_graph_data():
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    return engine.get_graph_data()


# ── Audit Trail (preserved) ─────────────────────────────────────

@router.post("/api/investigate/{record_id}")
async def update_investigation(record_id: str, body: dict):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")

    audit = _load_audit()
    entry = {
        'record_id': record_id,
        'previous_status': 'Unreviewed',
        'decision': body.get('decision', ''),
        'reviewer': body.get('reviewer', 'Investigator'),
        'note': body.get('note', ''),
        'timestamp': datetime.now().isoformat(),
    }
    audit.append(entry)
    _save_audit(audit)
    return {'status': 'saved', 'entry': entry}


@router.get("/api/audit-trail")
async def get_audit_trail():
    return _load_audit()


# ── MP Performance (preserved) ──────────────────────────────────

@router.get("/api/mp-performance/{mp_name}")
async def get_mp_performance(mp_name: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    result = engine.get_mp_performance(mp_name)
    if 'error' in result and result.get('total_works', 0) == 0:
        raise HTTPException(status_code=404, detail=result['error'])
    return result


@router.get("/api/constituency-performance/{constituency_name}")
async def get_constituency_performance(constituency_name: str):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    result = engine.get_constituency_performance(constituency_name)
    if 'error' in result and result.get('total_works', 0) == 0:
        raise HTTPException(status_code=404, detail=result['error'])
    return result


@router.get("/api/mp-comparison")
async def get_mp_comparison(mps: str = Query(..., description="Comma-separated MP names")):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    names = [n.strip() for n in mps.split(',') if n.strip()]
    if len(names) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 MP names separated by commas.")
    if len(names) > 4:
        raise HTTPException(status_code=400, detail="Maximum 4 MPs for comparison.")
    return engine.get_mp_comparison(names)


@router.get("/api/constituency-comparison")
async def get_constituency_comparison(constituencies: str = Query(..., description="Comma-separated constituency names")):
    engine = get_sentinel_engine()
    if not engine.is_loaded:
        raise HTTPException(status_code=400, detail="Dataset not loaded.")
    names = [n.strip() for n in constituencies.split(',') if n.strip()]
    if len(names) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 constituency names separated by commas.")
    if len(names) > 4:
        raise HTTPException(status_code=400, detail="Maximum 4 constituencies for comparison.")
    return engine.get_constituency_comparison(names)
