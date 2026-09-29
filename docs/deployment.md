# MPLADS Sentinel: deployment (Phase 14)

## Architecture

| Part | Where | What |
| --- | --- | --- |
| **Frontend** | Vercel | A static build of `frontend/` (React + Vite, unchanged except the `API_BASE` line). SPA rewrite only. |
| **Backend** | Persistent container (`api` in `docker-compose.deploy.yml`) | FastAPI `backend_v2` on **one** uvicorn worker. It publishes no host port and is reachable only through the tunnel. |
| **Worker** | Persistent container (`worker`) | `python -m worker.main` |
| **Database** | PostgreSQL | Holds published **run 44**, checksum `c4d589e0e0fc40621d4e011a64a7233d`. The demo path uses the existing local run-44 database (host port 5447). |
| **HTTPS for the API** | Cloudflare **quick tunnel** (`cloudflared`) | `https://<random>.trycloudflare.com` → `http://api:8000`. No Cloudflare account, domain or DNS is needed. |

- Cloudflare terminates TLS, so the HTTPS Vercel page can call the API; a browser blocks an `http://` API from an HTTPS page.
- **The tunnel URL changes every time the `cloudflared` container restarts.** See "After a restart" below.
- The backend is **not** a Vercel serverless function. The old root `vercel.json`, which deployed `backend_v2` as a Vercel service, has been removed.

## Environment variables

| Name | Set where | Public / secret | Value |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Vercel project → Environment Variables (Production and Preview) | **Public**: compiled into the JS bundle | `<tunnel URL>/api` |
| `DATABASE_URL` | `ops/deploy/deploy.env` (git-ignored) | Secret | run-44 database |
| `JWT_SECRET` | `ops/deploy/deploy.env` | Secret | ≥ 32 random characters |
| `CORS_ORIGINS` | `ops/deploy/deploy.env` | Public | `https://sentinel-mplads.vercel.app` (exact; never `*`) |
| `ANONYMOUS_READ` | `ops/deploy/deploy.env` | Public | `true`: the unchanged frontend sends no token |
| `GEMINI_API_KEY` | `ops/deploy/deploy.env` | Secret | The **rotated** key, attached last (step 5) |
| `TRUSTED_PROXIES` | `docker-compose.deploy.yml` | Public | `172.30.14.10`, the cloudflared container |
| `APP_ENV` | `docker-compose.deploy.yml` | Public | `production` (refuses to start without a real `JWT_SECRET`) |

`VITE_*` variables are public, so never put a key in one. Templates: `frontend/.env.example`, `ops/deploy/deploy.env.example`.

## Vercel project settings

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework preset | Vite (auto-detected) |
| Node.js version | 20.x (Project → Settings → General) |
| Install command | `npm ci` |
| Build command | `vite build` (the `npm run build` script) |
| Output directory | `dist` |
| `frontend/vercel.json` | `{"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]}` |

Vercel serves a static file first when one exists at the path. Every other path gets `index.html`, so deep links and refreshes load the app.

## Start to finish

Run from the repository root unless noted. Steps marked **(owner)** are yours.

### 1. Backend stack and quick tunnel
```bash
cp ops/deploy/deploy.env.example ops/deploy/deploy.env       # fill DATABASE_URL, JWT_SECRET; leave GEMINI_API_KEY empty
docker start sentinel-p5c-pg                                 # demo path: the local run-44 database
docker build -t sentinel-deploy-api backend_v2
docker compose -f docker-compose.deploy.yml --env-file ops/deploy/deploy.env up -d
```
Get the tunnel URL with the first command of step 2, then check it with `curl -s "$URL/api/health"`.

On a real host, restore the run-44 backup instead of re-running the pipeline:
```bash
pg_restore --no-owner --dbname "<libpq URL of the hosted database>" sentinel_<timestamp>.dump
```
The dump comes from `ops/backup/backup.sh`.

### 2. After a restart: the new tunnel URL (two commands)
Restarting the `cloudflared` container, or the machine, gives a new `*.trycloudflare.com` URL. The API URL is compiled into the frontend bundle, so Vercel must rebuild. From the repository root:
```bash
URL=$(docker compose -f docker-compose.deploy.yml --env-file ops/deploy/deploy.env logs cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1) && echo "$URL"
cd frontend && npx vercel env rm VITE_API_BASE_URL production -y; printf '%s/api' "$URL" | npx vercel env add VITE_API_BASE_URL production && npx vercel deploy --prod; cd ..
```
- For a preview instead of production, use `preview` in both `env` commands and plain `npx vercel deploy`.
- Nothing else changes. `CORS_ORIGINS` names the frontend URL, which stays the same, and the API needs no restart.
- Re-run the post-deploy gate (step 3) with the new URL.

### 3. Post-deploy gate (must PASS before sharing anything)
```bash
cd backend_v2
DATABASE_URL=... python scripts/postdeploy_gate.py --manifest ../ops/deploy/manifest_run44.json --api-url "$URL"
```
It checks:
- the Alembic revision and published run 44;
- the checksum `c4d589e0…`;
- every table's row count against the manifest, except accounts, case events and reviews created after deploy;
- the serving build and the CRITICAL/HIGH totals;
- that the public API answers and serves the same totals.

### 4. Frontend on Vercel: preview deploy and test (owner, step by step)
Run from the repository root in Git Bash. Each block is copy-paste.

**4a. Current tunnel URL** (the same command as step 2):
```bash
URL=$(docker compose -f docker-compose.deploy.yml --env-file ops/deploy/deploy.env logs cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1) && echo "$URL"
```

**4b. Log in, link, set the API URL, deploy a preview:**
```bash
cd frontend
npx vercel login
npx vercel link --project sentinel-mplads --yes              # writes frontend/.vercel (git-ignored)
printf '%s/api' "$URL" | npx vercel env add VITE_API_BASE_URL preview
printf '%s/api' "$URL" | npx vercel env add VITE_API_BASE_URL production
npx vercel deploy                                            # PREVIEW only; the last line printed is the preview URL
cd ..
```
In the Vercel dashboard, check Project → Settings: Root Directory `frontend`, Node.js 20.x.

**4c. Allow the preview URL in CORS (test window only):**
```bash
PREVIEW=https://<the preview URL printed by vercel deploy>
sed -i "s#^CORS_ORIGINS=.*#CORS_ORIGINS=https://sentinel-mplads.vercel.app,$PREVIEW#" ops/deploy/deploy.env
docker compose -f docker-compose.deploy.yml --env-file ops/deploy/deploy.env up -d api
curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS -H "Origin: $PREVIEW" -H 'Access-Control-Request-Method: GET' "$URL/api/summary"   # expect 200
```
If Deployment Protection is on, switch it off for this test (step 5 switches it back on).

**4d. Route tests against the real preview** (every route, direct and refresh; query strings; House selector after refresh; unknown path; copilot):
```bash
docker exec -i sentinel-p5c-pg psql -U sentinel -d sentinel -At < ops/deploy/routes/expected.sql > ops/deploy/routes/expected.json
MSYS_NO_PATHCONV=1 docker run --rm --network host -v "$PWD/ops/deploy/routes:/work" mcr.microsoft.com/playwright/python:v1.47.0-jammy \
  sh -c "pip install -q playwright==1.47.0 >/dev/null 2>&1; cd /work && python vercel_routes.py $PREVIEW $URL /work/out"
```
Expect `vercel route checks: 101 passed, 0 failed`. Screenshots are in `ops/deploy/routes/out/`, which is git-ignored.

**4e. Remove the preview URL from CORS again:**
```bash
sed -i "s#^CORS_ORIGINS=.*#CORS_ORIGINS=https://sentinel-mplads.vercel.app#" ops/deploy/deploy.env
docker compose -f docker-compose.deploy.yml --env-file ops/deploy/deploy.env up -d api
curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS -H "Origin: $PREVIEW" -H 'Access-Control-Request-Method: GET' "$URL/api/summary"   # expect 400
```

**4f. Access check through the public URL** (expect 401 for each; 200 for the last):
```bash
for ep in "POST /api/investigate/251224" "GET /api/audit-trail" "GET /api/cases/251224/events" "GET /api/audit/samples" "POST /api/audit/items/abc/reviews" "GET /api/entities/payee/1"; do set -- $ep; echo "$2 $(curl -s -o /dev/null -w '%{http_code}' -X $1 -H 'Content-Type: application/json' -d '{}' $URL$2)"; done
echo "/api/summary $(curl -s -o /dev/null -w '%{http_code}' $URL/api/summary)"
```

Never use a regex or a wildcard for CORS. The production deploy (`npx vercel deploy --prod`) is **the owner's call**; do step 5 first.

### 5. Before sharing the link or attaching the Gemini key (owner)
1. **Keep it unlisted.** Vercel → Project → Settings → Deployment Protection → *Vercel Authentication* (Standard Protection) for previews, or *All Deployments* to cover production too.
   - Alternatively, put Cloudflare Access in front of a custom frontend domain.
   - Do **not** put Access on the API URL: the browser's cross-origin API calls can't carry the Access login.
2. **Rotate the Gemini key.** Put the new one in `ops/deploy/deploy.env` as `GEMINI_API_KEY=...`, then run `docker compose -f docker-compose.deploy.yml --env-file ops/deploy/deploy.env up -d api`.
3. **Push** the repository. The first push gives CI its first real run.

## CORS

- `CORS_ORIGINS` is an exact list read from the environment. A `*` refuses to start the API, `CORS_ORIGIN_REGEX` is empty, and credentials are off.
- Preview URLs are refused unless one is listed explicitly for a test window (option (i)).
- The frontend uses **no cookies and no Authorization header**: every call is a plain `fetch`. So no cross-site cookie settings (`SameSite=None; Secure`, `allow_credentials`) are needed. If a future frontend sent the bearer token, the header is already allowed and credentials stay off.

## Client IP and rate limits

- `app/auth/ratelimit.py` uses forwarded headers **only when the TCP peer is in `TRUSTED_PROXIES`**: the cloudflared container, pinned to `172.30.14.10` on a fixed network.
- It then takes Cloudflare's `CF-Connecting-IP`, else the right-most untrusted `X-Forwarded-For` hop.
- A client-written `X-Forwarded-For` is ignored, as are all forwarded headers from any other peer.
- uvicorn runs with `--no-proxy-headers` so it does not rewrite the peer itself.
- **Fixed in Phase 14:** the old `TRUST_FORWARDED_FOR` flag took the left-most `X-Forwarded-For` entry from any caller, which let a client choose its own rate-limit key. It has been removed.
- The limiter is **in-process memory**, so the API runs **one worker**. More workers or replicas would need a shared store (for example Redis) behind the same `RateLimiter` interface.

## Access from the public site

- The public site is anonymous and calls the API with no token. With `ANONYMOUS_READ=true` (the explicit switch) it gets the national, read-only `public` role.
- These all answer **401** to it:
  - investigate, and the recalculate request;
  - the audit trail and its verification, and the case export;
  - audit samples, items, reports and reviews;
  - payee profiles.
- `tests/test_phase14_deploy.py` checks each one, and they were also checked live through the tunnel.
- `ANONYMOUS_READ=false` closes every data endpoint to anonymous callers, which also takes the public site down, because it cannot log in.

## Known limitations (accepted, Phase 14)

- **No Graph route.** The graph API exists, but `App.jsx` has no page for it.
- **No not-found page.** An unknown path renders the app shell with an empty content area. Vercel serves `index.html`, so it is never a server 404.
- **Recalculate** on the Record page shows its existing "request failed" notice, because the public role cannot write case events.
- **Investigate, audit and reviewer features are unreachable from the public site**, which sends no token.
- **The login page is a client-side demo.** It never calls `/api/auth/login`.
- **Rate limiting is per process** (one API worker).
- **The demo backend is a quick tunnel to a local Docker stack.** It is up only while this machine and the `sentinel-deploy` stack are running.
  - Its URL changes on every `cloudflared` restart; run the two commands in step 2.
  - Quick tunnels have no uptime guarantee (Cloudflare documents them for testing). A stable URL needs a named tunnel on a Cloudflare-managed domain, or a hosted backend.

## Tests

- `backend_v2/tests/test_phase14_deploy.py`: CORS preflight from the production origin passes and other origins are refused; the single-preview add/remove; the trusted-proxy client-IP rules and a spoofing attempt; the anonymous 401s and the `ANONYMOUS_READ` switch; the deploy files.
- `python ops/ci/secret_scan.py --root frontend/dist --walk`: the build output holds no key patterns.
- Browser tests against the real Vercel preview: every route by direct navigation and refresh, query strings, the House selector after a refresh, an unknown path, and the copilot. Results are in `docs/validation_report_v1.md` §12.
