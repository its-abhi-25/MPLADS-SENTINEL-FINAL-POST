"""
In-app help & navigation chatbot.

Two layers, so the assistant is useful immediately and gets smarter once
configured:

  1. A local, rule-based navigation guide (`_local_answer`) that always
     works, with zero setup and zero external calls -- it matches the
     question against a small knowledge base of this platform's pages,
     workflows and terminology.

  2. An optional AI layer (Google Gemini, via the official `google-genai`
     Python SDK) used for free-form questions when `GEMINI_API_KEY` is
     configured (see `app.core.chat_config`). The key lives only in the
     backend process environment; it is never read from, or exposed to,
     the frontend, and the SDK never puts it in a URL that could end up
     in a log line. If the call fails for any reason (no key, bad key,
     package not installed, retired model, network error, quota), we
     fall back to the local guide so the chatbot never just breaks -- but
     we log *why* it failed server-side (with the key redacted) so a
     misconfiguration is diagnosable instead of silently looking like
     "no key configured".
"""
import logging
from functools import lru_cache
from typing import List, Optional, Tuple

from fastapi import APIRouter
from pydantic import BaseModel

from ..core.chat_config import (
    get_gemini_api_key,
    get_gemini_model,
    get_fallback_models,
    is_ai_configured,
    mask_key,
)

router = APIRouter()
log = logging.getLogger("sentinel.chat")

SYSTEM_PROMPT = """You are the in-app help assistant for MPLADS Sentinel, an investigation and \
analytics platform for the Members of Parliament Local Area Development Scheme (MPLADS).

Answer only questions about how to use this platform, what its pages/features mean, and how its \
analytical methodology works. Be concise (2-5 sentences unless a list is clearer), friendly, and precise. \
If asked something unrelated to the platform, briefly say you're focused on helping with MPLADS Sentinel \
and redirect to what you can help with. Never claim the platform makes accusations of fraud or corruption \
— it only prioritises works for human review, based on statistical/analytical signals.

PLATFORM MAP
- Overview (Dashboard, "/"): headline KPIs, a risk-distribution donut chart, works-by-category bar chart, \
implementation stage funnel (Recommended -> Sanctioned -> Completed), and a table of top cost anomalies.
- Investigation Map ("/map"): a Leaflet map plotting flagged works geographically (state/constituency-level \
approximate locations), colour-coded by risk priority, with filters and marker clustering.
- Priority Queue ("/queue"): a filterable, sortable, paginated table of every work record ranked by \
priority/risk score. Filters include priority tier, implementation stage, state, MP, and free-text search. \
Sort options include risk score, cost anomaly score, evidence count, and amount.
- Analytics ("/analytics"): platform-wide statistics — risk distribution donut, amount-distribution histogram, \
analytical signal distribution, and flag-rate rankings by category and by state (switchable tabs).
- MP Performance ("/mp-performance"): search any MP or constituency to see their works, completion rate, \
recorded fund amounts by stage, category breakdown, a trend chart, and their flagged works. Supports \
comparing 2+ MPs or 2+ constituencies side by side.
- Data Health ("/data-health"): dataset quality report — completeness, duplicate/near-duplicate counts, \
per-column missingness, which analytical signals are active vs unavailable, and category-inference stats.
- Methodology ("/methodology"): explains the guiding principle ("AI prioritises, evidence explains, humans \
decide"), the 8-step processing pipeline, the six analytical signals and their weights, the evidence model, \
and explicit limitations of the system.
- Case / Record Detail ("/record/:id", opened by clicking any work): full case file for one work — a \
radial priority-score ring, a "signal fingerprint" radar chart of which detectors fired, the evidence chain \
(source record -> normalized data -> category inference -> peer group comparison -> signals -> priority), \
raw source/normalized fields, and related/similar records.

KEY CONCEPTS
- Priority tiers: HIGH_PRIORITY_REVIEW (strongest combined evidence), REVIEW_RECOMMENDED (moderate evidence), \
LOW (little to no anomalous signal). These are analytical prioritisation tiers, not findings of wrongdoing.
- Six analytical signals (with fusion weights): Cost Anomaly (30%, peer-group amount outliers via robust \
statistics), Concentration Analysis (20%, unusually many works for one MP/constituency in a category), \
Duplicate Detection (15%), Data Quality (15%), Temporal Clustering (10%, batch-sanctioning patterns), \
Lifecycle Anomaly (10%, e.g. sanctioned works with no completion status).
- The priority score is a weighted fusion of whichever signals fired for a given work, together with a \
confidence level reflecting how much data was available.

Keep answers grounded in the above. If you don't know a specific number (e.g. "how many high-priority \
works are there right now"), tell the user to check the Overview or Analytics page rather than guessing.
"""

_KB = [
    {
        "keywords": ["risk score", "priority score", "what does the score mean", "how is the score calculated"],
        "answer": "The priority score is a weighted combination of seven analytical signals (cost anomaly, "
                  "description similarity, MP concentration, constituency pattern, temporal anomaly, "
                  "stage consistency, cross-signal pattern). It maps to "
                  "one of four bands: LOW, MODERATE, HIGH, or CRITICAL. It's a prioritisation "
                  "signal for human review — not a finding of wrongdoing. See the Methodology page for the full "
                  "breakdown and signal weights.",
    },
    {
        "keywords": ["find high", "high priority", "high-risk works", "most risky"],
        "answer": "Open Priority Queue from the sidebar and set the Priority filter to \"High Priority Review\" — "
                  "or click the red slice/legend row on the Overview donut chart, which jumps straight there.",
    },
    {
        "keywords": ["compare", "comparison", "two mps", "vs"],
        "answer": "Go to MP Performance, click \"Compare\", choose MPs or Constituencies, then search and add two "
                  "or more to the comparison list before running it. You'll get a side-by-side table of works, "
                  "completion rate, recorded amounts and risk counts.",
    },
    {
        "keywords": ["map", "geospatial", "where are the works", "location"],
        "answer": "The Investigation Map plots flagged works by state/constituency (approximate locations — the "
                  "dataset doesn't include exact coordinates for individual works). Markers are colour-coded by "
                  "risk priority and cluster together when zoomed out; use the filters panel to narrow by state, "
                  "priority or stage.",
    },
    {
        "keywords": ["evidence chain", "how was this flagged", "why flagged", "evidence"],
        "answer": "Open any work's Case Detail page (click a row in the Priority Queue or a marker on the map) "
                  "and look at the Evidence Chain section — it traces the full path from the source record "
                  "through normalization, category inference, peer-group comparison, individual signals, and "
                  "finally the fused priority score.",
    },
    {
        "keywords": ["data quality", "data health", "missing data", "completeness"],
        "answer": "The Data Health page reports dataset completeness, duplicate/near-duplicate candidate counts, "
                  "per-column missing-value rates, and which of the seven analytical signals are currently active "
                  "vs unavailable (e.g. if a required field is missing from the source data). Data quality affects "
                  "confidence, not risk scores.",
    },
    {
        "keywords": ["signal", "how many signals", "what signals"],
        "answer": "There are six analytical signals: Cost Anomaly (30% weight), Concentration Analysis (20%), "
                  "Duplicate Detection (15%), Data Quality (15%), Temporal Clustering (10%), and Lifecycle "
                  "Anomaly (10%). Full definitions are on the Methodology page.",
    },
    {
        "keywords": ["export", "download", "csv"],
        "answer": "MPLADS Sentinel doesn't currently have a built-in export/download button — the Priority Queue "
                  "and Analytics pages are the best views for reviewing records in bulk on-screen.",
    },
    {
        "keywords": ["fraud", "corruption", "guilty", "accuse"],
        "answer": "MPLADS Sentinel never determines fraud, corruption or guilt. It only identifies statistically "
                  "unusual patterns and prioritises works for human investigators to verify — see the "
                  "Methodology page's \"Important Limitations\" section for details.",
    },
    {
        "keywords": ["navigate", "pages", "sections", "what can this do", "features", "help", "what is this"],
        "answer": "MPLADS Sentinel has seven main sections in the sidebar: Overview (KPIs & headline charts), "
                  "Investigation Map (geospatial view), Priority Queue (filterable ranked table), Analytics "
                  "(platform-wide statistics), MP Performance (per-MP/constituency profiles & comparison), Data "
                  "Health (dataset quality report), and Methodology (how the scoring works). Click any work row "
                  "or map marker to open its full Case Detail file.",
    },
]


def _local_answer(message: str, ai_failed: bool = False) -> str:
    text = message.lower()
    best_score, best_answer = 0, None
    for entry in _KB:
        score = sum(1 for kw in entry["keywords"] if kw in text)
        if score > best_score:
            best_score, best_answer = score, entry["answer"]
    if best_answer:
        return best_answer
    if ai_failed:
        return (
            "I can help you navigate MPLADS Sentinel and explain how it works -- try asking about a specific "
            "page (Overview, Investigation Map, Priority Queue, Analytics, MP Performance, Data Health, "
            "Methodology), what the risk score or an analytical signal means, or how to compare two MPs. "
            "The AI-powered assistant is configured but couldn't be reached just now, so you're getting the "
            "built-in guide instead -- the backend console has the exact reason logged."
        )
    return (
        "I can help you navigate MPLADS Sentinel and explain how it works — try asking about a specific page "
        "(Overview, Investigation Map, Priority Queue, Analytics, MP Performance, Data Health, Methodology), "
        "what the risk score or an analytical signal means, or how to compare two MPs. For smarter, free-form "
        "answers, ask the platform owner to configure a Gemini API key (see .env.example)."
    )


@lru_cache(maxsize=4)
def _get_client(api_key: str):
    """One SDK client per distinct API key -- in practice there's only
    ever one, since the key is fixed for the life of the process. Import
    is deferred into this function (and `_call_gemini` below) so that a
    missing `google-genai` package can't prevent the whole backend from
    starting; the chat endpoint just falls back to the local guide with
    a clear log line telling you to install it.
    """
    from google import genai
    return genai.Client(api_key=api_key)


def _build_contents(message: str, history: List[dict]):
    from google.genai import types

    contents = []
    for turn in history[-8:]:
        role = "model" if turn.get("role") == "assistant" else "user"
        text = str(turn.get("content", "")).strip()
        if text:
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
    return contents


def _call_gemini(message: str, history: List[dict]) -> Tuple[Optional[str], bool]:
    """Returns (reply_text_or_None, was_attempted).

    was_attempted is True whenever we actually tried to reach Gemini (key
    was present), regardless of whether it succeeded -- callers use this to
    give an accurate fallback message instead of implying "no key configured"
    when a call genuinely failed.

    Uses the official `google-genai` SDK (`pip install google-genai`).
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return None, False

    try:
        from google.genai import types, errors
    except ImportError:
        log.warning(
            "Gemini call skipped: the 'google-genai' package isn't installed. "
            "Run `pip install -r backend/requirements.txt` (inside your backend "
            "virtualenv) and restart the backend."
        )
        return None, True

    try:
        client = _get_client(api_key)
    except Exception as e:
        log.warning(
            "Gemini call failed: could not create SDK client (key: %s) -- %s: %s",
            mask_key(api_key), type(e).__name__, e,
        )
        return None, True

    contents = _build_contents(message, history)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.4,
        max_output_tokens=500,
    )

    # Try the configured/default model first; only fall back to alternates
    # when Gemini says the model itself doesn't exist (HTTP 404) -- e.g. a
    # pinned model id that Google has since retired. Any other failure
    # (auth, quota, network, safety block) is reported immediately rather
    # than masked by silently switching models.
    models_to_try = [get_gemini_model(), *get_fallback_models()]
    last_error_summary = None

    for i, model in enumerate(models_to_try):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
        except errors.ClientError as e:
            code = getattr(e, "code", None)
            last_error_summary = f"ClientError {code}: {getattr(e, 'message', e)}"
            if code == 404 and i < len(models_to_try) - 1:
                log.info(
                    "Gemini model '%s' not found/unavailable, trying '%s' next.",
                    model, models_to_try[i + 1],
                )
                continue
            log.warning("Gemini call failed (key: %s): %s", mask_key(api_key), last_error_summary)
            return None, True
        except errors.ServerError as e:
            log.warning(
                "Gemini call failed (key: %s): ServerError %s: %s",
                mask_key(api_key), getattr(e, "code", "?"), getattr(e, "message", e),
            )
            return None, True
        except errors.APIError as e:
            log.warning(
                "Gemini call failed (key: %s): APIError %s: %s",
                mask_key(api_key), getattr(e, "code", "?"), getattr(e, "message", e),
            )
            return None, True
        except Exception as e:
            log.warning(
                "Gemini call failed (key: %s): %s: %s",
                mask_key(api_key), type(e).__name__, e,
            )
            return None, True

        try:
            text = (response.text or "").strip()
        except Exception:
            text = ""

        if not text:
            feedback = getattr(response, "prompt_feedback", None)
            block_reason = getattr(feedback, "block_reason", None) if feedback else None
            log.warning(
                "Gemini call to '%s' succeeded but returned no text (blockReason=%s).",
                model, block_reason,
            )
            return None, True

        if i > 0:
            log.info("Gemini: model '%s' was unavailable; '%s' answered instead.", models_to_try[0], model)
        return text, True

    log.warning(
        "Gemini call failed (key: %s): all candidate models unavailable. Last error: %s",
        mask_key(api_key), last_error_summary,
    )
    return None, True


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


@router.get("/api/chat/status")
async def chat_status():
    """Never returns the key itself — only whether one is configured."""
    return {"configured": is_ai_configured(), "provider": "gemini"}


@router.post("/api/chat")
async def chat(body: ChatRequest):
    message = (body.message or "").strip()
    if not message:
        return {"reply": "Ask me anything about navigating MPLADS Sentinel or how its scoring works.", "source": "guide"}

    history = [h.dict() for h in body.history]
    reply, ai_attempted = _call_gemini(message, history)
    if reply:
        return {"reply": reply, "source": "gemini"}

    return {"reply": _local_answer(message, ai_failed=ai_attempted), "source": "guide"}
