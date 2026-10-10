from garden.concordia_twins import _clean_speech


def test_narration_around_a_quote_keeps_only_the_quote():
    raw = 'Jun looks over at Mara and asks, "Is this your first time here?'
    assert _clean_speech("Jun", raw) == "Is this your first time here?"


def test_curly_quotes():
    assert _clean_speech("Mara", "Mara says, “I missed you.”") == "I missed you."


def test_plain_line_with_name_prefix():
    assert _clean_speech("Ren", "Ren Come with me.") == "Come with me."
    assert _clean_speech("Ren", "Answer: Ren: Let's go.") == "Let's go."
