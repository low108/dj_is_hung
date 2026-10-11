"""D4 endpoints: build the signed-in user's twin from their answers, review it, rewrite sections."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from garden import onboarding as qa
from garden import twin_builder as tb

from .auth import current_user

router = APIRouter(prefix="/me/twin", tags=["twin"])
log = logging.getLogger(__name__)


class SectionEdit(BaseModel):
    text: str = Field(max_length=qa.MAX_CHARS)


def own_twin(request: Request, uid: str) -> dict:
    """The user's twin, or 404."""
    doc = request.app.state.store.get_user(uid)
    if not doc or not doc.get("twin"):
        raise HTTPException(404, "no twin yet: finish the questions, then build your twin")
    return doc["twin"]


@router.post("", status_code=201)
def build_twin(request: Request, uid: str = Depends(current_user)) -> dict:
    """One extraction call over the user's answers. Rebuilding keeps the user's rewritten sections."""
    doc = request.app.state.store.get_user(uid) or qa.new_doc()
    if not qa.has_current_consent(doc):
        raise HTTPException(403, "consent first: your answers are only used once you agree")
    if qa.next_question(doc["answers"]) is not None:
        raise HTTPException(409, "finish the questions first")
    configured = request.app.state.extraction_model()
    if configured is None:
        raise HTTPException(503, "no model is configured to build twins (set GEMINI_API_KEY)")
    model_name, model = configured
    try:
        extraction = tb.extract(doc["answers"], model)
    except tb.ExtractionFailed as e:
        raise HTTPException(502, f"couldn't build your twin, please try again: {e}") from e
    except Exception as e:  # quota, network, auth: say what happened without the provider's full reply
        log.warning("twin extraction with %s failed: %s", model_name, e)
        raise HTTPException(503, f"the twin builder ({model_name}) is unavailable right now") from e
    built = tb.new_twin(uid, extraction, model_name, datetime.now(timezone.utc).isoformat())

    def save(current: dict | None) -> dict:
        current = current or qa.new_doc()
        kept = (current.get("twin") or {}).get("overrides", {})
        return current | {"twin": built | {"overrides": kept}}

    return tb.summary(request.app.state.store.update_user(uid, save)["twin"])


@router.get("")
def get_twin(request: Request, uid: str = Depends(current_user)) -> dict:
    return tb.summary(own_twin(request, uid))


@router.put("/sections/{section}")
def edit_section(section: str, body: SectionEdit, request: Request, uid: str = Depends(current_user)) -> dict:
    """Rewrite one section in your own words; it replaces that section's extracted memories. Empty text
    goes back to the extraction."""
    if section not in tb.SECTIONS:
        raise HTTPException(404, f"no section {section!r}")
    own_twin(request, uid)

    def change(current: dict | None) -> dict:
        return current | {"twin": tb.edit(current["twin"], section, body.text)}

    return tb.summary(request.app.state.store.update_user(uid, change)["twin"])
