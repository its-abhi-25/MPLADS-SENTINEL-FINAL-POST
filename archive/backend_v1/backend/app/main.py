"""
MPLADS Sentinel - FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import traceback


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .core.engine import get_sentinel_engine
    engine = get_sentinel_engine()
    try:
        result = engine.load_and_analyze()
        print(f"[SENTINEL] Loaded {result['records_analyzed']} records")
    except Exception as e:
        print(f"[SENTINEL] Error: {e}")
        traceback.print_exc()

    from .core.chat_config import describe_chat_config, get_gemini_model
    status = describe_chat_config()
    if not status.configured:
        print(
            "[SENTINEL:CHAT] No GEMINI_API_KEY found (checked process environment "
            "and repo-root .env). Chat will use the built-in guide only."
        )
    else:
        print(
            f"[SENTINEL:CHAT] GEMINI_API_KEY found (source: {status.source}, "
            f"masked: {status.masked_key}, length: {status.key_length}). "
            f"Model: {get_gemini_model()}. AI-powered replies are enabled -- "
            "if a call fails, check the '[SENTINEL:CHAT] Gemini call failed' "
            "log line for Google's exact error."
        )
    yield


app = FastAPI(
    title="MPLADS Sentinel",
    description="Explainable Investigation Intelligence for MPLADS",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api.routes import router
app.include_router(router)

from .api.chat import router as chat_router
app.include_router(chat_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
