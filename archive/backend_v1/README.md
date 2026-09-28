# ARCHIVED: the old MPLADS Sentinel backend (v1). Do not run or deploy.

This folder is kept as a **forensic reference only**. It was archived at the
Phase 12 cutover (SENTINEL_REBUILD_PLAN_v2.md), when the live frontend was
switched to `backend_v2/`.

## What's here

- **`backend/`** is the old FastAPI backend, moved unchanged from the repo
  root's `backend/`. It includes:
  - `app/`: the in-memory pandas engine.
  - `data/`: its CSV, GeoJSON and risk-history files.
  - `requirements.txt`.
- **`scripts/`** holds the old backend's tooling, moved unchanged from the
  repo root's `scripts/`: dataset generation, geocoding, and debug and
  validation scripts. Most of them hard-code `PROJECT_ROOT / "backend"`, so
  they will not run from this location as-is.

## Why it is kept

- Earlier phases cite this code as the specification of the old behaviour.
  The comments in `backend_v2/app/**` refer to it by its original paths
  (for example, `backend/app/risk/confidence.py` now lives at
  `archive/backend_v1/backend/app/risk/confidence.py`).
- `backend_v2/tests/test_phase5_fusion_unit.py` reads the old risk and
  feature sources from here. It uses them to prove that the v3-compatible
  fusion reproduces the old engine exactly.
- The confirmed defects that the rebuild fixed are documented against this
  code. The Phase 12 regression suite
  (`backend_v2/tests/test_phase12_cutover.py`) lists each one.

## Do not

- **Start it on port 8000.** That port is now backend_v2's, and it is the
  target of the frontend dev proxy (`docker-compose.yml`).
- **Point `vercel.json` back at it.**
- **Edit it.** A forensic reference is only useful unchanged.

One deliberate exception: `backend/.env` was deleted on 2026-09-28 at the owner's request. It held a
live Gemini API key, which must be rotated. It was git-ignored and never committed. Nothing else here
has changed.
