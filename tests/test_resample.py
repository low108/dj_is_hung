"""B8: resample immersion breaks instead of excluding whole runs."""
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
    assert result.resamples == 1


def test_a_twin_that_keeps_breaking_immersion_still_gets_the_run_excluded():
    result = run([BROKEN] * (RESAMPLES + 1))
    assert result.outcome is OutcomeKind.EXCLUDED and result.resamples == RESAMPLES


def test_clean_runs_have_no_resamples():
    assert run([]).resamples == 0
