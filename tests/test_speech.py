from garden.concordia_twins import _clean_speech
from garden.llm import parse_choice_letter


def test_narration_around_a_quote_keeps_only_the_quote():
    raw = 'Jun looks over at Mara and asks, "Is this your first time here?'
    assert _clean_speech("Jun", raw) == "Is this your first time here?"


def test_curly_quotes():
    assert _clean_speech("Mara", "Mara says, “I missed you.”") == "I missed you."


def test_plain_line_with_name_prefix():
    assert _clean_speech("Ren", "Ren Come with me.") == "Come with me."
    assert _clean_speech("Ren", "Answer: Ren: Let's go.") == "Let's go."


LETTERS = list("abcdefg")


def test_choice_letter_from_completion_style_replies():
    assert parse_choice_letter("b)", LETTERS) == "b"
    assert parse_choice_letter("**c**", LETTERS) == "c"
    assert parse_choice_letter("(d) Go somewhere", LETTERS) == "d"


def test_choice_letter_from_chatty_replies_ignores_letters_inside_words():
    assert parse_choice_letter("The correct answer is:\n\n**(a) apple**", LETTERS) == "a"
    assert parse_choice_letter("The best option here", LETTERS) is None


def test_repeated_name_prefix():
    assert _clean_speech("Theo", "Theo Theo: Hey, Ren.") == "Hey, Ren."
