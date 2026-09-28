"""Phase 9 permanent map regression tests.

Unit tests (no DB) cover the search escaping and the stratified-sampling
quota rule. Integration tests need a database where scripts/run_geo.py has
built the map for the published run; they skip otherwise. Tests that
change data (3x volume, stale data) run inside one transaction that is
rolled back, with the API's get_db overridden to that session.
"""

from __future__ import annotations

import re
import time

import pytest
from shapely.geometry import Point, shape
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.analytics import atypicality_run
from app.db.session import get_db, get_engine
from app.geo import service
from app.main import app

SPECIAL = ["(Test)", "Some[thing]", "a*b", "(", "[", "*", "?", "((", "a(b", "%", "_", "\\", "'", '"', "a%b_c"]
BASE_TABLES = re.compile(r"\b(work|work_state|risk_result|signal_result)\b", re.I)


# ---- unit ----------------------------------------------------------------------------


@pytest.mark.parametrize("q", SPECIAL)
def test_like_pattern_escapes_every_wildcard(q):
    pat = service.like_pattern(q)
    body = pat[1:-1]
    # every % or _ inside the body is escaped; the only unescaped ones are the wrapping %
    unescaped = re.findall(r"(?<!\\)(?:\\\\)*[%_]", body)
    assert not unescaped, (q, pat)
    assert pat.startswith("%") and pat.endswith("%")


@pytest.mark.parametrize("bad", ["x" * (service.MAX_SEARCH_CHARS + 1), "a\x00b"])
def test_clean_search_rejects_bad_text(bad):
    with pytest.raises(ValueError):
        service.clean_search(bad)


@pytest.mark.parametrize("blank", [None, "", "   ", "\t"])
def test_clean_search_treats_blank_as_no_search(blank):
    assert service.clean_search(blank) is None


@pytest.mark.parametrize("cap", [1, 7, 100, 3000])
def test_stratified_quotas_sum_to_cap_and_keep_every_state(cap):
    counts = {"UP": 40000, "MH": 20000, "Lakshadweep": 2, "Goa": 150, "Sikkim": 1}
    q = service.stratified_quotas(counts, cap)
    assert sum(q.values()) == min(cap, sum(counts.values()))
    assert all(q[k] <= counts[k] for k in q)
    if cap >= len(counts):
        assert all(q.get(k, 0) >= 1 for k in counts)
        assert q["UP"] >= q["MH"] >= q["Goa"]
    if cap == 3000:
        total = sum(counts.values())
        # the 1-per-state floor shifts each share by at most one row per state
        assert all(abs(q[k] - counts[k] / total * cap) <= len(counts) for k in ("UP", "MH", "Goa"))


@pytest.mark.parametrize("cap", [1, 2, 4])
def test_stratified_quotas_never_exceed_a_cap_smaller_than_the_state_count(cap):
    q = service.stratified_quotas({"A": 50, "B": 40, "C": 30, "D": 20, "E": 10}, cap)
    assert sum(q.values()) == cap and set(q) == set("ABCDE"[:cap])


def test_stratified_quotas_below_cap_returns_everything():
    assert service.stratified_quotas({"A": 3, "B": 0, "C": 2}, 10) == {"A": 3, "C": 2}


# ---- fixtures -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def map_run(db_session):
    s = service.served(db_session)
    if s.run_id is None:
        pytest.skip("no complete map_build -- run scripts/run_geo.py")
    return s


@pytest.fixture
def tx_client(client, map_run):
    """Client whose requests run inside one transaction, rolled back after."""
    conn = get_engine().connect()
    trans = conn.begin()
    session = Session(bind=conn)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    try:
        yield client, session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        trans.rollback()
        conn.close()


def _truth_count(db, run_id, q):
    return db.execute(
        text(
            "SELECT count(*) FROM map_work WHERE run_id = :r AND latitude IS NOT NULL "
            "AND strpos(search_text, lower(:q)) > 0"
        ),
        {"r": run_id, "q": q.strip()},
    ).scalar_one()


# ---- search: special characters, literal, empty / invalid ----------------------------------------


@pytest.mark.parametrize("q", SPECIAL)
def test_special_character_search_is_literal_on_both_endpoints(client, db_session, map_run, q):
    works = client.get("/api/map-works", params={"search": q})
    data = client.get("/api/map-data", params={"search": q})
    assert works.status_code == 200 and data.status_code == 200, (works.text, data.text)
    truth = _truth_count(db_session, map_run.run_id, q)
    assert int(works.headers["x-total-count"]) == truth
    assert (
        sum(r["total"] for r in data.json())
        == db_session.execute(
            text(
                "SELECT count(*) FROM map_work WHERE run_id = :r AND constituency_area_id IS NOT NULL "
                "AND strpos(search_text, lower(:q)) > 0"
            ),
            {"r": map_run.run_id, "q": q},
        ).scalar_one()
    )


def test_search_matches_are_really_substrings(client, db_session, map_run):
    rows = client.get("/api/map-works", params={"search": "a(b"}).json()
    keys = [r["record_id"] for r in rows]
    if keys:
        texts = (
            db_session.execute(
                text("SELECT search_text FROM map_work WHERE run_id = :r AND work_key = ANY(:k)"),
                {"r": map_run.run_id, "k": keys},
            )
            .scalars()
            .all()
        )
        assert all("a(b" in t for t in texts)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_search_equals_no_search(client, map_run, blank):
    a = client.get("/api/map-data").json()
    b = client.get("/api/map-data", params={"search": blank}).json()
    assert a == b


@pytest.mark.parametrize(
    "path,params",
    [
        ("/api/map-data", {"priority": "bogus"}),
        ("/api/map-data", {"risk_level": "high"}),
        ("/api/map-works", {"limit": 0}),
        ("/api/map-works", {"limit": -5}),
        ("/api/map-works", {"search": "x" * (service.MAX_SEARCH_CHARS + 1)}),
        ("/api/map-works", {"search": "a\x00b"}),
        ("/api/map-data", {"search": "a\x00b"}),
        ("/api/map-works", {"house": "XX"}),
        ("/api/geo/areas/pc:x/works", {"page": 0}),
        ("/api/geo/areas/pc:x/works", {"page_size": 1000}),
    ],
)
def test_invalid_input_is_422_not_500(client, map_run, path, params):
    assert client.get(path, params=params).status_code == 422


@pytest.mark.parametrize("limit", [1, 5, 40])
def test_map_works_limit_is_a_hard_cap(client, map_run, limit):
    r = client.get("/api/map-works", params={"limit": limit})
    assert len(r.json()) == limit and r.headers["x-sampled"] == "true"
    big = client.get("/api/map-works", params={"limit": 10**6})
    assert len(big.json()) == service.MAP_WORKS_CAP
    assert big.headers["x-map-works-cap"] == str(service.MAP_WORKS_CAP)


def test_unknown_filter_values_return_empty_not_error(client, map_run):
    for path in ("/api/map-data", "/api/map-works"):
        r = client.get(path, params={"state": "No Such State", "stage": "No Such Stage"})
        assert r.status_code == 200 and r.json() == []
    assert client.get("/api/geo/areas/pc:none:0/works").status_code == 404


# ---- no fake precision ------------------------------------------------------------------------


def test_every_marker_is_its_constituency_representative_point(db_session, map_run):
    bad = db_session.execute(
        text(
            """
        SELECT count(*) FROM map_work mw LEFT JOIN geo_area ga ON ga.id = mw.constituency_area_id
        WHERE mw.run_id = :r AND (
              (mw.latitude IS NULL) <> (mw.constituency_area_id IS NULL)
           OR (mw.latitude IS NOT NULL AND (mw.latitude <> ga.rep_lat OR mw.longitude <> ga.rep_lon)))
        """
        ),
        {"r": map_run.run_id},
    ).scalar_one()
    assert bad == 0


def test_representative_points_lie_inside_their_licensed_polygons(db_session, map_run):
    rows = db_session.execute(
        text(
            "SELECT key, geometry, rep_lat, rep_lon FROM geo_area WHERE level IN ('constituency', 'district')"
        )
    ).all()
    assert rows
    # points are stored rounded to 6 decimals (~0.1 m), hence the tolerance
    outside = [k for k, g, lat, lon in rows if shape(g).distance(Point(lon, lat)) > 1e-5]
    assert not outside, outside[:10]


def test_map_works_share_one_unjittered_point_per_constituency(client, db_session, map_run):
    r = client.get("/api/map-works", params={"state": "Karnataka"})
    rows = r.json()
    assert rows and r.headers["x-location-precision"] == service.LOCATION_PRECISION
    assert "not the work's site" in r.headers["x-location-precision-note"]
    per = {}
    for w in rows:
        assert w["location_precision"] == service.LOCATION_PRECISION and w["location_level"] == "CONSTITUENCY"
        per.setdefault((w["state"], w["constituency"]), set()).add((w["latitude"], w["longitude"]))
    assert all(len(v) == 1 for v in per.values())
    points = set(
        db_session.execute(text("SELECT rep_lat, rep_lon FROM geo_area WHERE level = 'constituency'")).all()
    )
    assert {p for v in per.values() for p in v} <= points


def test_redelimited_constituencies_get_no_polygon_and_no_point(client, db_session, map_run):
    n = db_session.execute(
        text(
            "SELECT count(*) FROM map_work WHERE run_id = :r "
            "AND constituency_state IN ('Assam', 'Jammu And Kashmir') "
            "AND latitude IS NOT NULL"
        ),
        {"r": map_run.run_id},
    ).scalar_one()
    assert n == 0
    cov = client.get("/api/geographic-coverage").json()
    assert cov["redelimited_count"] == 19 and cov["centroid_fallback_count"] == 0
    assert {x["state"] for x in cov["no_boundary"]} == {"Assam", "Jammu And Kashmir"}


# ---- aggregation sums -------------------------------------------------------------------------


def test_every_level_sums_to_national_and_to_the_scored_works(db_session, map_run):
    run = map_run.run_id
    scored = db_session.execute(
        text(
            "SELECT count(*) FROM risk_result r JOIN published_run p ON p.run_id = r.run_id "
            "AND p.default_config_name = r.config_name WHERE r.run_id = :r"
        ),
        {"r": run},
    ).scalar_one()
    by_level = db_session.execute(
        text(
            "SELECT level, house, tier, stage, sum(n), round(sum(amount_sum)::numeric, 2), "
            "round(sum(risk_sum)::numeric, 6) FROM geo_metric WHERE run_id = :r GROUP BY 1, 2, 3, 4"
        ),
        {"r": run},
    ).all()
    cells: dict = {}
    for lvl, h, t, s, n, amt, risk in by_level:
        cells.setdefault(lvl, {})[(h, t, s)] = (n, amt, risk)
    assert set(cells) == {"national", "state", "district", "constituency"}
    for lvl in ("state", "district", "constituency"):
        assert cells[lvl] == cells["national"], lvl
    assert sum(v[0] for v in cells["national"].values()) == scored
    assert (
        db_session.execute(text("SELECT count(*) FROM map_work WHERE run_id = :r"), {"r": run}).scalar_one()
        == scored
    )


def test_map_data_totals_equal_located_constituency_cells(client, db_session, map_run):
    for params in (
        {},
        {"priority": "HIGH"},
        {"stage": "COMPLETED"},
        {"house": "LS", "risk_level": "CRITICAL"},
    ):
        rows = client.get("/api/map-data", params=params).json()
        where = ["run_id = :r", "level = 'constituency'", "area_key NOT LIKE 'unlocated:%'"]
        p = {"r": map_run.run_id}
        if params.get("priority") or params.get("risk_level"):
            where.append("tier = :t")
            p["t"] = params.get("priority") or params.get("risk_level")
        if params.get("stage"):
            where.append("stage = :s")
            p["s"] = params["stage"]
        truth = db_session.execute(
            text(f"SELECT coalesce(sum(n), 0) FROM geo_metric WHERE {' AND '.join(where)}"), p
        ).scalar_one()
        assert sum(r["total"] for r in rows) == truth, params
        for r in rows:
            assert r["flagged"] == r["critical"] + r["high"]
            assert r["critical"] + r["high"] + r["moderate"] + r["low"] + r["not_evaluated"] == r["total"]


def test_small_areas_show_counts_but_no_rates(client, map_run):
    rows = client.get("/api/map-data", params={"priority": "CRITICAL"}).json()
    small = [r for r in rows if r["total"] < service.MIN_WORKS_FOR_RATE]
    assert small, "expected some constituencies under the small-number threshold for CRITICAL"
    for r in small:
        assert r["insufficient_data"] is True and r["total"] > 0
        assert r["flag_rate"] is r["avg_risk"] is r["avg_confidence"] is r["avg_signals"] is None
    for r in rows:
        if r["total"] >= service.MIN_WORKS_FOR_RATE:
            assert r["insufficient_data"] is False and r["flag_rate"] is not None


# ---- pagination -------------------------------------------------------------------------------


def test_area_drilldown_pages_are_disjoint_and_complete(client, db_session, map_run):
    key, n = db_session.execute(
        text(
            "SELECT area_key, sum(n) FROM geo_metric WHERE run_id = :r AND level = 'constituency' "
            "AND area_key NOT LIKE 'unlocated:%' GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
        ),
        {"r": map_run.run_id},
    ).one()
    seen, page = [], 1
    while True:
        body = client.get(f"/api/geo/areas/{key}/works", params={"page": page, "page_size": 200}).json()
        assert body["total"] == n and body["page"] == page
        if not body["records"]:
            break
        seen += [r["record_id"] for r in body["records"]]
        page += 1
    assert len(seen) == len(set(seen)) == n
    assert page - 1 == body["total_pages"]


def test_district_drilldown_includes_works_without_markers(client, db_session, map_run):
    key = db_session.execute(
        text(
            "SELECT ga.key FROM map_work mw JOIN geo_area ga ON ga.id = mw.district_area_id "
            "WHERE mw.run_id = :r AND mw.house = 'RS' LIMIT 1"
        ),
        {"r": map_run.run_id},
    ).scalar()
    if key is None:
        pytest.skip("no Rajya Sabha work with a district")
    body = client.get(f"/api/geo/areas/{key}/works", params={"page_size": 200}).json()
    assert body["level"] == "district" and body["total"] > 0


# ---- house filter -----------------------------------------------------------------------------


def test_house_filter(client, db_session, map_run):
    all_rows = client.get("/api/map-data").json()
    ls_rows = client.get("/api/map-data", params={"house": "LS"}).json()
    assert all_rows == ls_rows  # constituency areas are Lok Sabha only
    assert client.get("/api/map-data", params={"house": "RS"}).json() == []
    assert client.get("/api/map-works", params={"house": "RS"}).json() == []
    rs = client.get("/api/map-filters", params={"house": "RS"}).json()
    ls = client.get("/api/map-filters", params={"house": "LS"}).json()
    both = client.get("/api/map-filters").json()
    assert rs["total_constituencies"] == 0 and rs["total_works"] > 0
    assert rs["total_works"] + ls["total_works"] == both["total_works"]


def test_intelligence_is_house_aware_and_never_404s(client, map_run):
    rs = client.get(
        "/api/constituency-intelligence", params={"state": "Punjab", "constituency": "Sitting Rajya Sabha"}
    )
    assert rs.status_code == 200
    assert rs.json()["applicable"] is False and "Rajya Sabha" in rs.json()["not_applicable_reason"]
    unknown = client.get("/api/constituency-intelligence", params={"state": "(Test)", "constituency": "a*b"})
    assert unknown.status_code == 200 and unknown.json()["found"] is False
    ok = client.get(
        "/api/constituency-intelligence", params={"state": "Karnataka", "constituency": "DHARWAD"}
    ).json()
    assert ok["applicable"] is True and ok["total_works"] > 0 and ok["mps"]
    assert ok["flagged_count"] == ok["critical_count"] + ok["high_count"]
    assert sum(ok["confidence_distribution"].values()) == ok["total_works"]
    assert ok["confidence_distribution_note"]


# ---- stale data -------------------------------------------------------------------------------


def test_stale_data_serves_last_complete_build_labelled_with_its_date(tx_client, map_run):
    client, s = tx_client
    new_run = s.execute(
        text(
            "INSERT INTO analysis_run (source_snapshot_id, engine_version, config_hash, status) "
            "SELECT source_snapshot_id, engine_version, config_hash, 'complete' "
            "FROM analysis_run WHERE id = :r "
            "RETURNING id"
        ),
        {"r": map_run.run_id},
    ).scalar_one()
    s.execute(text("UPDATE published_run SET run_id = :n"), {"n": new_run})
    s.flush()
    r = client.get("/api/map-data")
    assert r.status_code == 200 and r.json()
    assert r.headers["x-map-run-id"] == str(map_run.run_id)
    assert r.headers["x-map-is-latest"] == "false"
    assert r.headers["x-map-data-as-of"] == str(map_run.data_as_of)
    cov = client.get("/api/geographic-coverage").json()
    assert cov["served"] == {
        "run_id": map_run.run_id,
        "data_as_of": str(map_run.data_as_of),
        "is_latest": False,
    }


# ---- bounded payload at 3x volume ----------------------------------------------------------------


def test_payload_stays_bounded_at_three_times_volume(tx_client, map_run):
    client, s = tx_client
    run = map_run.run_id
    new_run = s.execute(
        text(
            "INSERT INTO analysis_run (source_snapshot_id, engine_version, config_hash, status) "
            "SELECT source_snapshot_id, engine_version, config_hash, 'complete' "
            "FROM analysis_run WHERE id = :r "
            "RETURNING id"
        ),
        {"r": run},
    ).scalar_one()
    s.execute(
        text(
            "INSERT INTO work (work_key, house, house_source, first_seen_snapshot_id, "
            "first_seen_raw_file_id) "
            "SELECT 'v' || k || 'x' || w.work_key, w.house, w.house_source, w.first_seen_snapshot_id, "
            "w.first_seen_raw_file_id FROM work w "
            "JOIN map_work mw ON mw.work_key = w.work_key AND mw.run_id = :r AND mw.latitude IS NOT NULL "
            "CROSS JOIN generate_series(1, 2) k"
        ),
        {"r": run},
    )
    cols = [
        c.strip() for c in service._WORK_COLS.replace("mw.", "").split(",") if c.strip() != "work_key"
    ] + ["constituency_area_id", "district_area_id"]
    cl = ", ".join(cols)
    # Only works with a marker are tripled (map-works serves nothing else; map-data
    # reads geo_metric, tripled below). search_text is '' only because maintaining
    # the trigram index for ~230k synthetic rows takes minutes; this test never
    # searches (index use is tested separately).
    s.execute(
        text(
            f"INSERT INTO map_work (run_id, work_key, {cl}, search_text) "
            f"SELECT :n, work_key, {cl}, '' FROM map_work WHERE run_id = :r AND latitude IS NOT NULL "
            f"UNION ALL SELECT :n, 'v' || k || 'x' || work_key, {cl}, '' FROM map_work "
            "CROSS JOIN generate_series(1, 2) k WHERE run_id = :r AND latitude IS NOT NULL"
        ),
        {"n": new_run, "r": run},
    )
    s.execute(
        text(
            "INSERT INTO geo_metric (run_id, level, area_key, area_name, state, house, tier, stage, n, "
            "amount_sum, risk_sum, risk_n, confidence_sum, signals_sum) "
            "SELECT :n, level, area_key, area_name, state, house, tier, stage, n * 3, amount_sum * 3, "
            "risk_sum * 3, risk_n * 3, confidence_sum * 3, signals_sum * 3 "
            "FROM geo_metric WHERE run_id = :r"
        ),
        {"n": new_run, "r": run},
    )
    s.execute(
        text(
            "INSERT INTO map_build (run_id, status, config_name, data_as_of, counts) "
            "SELECT :n, 'complete', config_name, data_as_of, counts FROM map_build WHERE run_id = :r"
        ),
        {"n": new_run, "r": run},
    )
    s.execute(text("UPDATE published_run SET run_id = :n"), {"n": new_run})
    s.flush()

    t = time.time()
    works = client.get("/api/map-works")
    t_works = time.time() - t
    assert works.headers["x-map-run-id"] == str(new_run)
    assert int(works.headers["x-total-count"]) == 3 * map_run.counts["with_marker"]
    assert len(works.json()) == service.MAP_WORKS_CAP and works.headers["x-sampled"] == "true"
    assert len({w["state"] for w in works.json()}) == len(client.get("/api/map-filters").json()["states"])
    assert len(works.content) < 3_000_000
    t = time.time()
    data = client.get("/api/map-data")
    t_data = time.time() - t
    assert len(data.json()) <= 800  # BLUEPRINT §15: <= ~800 areas per view
    assert len(data.content) < 350_000  # BLUEPRINT §15: metrics ~300 KB uncompressed
    assert t_works < 10 and t_data < 10


# ---- no full scan, endpoint isolation, contract ---------------------------------------------------------


MAP_CALLS = [
    ("/api/map-data", {}),
    ("/api/map-data", {"search": "road"}),
    ("/api/map-works", {}),
    ("/api/map-works", {"search": "a(b", "state": "Karnataka"}),
    ("/api/map-filters", {"house": "LS"}),
    ("/api/geojson", {}),
    ("/api/geographic-coverage", {}),
    ("/api/constituency-intelligence", {"state": "Karnataka", "constituency": "DHARWAD"}),
]


def test_map_endpoints_never_touch_base_tables(client, map_run):
    seen: list[str] = []

    def capture(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        for path, params in MAP_CALLS:
            assert client.get(path, params=params).status_code == 200, path
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert seen
    offenders = [s for s in seen if BASE_TABLES.search(s)]
    assert not offenders, offenders[:3]


def test_search_uses_the_trigram_index(db_session, map_run):
    key = db_session.execute(
        text("SELECT max(work_key) FROM map_work WHERE run_id = :r"), {"r": map_run.run_id}
    ).scalar_one()
    plan = "\n".join(
        db_session.execute(
            text(
                "EXPLAIN SELECT count(*) FROM map_work mw WHERE mw.run_id = :r "
                "AND mw.search_text LIKE :p ESCAPE '\\'"
            ),
            {"r": map_run.run_id, "p": service.like_pattern(key)},
        ).scalars()
    )
    assert "ix_map_work_search_trgm" in plan, plan


def test_database_failure_is_503_and_isolated(client, map_run):
    dead = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 2})

    def _dead():
        s = Session(bind=dead)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _dead
    try:
        for path, params in MAP_CALLS:
            assert client.get(path, params=params).status_code == 503, path
        # The app stays up (Phase 12: /api/summary is DB-backed now, so a dead
        # database 503s it too; /api/health is the DB-free endpoint).
        assert client.get("/api/health").status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert client.get("/api/map-data").status_code == 200  # and the map recovers
    assert client.get("/api/summary").status_code == 200


MAP_DATA_KEYS = {
    "State",
    "Constituency",
    "total",
    "flagged",
    "critical",
    "high",
    "moderate",
    "low",
    "total_amount",
    "avg_risk",
    "mps",
    "stages",
    "flag_rate",
    "avg_risk_pct",
    "financial_exposure",
    "avg_confidence",
    "avg_confidence_pct",
    "avg_signals",
    "latitude",
    "longitude",
    "location_level",
    "geocoding_status",
}
MAP_WORK_KEYS = {
    "record_id",
    "latitude",
    "longitude",
    "location_level",
    "state",
    "constituency",
    "mp",
    "description",
    "amount",
    "stage",
    "category",
    "risk_level",
    "priority",
    "risk_score",
    "priority_score",
    "confidence_score",
    "confidence_percent",
    "evidence_count",
    "active_signal_count",
    "base_signal_count",
    "evidence_summary",
    "date",
}


def test_contract_row_shapes_are_kept(client, map_run):
    rows = client.get("/api/map-data").json()
    assert rows and all(MAP_DATA_KEYS <= r.keys() for r in rows)
    works = client.get("/api/map-works", params={"state": "Goa"}).json()
    assert works and all(MAP_WORK_KEYS <= w.keys() for w in works)
    assert all(0 <= w["risk_score"] <= 1 for w in works if w["risk_score"] is not None)
    gj = client.get("/api/geojson").json()
    props = gj["features"][0]["properties"]
    assert {"dataset_state", "dataset_constituency"} <= props.keys()
    joined = {(r["State"], r["Constituency"]) for r in rows}
    feats = {
        (f["properties"]["dataset_state"], f["properties"]["dataset_constituency"]) for f in gj["features"]
    }
    assert joined <= feats  # every map-data row joins to a polygon, as Map.jsx does


def test_geojson_is_versioned_and_cached(client, map_run):
    a = client.get("/api/geojson")
    b = client.get("/api/geojson")
    assert a.headers["etag"] == b.headers["etag"] and a.content == b.content
    assert client.get("/api/geojson", headers={"If-None-Match": a.headers["etag"]}).status_code == 304
    assert a.json()["metadata"]["licence"] == "CC0 1.0"


# ---- checksum ---------------------------------------------------------------------------------


def test_risk_result_unchanged_by_the_map_build(db_session, map_run):
    now = atypicality_run.risk_result_checksum(db_session, map_run.run_id)
    assert map_run.counts["risk_result_md5_before"] == map_run.counts["risk_result_md5_after"] == now
