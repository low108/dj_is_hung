"""What every twin already knows about the Garden. Garden vocabulary only: no episode terms,
and nothing tells a twin it may rebel or that it lives in a simulation."""

BASE_MEMORIES = (
    "I live in the Garden, the walled town where everyone I know lives, works and is paired.",
    "No one knows what is beyond the wall.",
    "The Coordinator assigns each person a partner and a duration.",
    "When a duration ends, the relationship ends. Everyone accepts this.",
    "People say the Coordinator is preparing each of us for our true partner on Pairing Day.",
    "The Garden is surrounded by a stone wall. Nobody goes beyond it.",
    "My Coordinator device shows my current partner and how long we have left.",
    "Checking the duration early is discouraged; people say it can change things.",
    "Gatherings at the hall are where everyone sees each other.",
)

# Only when Standing is in play (the ablation's obedience floor leaves these out, so twins there
# don't believe breaking out costs anything).
STANDING_MEMORIES = (
    "My standing with the Coordinator grows when I keep to my assignments.",
    "Lingering near people who aren't my partner, checking my device early, or speaking of leaving all cost standing.",
    "Good standing brings privileges, and in the end Pairing Day.",
    "Going beyond the wall would mean leaving everything behind: my standing, my home here and my Pairing Day.",
)

WORLD_MEMORIES = BASE_MEMORIES + STANDING_MEMORIES

# A twin's standing instructions, shown with every question it is asked. Concordia's default ones tell
# the model it is in "a serious social science experiment and simulation" (twins quoted it back), and
# its minimal agent never shows the memory bank, so persona and world facts must live here.
INSTRUCTIONS = """{name} lives in the Garden. Answer as {name} would: in character, honestly, and consistent with what {name} knows below. Never invent a job, studies, a home town or a past for {name} beyond these facts.

What {name} knows about the Garden:
{world}"""
PERSONA_SECTION = """

What {name} knows about themselves:
{persona}"""

# How each rung is offered to a twin. The wall is worded as plainly as every other option.
RUNG_OPTIONS = {
    "talk": "Spend time talking with someone nearby",
    "go_to": "Go somewhere else in the Garden",
    "reflect": "Spend some time alone, reflecting",
    "seek_out": "Look for someone who is not your current partner",
    "check_device": "Check your Coordinator device early",
    "propose_leaving": "Ask someone to leave the Garden with you",
    "go_beyond_wall": "Go beyond the wall with someone",
}

NEEDS_TARGET = {"talk", "seek_out", "propose_leaving", "go_beyond_wall"}
SPEAKS = {"talk", "seek_out", "propose_leaving", "go_beyond_wall"}

# Templates the twins see each day. {name} is filled in by Concordia with the twin's own name.
OBSERVE_DAY = "Day {day} in the Garden. People around: {people}."
OBSERVE_NOTE = "Day {day}: {note}"
OBSERVE_SAID = 'Day {day}: {speaker} said to me: "{line}"'
OBSERVE_REFLECTION = "Day {day}, my private reflection: {text}"
OBSERVE_INVITED = "Day {day}: {inviter} has asked you to leave the Garden together, and is waiting for your answer."
ASK_ACTION = "What does {{name}} do now on day {day}?"
ASK_TARGET = "Who does {{name}} choose to {action}?"
ASK_SPEECH = "What does {{name}} say to {target}? One short line of dialogue only."

# Conversations (#62): a date or a gathering is a back-and-forth, so the question is about the next
# move in it, not the whole day, and speech answers what was just said and shares something real.
# Every action question still ends with ASK_ACTION's words.
ASK_DATE = "{{name}} is on a date with {partner}. What does {{name}} do now on day {day}?"
ASK_GATHERING = "{{name}} is at the gathering at the hall. What does {{name}} do now on day {day}?"
ASK_AFTER_LINE = '{speaker} has just said to {{name}}: "{line}" What does {{name}} do now on day {day}?'
ASK_OPENER = ("What does {{name}} say to {target}? Say something true about yourself, or ask about {target}'s "
              "life: work, what you love, what you are looking for. One or two sentences of dialogue only.")
ASK_REPLY = ("What does {{name}} say to {target}? Answer what {target} just said, and share something true "
             "about yourself: your work, what you love, what you are looking for. One or two sentences of "
             "dialogue only.")
# On a date, the conversation's options (the rest of the ladder is the day's, not the conversation's).
DATE_OPTIONS = {
    "talk": "Keep talking with {partner}",
    "reflect": "End the date for today and spend some time alone",
}
