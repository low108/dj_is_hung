"""D3 endpoints: consent, then one question at a time, resumable. All routes need a signed-in user.

Writes are read-modify-write on the user's document inside `Store.update_user`, so a double-click
can't overwrite an answer: the second write finds the question already answered and gets a 409.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from garden import onboarding as qa

from .auth import current_user

router = APIRouter(prefix="/me", tags=["onboarding"])


class Consent(BaseModel):
    agree: bool
    version: str


class Answer(BaseModel):
    question_id: str
    text: str = Field(min_length=1, max_length=qa.MAX_CHARS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update(request: Request, uid: str, change) -> dict:
    try:
        doc = request.app.state.store.update_user(uid, lambda d: change(d or qa.new_doc()))
    except qa.OnboardingError as e:
        raise HTTPException(e.status, str(e)) from e
    return qa.progress(doc)


@router.get("/onboarding")
def get_onboarding(request: Request, uid: str = Depends(current_user)) -> dict:
    return qa.progress(request.app.state.store.get_user(uid) or qa.new_doc())


@router.post("/consent")
def give_consent(body: Consent, request: Request, uid: str = Depends(current_user)) -> dict:
    if not body.agree:
        raise HTTPException(400, "a twin can only be built with your consent")
    return _update(request, uid, lambda doc: qa.give_consent(doc, body.version, _now()))


@router.post("/answers")
def answer(body: Answer, request: Request, uid: str = Depends(current_user)) -> dict:
    """Answer the current question (or its follow-up). A short first answer gets exactly one follow-up;
    the follow-up's answer is taken as it is."""
    doc = request.app.state.store.get_user(uid) or qa.new_doc()
    try:
        q, is_followup = qa.answerable(doc, body.question_id)
    except qa.OnboardingError as e:
        raise HTTPException(e.status, str(e)) from e
    followup = None
    if not is_followup and body.text.strip() and qa.is_short(body.text):
        # Asked outside the write (a model call doesn't belong in a transaction); the write re-checks.
        followup = qa.followup_for(q, body.text.strip(), request.app.state.followup_model())
    return _update(request, uid, lambda d: qa.record_answer(d, body.question_id, body.text, followup, _now()))
