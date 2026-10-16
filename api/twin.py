"""D4 endpoints: build the signed-in user's twin from their answers, review it, change it, confirm it."""
from __future__ import annotations

import logging
from collections.abc import Callable
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


def _doc(request: Request, uid: str) -> dict:
    return request.app.state.store.get_user(uid) or qa.new_doc()


def own_twin(request: Request, uid: str) -> dict:
    """The user's twin, or 404."""
    twin = _doc(request, uid).get("twin")
    if not twin:
        raise HTTPException(404, "no twin yet: finish the questions, then build your twin")
    return twin


def _change_twin(request: Request, uid: str, change: Callable[[dict], dict]) -> dict:
    """Apply `change` to the twin inside the user's transaction (404 if there's no twin by then)."""
    def update(current: dict | None) -> dict:
        if not current or not current.get("twin"):
            raise HTTPException(404, "no twin yet: finish the questions, then build your twin")
        return current | {"twin": change(current["twin"])}

    doc = request.app.state.store.update_user(uid, update)
    return tb.summary(doc["twin"], doc["answers"])


@router.post("", status_code=201)
def build_twin(request: Request, uid: str = Depends(current_user)) -> dict:
    """One extraction call over the user's answers. A rebuild keeps the user's edits and needs review."""
    doc = _doc(request, uid)
    if not qa.has_current_consent(doc):
        raise HTTPException(403, "consent first: your answers are only used once you agree")
    if qa.next_question(doc["answers"]) is not None:
        raise HTTPException(409, "finish the questions first")
    configured: tb.ExtractionModel | None = request.app.state.extraction_model()
    if configured is None:
        raise HTTPException(503, "no model is configured to build twins (set GEMINI_API_KEY)")
    try:
        extraction = tb.extract(doc["answers"], configured.model)
    except tb.ExtractionFailed as e:
        raise HTTPException(502, f"couldn't build your twin, please try again: {e}") from e
    except Exception as e:  # quota, network, auth: say what happened without the provider's full reply
        log.warning("twin extraction with %s failed: %s", configured.name, e)
        raise HTTPException(503, f"the twin builder ({configured.name}) is unavailable right now") from e
    at = datetime.now(timezone.utc).isoformat()

    def save(current: dict | None) -> dict:
        current = current or qa.new_doc()
        return current | {"twin": tb.new_twin(uid, extraction, configured.name, at, current.get("twin"),
                                              current.get("about"))}

    saved = request.app.state.store.update_user(uid, save)
    return tb.summary(saved["twin"], saved["answers"])


@router.get("")
def get_twin(request: Request, uid: str = Depends(current_user)) -> dict:
    doc = _doc(request, uid)
    return tb.summary(own_twin(request, uid), doc["answers"])


@router.put("/sections/{section}")
def edit_section(section: str, body: SectionEdit, request: Request, uid: str = Depends(current_user)) -> dict:
    """Rewrite one section in your own words; it replaces that section's extracted memories. Empty text
    goes back to the extraction."""
    if section not in tb.SECTIONS:
        raise HTTPException(404, f"no section {section!r}")
    return _change_twin(request, uid, lambda twin: tb.edit(twin, section, body.text))


@router.put("/traits")
def edit_traits(body: tb.TraitEdit, request: Request, uid: str = Depends(current_user)) -> dict:
    """Change attachment style, values, dealbreakers or rebelliousness; your values win over the extraction."""
    return _change_twin(request, uid, lambda twin: tb.edit_traits(twin, body))


@router.post("/review")
def confirm(request: Request, uid: str = Depends(current_user)) -> dict:
    """'This is me': only a reviewed twin can enter the Garden."""
    return _change_twin(request, uid, tb.mark_reviewed)


def reviewed_twin(request: Request, uid: str) -> dict:
    twin = own_twin(request, uid)
    if not twin.get("reviewed"):
        raise HTTPException(409, "review your twin first: confirm it sounds like you")
    return twin
