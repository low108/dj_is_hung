"""Q&A onboarding (D3): about 15 questions, one per screen, grouped by theme. A short answer gets exactly
one follow-up question (from Gemini Flash, or a theme template). Answers are only accepted after the
user consents to a twin being built and simulated from them.

The answers feed twin extraction (D4); the themes cover what the Garden's twins need: who they are,
how they love and fight, what they won't accept, and how readily they break rules.
"""
from __future__ import annotations

from dataclasses import dataclass

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

CONSENT_VERSION = "2026-10-1"
CONSENT_TEXT = (
    "I agree that my answers will be used to build an AI twin of me, that the twin will be simulated "
    "on dates with other people's twins, and that my answers are sent to Google's Gemini models to do this. "
    "My twin is shown to others only under an anonymous alias."
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
    if model is not None:
        try:
            text = model.sample_text(FOLLOWUP_PROMPT.format(question=question.text, answer=answer))
        except Exception:  # quota, network: onboarding carries on with the template
            text = ""
        line = next((ln.strip().strip('"') for ln in text.splitlines() if ln.strip()), "")
        if line.endswith("?") and len(line) <= 200:
            return line
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
