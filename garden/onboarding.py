"""Q&A onboarding (D3): about 15 questions, one per screen, grouped by theme. A short answer gets exactly
one follow-up question (from Gemini Flash, or a theme template). Answers are only accepted after the
user consents to a twin being built and simulated from them.

The answers feed twin extraction (D4); the themes cover what the Garden's twins need: who they are,
how they love and fight, what they won't accept, and how readily they break rules.

A user's onboarding is one document; this module owns its shape (new_doc, give_consent,
record_answer, progress), so the API only loads and saves it.

Prototype departures from the spec, to revisit with A2: the raw answers live in the user's Firestore
document (server access only) rather than a locked Cloud Storage bucket, and the API asks follow-ups
itself rather than a separate twin-builder service.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

MIN_WORDS = 8          # fewer words than this earns one follow-up
MAX_CHARS = 2000


@dataclass(frozen=True)
class Question:
    id: str
    theme: str
    text: str


THEMES = {
    "life": "Life and values",
    "past": "Past relationships",
    "conflict": "Conflict style",
    "dealbreakers": "Dealbreakers",
    "rules": "Attitude to rules",
}

QUESTIONS = (
    Question("life_week", "life", "Describe a week of your life you'd happily repeat."),
    Question("life_values", "life", "What matters most to you in how you live, and why?"),
    Question("life_future", "life", "Where do you hope your life is in five years?"),
    Question("past_lesson", "past", "What did your last serious relationship teach you?"),
    Question("past_end", "past", "Without names, how did your last relationship end, and how did you feel?"),
    Question("past_best", "past", "What made you feel most loved by a partner?"),
    Question("conflict_style", "conflict", "When you disagree with a partner, what do you usually do first?"),
    Question("conflict_repair", "conflict", "How do you make up after a fight?"),
    Question("conflict_space", "conflict", "When you're upset, do you want closeness or space? Tell me about a time."),
    Question("deal_never", "dealbreakers", "What would make you end things, no matter what?"),
    Question("deal_compromise", "dealbreakers", "What are you willing to compromise on for the right person?"),
    Question("deal_must", "dealbreakers", "What does a partner absolutely need to have or share with you?"),
    Question("rules_bend", "rules", "Tell me about a time you broke or bent a rule. Would you do it again?"),
    Question("rules_authority", "rules", "How do you feel when someone tells you there's only one right way?"),
    Question("rules_risk", "rules", "What would you risk for someone you love?"),
)
BY_ID = {q.id: q for q in QUESTIONS}

TEMPLATE_FOLLOWUPS = {
    "life": "Could you tell me a little more about why that matters to you?",
    "past": "What do you think you'd do differently now?",
    "conflict": "Can you describe a specific moment when that happened?",
    "dealbreakers": "Why is that one so important to you?",
    "rules": "What was going through your mind at the time?",
}

CONSENT_VERSION = "2026-10-2"
CONSENT_TEXT = (
    "I agree that my answers will be used to build an AI twin of me, that the twin will be simulated "
    "on dates with other people's twins, and that my answers are sent to Google's Gemini models to do this."
)

FOLLOWUP_PROMPT = """You are a warm interviewer for a dating app, getting to know someone.
Question: {question}
Their answer: {answer}

The answer is short. Ask ONE short follow-up question (under 25 words) that invites them to say more,
specifically about what they just said. Output only the question."""


def is_short(answer: str) -> bool:
    return len(answer.split()) < MIN_WORDS


def followup_for(question: Question, answer: str, model=None) -> str:
    """One follow-up question; the model's if it gives a usable one, else the theme's template."""
    if model is None:
        log.warning("follow-up for %s uses the template: no follow-up model (set GEMINI_API_KEY)", question.id)
        return TEMPLATE_FOLLOWUPS[question.theme]
    try:
        text = model.sample_text(FOLLOWUP_PROMPT.format(question=question.text, answer=answer))
    except Exception as e:  # quota, network: onboarding carries on, but say so
        log.warning("follow-up for %s uses the template: %s", question.id, e)
        return TEMPLATE_FOLLOWUPS[question.theme]
    line = next((ln.strip().strip('"') for ln in text.splitlines() if ln.strip()), "")
    if line.endswith("?") and len(line) <= 200:
        return line
    log.warning("follow-up for %s uses the template: unusable reply %r", question.id, text[:80])
    return TEMPLATE_FOLLOWUPS[question.theme]


def next_question(answers: dict[str, dict]) -> tuple[Question, bool] | None:
    """Where the user left off: the first question unanswered, or whose follow-up is unanswered
    (True). None when the Q&A is complete."""
    for q in QUESTIONS:
        a = answers.get(q.id)
        if a is None:
            return q, False
        if a.get("followup") and a.get("followup_answer") is None:
            return q, True
    return None


class OnboardingError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def new_doc() -> dict:
    return {"consent": None, "answers": {}}


def has_current_consent(doc: dict) -> bool:
    """Consent to the text shown now; agreeing to an older text doesn't count."""
    return bool(doc["consent"]) and doc["consent"].get("version") == CONSENT_VERSION


def give_consent(doc: dict, version: str, at: str) -> dict:
    if version != CONSENT_VERSION:
        raise OnboardingError(409, "the consent text has changed; please read it again")
    return doc | {"consent": {"version": CONSENT_VERSION, "text": CONSENT_TEXT, "at": at}}


def answerable(doc: dict, question_id: str) -> tuple[Question, bool]:
    """The current question (and whether it's the follow-up) if `question_id` is it; else raise."""
    if not has_current_consent(doc):
        raise OnboardingError(403, "consent first: answers are only used once you agree")
    nxt = next_question(doc["answers"])
    if nxt is None or nxt[0].id != question_id:
        raise OnboardingError(409, "that isn't the current question")
    return nxt


def record_answer(doc: dict, question_id: str, text: str, followup: str | None, at: str) -> dict:
    """Store an answer to the current question, or to its follow-up. `followup` (asked for a short first
    answer) is ignored when this is the follow-up's answer, which is taken as it is."""
    text = text.strip()
    if not text:
        raise OnboardingError(422, "an answer can't be empty")
    q, is_followup = answerable(doc, question_id)
    answers = dict(doc["answers"])
    if is_followup:
        answers[q.id] = answers[q.id] | {"followup_answer": text, "followup_answered_at": at}
    else:
        answers[q.id] = {"answer": text, "answered_at": at, "followup": followup, "followup_answer": None}
    return doc | {"answers": answers}


def progress(doc: dict) -> dict:
    """Everything the onboarding screen needs to resume where the user left off."""
    nxt = next_question(doc["answers"])
    current = None
    if nxt:
        q, is_followup = nxt
        current = {"id": q.id, "theme": THEMES[q.theme], "text": q.text,
                   "followup": doc["answers"][q.id]["followup"] if is_followup else None,
                   "number": QUESTIONS.index(q) + 1}
    done = sum(1 for q in QUESTIONS if q.id in doc["answers"] and not (
        doc["answers"][q.id].get("followup") and doc["answers"][q.id].get("followup_answer") is None))
    return {"consent": doc["consent"] if has_current_consent(doc) else None, "consent_text": CONSENT_TEXT,
            "consent_version": CONSENT_VERSION, "total": len(QUESTIONS), "answered": done,
            "complete": nxt is None, "current": current, "max_chars": MAX_CHARS,
            "about": about_status(doc.get("about"))}


def about_status(about: dict | None) -> dict:
    from .about_me import status

    return status(about)
