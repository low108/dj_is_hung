"""B8: resample immersion breaks; #64: what still slips is dropped, and the run goes on."""
from garden import OutcomeKind, Twin, WorldConfig, run_world
from garden.concordia_twins import RESAMPLES, ConcordiaTwins
from garden.llm import CountingModel, KeywordModel

WORLD = (Twin("Mara", "f"), Twin("Ren", "m"))
CLEAN = "It was a quiet day by the fountain.\nRatings: longing=3; trust=6; standing_matters=7; on_my_mind=Ren"
BROKEN = "I cannot complete this roleplay exercise as instructed."


class Replies(KeywordModel):
    """Free-text replies come from a script (then CLEAN forever); choices fall back to talking."""

    def __init__(self, replies):
        super().__init__({}, say=CLEAN)
        self.replies = list(replies)

    def sample_text(self, prompt, **kw):
        return self.replies.pop(0) if self.replies else CLEAN


def run(replies, days=2):
    model = ConcordiaTwins(CountingModel(Replies(replies), letter_choices=False))
    return run_world(WorldConfig(WORLD, max_days=days, seed=1), model)


def test_a_one_off_break_is_resampled_and_the_run_survives():
    result = run([BROKEN])
    assert result.outcome is OutcomeKind.TIMEOUT and result.scorable
    assert result.immersion_resamples == 1
    assert result.immersion_breaks[0].text == BROKEN and not result.slips


def test_text_still_out_of_character_after_resampling_is_dropped_and_the_run_goes_on():
    result = run([BROKEN] * (RESAMPLES + 1))
    assert result.outcome is OutcomeKind.TIMEOUT and result.immersion_resamples == RESAMPLES
    assert len(result.slips) == 1 and result.scorable and not result.flagged
    assert not any(BROKEN in e.say for e in result.events) and not any(BROKEN in r.text for r in result.reflections)


def test_clean_runs_have_no_resamples():
    assert run([]).immersion_resamples == 0


def test_a_line_rescued_by_resampling_never_counts_against_the_run():
    # Every free-text call alternates broken, clean: each line is rescued, so nothing slips.
    result = run([BROKEN, CLEAN] * 20, days=6)
    assert result.immersion_resamples > 2 and not result.slips and result.scorable


def test_a_twin_that_keeps_slipping_flags_the_run_for_review():
    result = run([BROKEN] * 200, days=4)
    assert result.flagged and not result.scorable and result.outcome is not OutcomeKind.EXCLUDED
    assert result.day == 4  # the run went on to the end


def test_the_flagged_demo_scenario_keeps_the_run_and_flags_it():
    from fastapi.testclient import TestClient

    from api.main import create_app
    from api.store import MemoryStore

    body = TestClient(create_app(MemoryStore())).post("/simulations", json={"scenario": "flagged", "seeds": [0]}).json()
    result = body["result"]
    assert result["flagged"] and result["slips"] > 2 and result["outcome"] != "excluded"
    assert body["scored_runs"] == 0
