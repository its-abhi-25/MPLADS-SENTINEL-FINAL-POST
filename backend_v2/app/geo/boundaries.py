"""
Phase 9 boundaries: Lok Sabha constituencies and districts into geo_area,
with reviewed name crosswalks. Sources, licences and every review decision:
docs/phase9_report.md.

Rules (owner decisions, Phase 9 inspection):
- Constituencies: DataMeet india_pc_2019_simplified (CC0 1.0). Assam (2023)
  and Jammu and Kashmir (2022) were re-delimited and no source has current
  boundaries, so their constituencies get NO polygon and NO point
  ("redelimited_boundary_not_available"); they still count in every total.
- Districts: india-geodata LGD_Districts (CC0-1.0 / CC-BY-4.0, LGD 2024).
- Each area's marker point is shapely's representative_point() of its own
  licensed polygon: guaranteed inside it, deterministic, never a geocode.
- Names are matched exactly after normalisation, then by an explicit,
  hand-reviewed alias table keyed by the source's (state, pc_no); anything
  else is reported unmatched, never fuzzy-matched at runtime.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pyarrow.parquet as pq
from shapely import wkb
from shapely.geometry import mapping, shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.geo import GeoArea, GeoNameCrosswalk
from ..models.reference import Constituency, State

GEO_DIR = Path(__file__).resolve().parents[1] / "geo_data_src"
PC_FILE = GEO_DIR / "india_pc_2019_simplified.geojson"
DISTRICT_FILE = GEO_DIR / "LGD_Districts.parquet"

PC_SOURCE = "DataMeet maps, parliamentary-constituencies/india_pc_2019_simplified.geojson"
PC_LICENCE = "CC0 1.0"
PC_VERSION = "2019 boundaries (2008 delimitation); sha256 54840686c3c5"
DISTRICT_SOURCE = "india-geodata release admin/districts, LGD_Districts.parquet (Local Government Directory)"
DISTRICT_LICENCE = "CC0-1.0 / CC-BY-4.0"
DISTRICT_VERSION = "LGD 2024 snapshot (metadata last_updated 2024-08-15); sha256 c205da56ce05"
DISTRICT_SIMPLIFY_DEG = 0.001  # ~100 m; visualisation only, keeps geo_area small

# Seats whose boundaries changed after the only available source's vintage.
REDELIMITED = {
    "Assam": "Assam re-delimited in 2023 (in force for the 2024 election); no source has the new boundaries",
    "Jammu And Kashmir": "Jammu and Kashmir re-delimited in 2022; no source has the new boundaries",
}

# DataMeet 2019 state names -> our portal state names.
PC_STATE_ALIASES = {
    "Orissa": "Odisha",
    "Andaman & Nicobar": "Andaman And Nicobar Islands",
    "Dadra & Nagar Haveli": "The Dadra And Nagar Haveli And Daman And Diu",
    "Daman & Diu": "The Dadra And Nagar Haveli And Daman And Diu",
    "Jammu & Kashmir": "Jammu And Kashmir",
}
# LGD district-file state names -> our portal state names (after normalisation).
LGD_STATE_ALIASES = {
    "ANDAMANANDNICOBAR": "Andaman And Nicobar Islands",
    "DADRANAGARHAVELIDAMANANDDIU": "The Dadra And Nagar Haveli And Daman And Diu",
}
# Phase 1 state polygons whose names differ from the portal's (reviewed).
STATE_POLYGON_ALIASES = {
    "Andaman And Nicobar Islands": "andaman_and_nicobar",
    "The Dadra And Nagar Haveli And Daman And Diu": "dadra_and_nagar_haveli_and_daman_and_diu",
}

# (our state, our constituency name) -> (DataMeet st_name, pc_no). Every entry
# was checked by hand against the DataMeet feature in the same state
# (docs/phase9_report.md). Names with our state suffixes (_BR, _UP, _HP, _MH)
# are handled by rule, not listed here.
DNHDD = "The Dadra And Nagar Haveli And Daman And Diu"
CONSTITUENCY_ALIASES = {
    ("Andhra Pradesh", "ANAKAPALLE"): ("Andhra Pradesh", 5),
    ("Andhra Pradesh", "ANANTAPUR"): ("Andhra Pradesh", 19),
    ("Andhra Pradesh", "NARASAPURAM"): ("Andhra Pradesh", 9),
    ("Bihar", "PURNEA"): ("Bihar", 12),
    ("Bihar", "UJJARPUR"): ("Bihar", 22),
    ("Chhattisgarh", "JANJGIR CHAMPA(SC)"): ("Chhattisgarh", 3),
    ("Chhattisgarh", "SARGUJA(ST)"): ("Chhattisgarh", 1),
    ("Delhi", "CHANDINI CHOWK"): ("Delhi", 1),
    ("Haryana", "SONEPAT"): ("Haryana", 6),
    ("Karnataka", "BELGAUM"): ("Karnataka", 2),
    ("Karnataka", "CHIKKODI"): ("Karnataka", 1),
    ("Karnataka", "DAVANAGERE"): ("Karnataka", 13),
    ("Karnataka", "HASSAN"): ("Karnataka", 16),
    ("Kerala", "MAVELIKKARA(SC)"): ("Kerala", 16),
    ("Ladakh", "LADAKH"): ("Jammu & Kashmir", 4),  # 2019 layer files Ladakh under J&K
    ("Madhya Pradesh", "MANDSOUR"): ("Madhya Pradesh", 23),
    # DataMeet labels pc 30 "Mumbai South" (attribute error); its geometry is
    # Mumbai South Central (96% overlap with the LGD layer's pc 30).
    ("Maharashtra", "MUMBAI SOUTH CENTRAL"): ("Maharashtra", 30),
    # ...so DataMeet has two "Mumbai South" features; ours is the other one, pc 31.
    ("Maharashtra", "MUMBAI SOUTH"): ("Maharashtra", 31),
    ("Punjab", "BHATINDA"): ("Punjab", 11),
    ("Punjab", "FIROZPUR"): ("Punjab", 10),
    ("Tamil Nadu", "DHARAMAPURI"): ("Tamil Nadu", 10),
    ("Tamil Nadu", "KANNIYAKUMARI"): ("Tamil Nadu", 39),
    ("Tamil Nadu", "MAYILADUTHURAI"): ("Tamil Nadu", 28),
    ("Tamil Nadu", "THOOTHUKKUDI"): ("Tamil Nadu", 36),
    ("Tamil Nadu", "TIRUVALLUR(SC)"): ("Tamil Nadu", 1),
    ("Telangana", "BHONGIR"): ("Telangana", 14),
    ("Telangana", "CHELVELLA"): ("Telangana", 10),
    ("Telangana", "PEDDAPALLE"): ("Telangana", 2),
    ("Telangana", "WARANGEL(SC)"): ("Telangana", 15),
    (DNHDD, "DADRA & NAGAR HAVELI (ST)"): ("Dadra & Nagar Haveli", 1),
    (DNHDD, "DAMAN and DIU"): ("Daman & Diu", 1),
    ("Uttarakhand", "HARDWAR"): ("Uttarakhand", 5),
    ("Uttarakhand", "NAINITAL UDHAM SINGH NAG."): ("Uttarakhand", 4),
    ("West Bengal", "ARAMBAG(SC)"): ("West Bengal", 29),
    ("West Bengal", "BARRACKPUR"): ("West Bengal", 15),
    ("West Bengal", "JOYNAGAR(SC)"): ("West Bengal", 19),
}
STATE_SUFFIX = re.compile(r"_(BR|UP|HP|MH)$")


def norm(name: str | None) -> str:
    """Uppercase letters only, reservation tag and our state suffix removed."""
    s = STATE_SUFFIX.sub("", (name or "").strip().upper())
    s = re.sub(r"\((SC|ST)\)", "", s.replace("&", " AND "))
    return re.sub(r"[^A-Z]", "", s)


def _point(geom) -> tuple[float, float]:
    p = geom.representative_point()
    return round(p.y, 6), round(p.x, 6)


def _state_areas(session: Session) -> dict[str, GeoArea]:
    """Our portal state name -> its state geo_area (Phase 1 polygons)."""
    areas = {a.key: a for a in session.execute(select(GeoArea).where(GeoArea.level == "state")).scalars()}
    out = {}
    for st in session.execute(select(State)).scalars():
        key = STATE_POLYGON_ALIASES.get(st.name) or re.sub(r"[^a-z]+", "_", st.name.lower()).strip("_")
        if key in areas:
            out[st.name] = areas[key]
    return out


def fix_state_crosswalk(session: Session) -> int:
    """Phase 1 left two portal states unmatched only because of naming; both
    polygons exist. Record reviewed aliases (Phase 1 rows are updated in place)."""
    areas = {a.key: a for a in session.execute(select(GeoArea).where(GeoArea.level == "state")).scalars()}
    fixed = 0
    for portal, key in STATE_POLYGON_ALIASES.items():
        row = session.execute(
            select(GeoNameCrosswalk).where(
                GeoNameCrosswalk.level == "state", GeoNameCrosswalk.portal_name == portal
            )
        ).scalar_one_or_none()
        if row is not None and row.geo_area_id is None and key in areas:
            row.geo_area_id = areas[key].id
            row.method = "reviewed_alias"
            row.review_status = "reviewed"
            row.detail = {"note": f"portal name differs from polygon name '{areas[key].name}'"}
            fixed += 1
    session.flush()
    return fixed


def load_constituencies(session: Session) -> dict:
    """geo_area rows for matched, non-re-delimited constituencies, and a
    crosswalk row for EVERY portal constituency (matched or not). Idempotent."""
    existing = session.execute(select(GeoArea.id).where(GeoArea.level == "constituency")).first()
    if existing:
        return {"skipped": "constituencies already loaded"}
    fc = json.loads(PC_FILE.read_text(encoding="utf-8"))
    feats: dict[tuple[str, int], dict] = {}
    by_name: dict[tuple[str, str], list] = {}
    for f in fc["features"]:
        p = f["properties"]
        st_ours = PC_STATE_ALIASES.get(p["st_name"], p["st_name"])
        feats[(p["st_name"], int(p["pc_no"]))] = f
        by_name.setdefault((st_ours, norm(p["pc_name"])), []).append(f)
    state_areas = _state_areas(session)
    states = {s.id: s.name for s in session.execute(select(State)).scalars()}
    counts: dict[str, int] = {}
    for c in session.execute(select(Constituency).where(Constituency.house == "LS")).scalars():
        st = states.get(c.state_id)
        detail: dict = {}
        feat = None
        if st in REDELIMITED:
            method = "redelimited_boundary_not_available"
            detail["reason"] = REDELIMITED[st]
        else:
            cands = by_name.get((st, norm(c.name)), [])
            if len(cands) == 1:
                feat, method = cands[0], "normalized"
            elif (st, c.name) in CONSTITUENCY_ALIASES:
                feat, method = feats.get(CONSTITUENCY_ALIASES[(st, c.name)]), "reviewed_alias"
                if feat is None:
                    method = "unmatched"
            else:
                method = "ambiguous" if cands else "unmatched"
        area_id = None
        if feat is not None:
            p = feat["properties"]
            geom = shape(feat["geometry"])
            lat, lon = _point(geom)
            area = GeoArea(
                level="constituency",
                key=f"pc:{p['st_code']}:{int(p['pc_no'])}",
                name=c.name,
                parent_id=state_areas[st].id if st in state_areas else None,
                geometry=mapping(geom),
                source=PC_SOURCE,
                licence=PC_LICENCE,
                version=PC_VERSION,
                rep_lat=lat,
                rep_lon=lon,
                attrs={
                    "dataset_state": st,
                    "dataset_constituency": c.name,
                    "constituency_id": c.id,
                    "source_pc_name": p["pc_name"],
                    "source_st_name": p["st_name"],
                    "pc_no": int(p["pc_no"]),
                    "pc_category": p.get("pc_category"),
                    "wikidata_qid": p.get("wikidata_qid"),
                    "match_method": method,
                },
            )
            session.add(area)
            session.flush()
            area_id = area.id
            detail["source_pc_name"] = p["pc_name"]
        session.add(
            GeoNameCrosswalk(
                portal_name=f"{st}|{c.name}",
                portal_state=st,
                level="constituency",
                geo_area_id=area_id,
                method=method,
                review_status="reviewed" if method != "normalized" else "auto",
                detail=detail,
            )
        )
        counts[method] = counts.get(method, 0) + 1
    session.flush()
    return counts


def load_districts(session: Session) -> dict:
    existing = session.execute(select(GeoArea.id).where(GeoArea.level == "district")).first()
    if existing:
        return {"skipped": "districts already loaded"}
    cols = ["OBJECTID", "dtname", "stname", "dist_lgd", "state_lgd", "geometry"]
    t = pq.read_table(DISTRICT_FILE, columns=cols)
    state_areas = _state_areas(session)
    portal_by_norm = {norm(s): s for s in state_areas}
    n = 0
    unmapped_states = set()
    for oid, dt, st, dl, sl, g in zip(*[t.column(c).to_pylist() for c in t.column_names]):
        ns = norm(st)
        our_state = LGD_STATE_ALIASES.get(ns) or portal_by_norm.get(ns)
        if our_state is None:
            unmapped_states.add(st)
        geom = wkb.loads(g).simplify(DISTRICT_SIMPLIFY_DEG, preserve_topology=True)
        lat, lon = _point(geom)
        session.add(
            GeoArea(
                level="district",
                key=f"dist:{oid}",
                name=dt,
                parent_id=state_areas[our_state].id if our_state in state_areas else None,
                geometry=mapping(geom),
                source=DISTRICT_SOURCE,
                licence=DISTRICT_LICENCE,
                version=DISTRICT_VERSION,
                rep_lat=lat,
                rep_lon=lon,
                attrs={
                    "lgd_district_code": dl,
                    "lgd_state_code": sl,
                    "source_state_name": st,
                    "state": our_state,
                    "name_norm": norm(dt),
                },
            )
        )
        n += 1
    session.flush()
    return {"districts": n, "unmapped_source_states": sorted(unmapped_states)}
