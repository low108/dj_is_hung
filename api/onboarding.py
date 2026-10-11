"""D3 endpoints: consent, then one question at a time, resumable. All routes need a signed-in user."""
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


def _load(request: Request, uid: str) -> dict:
    return request.app.state.store.get_user(uid) or {"consent": None, "answers": {}}


def _progress(doc: dict) -> dict:
    """Everything the onboarding screen needs to resume where the user left off."""
    nxt = qa.next_question(doc["answers"])
    current = None
    if nxt:
        q, is_followup = nxt
        current = {"id": q.id, "theme": qa.THEMES[q.theme], "text": q.text,
                   "followup": doc["answers"][q.id]["followup"] if is_followup else None,
                   "number": qa.QUESTIONS.index(q) + 1}
    return {"consent": doc["consent"], "consent_text": qa.CONSENT_TEXT, "consent_version": qa.CONSENT_VERSION,
            "total": len(qa.QUESTIONS), "answered": sum(1 for q in qa.QUESTIONS if q.id in doc["answers"]),
            "complete": nxt is None, "current": current}


@router.get("/onboarding")
def get_onboarding(request: Request, uid: str = Depends(current_user)) -> dict:
    return _progress(_load(request, uid))


@router.post("/consent")
def give_consent(body: Consent, request: Request, uid: str = Depends(current_user)) -> dict:
    if not body.agree:
        raise HTTPException(400, "a twin can only be built with your consent")
    if body.version != qa.CONSENT_VERSION:
        raise HTTPException(409, "the consent text has changed; please read it again")
    doc = _load(request, uid)
    doc["consent"] = {"version": qa.CONSENT_VERSION, "text": qa.CONSENT_TEXT, "at": _now()}
    request.app.state.store.save_user(uid, doc)
    return _progress(doc)


@router.post("/answers")
def answer(body: Answer, request: Request, uid: str = Depends(current_user)) -> dict:
    """Answer the current question (or its follow-up). A short first answer gets exactly one follow-up;
    the follow-up's answer is taken as it is."""
    doc = _load(request, uid)
    if not doc["consent"]:
        raise HTTPException(403, "consent first: answers are only used once you agree")
    nxt = qa.next_question(doc["answers"])
    if nxt is None or nxt[0].id != body.question_id:
        raise HTTPException(409, "that isn't the current question")
    q, is_followup = nxt
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "an answer can't be empty")
    if is_followup:
        doc["answers"][q.id] |= {"followup_answer": text, "followup_answered_at": _now()}
    else:
        followup = qa.followup_for(q, text, request.app.state.followup_model()) if qa.is_short(text) else None
        doc["answers"][q.id] = {"answer": text, "answered_at": _now(), "followup": followup,
                                "followup_answer": None}
    request.app.state.store.save_user(uid, doc)
    return _progress(doc)
