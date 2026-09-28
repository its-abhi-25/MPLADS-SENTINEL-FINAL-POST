"""
Sentinel v2 configuration.

Phase 0 scope was connection settings only. Phase 1 adds `data_dir`, the
path to the repo-root `data/` folder the ingestion pipeline reads raw files
from -- it lives outside backend_v2/ (and outside the Docker build context;
see docker-compose.yml / scripts/run_ingest.py for how it's bind-mounted).
No weights, thresholds, or scoring config yet -- those get ported (and
reconsidered) once business logic phases start. See
backend/app/core/config.py for the current provisional values this will
eventually need to account for.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://sentinel:sentinel@localhost:5432/sentinel"
    log_level: str = "info"
    # Default assumes `backend_v2/` sits beside `data/` at the repo root
    # (true for a local, non-Docker run); overridden to /data by the
    # container-based ingest runner.
    data_dir: str = str(Path(__file__).resolve().parents[3] / "data")
    # Phase 12: precompute the dataset-wide summary/analytics/data-health
    # payloads in a background thread at startup (off by default so tests
    # don't race it; docker-compose turns it on).
    warm_cache: bool = False

    # ---- Phase 13: security (BLUEPRINT.md §11). Every value comes from the
    # environment; no secret has a usable default. ----------------------------------------
    # HS256 signing key for access tokens. Unset: development generates a
    # random per-process key (tokens die with the process); any other
    # APP_ENV refuses to start (app/auth/tokens.py).
    jwt_secret: str = ""
    jwt_issuer: str = "mplads-sentinel"
    jwt_audience: str = "mplads-sentinel-api"
    access_token_minutes: int = 15  # short-lived; there is no refresh token
    # Read access without a token, as the built-in "public" role (national,
    # read-only, no personal-data or case/audit endpoints). ON by default
    # because the protected frontend sends no token (its login page is a
    # client-side demo); set false to require a token on every data endpoint.
    anonymous_read: bool = True
    # CORS: explicit allowlist, comma-separated; never "*". Defaults are the
    # two local dev origins in this repo (compose/vite dev :3000, vite preview
    # :4173). The deployed frontend's origin is added in Phase 14.
    cors_origins: str = "http://localhost:3000,http://localhost:4173"
    # Optional regex for preview-deployment origins (Phase 14), e.g.
    # ^https://mplads-sentinel-[a-z0-9-]+\.vercel\.app$ -- unset here.
    cors_origin_regex: str = ""
    # Rate limits, requests per minute per client (and per user where one
    # is authenticated). In-process: correct for one API process; a
    # multi-process deployment needs a shared store (docs/security.md).
    rate_limit_login_per_minute: int = 10
    rate_limit_chat_per_minute: int = 30
    rate_limit_search_per_minute: int = 300
    # Honour X-Forwarded-For only behind a proxy you control.
    trust_forwarded_for: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
