# Restore test report

RESULT: PASS

- **Run at:** 2026-09-28 04:12 UTC
- **Procedure:** `ops/backup/restore_test.sh`. It backs up with the scheduled job's own script
  (`ops/backup/backup.sh`), restores into a brand-new PostgreSQL 16 instance, verifies the result,
  then runs the API suites against the restored copy.
- **Source:** `localhost:5447/sentinel`
- **Target:** fresh postgres:16 container on :5460. It had 0 tables before the restore.

## 1. Backup

| | |
| --- | --- |
| Dump | `sentinel_20260928T040249Z.dump` (custom format, compressed) |
| Size | 139M |
| SHA-256 | `ae28077fd9c5f3ce573d8dfb59f90191034de4840753f727d0fd2e5818e8c111` |
| Backup time | 98 s |
| Restore time | 358 s |

## 2. Verification: source vs restored

Verifier: `backend_v2/scripts/verify_restore.py`.

| Check | Result |
| --- | --- |
| alembic_revision_equal | PASS |
| same_tables | PASS |
| row_counts_equal | PASS |
| published_run_intact | PASS |
| risk_checksum_equal | PASS |
| serving_build_intact | PASS |
| case_chain_valid | PASS |
| risk_checksum_expected | PASS |

- **Alembic revision:** `99c1d3031fb9`
- **Published run:** [1, 'v4-candidate']
- **risk_result checksum (published run):** `97f08303369f9ed6c50e46d68a4609f5`
- **Tables:** 52, with 3,397,783 rows in total. Row-count mismatches:
  none
- **Case-event hash chain:** 0 events; valid = True

The largest restored tables:

| Table | Rows |
| --- | --- |
| compliance_result | 721,086 |
| raw_row | 655,306 |
| signal_result | 585,036 |
| atypicality_result | 195,012 |
| risk_result | 195,012 |
| work | 129,019 |
| work_state | 129,019 |
| served_work | 122,965 |
| work_geo | 122,965 |
| payment | 107,826 |
| map_work | 97,506 |
| work_context | 97,506 |

## 3. API suites against the restored database

`tests/test_contract.py` and `tests/test_phase12_cutover.py`, with `DATABASE_URL` pointing at the
restored instance:

    117 passed, 1 warning in 43.12s

Exit codes: verifier 0, pytest 0.
