# MPLADS Sentinel — Validation Report v1.0

| | |
| --- | --- |
| Report version | 1.0, 2026-09-28 (Phase 13) |
| Engine | `context_v1` |
| Default risk configuration | `v4-candidate`. The fusion config hash is `953866a5ebbd97cf…` |
| Published run | 1 (Snapshot A, data as of 2026-08-30) |
| risk_result checksum (run 1) | `97f08303369f9ed6c50e46d68a4609f5`. It is unchanged through Phases 5c–13. |
| API version | `2.0.0-phase13` |
| Database revision | Alembic `99c1d3031fb9` |

BLUEPRINT.md §12 ("Reporting") asks for a versioned validation report covering:
- data reconciliation;
- test coverage;
- stability and sensitivity;
- ablations;
- the audit-sample protocol;
- every limitation.

Phase 13 adds:
- the known-defect suite across all phases;
- the security checklist;
- the executed restore test;
- performance at full volume;
- a verification, against this implementation, of every §14 "cannot claim" item.

Every figure below comes from a named test, script or query over the live data. Nothing is
restated from earlier text without being re-checked.

---

## 1. Data reconciliation (Phase 1; BLUEPRINT §12 "Data contracts", "Reconciliation")

**Core files.** All nine reconcile to the portal's own footer totals and to the BLUEPRINT §2
control figures, to four decimal places in crore:

| File | Figure |
| --- | --- |
| Payments LS | 2,736.15 |
| Payments RS | 1,232.93 |
| Allocation LS | 8,318.06 |
| Allocation RS | 3,363.85 |
| Completed LS | 1,632.00 |
| Completed RS | 755.42 |
| Recommended LS | 5,638.66 |
| Sanctioned LS | 4,117.67 |
| Sanctioned RS | 1,693.24 |

Sources: `docs/phase1_reconciliation_report.md`, and compliance check C9, which passes 9 of 9 in
run 1.

**Contract rejects.**
- The nine core files have 0 rejected rows.
- Snapshot B's recommended file has 30 rows rejected with reason code `SCHEMA_VIOLATION`. They are
  logged in `import_reject`, not dropped silently.

**Referential.** 361 sanctioned Lok Sabha works are absent from the recommended file. They are
logged (C8 `sanctioned_in_recommended_file`), matching BLUEPRINT's figure.

**Identity.**
- 136 portal IDs were shared by different Lok Sabha and Rajya Sabha works.
- Phase 5a split each into House-qualified works.
- C8 `one_record_per_portal_id_and_house` now reports 0 failures over 122,965 works.

**Deterministic compliance panel** (outside the score; run 1):

| Check | Result |
| --- | --- |
| C1 actual ≤ sanction | 0 of 43,842 fail |
| C2, C3 payments | 0 fail |
| C4 dates in order | 0 fail |
| C5 completed within one year | 5,203 of 43,842 (11.87%) take longer |
| C5 open works | 13,476 open past one year |
| C6 completed without a payment | 100 |
| C7 | 0 fail |
| C8 FLAG-2 rows lacking stage and sanction date | 499 |

Source: `docs/phase5_gate_report_v3.md`.

**Restore of the whole dataset.** Every one of the 52 tables and 3,397,783 rows was reproduced
exactly from a backup (§8).

## 2. Test coverage and results (BLUEPRINT §12 "Unit", "Property", "Golden", "Known-defect", "API and UI", "Migration")

The suite runs as **one CI job**, `regression` in `.github/workflows/ci.yml`. It covers:
- lint;
- all pytest suites, run against the database built by the full pipeline;
- the executed restore test;
- the House-toggle browser e2e against the real-data API.

**Final local run** (after the pre-Phase 14 fixes, 2026-09-28): **604 passed, 5 skipped, 0 xfailed, 0 failed** (17 min 40 s; 609 tests; lint clean; secret scan 0 findings). The 5 skips are the 4 browser e2e tests, run separately against the real-data stack (4/4 passed), and one Phase 11 test that has no NOT_EVALUATED work to use in run 1. Browser checks on the same build: 93/93 targeted checks passed, and 54 page visits across all three House states showed no page errors. The only failed requests were the 3 deliberate visits to a missing record (404). risk_result checksum after all runs: `97f08303…`.

| Suite | Tests | What it proves |
| --- | ---: | --- |
| `test_contract.py` | 80 | See [Contract suite](#contract-suite). |
| `test_phase1_ingest.py` | 8 | Reconciliation, House tagging, idempotent re-ingest (same output hash), reject policy |
| `test_phase2_normalize.py` | 9 | Parsing rules, the referential gap, the NaN-vs-NULL fix |
| `test_phase3_peers_unit.py`, `test_phase3_context.py` | 9 + 12 | See [Peer context](#peer-context). |
| `test_phase4_signals_unit.py`, `test_phase4_signals_context.py` | 45 + 17 | See [Base signals](#base-signals). |
| `test_phase5_fusion_unit.py`, `test_phase5_risk_context.py`, `test_phase5a_*` | 29 + 10 + 28 | See [Fusion and risk](#fusion-and-risk). |
| `test_phase6_atypicality.py`, `test_phase7_survival.py` | 34 + 43 | ML layers stay evidence-only; leakage guards; censoring; no ML in fusion |
| `test_phase9_map.py` | 80 | See [Map](#map). |
| `test_phase10_entities.py`, `test_phase11_chat.py` | 47 + 18 | Payee typing, entity metrics with denominators, graph bounds; the copilot is grounded and fails closed |
| `test_phase12_cutover.py` | 37 | See [Cutover known-defect suite](#cutover-known-defect-suite). |
| `test_phase13_security.py` | 32 | The §11 security checklist, one section per row (§6), including the CI secret scan and `.env` exclusion |
| `test_phase13_claims.py` | 14 | §14 claims discipline (§7), including the frontend copy in all 12 languages |
| `test_phase13_redaction.py` | 42 | Phone masking in every public output; no false positives; raw text unchanged (§10) |
| `test_phase13_audit_sample.py` | 4 | The randomised audit-sample mechanism (§9) |
| `tests/e2e/test_house_toggle_e2e.py` | 4 | See [Browser e2e](#browser-e2e). |
| Other | 7 | Report-note guards and a placeholder |

### Contract suite

- All 32 frontend endpoints are called against real data.
- Top-level and item-level shapes are checked, and every list must be non-empty.
- Case endpoints need an authenticated caller.
- The House parameter works on the seven endpoints that take it.

### Peer context

- Leave-one-out: a work never counts itself.
- Coverage figures match BLUEPRINT to within ±1.5 percentage points.
- House-mixed peer groups.

### Base signals

- Unit cases: peer groups of size 2, 3 and 4, identical amounts, missing amounts.
- Property tests with Hypothesis: shuffling rows never changes a score; raising an amount never
  lowers the cost score.
- Each signal attaches to the row that owns its group.

### Fusion and risk

- The old engine is reproduced exactly (v3-compatible).
- Tier boundaries.
- A not-evaluated signal is never scored as 0.
- Corroboration is counted once.
- Identity split and calibration.

### Map

- No regex crash on search.
- No stacked or fake coordinates.
- Payload bounds.
- Stale-data rule.
- Rajya Sabha not-applicable panels.

### Cutover known-defect suite

It covers every old-engine defect class:
- self in the peer group;
- positional misalignment;
- stage-multiplied rows;
- special-character search;
- map precision and payload;
- a failed endpoint;
- missing routes;
- route order;
- `/api/load`;
- the graph;
- impossible tiers;
- House-filter correctness.

### Browser e2e

- The House toggle is checked against the real-data API.
- It must send exactly the seven House-scoped calls.
- It must show the Rajya Sabha not-applicable panels.

**Golden regression.**
- The md5 checksum of run 1's risk_result is `97f08303…`.
- Every phase since 5c records it before and after its own work and aborts if it changes.
- It is unchanged at the end of Phase 13, and it matches in a restored copy on a different
  PostgreSQL build (§8).

**Migration.**
- Every migration is create or add only.
- Phase 13's migration was run up → down → up on the real database.
- The restored copy matches the Alembic revision.

## 3. Stability, sensitivity and ablation (Phase 5 gate; BLUEPRINT §12 "Stability", "Sensitivity", "Ablation")

Source: `docs/phase5_gate_report_v3.md`, owner decision of 2026-09-26: v4-candidate is the default.

| Gate item | v4-candidate (default) | Status |
| --- | --- | --- |
| K3 reachability: CRITICAL reachable with ≥ 3 evaluated signals | 100.0% of works | PASS |
| K2 weight sensitivity: each weight ±20%, 50 seeded draws | Top-1,000 overlap median 96.8%, P5 89.8%, min 89.4%; median 4.49% of works change tier | PASS (target: median ≥ 80%, P5 ≥ 70%) |
| K1 missing-signal behaviour | A not-evaluated signal is dropped from the denominator, not scored 0 | PASS |
| K5 corroboration counted once | No additive pattern term | PASS |
| Tier-boundary fixtures | 13 of 13 | PASS |
| K4 HIGH + CRITICAL ≤ 20% | **32.5%** | **FAIL**, accepted as an explained limitation (see K4 below) |

**K4.** The ablation shows the cause. The corroboration multiplier (×1.15 at 4 or more active
signals) applies to 92.5% of works; without it the rate is 16.7%.

**Ablation.** Each signal removed in turn, top-1,000 overlap with the full ranking:

| Signal removed | Overlap |
| --- | ---: |
| cost_anomaly | 43.4% (the ranking leans on it most) |
| near_duplicate | 50.2% |
| temporal_anomaly | 67.3% |
| portfolio_concentration | 68.0% |
| district_authority_pattern | 75.1% |
| lifecycle_delay | 96.8% |

**Rank agreement.** v3-compatible and v4-candidate agree with Spearman 0.938, but their top-1,000
overlap is only 7.4%. The default was an owner decision, recorded with this evidence.

**Not done:**
- Synthetic injection (detection-versus-magnitude curves).
- Hand-labelled duplicate pairs (about 500 pairs).

No phase built them. See the limitations in §10.

## 4. ML validation summary (Phases 6/8 and 7; BLUEPRINT §7, §12 "What each ML layer must show")

**No Phase 8 deliverable exists as a separate artefact.** Its registry and explainability work
landed in Phase 6, whose report is titled "Phase 6/8". There is no consolidated ML validation
report and **no written gate-G6 criteria document**. This section is compiled from:
- `docs/phase6_atypicality_report.md`;
- `docs/phase7_report.md`;
- the `model_version` registry.

It is not a substitute for Phase 8's missing documents (flagged in §11).

### Layers

| Layer | Registry | Validation result | Status |
| --- | --- | --- | --- |
| B4 robust Mahalanobis (MinCovDet) | id 3: algorithm, feature-spec hash `59dbbc66…`, training snapshot 1, seed 20260926, metrics, artifact hash | See [B4](#b4-multivariate-atypicality). | **Active, evidence only** |
| B4 Isolation Forest (comparator) | id 4: same metadata | Agrees with Mahalanobis at Spearman 0.921, but top-1,000 overlap is only 32.7% | **Active, evidence only** |
| A1 Cox time-to-completion | id 5: coefficients and metrics | Out-of-time C-index 0.553 (Lok Sabha 0.554, Rajya Sabha 0.570; strict variant 0.555), barely above chance (0.5) | **Inactive experiment** (owner decision). 0 forecast rows. |
| A2 365-day delay (day 90 / day 180) | Not registered | Brier 0.2527 vs base rate 0.2500; 0.2352 vs 0.2343. AUC 0.538 / 0.544. No better than the base rate out of time. | **Closed, not shipped** |

### B4 multivariate atypicality

- Evaluated on 76,732 Lok Sabha works.
- 0 Rajya Sabha works are evaluated: they have no recommendation date (Hard Limit 6), so they are
  not evaluated rather than imputed.
- Orthogonality to cost anomaly is Spearman 0.280, so it is not just rediscovering large amounts.
- Per-feature contributions sum to the squared distance, which is the explainability surface.
- Leakage guard: MP identity, payee identity and risk score raise `LeakageError`.

### Leakage and validity (BLUEPRINT §7)

Leakage:
- A1 and A2 use features known at prediction time only.
- `amount_used`, which is the actual amount after completion, is barred.
- Calendar quarter is dropped as a cohort proxy.
- Payments are time-cut at sanction + t.

Validity:
- Open works are right-censored, never dropped.
- Everything is validated out of time.

### Gate G6

**No ML layer enters risk_score.** This is verified as fact in §7:
- fusion reads only the six base signals;
- no ML table or library is reachable from the scoring code;
- risk_result has no ML-derived column.

## 5. Performance at full volume (BLUEPRINT §5 runtime target; §12 "Performance")

Source: `docs/performance_report.md`, run 2026-09-28. The full pipeline ran on a fresh,
empty PostgreSQL 16 instance over 122,965 works, 107,826 payments and 655,306 raw rows, on a
Windows laptop under Docker Desktop.

| | |
| --- | --- |
| Full pipeline as scripted (CI order) | **49.7 min** |
| Minimal path to one published run | **39.4 min** (derived: `run_risk.py` rebuilds context and signals itself) |
| Slowest stages | fusion + compliance 826 s; signals 534 s; ingest 411 s |
| Peak memory of one stage | 1,521 MB |
| 3× volume, worst-case estimate | about 296 min |
| 3× memory estimate | about 4.6 GB |

**Against the §5 target.** §5's target, "in minutes on a laptop-class machine", is stated as a
target to verify with no numeric limit, so no pass or fail is declared. The owner should judge
39–50 minutes.

**3× volume estimate.** It is an estimate, not a measurement. The group-quadratic stages are
scaled 9×.

**Reproducibility (§5 "Idempotent").** Rebuilding everything from an empty database reproduced the
pipeline's own output hashes exactly:

| Hash | Value |
| --- | --- |
| Signals | `7f98f33d…` |
| Risk | `708357bb…` |
| Fusion config | `953866a5…` |

The md5 regression checksum is a different, stricter guard:
- A rebuild differs from it only in float last bits: at most 4.3e-14 on risk, and one unit in the
  last place on confidence.
- Every tier and count is identical.
- The cause is summation order.
- The md5 therefore guards the stored run against any change, which is its role in every phase.
  It is not a cross-rebuild check.

## 6. Security checklist (BLUEPRINT §11 Controls; `tests/test_phase13_security.py`)

| §11 row | Verified behaviour | Result |
| --- | --- | --- |
| Authentication | See [Authentication](#authentication). | PASS |
| Authorisation | See [Authorisation](#authorisation). | PASS |
| Identity in audit | The actor is the token's account. A `reviewer` in the body is ignored (investigate) or rejected with 422 (audit review). | PASS |
| Audit trail | See [Audit trail](#audit-trail). | PASS |
| Imports | No route has a path, file or directory parameter; no load or import endpoint exists; imports are CLI-only. | PASS |
| CORS | See [CORS](#cors). | PASS |
| Rate limits | Login (per address and per username), copilot and search return 429 with `Retry-After`. Browsing without a search term is unaffected. | PASS |
| Input handling | See [Input handling](#input-handling). | PASS |
| Secrets | No key pattern in any tracked file, and CI now fails if one appears (`ops/ci/secret_scan.py`). Every `.env` at every level is git-ignored and docker-ignored; no Dockerfile copies one. The archive `.env` copy is deleted. `JWT_SECRET` has no usable default. **Key rotation is still the owner's action; see [Secrets](#secrets).** | PASS |
| Backups | A scheduled `backup` service exists, and the restore test was executed and passed (§8). | PASS |
| Copilot | See [Copilot](#copilot). | PASS |
| Personal data | Phone numbers are masked in every public output (see [Personal data](#personal-data)). The public graph withholds names of individual and untyped payees. Payee profiles are never public. | PASS |

Security issues found **in the pre-Phase 13 code** and fixed:
- CORS was `allow_origins=["*"]` with `allow_credentials=True`, exactly what §11 forbids.
- Investigate recorded a placeholder actor.
- The dev dependencies were unresolvable: `httpx==0.27.2` conflicted with `google-genai`, so CI's
  first install step would have failed.
- A 61–100 character investigation decision passed validation, then failed in the database.

### Authentication

- Login returns an HS256 JWT valid for 15 minutes, with OIDC claims.
- Passwords are stored as salted scrypt hashes.
- A wrong password and an unknown user get the same 401.
- Tampered, expired, unsigned and wrong-audience tokens are all rejected.
- A disabled account's token fails immediately.
- An invalid token never falls back to anonymous.

### Authorisation

- Every `/api` route resolves the caller; this is checked by walking the dependency tree.
- State, district, MP and House scopes are applied in SQL. This is verified on:
  - the summary, queue, analytics and lists;
  - record, risk and chat (out-of-scope reads as absent);
  - map-works, map-data and map-filters, re-aggregated under the scope.
- National-only figures (the graph, payee profiles) are refused to scoped accounts.
- Case writes need an investigator, supervisor or admin.
- Auditors are blind to tiers.
- Anonymous access can be switched off.

### Audit trail

- No application code updates or deletes `case_event`.
- Timestamps come from the server.
- The hash chain verifies, and a tampered middle event is detected at that event.
- Per-case export includes the hashes.

### CORS

- An allowed origin is echoed back; an unlisted origin gets no CORS headers.
- Credentials are off.
- A wildcard in `CORS_ORIGINS` refuses to start the app.

### Input handling

- Every request body is a Pydantic model.
- Bounds are enforced (422).
- Five injection payloads were tried on six parameters. They are inert: matched literally, with no
  rows returned and no tables touched.
- No SQL is built with `%` or `.format`.

### Secrets

Resolved before Phase 14 (owner request), except rotation:
- **History.** The repository has no git history yet, so no secret can have been committed. The CI
  step scans every blob of every commit (`--history`) from the first push on.
- **CI check.** `ops/ci/secret_scan.py` runs first in the `regression` job. It fails on any tracked
  file with a key pattern (Google API key, Google token, private key, AWS, GitHub, Slack,
  OpenAI/Anthropic-style key, JWT), a tracked `.env`, or a secret-named variable set to a literal.
  It prints file, line and pattern name only, never a value. Current tree: 0 findings.
- **Local copies.** `archive/backend_v1/backend/.env`, the old prototype's copy of the key, is
  deleted. The repo-root `.env` (git-ignored, the developer's own) remains.
- **Ignore rules.** `.gitignore`, `backend_v2/.dockerignore` and a new root `.dockerignore` exclude
  `.env`, `.env.*`, `**/.env` and `**/.env.*`; `.env.example` stays trackable. The only
  Dockerfile (`backend_v2/Dockerfile`) copies no `.env`. A test Docker build copied 0 `.env` files.
- **Still the owner's action:** the key was on disk in two places, so it must be **rotated in
  Google Cloud** and the old one revoked. That can't be done from this codebase.

### Copilot

- It is grounded on stored results.
- It is scope-aware.
- It is rate-limited.
- A token never reaches the model.
- It never changes the checksum.
- Its system prompt forbids every cannot-claim item.
- Phone numbers are masked in the message and history before they reach the model.

## 7. Claims discipline: every §14 "cannot claim" item verified against this implementation (`tests/test_phase13_claims.py`)

**Text scanned.** Each area was scanned for each claim; a match is allowed only inside a
disclaiming sentence:
- every backend string literal;
- live API responses, anonymous and authenticated, from 44 endpoint and record combinations;
- the copilot's answers to 10 adversarial prompts and 6 work explanations;
- its generated method text and its system prompt;
- the frontend's UI copy in all 12 languages.

| Cannot claim | Fact checked in code or data | Text result |
| --- | --- | --- |
| Cost-overrun detection | 0 of 43,842 completed works have actual > sanction, so there is nothing to detect. It is reported as integrity check C1. No overrun route or field exists. | No claim anywhere |
| Fraud detection or probability | No fraud or probability field in any work response. The copilot says "never determines fraud". | No claim anywhere |
| Multi-Lok-Sabha history or longitudinal MP analysis | No API, serving, geo or entity code reads `prior_cycle_work`. MP profiles cover the served snapshot only (18th Lok Sabha and sitting Rajya Sabha). | No claim anywhere |
| Vendor wrongdoing from concentration alone | No such endpoint. Entity metrics carry denominators, intervals and peer definitions (BLUEPRINT §8 wording rules). | No claim anywhere |
| Ratings, image or asset verification | No such data, endpoint or field. | No claim anywhere |
| Coordinates or map-level location of works | `X-Location-Precision: approximate_constituency_level`. Every marker is `CONSTITUENCY` level, one point per constituency, "not the work's site". | No claim anywhere |
| Any ML in the score before gate G6 | See [ML in the score](#ml-in-the-score). | No claim anywhere (frontend fixed; see [Frontend copy](#frontend-copy)) |

### ML in the score

- `fusion.BASE_SIGNALS` holds only the six rule signals.
- The published weights cover only those six.
- `fusion.py`, `confidence.py` and `risk_run.py` never reference `atypicality_result`,
  `forecast_result`, `model_version`, sklearn or lifelines.
- risk_result has no ML-derived column.
- No forecast model is active.

### Frontend copy

**Resolved before Phase 14 (owner-approved change).** Three strings presented the rule-based
ranking as AI:
- `login.brand.point2`: "AI-assisted anomaly and risk detection";
- `landing.principle.statement` and `meth.principle`: "AI prioritizes. Evidence explains. Humans
  decide."

They now say that risk indicators prioritise records for human review and are not evidence of
wrongdoing.

`meth.lim.6` wrongly said the data has no contractor, payment or agency information. It now:
- lists what the data lacks: tender, beneficiary, inspection, physical-progress and site-GPS
  records;
- says payments, payees and agencies are evidence only, never in the score;
- names all seven cannot-claim items the copilot's prompt enforces.

| Language file | Change |
| --- | --- |
| `en.js` | All four keys rewritten |
| `hi.js` | `landing.principle.statement`, `meth.principle` and `meth.lim.6` translated. It has no `login.brand.*` keys, so the login line falls back to English. |
| `as`, `bn`, `gu`, `kn`, `ml`, `mr`, `or`, `pa`, `ta`, `te` | The keys are removed, so they fall back to the English text. No translation was guessed. |

The expected-failure marker is removed, and `test_frontend_copy_makes_no_cannot_claim` passes. A
new test checks that no language file keeps an "AI" claim in any of the four keys (Latin script
plus nine Indian scripts). The only remaining "AI" text is the copilot's own label ("AI-powered
(Gemini)"), which is true.

**Fixed in backend text.** The chatbot's system prompt described the Methodology page's "AI
prioritises" motto as fact. It now states that the score is rule-based and that no AI or ML is
part of it, and it lists all seven cannot-claims. The deterministic guide gained honest answers
for cost-overrun, history and ML questions.

## 8. Backup and restore: executed (BLUEPRINT §11 "Backups")

Source: `docs/restore_test_report.md`. **RESULT: PASS**, run on 2026-09-28.

**Steps:**
1. Back up with the scheduled job's own script (`ops/backup/backup.sh`): a 139 MB custom-format
   dump, checked readable, with its SHA-256 recorded. 98 s.
2. Restore into a **brand-new PostgreSQL 16 container** (glibc) that had 0 tables. 358 s.
3. Verify: all 8 checks PASS.
   - Alembic revision.
   - Same 52 tables.
   - All 3,397,783 rows, with zero row-count mismatches.
   - Published run (1, v4-candidate) intact.
   - risk_result checksum `97f08303…`, equal to the source and to the pinned value.
   - Serving build intact.
   - Case chain valid. There were 0 events at dump time: tests remove their own. Chain tamper
     detection is covered in §6.
4. Run the contract and Phase 12 cutover suites **against the restored database**: 117 passed.

**A bug the restore test found.** The checksum was collation-dependent: it ordered by the
database's default collation, `en_US.utf8`.
- The musl-based `postgres:16-alpine` used so far sorts keys by bytes. glibc's `postgres:16` does
  not, so the same rows gave a different md5 on the restored server.
- The fix orders by `COLLATE "C"`. The value on alpine is unchanged (`97f08303…`), and it is now
  identical on every server.
- It would have made every checksum check fail on most managed PostgreSQL services.
- The GeoJSON version hash had the same flaw and was fixed the same way.

The same script runs in the CI `regression` job.

## 9. Randomised audit sample: mechanism (BLUEPRINT §12)

**Design.**
- Tier-stratified simple random sampling without replacement, seeded and stored with its design
  (population sizes, quotas, drawn counts, seed, method).
- Quotas: all CRITICAL up to 30, 100 HIGH, 100 MODERATE, 70 LOW. On run 1 that is 300 works drawn
  from populations of 7,040, 24,643, 46,744 and 19,079.
- The review order is shuffled across strata.

**Blinding.** Reviewers (the `auditor` role) see a random blind code and source facts only. They
never see the tier, score, confidence, signals or peer figures. The auditor role is refused by
every risk-bearing endpoint.

**Outcomes.** Follow-up needed, no follow-up, or data issue. The reviewer comes from the token.

**Report.**
- Per-stratum precision, excluding data issues, with Wilson 95% intervals.
- Population-weighted precision of the flagged tiers.
- Cohen's kappa over items with two or more reviews.

**Verified by tests.** 4 tests run end to end on the real run:
- draw and re-draw with the same seed, giving the same works;
- blindness of the reviewer list;
- role gates;
- reviews, with duplicates refused (409) and a reviewer in the body refused (422);
- the report maths against hand-computed values, for example Wilson(7,10) and kappa;
- the CLI `scripts/draw_audit_sample.py`.

**Human review is out of scope.** No precision estimate exists yet. Sample #13
(seed 20260928) has been drawn and left in the database, ready for a review round.

## 10. Limitations: each re-verified against the live data or code on 2026-09-28

| Limitation | Evidence (checked now) |
| --- | --- |
| **K4:** HIGH + CRITICAL is 32.5% of works (target ≤ 20%) | See [K4](#k4). |
| **Authority-state bug (open since Phase 9):** 52 district authorities have a stored state that differs from their resolved location state | See [Authority state](#authority-state). |
| `work.tenure_id` is populated for **0 of 129,019** works | The MP-tenure entity uses a synthesized (name, House) key instead (Phase 10) |
| Rajya Sabha works have no constituency: **19,274 of 19,274** | Constituency features show "not applicable" under Rajya Sabha |
| B4 atypicality evaluates **0** Rajya Sabha works | No Rajya Sabha recommended file (Hard Limit 6); not evaluated, never imputed |
| A1 and A2 forecasts are not shipped | C-index 0.553; Brier no better than the base rate. There are 0 `forecast_result` rows. |
| Single tenure and snapshot; no longitudinal analysis | Snapshot A only for scores; the prior cycle is ingested but never served (§7) |
| Work-level location is unknown | Markers are one per constituency; 139 works have no located district |
| No synthetic-injection curves, no labelled duplicate pairs | Not built in any phase. The duplicate signal's precision is unmeasured. |
| **No gate-G6 criteria document; no consolidated Phase 8 report** | Absent from `docs/` (§4) |
| No human audit results yet | The mechanism only (§9) |
| **Anonymous read is on by default** | See [Anonymous read](#anonymous-read). |
| ~~Frontend copy claims "AI prioritises" (3 strings)~~ | **Resolved:** rewritten in all 12 languages (§7) |
| ~~Frontend Methodology limitation `meth.lim.6` is out of date~~ | **Resolved:** rewritten to match the current data and the seven cannot-claim items (§7) |
| **Personal data in work descriptions** | Phone numbers are masked. Names, disability details and Aadhaar-shaped numbers remain (see [Personal data](#personal-data)). |
| Real Gemini key in the git-ignored root `.env` | The archive copy is deleted and a CI scan is in place. The key must still be rotated (§6). |
| Rate limits are per API process | Multi-process deployments need a shared store (`docs/security.md`) |
| No refresh token, no password-reset endpoint | Admin resets with `scripts/create_user.py` |
| Run manifest has no git commit | The repository has no git history yet (§11 provenance) |
| **CI has never run on GitHub** | See [CI](#ci). |
| Runtime 39–50 min on a laptop | §5 "in minutes" has no numeric limit (§5); for the owner to judge |
| The md5 checksum is not rebuild-reproducible to float last bits | Rebuilds reproduce the pipeline's rounded output hashes exactly (§5) |

### K4

- Gate report item 2.
- An owner-accepted limitation (2026-09-26), caused by the corroboration multiplier.
- Live: 31,683 of 97,506 scored works.

### Authority state

- These authorities cover **11,783 scored works (12.1%)**.
- Their peer groups, and the risk built on them, used the stored state.
- The map and the displays use the corrected location state.
- The fix is an upstream correction plus a re-run of Phases 3–5, which would change the checksum.
  **Owner's decision; still open.**

### Anonymous read

- The unchanged frontend sends no token; its login page is a client-side demo.
- The public role is national and read-only, with no case, audit or payee-profile access
  (`docs/security.md`).
- Owner decision.

### Personal data

**Phone numbers: resolved before Phase 14 (owner decision).** They are replaced with
`[phone removed]` at the output layer only (`app/serving/redact.py`).

Where masking applies:
- both read models, `served_work` and `map_work` (description and search text);
- every API response that emits a description;
- the audit-sample list;
- the copilot's message and history sent to Gemini;
- the case export and audit trail (note and decision).

What is masked: 10-digit Indian mobiles (with optional +91, 91 or 0, and spaces or hyphens),
11-digit STD landlines, mistyped 11-digit mobiles, and two mobiles glued together.

What is never touched:
- raw stored text (`work.raw_description`, `raw_row`);
- anything feeding risk_result (the checksum is unchanged, `97f08303…`);
- the stored case note and its hash chain.

What is not masked, by design: amounts, work and sanction IDs, pincodes, years, dates, 11-digit
school codes, letter numbers, decimals, and long asset or account codes.

**Run 1 figures.**
- 1,897 of 122,965 descriptions changed; 1,987 numbers masked.
- Before: 2,009 mobile-shaped 10-digit runs. After: 0 phones. 134 non-phone codes still match the
  loose mobile-shaped query.
- `tests/test_phase13_redaction.py` (42 tests) covers the rules, false positives, both read
  models, every endpoint, the copilot context, the export and the unchanged raw text.

**Still open (owner decision; not redacted).** After masking:
- 583 descriptions mention a disability;
- 514 name a contact person;
- 335 have a name next to `[phone removed]`;
- 3 contain a 12-digit Aadhaar-shaped number.

### CI

- There is no git remote.
- Every result here is from local Docker.
- The first push should get one real Actions run of the `regression` job.

## 11. Open items for the owner before Phase 14

1. ~~Secrets hygiene.~~ **Resolved** (§6). No git history exists to leak from; the archive
   `.env` is deleted; every `.env` is git- and docker-ignored; CI fails on any secret pattern.
   **Rotating the Gemini key remains the owner's action.**
2. **Anonymous read.** Keep it (the public, national, read-only role), or require login. Requiring
   login needs a frontend change so the app calls `/api/auth/login` (§10).
3. ~~Frontend copy.~~ **Resolved** (§7). The 3 "AI prioritises" strings and `meth.lim.6` are
   rewritten in all 12 languages; the claims test passes without an xfail.
4. **Authority-state bug.** Fix it upstream and re-run Phases 3–5, accepting a new checksum, or
   keep deferring it (§10).
5. **Phase 8 gap.** Write the gate-G6 criteria document and a consolidated ML report, or accept
   §4 as the record.
6. **Runtime.** Accept 39–50 minutes as meeting "in minutes", or set a numeric target (§5).
7. ~~Personal data: phone numbers.~~ **Resolved** (§10): masked in every public output.
   **Still open:** whether to redact names, disability details and Aadhaar-shaped numbers (§10).
8. **CORS.** Add the Phase 14 Vercel origin and preview pattern to `CORS_ORIGINS` and
   `CORS_ORIGIN_REGEX` (`docs/security.md`).
